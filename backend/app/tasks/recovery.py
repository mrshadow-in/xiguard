"""Blackhole expiry check — lifts blackhole routes whose duration has passed."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.services import stats
from app.services.mitigator import remove_blackhole
from app.services.pubsub import CH_STATE, publish
from app.tasks._runner import run
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.recovery.check_blackhole_expiry")
def check_blackhole_expiry() -> dict:
    return run(_check())


async def _check() -> dict:
    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    lifted = 0
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(MonitoredIP).where(
                    MonitoredIP.state == "BLACKHOLED",
                    MonitoredIP.blackholed_at.is_not(None),
                )
            )
        ).scalars().all()

        for ip in rows:
            pool = await session.get(IPPool, ip.pool_id)
            if not pool or ip.blackholed_at is None:
                continue
            elapsed = (now - ip.blackholed_at).total_seconds()
            if elapsed < pool.blackhole_duration_sec:
                continue
            chr_node = await session.get(CHRNode, pool.chr_node_id)
            if not chr_node:
                continue
            ok = await remove_blackhole(ip.ip_address, chr_node)
            if not ok:
                logger.error("failed to lift blackhole for %s", ip.ip_address)
                continue
            ip.state = "RECOVERING"
            ip.recovering_at = now
            ip.blackholed_at = None
            lifted += 1
            await publish(
                CH_STATE,
                {
                    "ip": ip.ip_address,
                    "old_state": "BLACKHOLED",
                    "new_state": "RECOVERING",
                    "timestamp": now.isoformat(),
                },
            )
        await session.commit()
    duration_ms = int((time.perf_counter() - started) * 1000)
    result = {"lifted": lifted}
    await stats.record_task("check_blackhole_expiry", duration_ms=duration_ms, result=result)
    return result
