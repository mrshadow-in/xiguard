"""Fast-path mitigation tasks dispatched from the polling cycle.

The polling task must NEVER block on RouterOS API calls or SMTP — during
a real attack those are the things most likely to be slow, and a blocked
polling cycle means no new detections for any other IP.

Pattern: polling does the detector + state transition (in memory + DB),
then `.delay()`s `push_blackhole_now` onto the `critical` Celery queue
and `dispatch_ddos_alert_email` onto the `email` queue. The blackhole
task verifies the route landed; if not, it flips the IP back to ALERT
and writes a `blackhole_failed` Alert so the UI tells the truth.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.alert import (
    ALERT_BLACKHOLE_APPLIED,
    ALERT_BLACKHOLE_FAILED,
    Alert,
)
from app.models.chr_node import CHRNode
from app.models.monitored_ip import MonitoredIP
from app.services.mitigator import push_blackhole, remove_blackhole
from app.services.pubsub import CH_STATE, publish
from app.tasks._runner import run
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.mitigation.push_blackhole_now",
    queue="critical",
    priority=9,
)
def push_blackhole_now(ip_id: str, chr_id: str) -> dict:
    return run(_push(uuid.UUID(ip_id), uuid.UUID(chr_id)))


async def _push(ip_id: uuid.UUID, chr_id: uuid.UUID) -> dict:
    async with SessionLocal() as session:
        ip = await session.get(MonitoredIP, ip_id)
        chr_node = await session.get(CHRNode, chr_id)
        if not ip or not chr_node:
            return {"ok": False, "reason": "ip_or_chr_missing"}

        ok, err = await push_blackhole(ip.ip_address, chr_node)
        now = datetime.now(timezone.utc)

        if ok:
            session.add(
                Alert(
                    ip_id=ip.id,
                    type=ALERT_BLACKHOLE_APPLIED,
                    severity="info",
                    action_taken="auto_blackhole",
                )
            )
            await session.commit()
            return {"ok": True}

        # Failed — roll the optimistic state back so the dashboard doesn't lie.
        prior = ip.state
        ip.state = "ALERT"
        ip.blackholed_at = None
        session.add(
            Alert(
                ip_id=ip.id,
                type=ALERT_BLACKHOLE_FAILED,
                severity="critical",
                action_taken=f"blackhole_failed: {(err or 'unknown')[:64]}",
            )
        )
        await session.commit()
        await publish(
            CH_STATE,
            {
                "ip": str(ip.ip_address),
                "old_state": prior,
                "new_state": "ALERT",
                "timestamp": now.isoformat(),
            },
        )
        return {"ok": False, "error": err}


@celery_app.task(
    name="app.tasks.mitigation.remove_blackhole_now",
    queue="critical",
    priority=9,
)
def remove_blackhole_now(ip_id: str, chr_id: str) -> dict:
    return run(_remove(uuid.UUID(ip_id), uuid.UUID(chr_id)))


async def _remove(ip_id: uuid.UUID, chr_id: uuid.UUID) -> dict:
    async with SessionLocal() as session:
        ip = await session.get(MonitoredIP, ip_id)
        chr_node = await session.get(CHRNode, chr_id)
        if not ip or not chr_node:
            return {"ok": False, "reason": "ip_or_chr_missing"}
        ok, err = await remove_blackhole(ip.ip_address, chr_node)
        return {"ok": ok, "error": err}
