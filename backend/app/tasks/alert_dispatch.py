"""Alert email dispatch — runs on the `email` queue, off the polling cycle.

Polling persists the Alert row and then `.delay()`s this task. SMTP
latency can never block detection because this lives in a separate
worker pool.
"""
from __future__ import annotations

import logging
import uuid

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.services import alerter
from app.services.pubsub import CH_ALERTS, get_redis, publish
from app.tasks._runner import run
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.alert_dispatch.dispatch_ddos_email", queue="email")
def dispatch_ddos_email(alert_id: str, multiplier: float) -> dict:
    return run(_dispatch_ddos(uuid.UUID(alert_id), multiplier))


async def _dispatch_ddos(alert_id: uuid.UUID, multiplier: float) -> dict:
    async with SessionLocal() as session:
        alert = await session.get(Alert, alert_id)
        if not alert:
            return {"ok": False, "reason": "alert_missing"}
        ip = await session.get(MonitoredIP, alert.ip_id)
        if not ip:
            return {"ok": False, "reason": "ip_missing"}
        pool = await session.get(IPPool, ip.pool_id)
        chr_node = await session.get(CHRNode, pool.chr_node_id) if pool else None

        redis = get_redis()
        if await alerter.is_deduplicated(redis, ip.ip_address):
            return {"ok": True, "deduped": True}
        await alerter.mark_alerted(redis, ip.ip_address)

        hosting_ok, isp_ok = await alerter.dispatch_ddos_alert(
            session,
            alert_id=str(alert.id),
            ip=str(ip.ip_address),
            pool_cidr=str(pool.cidr) if pool else "",
            chr_name=chr_node.name if chr_node else "",
            chr_host=chr_node.host if chr_node else "",
            baseline_bps=int(alert.baseline_bps or 0),
            peak_bps=int(alert.peak_bps or 0),
            multiplier=float(multiplier),
            configured_multiplier=float(pool.multiplier) if pool else 0.0,
            action=alert.action_taken or "Alert Only",
            blackhole_expires_at=None,
        )
        alert.hosting_email_sent = hosting_ok
        alert.isp_email_sent = isp_ok
        await session.commit()

        await publish(
            CH_ALERTS,
            {
                "id": str(alert.id),
                "ip": str(ip.ip_address),
                "severity": alert.severity,
                "type": alert.type,
                "baseline_bps": alert.baseline_bps,
                "peak_bps": alert.peak_bps,
                "multiplier": multiplier,
                "action_taken": alert.action_taken,
                "timestamp": alert.created_at.isoformat(),
            },
        )
        return {"ok": True, "hosting": hosting_ok, "isp": isp_ok}


@celery_app.task(name="app.tasks.alert_dispatch.dispatch_recovery_email", queue="email")
def dispatch_recovery_email(ip_id: str) -> dict:
    return run(_dispatch_recovery(uuid.UUID(ip_id)))


async def _dispatch_recovery(ip_id: uuid.UUID) -> dict:
    async with SessionLocal() as session:
        ip = await session.get(MonitoredIP, ip_id)
        if not ip:
            return {"ok": False, "reason": "ip_missing"}
        pool = await session.get(IPPool, ip.pool_id)
        chr_node = await session.get(CHRNode, pool.chr_node_id) if pool else None
        hosting_ok, isp_ok = await alerter.dispatch_recovery(
            session,
            ip=str(ip.ip_address),
            pool_cidr=str(pool.cidr) if pool else "",
            chr_name=chr_node.name if chr_node else "",
            baseline_bps=int(ip.baseline_bps or 0),
            current_bps=int(ip.current_bps or 0),
        )
        return {"ok": True, "hosting": hosting_ok, "isp": isp_ok}
