"""Alert history, detail, acknowledge, stats."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB
from app.models.alert import Alert
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.schemas.alert import AlertOut, AlertStats

router = APIRouter()


async def _augment(db, row: Alert) -> AlertOut:
    ip = await db.get(MonitoredIP, row.ip_id)
    out = AlertOut.model_validate(row)
    if ip:
        out.ip_address = str(ip.ip_address)
        pool = await db.get(IPPool, ip.pool_id)
        if pool:
            out.pool_cidr = str(pool.cidr)
            chr_node = await db.get(CHRNode, pool.chr_node_id)
            if chr_node:
                out.chr_name = chr_node.name
    return out


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    _: CurrentUser,
    db: DB,
    severity: str | None = Query(default=None),
    ip: str | None = Query(default=None),
    alert_type: str | None = Query(default=None, alias="type"),
    since_hours: int = Query(default=24 * 7, ge=1, le=24 * 90),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AlertOut]:
    stmt = select(Alert).order_by(Alert.created_at.desc())
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if alert_type:
        stmt = stmt.where(Alert.type == alert_type)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    stmt = stmt.where(Alert.created_at >= since)
    if ip:
        sub = select(MonitoredIP.id).where(MonitoredIP.ip_address == ip)
        stmt = stmt.where(Alert.ip_id.in_(sub))
    stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [await _augment(db, r) for r in rows]


@router.get("/stats", response_model=AlertStats)
async def stats(_: CurrentUser, db: DB) -> AlertStats:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = await db.execute(
        select(Alert.severity, func.count(Alert.id)).where(Alert.created_at >= since)
        .group_by(Alert.severity)
    )
    counts = {sev: n for sev, n in rows}
    by_day_rows = await db.execute(
        select(func.date(Alert.created_at).label("d"), func.count(Alert.id))
        .where(Alert.created_at >= datetime.now(timezone.utc) - timedelta(days=14))
        .group_by("d")
        .order_by("d")
    )
    by_day = [{"date": str(d), "count": n} for d, n in by_day_rows]
    return AlertStats(
        total_24h=sum(counts.values()),
        critical_24h=counts.get("critical", 0),
        warning_24h=counts.get("warning", 0),
        info_24h=counts.get("info", 0),
        by_day=by_day,
    )


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: uuid.UUID, _: CurrentUser, db: DB) -> AlertOut:
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return await _augment(db, alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge(alert_id: uuid.UUID, user: CurrentUser, db: DB) -> AlertOut:
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    alert.acknowledged_by = user.username
    await db.commit()
    await db.refresh(alert)
    return await _augment(db, alert)
