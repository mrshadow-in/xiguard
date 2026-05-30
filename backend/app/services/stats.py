"""Lightweight runtime stats — written by tasks + collector, read by the API.

Everything lives in Redis so we don't burn DB write traffic just to surface
"last poll was 4 seconds ago" on the UI.

Keys:
  xiguard:stats:task:<name>              hash  { last_at, duration_ms, result }
  xiguard:stats:task:<name>:count        int   (INCR on each completion)
  xiguard:stats:flow:meta                hash  { packets, records, last_packet_at }
  xiguard:stats:flow:exporter:<ip>       hash  { packets, last_packet_at }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from app.services.pubsub import get_redis

_TTL_TASK_SEC = 24 * 3600
_TTL_FLOW_META_SEC = 24 * 3600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── task stats ───────────────────────────────────────────────────────────
async def record_task(
    name: str,
    *,
    duration_ms: int,
    result: dict[str, Any] | None = None,
    redis: Redis | None = None,
) -> None:
    r = redis or get_redis()
    key = f"xiguard:stats:task:{name}"
    pipe = r.pipeline(transaction=False)
    pipe.hset(
        key,
        mapping={
            "last_at": _now_iso(),
            "duration_ms": int(duration_ms),
            "result": json.dumps(result or {}),
        },
    )
    pipe.expire(key, _TTL_TASK_SEC)
    pipe.incr(f"xiguard:stats:task:{name}:count")
    await pipe.execute()


async def read_task(name: str, redis: Redis | None = None) -> dict[str, Any]:
    r = redis or get_redis()
    key = f"xiguard:stats:task:{name}"
    data = await r.hgetall(key)
    count = await r.get(f"xiguard:stats:task:{name}:count")
    if not data:
        return {"name": name, "last_at": None, "duration_ms": None, "result": None, "count": int(count or 0)}
    try:
        result = json.loads(data.get("result") or "{}")
    except (ValueError, TypeError):
        result = None
    return {
        "name": name,
        "last_at": data.get("last_at"),
        "duration_ms": int(data.get("duration_ms") or 0),
        "result": result,
        "count": int(count or 0),
    }


# ── flow collector stats ────────────────────────────────────────────────
async def record_flow_batch(
    *,
    packets: int,
    records: int,
    per_exporter_packets: dict[str, int],
    redis: Redis | None = None,
) -> None:
    if packets == 0 and records == 0:
        return
    r = redis or get_redis()
    pipe = r.pipeline(transaction=False)
    now = _now_iso()
    pipe.hincrby("xiguard:stats:flow:meta", "packets", packets)
    pipe.hincrby("xiguard:stats:flow:meta", "records", records)
    pipe.hset("xiguard:stats:flow:meta", "last_packet_at", now)
    pipe.expire("xiguard:stats:flow:meta", _TTL_FLOW_META_SEC)
    for exporter, count in per_exporter_packets.items():
        ek = f"xiguard:stats:flow:exporter:{exporter}"
        pipe.hincrby(ek, "packets", count)
        pipe.hset(ek, "last_packet_at", now)
        pipe.expire(ek, _TTL_FLOW_META_SEC)
    await pipe.execute()


async def read_flow_meta(redis: Redis | None = None) -> dict[str, Any]:
    r = redis or get_redis()
    meta = await r.hgetall("xiguard:stats:flow:meta")
    return {
        "packets": int(meta.get("packets") or 0),
        "records": int(meta.get("records") or 0),
        "last_packet_at": meta.get("last_packet_at"),
    }


async def read_flow_exporters(redis: Redis | None = None) -> list[dict[str, Any]]:
    r = redis or get_redis()
    out: list[dict[str, Any]] = []
    cursor = 0
    keys: list[str] = []
    while True:
        cursor, batch = await r.scan(cursor=cursor, match="xiguard:stats:flow:exporter:*", count=200)
        keys.extend(batch)
        if cursor == 0:
            break
    for key in keys:
        exporter = key.removeprefix("xiguard:stats:flow:exporter:")
        data = await r.hgetall(key)
        if not data:
            continue
        out.append(
            {
                "exporter": exporter,
                "packets": int(data.get("packets") or 0),
                "last_packet_at": data.get("last_packet_at"),
            }
        )
    return sorted(out, key=lambda e: e["packets"], reverse=True)


async def count_active_flow_ips(redis: Redis | None = None) -> int:
    """How many distinct IPs currently have a non-expired flow counter."""
    r = redis or get_redis()
    count = 0
    cursor = 0
    while True:
        cursor, batch = await r.scan(cursor=cursor, match="xiguard:flow:*", count=500)
        # Don't count the meta keys we keep under xiguard:stats:flow:*
        count += sum(1 for k in batch if not k.startswith("xiguard:stats:"))
        if cursor == 0:
            break
    return count


async def active_flow_ip_set(redis: Redis | None = None) -> set[str]:
    """Set of IPs currently flowing (for per-CHR breakdown)."""
    r = redis or get_redis()
    out: set[str] = set()
    cursor = 0
    while True:
        cursor, batch = await r.scan(cursor=cursor, match="xiguard:flow:*", count=500)
        for k in batch:
            if k.startswith("xiguard:stats:"):
                continue
            out.add(k.removeprefix("xiguard:flow:"))
        if cursor == 0:
            break
    return out
