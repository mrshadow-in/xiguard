"""Expand a pool's CIDR into individual MonitoredIP rows."""
from __future__ import annotations

import ipaddress
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP

logger = logging.getLogger(__name__)

# Refuse to expand /0../15 (millions of IPs) — these are clearly mis-entered.
_MIN_PREFIX = 16


async def sync_pool_ips(session: AsyncSession, pool: IPPool) -> tuple[int, int]:
    """Add missing host IPs, return (added, removed)."""
    net = ipaddress.ip_network(str(pool.cidr), strict=False)
    if net.prefixlen < _MIN_PREFIX:
        raise ValueError(f"Refusing to expand prefix /{net.prefixlen}; min is /{_MIN_PREFIX}")

    desired: set[str] = {str(addr) for addr in net.hosts()}
    # /31 and /32 have no `hosts()` output for the network/broadcast; for /32 add it explicitly.
    if net.prefixlen == 32:
        desired = {str(net.network_address)}

    existing_rows = await session.execute(
        select(MonitoredIP.id, MonitoredIP.ip_address).where(MonitoredIP.pool_id == pool.id)
    )
    existing_map: dict[str, uuid.UUID] = {row.ip_address: row.id for row in existing_rows}
    existing_set = set(existing_map.keys())

    to_add = desired - existing_set
    to_remove = existing_set - desired

    for ip in to_add:
        session.add(MonitoredIP(pool_id=pool.id, ip_address=ip))

    if to_remove:
        for ip in to_remove:
            await session.delete(await session.get(MonitoredIP, existing_map[ip]))

    return len(to_add), len(to_remove)
