"""Mail config CRUD + general settings."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DB
from app.config import settings
from app.models.mail_config import MAIL_HOSTING_NOC, MAIL_ISP_NOC, MailConfig
from app.schemas.mail_config import MailConfigOut, MailConfigUpdate, TestEmailResult
from app.services.alerter import send_test_email
from app.services.crypto import encrypt

router = APIRouter()
_VALID_TYPES = {MAIL_HOSTING_NOC, MAIL_ISP_NOC}


def _to_out(cfg: MailConfig) -> MailConfigOut:
    out = MailConfigOut.model_validate(cfg)
    out.has_password = bool(cfg.smtp_pass_enc)
    return out


@router.get("/mail", response_model=list[MailConfigOut])
async def list_mail_configs(_: CurrentUser, db: DB) -> list[MailConfigOut]:
    rows = (await db.execute(select(MailConfig).order_by(MailConfig.config_type))).scalars().all()
    return [_to_out(c) for c in rows]


@router.put("/mail/{config_type}", response_model=MailConfigOut)
async def update_mail_config(
    config_type: str, payload: MailConfigUpdate, _: CurrentUser, db: DB
) -> MailConfigOut:
    if config_type not in _VALID_TYPES:
        raise HTTPException(400, f"unknown mail config type: {config_type}")
    cfg = (
        await db.execute(select(MailConfig).where(MailConfig.config_type == config_type))
    ).scalar_one_or_none()
    if not cfg:
        cfg = MailConfig(config_type=config_type)
        db.add(cfg)
    cfg.smtp_host = payload.smtp_host
    cfg.smtp_port = payload.smtp_port
    cfg.smtp_user = payload.smtp_user
    cfg.from_address = payload.from_address
    cfg.to_addresses = payload.to_addresses
    cfg.cc_addresses = payload.cc_addresses
    cfg.use_tls = payload.use_tls
    cfg.enabled = payload.enabled
    if payload.smtp_password is not None and payload.smtp_password != "":
        cfg.smtp_pass_enc = encrypt(payload.smtp_password)
    await db.commit()
    await db.refresh(cfg)
    return _to_out(cfg)


@router.post("/mail/{config_type}/test", response_model=TestEmailResult)
async def test_mail_config(config_type: str, _: CurrentUser, db: DB) -> TestEmailResult:
    if config_type not in _VALID_TYPES:
        raise HTTPException(400, f"unknown mail config type: {config_type}")
    cfg = (
        await db.execute(select(MailConfig).where(MailConfig.config_type == config_type))
    ).scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "config not found")
    ok, err = await send_test_email(cfg)
    return TestEmailResult(ok=ok, error=err)


@router.get("/general")
async def get_general_settings(_: CurrentUser) -> dict:
    return {
        "default_multiplier": settings.default_multiplier,
        "default_eval_window_sec": settings.default_eval_window_sec,
        "default_blackhole_duration_sec": settings.default_blackhole_duration_sec,
        "baseline_ewma_span": settings.baseline_ewma_span,
        "alert_dedup_window_sec": settings.alert_dedup_window_sec,
        "poll_interval_sec": settings.poll_interval_sec,
        "traffic_retention_days": settings.traffic_retention_days,
        "alert_retention_days": settings.alert_retention_days,
        "audit_retention_days": settings.audit_retention_days,
        "org_name": settings.org_name,
        "org_as_number": settings.org_as_number,
    }
