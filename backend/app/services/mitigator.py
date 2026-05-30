"""Blackhole route push / remove with bounded retry + read-back verification.

Earlier this module reported success the instant `/ip/route/add` returned
without an exception, even though the API could silently refuse to create
the route (permission, validation, etc.) and leave the CHR routing table
untouched. We now ALWAYS read the route back after pushing and only
report success if it's actually present.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.models.chr_node import CHRNode
from app.services.chr_api import CHRClient

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SEC = 2.0


async def push_blackhole(ip: str, chr_node: CHRNode) -> tuple[bool, str | None]:
    """Push + verify. Returns (success, error_detail)."""
    comment = f"Xiguard auto-blackhole {datetime.now(timezone.utc).isoformat()}"
    last_err: str | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with CHRClient.from_node(chr_node) as api:
                returned_id = await api.route_add_blackhole(ip, comment)
                existing = await api.route_find_xiguard(ip)
            if existing:
                logger.info(
                    "blackhole verified ip=%s chr=%s id=%s",
                    ip, chr_node.name, returned_id or "?",
                )
                return True, None
            last_err = (
                f"add returned {returned_id or 'no id'} but /ip/route/print "
                "shows no matching Xiguard blackhole route after the call"
            )
            logger.error("blackhole add not visible ip=%s chr=%s: %s", ip, chr_node.name, last_err)
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            logger.warning(
                "blackhole push exception (attempt %s/%s) ip=%s chr=%s: %s",
                attempt, _MAX_RETRIES, ip, chr_node.name, last_err,
            )
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_BACKOFF_SEC)
    logger.error("blackhole push gave up ip=%s chr=%s: %s", ip, chr_node.name, last_err)
    return False, last_err


async def remove_blackhole(ip: str, chr_node: CHRNode) -> tuple[bool, str | None]:
    last_err: str | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with CHRClient.from_node(chr_node) as api:
                removed = await api.route_remove_xiguard(ip)
                remaining = await api.route_find_xiguard(ip)
            if not remaining:
                logger.info("blackhole removed ip=%s chr=%s count=%s", ip, chr_node.name, removed)
                return True, None
            last_err = f"removed {removed} but {len(remaining)} still present"
            logger.error("blackhole remove incomplete ip=%s chr=%s: %s", ip, chr_node.name, last_err)
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            logger.warning(
                "blackhole remove exception (attempt %s/%s) ip=%s chr=%s: %s",
                attempt, _MAX_RETRIES, ip, chr_node.name, last_err,
            )
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_BACKOFF_SEC)
    logger.error("blackhole remove gave up ip=%s chr=%s: %s", ip, chr_node.name, last_err)
    return False, last_err
