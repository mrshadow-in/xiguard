"""Manual blackhole / unblackhole actions and test email."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DB
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.mail_config import MAIL_HOSTING_NOC, MAIL_ISP_NOC, MailConfig
from app.models.monitored_ip import MonitoredIP
from app.schemas.action import ActionResult, BlackholeRequest
from app.schemas.mail_config import TestEmailResult
from app.services.alerter import send_test_email
from app.services.mitigator import push_blackhole, remove_blackhole

router = APIRouter()


async def _resolve(db, ip: str) -> tuple[MonitoredIP, IPPool, CHRNode]:
    rec = (
        await db.execute(select(MonitoredIP).where(MonitoredIP.ip_address == ip))
    ).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, f"IP {ip} is not monitored")
    pool = await db.get(IPPool, rec.pool_id)
    if not pool:
        raise HTTPException(500, "Pool missing for IP")
    chr_node = await db.get(CHRNode, pool.chr_node_id)
    if not chr_node:
        raise HTTPException(500, "CHR node missing for pool")
    return rec, pool, chr_node


@router.post("/blackhole", response_model=ActionResult)
async def manual_blackhole(payload: BlackholeRequest, _: CurrentUser, db: DB) -> ActionResult:
    rec, _pool, chr_node = await _resolve(db, payload.ip)
    ok = await push_blackhole(payload.ip, chr_node)
    if not ok:
        return ActionResult(ok=False, ip=payload.ip, state=rec.state, error="blackhole push failed")
    rec.state = "BLACKHOLED"
    rec.blackholed_at = datetime.now(timezone.utc)
    rec.spike_start = None
    await db.commit()
    return ActionResult(ok=True, ip=payload.ip, state="BLACKHOLED")


@router.post("/unblackhole", response_model=ActionResult)
async def manual_unblackhole(payload: BlackholeRequest, _: CurrentUser, db: DB) -> ActionResult:
    rec, _pool, chr_node = await _resolve(db, payload.ip)
    ok = await remove_blackhole(payload.ip, chr_node)
    if not ok:
        return ActionResult(ok=False, ip=payload.ip, state=rec.state, error="route remove failed")
    rec.state = "RECOVERING"
    rec.blackholed_at = None
    rec.recovering_at = datetime.now(timezone.utc)
    await db.commit()
    return ActionResult(ok=True, ip=payload.ip, state="RECOVERING")


@router.post("/test-email", response_model=dict)
async def test_emails(_: CurrentUser, db: DB) -> dict:
    out: dict[str, TestEmailResult] = {}
    for ct in (MAIL_HOSTING_NOC, MAIL_ISP_NOC):
        cfg = (
            await db.execute(select(MailConfig).where(MailConfig.config_type == ct))
        ).scalar_one_or_none()
        if not cfg:
            out[ct] = TestEmailResult(ok=False, error="config missing")
            continue
        ok, err = await send_test_email(cfg)
        out[ct] = TestEmailResult(ok=ok, error=err)
    return {k: v.model_dump() for k, v in out.items()}
