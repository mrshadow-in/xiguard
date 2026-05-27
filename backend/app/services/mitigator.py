"""Blackhole route push / remove with bounded retry."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.models.chr_node import CHRNode
from app.services.chr_api import CHRClient

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SEC = 2.0


async def push_blackhole(ip: str, chr_node: CHRNode) -> bool:
    comment = f"CHRGuard auto-blackhole {datetime.now(timezone.utc).isoformat()}"
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with CHRClient.from_node(chr_node) as api:
                await api.route_add_blackhole(ip, comment)
            logger.info("blackhole pushed", extra={"ip": ip, "chr": chr_node.name})
            return True
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning(
                "blackhole push failed (attempt %s/%s): %s",
                attempt, _MAX_RETRIES, e,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_SEC)
    logger.error("blackhole push gave up for ip=%s: %s", ip, last_err)
    return False


async def remove_blackhole(ip: str, chr_node: CHRNode) -> bool:
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with CHRClient.from_node(chr_node) as api:
                removed = await api.route_remove_chrguard(ip)
            logger.info("blackhole removed", extra={"ip": ip, "count": removed})
            return True
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning(
                "blackhole remove failed (attempt %s/%s): %s",
                attempt, _MAX_RETRIES, e,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_SEC)
    logger.error("blackhole remove gave up for ip=%s: %s", ip, last_err)
    return False
