"""Dual-target email dispatch (Hosting NOC + ISP NOC) with dedup."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.mail_config import MAIL_HOSTING_NOC, MAIL_ISP_NOC, MailConfig
from app.services import templates
from app.services.crypto import decrypt

logger = logging.getLogger(__name__)


def _dedup_key(ip: str) -> str:
    return f"chrguard:alert-dedup:{ip}"


async def is_deduplicated(redis: Redis, ip: str) -> bool:
    return bool(await redis.exists(_dedup_key(ip)))


async def mark_alerted(redis: Redis, ip: str) -> None:
    await redis.set(_dedup_key(ip), "1", ex=settings.alert_dedup_window_sec)


async def _send(
    cfg: MailConfig, subject: str, body: str, *, prefix_test: bool = False
) -> tuple[bool, str | None]:
    if not cfg.enabled or not cfg.to_addresses or not cfg.smtp_host:
        return False, "mail config disabled or incomplete"

    msg = EmailMessage()
    msg["From"] = cfg.from_address
    msg["To"] = ", ".join(cfg.to_addresses)
    if cfg.cc_addresses:
        msg["Cc"] = ", ".join(cfg.cc_addresses)
    msg["Subject"] = f"[TEST] {subject}" if prefix_test else subject
    msg.set_content(body)

    smtp_kwargs: dict[str, Any] = {
        "hostname": cfg.smtp_host,
        "port": cfg.smtp_port,
        "timeout": 15,
        "start_tls": cfg.use_tls,
    }
    if cfg.smtp_user and cfg.smtp_pass_enc:
        smtp_kwargs["username"] = cfg.smtp_user
        smtp_kwargs["password"] = decrypt(cfg.smtp_pass_enc)

    try:
        await aiosmtplib.send(msg, **smtp_kwargs)
        return True, None
    except Exception as e:  # noqa: BLE001
        logger.exception("smtp send failed", extra={"host": cfg.smtp_host})
        return False, str(e)


async def _get_config(session: AsyncSession, config_type: str) -> MailConfig | None:
    result = await session.execute(
        select(MailConfig).where(MailConfig.config_type == config_type)
    )
    return result.scalar_one_or_none()


async def dispatch_ddos_alert(
    session: AsyncSession,
    *,
    alert_id: str,
    ip: str,
    pool_cidr: str,
    chr_name: str,
    chr_host: str,
    baseline_bps: int,
    peak_bps: int,
    multiplier: float,
    configured_multiplier: float,
    action: str,
    blackhole_expires_at: datetime | None,
) -> tuple[bool, bool]:
    """Send both hosting + ISP alert emails. Returns (hosting_sent, isp_sent)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    hosting_body = templates.HOSTING_BODY.render(
        ip=ip,
        pool_cidr=pool_cidr,
        chr_name=chr_name,
        chr_host=chr_host,
        ts=ts,
        baseline_bps=baseline_bps,
        peak_bps=peak_bps,
        multiplier=multiplier,
        configured_multiplier=configured_multiplier,
        action=action,
        blackhole_expires_at=(
            blackhole_expires_at.strftime("%Y-%m-%d %H:%M:%S")
            if blackhole_expires_at
            else None
        ),
        org_name=settings.org_name,
    )
    isp_body = templates.ISP_BODY.render(
        ip=ip,
        asn=settings.org_as_number,
        peak_bps=peak_bps,
        ts=ts,
        multiplier=multiplier,
        org_name=settings.org_name,
        noc_email=settings.org_noc_email,
        noc_phone=settings.org_noc_phone,
        website=settings.org_website,
        alert_id=alert_id[:8],
    )

    hosting_cfg = await _get_config(session, MAIL_HOSTING_NOC)
    isp_cfg = await _get_config(session, MAIL_ISP_NOC)

    async def _hosting() -> bool:
        if not hosting_cfg:
            return False
        ok, _ = await _send(hosting_cfg, templates.HOSTING_SUBJECT.format(ip=ip), hosting_body)
        return ok

    async def _isp() -> bool:
        if not isp_cfg:
            return False
        subject = templates.ISP_SUBJECT.format(ip=ip, asn=settings.org_as_number)
        ok, _ = await _send(isp_cfg, subject, isp_body)
        return ok

    hosting_sent, isp_sent = await asyncio.gather(_hosting(), _isp())
    return hosting_sent, isp_sent


async def dispatch_recovery(
    session: AsyncSession,
    *,
    ip: str,
    pool_cidr: str,
    chr_name: str,
    baseline_bps: int,
    current_bps: int,
) -> tuple[bool, bool]:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    body = templates.RECOVERY_BODY.render(
        ip=ip,
        pool_cidr=pool_cidr,
        chr_name=chr_name,
        ts=ts,
        baseline_bps=baseline_bps,
        current_bps=current_bps,
        org_name=settings.org_name,
    )
    subject = templates.RECOVERY_SUBJECT.format(ip=ip)
    hosting_cfg = await _get_config(session, MAIL_HOSTING_NOC)
    isp_cfg = await _get_config(session, MAIL_ISP_NOC)

    async def _h() -> bool:
        return (await _send(hosting_cfg, subject, body))[0] if hosting_cfg else False

    async def _i() -> bool:
        return (await _send(isp_cfg, subject, body))[0] if isp_cfg else False

    return await asyncio.gather(_h(), _i())


async def send_test_email(cfg: MailConfig) -> tuple[bool, str | None]:
    body = (
        "This is a CHRGuard test email.\n\n"
        "If you can read this, your SMTP configuration is working correctly."
    )
    return await _send(cfg, "CHRGuard test email", body, prefix_test=True)
