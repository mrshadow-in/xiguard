"""RouterOS API wrapper around librouteros.

librouteros is synchronous; we wrap calls in a thread executor so the rest
of the system can stay async. Each ``CHRClient`` owns one short-lived
connection and is intended to be used as an async context manager.
"""
from __future__ import annotations

import asyncio
import socket
import ssl
from dataclasses import dataclass
from typing import Any

import librouteros
from librouteros.exceptions import TrapError

from app.config import settings
from app.models.chr_node import CHRNode
from app.services.crypto import decrypt


@dataclass
class CHRConnectionInfo:
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool


def _info_from_node(node: CHRNode) -> CHRConnectionInfo:
    return CHRConnectionInfo(
        host=node.host,
        port=node.api_port,
        username=node.username,
        password=decrypt(node.password_enc),
        use_ssl=bool(node.use_ssl),
    )


def _connect_sync(info: CHRConnectionInfo) -> librouteros.api.Api:
    kwargs: dict[str, Any] = {
        "host": info.host,
        "port": info.port,
        "username": info.username,
        "password": info.password,
        "timeout": settings.poll_timeout_sec,
    }
    if info.use_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_wrapper"] = ctx.wrap_socket
    return librouteros.connect(**kwargs)


class CHRClient:
    def __init__(self, info: CHRConnectionInfo) -> None:
        self._info = info
        self._api: librouteros.api.Api | None = None

    @classmethod
    def from_node(cls, node: CHRNode) -> "CHRClient":
        return cls(_info_from_node(node))

    async def __aenter__(self) -> "CHRClient":
        self._api = await asyncio.to_thread(_connect_sync, self._info)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._api is not None:
            try:
                await asyncio.to_thread(self._api.close)
            except Exception:
                pass
            self._api = None

    async def call(self, path: str, **params: Any) -> list[dict]:
        if self._api is None:
            raise RuntimeError("CHRClient not connected; use within `async with`")

        def _run() -> list[dict]:
            assert self._api is not None
            return list(self._api(path, **params))

        return await asyncio.to_thread(_run)

    async def identity(self) -> dict:
        rows = await self.call("/system/identity/print")
        return rows[0] if rows else {}

    async def resource(self) -> dict:
        rows = await self.call("/system/resource/print")
        return rows[0] if rows else {}

    async def route_add_blackhole(self, ip: str, comment: str) -> tuple[str | None, str]:
        """Add a blackhole route. Tries the three known RouterOS syntaxes
        in order until one is accepted:

          1. type=blackhole          (RouterOS 6, and most 7.x docs)
          2. blackhole=yes           (RouterOS 7.x post routing-rewrite)
          3. gateway=blackhole       (legacy)

        Returns (new_id_or_none, syntax_used). Raises the last exception
        if all three were rejected.
        """
        base = {"dst-address": f"{ip}/32", "comment": comment}
        attempts: list[tuple[str, dict[str, str]]] = [
            ("type=blackhole", {**base, "type": "blackhole"}),
            ("blackhole=yes", {**base, "blackhole": "yes"}),
            ("gateway=blackhole", {**base, "gateway": "blackhole"}),
        ]
        last_exc: Exception | None = None
        for label, params in attempts:
            try:
                result = await self.call("/ip/route/add", **params)
                first = (result[0] if isinstance(result, list) and result else {}) or {}
                return (first.get("ret") or first.get(".id"), label)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                continue
        assert last_exc is not None
        raise last_exc

    async def route_find_xiguard(self, ip: str) -> list[dict]:
        """Return any /ip/route entries for this /32 that we (Xiguard) created."""
        rows = await self.call("/ip/route/print", **{"?dst-address": f"{ip}/32"})
        out: list[dict] = []
        for r in rows:
            comment = str(r.get("comment", ""))
            type_ = str(r.get("type", ""))
            if type_ == "blackhole" and comment.startswith("Xiguard"):
                out.append(r)
        return out

    async def route_remove_xiguard(self, ip: str) -> int:
        removed = 0
        for r in await self.route_find_xiguard(ip):
            await self.call("/ip/route/remove", **{".id": r[".id"]})
            removed += 1
        return removed


async def test_connection(info: CHRConnectionInfo) -> dict:
    """Return {ok, routeros_version, uptime, error?} for an ad-hoc test."""
    try:
        client = CHRClient(info)
        async with client:
            res = await client.resource()
            return {
                "ok": True,
                "routeros_version": str(res.get("version", "")),
                "uptime": str(res.get("uptime", "")),
                "error": None,
            }
    except (TrapError, OSError, socket.timeout) as e:
        return {"ok": False, "routeros_version": None, "uptime": None, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "routeros_version": None, "uptime": None, "error": repr(e)}
