"""Showcase provisioning: connects Xiguard to the bundled CHR with no manual setup.

Runs in the backend image on every `docker compose up` and is safe to re-run:
  1. waits for Xiguard's database and for the CHR to finish booting,
  2. configures the CHR: API user, identity, customer prefixes, NetFlow export,
  3. registers the CHR, one IP pool per prefix, and both NOC mailboxes
     (pointed at the local Mailpit inbox) in Xiguard,
  4. pushes, verifies and removes a test blackhole route on the CHR.
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import sys
import time

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.mail_config import MAIL_HOSTING_NOC, MAIL_ISP_NOC, MailConfig
from app.services.chr_api import CHRClient, CHRConnectionInfo
from app.services.crypto import encrypt
from app.services.mitigator import push_blackhole, remove_blackhole
from app.services.pool_sync import sync_pool_ips

PREFIXES = [
    str(ipaddress.ip_network(p.strip(), strict=False))
    for p in os.environ.get("SHOWCASE_PREFIXES", "203.0.113.0/24").split(",")
    if p.strip()
]
CHR_HOST = "chr"
CHR_NAME = "CHR-Showcase"
API_USER = "xiguard"
API_PASSWORD = os.environ.get("SHOWCASE_CHR_PASSWORD", "xiguard-demo")
COLLECTOR = "flow-collector"

# Shorter than production defaults so a full attack → blackhole → recovery
# cycle fits in a few minutes on stage. Applied only when a pool is created.
POOL_SETTINGS = dict(
    multiplier=3.0,
    eval_window_sec=15,         # production default 30
    auto_blackhole=True,
    blackhole_duration_sec=120,  # production default 600
    warmup_samples=24,           # 2 minutes at 5 s polling; production default 120
    min_baseline_bps=1_000_000,
    min_spike_bps=10_000_000,
)

MAILBOXES = {
    MAIL_HOSTING_NOC: ["noc@netpool.in"],
    MAIL_ISP_NOC: ["noc@upstream-isp.example"],
}


def log(msg: str) -> None:
    print(f"[showcase] {msg}", flush=True)


async def wait_for_database(deadline: float) -> None:
    """The api container runs migrations and creates the mail_configs rows on start."""
    while True:
        try:
            async with SessionLocal() as s:
                if (await s.execute(text("SELECT count(*) FROM mail_configs"))).scalar_one() >= 2:
                    return
        except Exception:  # noqa: BLE001 — not migrated yet
            pass
        if time.monotonic() > deadline:
            raise SystemExit("Xiguard's database never became ready — check `docker compose logs api`.")
        await asyncio.sleep(3)


async def connect_chr(deadline: float) -> tuple[CHRClient, bool]:
    """Returns (connected client, logged in as the factory admin)."""
    started = time.monotonic()
    last_note = 0.0
    while True:
        for user, password, factory in ((API_USER, API_PASSWORD, False), ("admin", "", True)):
            client = CHRClient(CHRConnectionInfo(CHR_HOST, 8728, user, password, False))
            try:
                await client.__aenter__()
                return client, factory
            except Exception as e:  # noqa: BLE001 — still booting, or wrong credentials
                error = e
        if time.monotonic() > deadline:
            raise SystemExit(f"CHR API never answered ({error!r}) — check `docker compose logs chr`.")
        if time.monotonic() - last_note > 20:
            log(f"waiting for the CHR to boot ({int(time.monotonic() - started)}s so far, usually 1–3 min)")
            last_note = time.monotonic()
        await asyncio.sleep(5)


async def configure_chr(api: CHRClient, factory_login: bool) -> None:
    users = await api.call("/user/print", f"?name={API_USER}")
    if users:
        await api.call("/user/set", **{".id": users[0][".id"], "password": API_PASSWORD, "group": "full"})
    else:
        await api.call("/user/add", name=API_USER, password=API_PASSWORD, group="full",
                       comment="Xiguard API user (showcase)")
    if factory_login:
        log(f"created RouterOS user '{API_USER}'")

    await api.call("/system/identity/set", name=CHR_NAME)

    if not await api.call("/interface/bridge/print", "?name=customers"):
        await api.call("/interface/bridge/add", name="customers", comment="Showcase customer servers")
    for cidr in PREFIXES:
        net = ipaddress.ip_network(cidr)
        gateway = f"{next(net.hosts())}/{net.prefixlen}"
        if not await api.call("/ip/address/print", f"?address={gateway}"):
            await api.call("/ip/address/add", address=gateway, interface="customers",
                           comment="Showcase customer prefix")

    collector_ip = socket.gethostbyname(COLLECTOR)
    await api.call("/ip/traffic-flow/set", enabled="yes", interfaces="all",
                   **{"active-flow-timeout": "00:00:05", "inactive-flow-timeout": "00:00:05"})
    for target in await api.call("/ip/traffic-flow/target/print"):
        await api.call("/ip/traffic-flow/target/remove", **{".id": target[".id"]})
    await api.call("/ip/traffic-flow/target/add", port="2055", version="9",
                   **{"dst-address": collector_ip})
    log(f"CHR configured: identity {CHR_NAME}, prefixes {', '.join(PREFIXES)}, NetFlow → {collector_ip}:2055")


async def register_in_xiguard() -> CHRNode:
    async with SessionLocal() as s:
        node = (await s.execute(select(CHRNode).where(CHRNode.name == CHR_NAME))).scalar_one_or_none()
        if node is None:
            node = CHRNode(name=CHR_NAME, host=CHR_HOST, description="Bundled showcase CHR (QEMU)")
            s.add(node)
        node.host, node.api_port, node.use_ssl = CHR_HOST, 8728, False
        node.username, node.password_enc = API_USER, encrypt(API_PASSWORD)
        await s.flush()

        existing = {str(p.cidr) for p in (await s.execute(select(IPPool))).scalars()}
        for cidr in PREFIXES:
            if cidr not in existing:
                pool = IPPool(chr_node_id=node.id, cidr=cidr, description="Showcase customers", **POOL_SETTINGS)
                s.add(pool)
                await s.flush()
                added, _ = await sync_pool_ips(s, pool)
                log(f"pool {cidr}: {added} IPs added, warming up for {POOL_SETTINGS['warmup_samples'] * 5}s")

        for config_type, recipients in MAILBOXES.items():
            cfg = (await s.execute(select(MailConfig).where(MailConfig.config_type == config_type))).scalar_one()
            if not cfg.smtp_host:  # never overwrite settings someone changed in the panel
                cfg.smtp_host, cfg.smtp_port, cfg.use_tls, cfg.enabled = "mailpit", 1025, False, True
                cfg.smtp_user, cfg.smtp_pass_enc = None, None
                cfg.from_address, cfg.to_addresses = "xiguard-showcase@netpool.in", recipients
        await s.commit()
        await s.refresh(node)
        return node


async def main() -> None:
    deadline = time.monotonic() + 15 * 60
    await wait_for_database(deadline)
    log("database ready")

    api, factory_login = await connect_chr(deadline)
    try:
        await configure_chr(api, factory_login)
    finally:
        await api.__aexit__(None, None, None)

    node = await register_in_xiguard()
    ok, err = await push_blackhole("192.0.2.123", node)
    if not ok:
        raise SystemExit(f"blackhole self-test FAILED on the CHR: {err}")
    removed, err = await remove_blackhole("192.0.2.123", node)
    if not removed:
        raise SystemExit(f"blackhole self-test could not remove its test route: {err}")
    log("blackhole self-test passed (push → verify → remove)")

    admin = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "")
    log("=" * 64)
    log("SHOWCASE READY")
    log(f"  Xiguard panel    http://localhost:8088     login {admin} / {password}")
    log("  Attack panel     http://localhost:8090")
    log("  NOC mailboxes    http://localhost:8025")
    log(f"  CHR WebFig       http://localhost:8081     login {API_USER} / {API_PASSWORD}")
    log(f"  New IPs arm after ~{POOL_SETTINGS['warmup_samples'] * 5 // 60} min of warm-up (state SAMPLING → NORMAL).")
    log("=" * 64)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as e:
        log(f"FAILED: {e}")
        sys.exit(1)
