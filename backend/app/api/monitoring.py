"""Real-time monitoring endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.models.traffic_sample import TrafficSample
from app.schemas.ip_pool import IPSummary
from app.schemas.monitoring import IPTrafficHistory, IPTrafficPoint, MonitoringOverview

router = APIRouter()


@router.get("/overview", response_model=MonitoringOverview)
async def overview(_: CurrentUser, db: DB) -> MonitoringOverview:
    chr_total = await db.scalar(select(func.count(CHRNode.id))) or 0
    chr_online = await db.scalar(
        select(func.count(CHRNode.id)).where(CHRNode.status == "online")
    ) or 0
    pools = await db.scalar(select(func.count(IPPool.id))) or 0
    ips = await db.scalar(select(func.count(MonitoredIP.id))) or 0
    alerts = await db.scalar(
        select(func.count(MonitoredIP.id)).where(MonitoredIP.state == "ALERT")
    ) or 0
    blackholes = await db.scalar(
        select(func.count(MonitoredIP.id)).where(MonitoredIP.state == "BLACKHOLED")
    ) or 0
    last_poll = await db.scalar(select(func.max(CHRNode.last_seen_at)))
    return MonitoringOverview(
        total_chr_nodes=chr_total,
        online_chr_nodes=chr_online,
        total_pools=pools,
        total_ips=ips,
        alert_count=alerts,
        blackhole_count=blackholes,
        last_poll_at=last_poll,
    )


@router.get("/traffic", response_model=list[IPSummary])
async def list_traffic(
    _: CurrentUser,
    db: DB,
    state: str | None = Query(default=None),
    pool_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=200, le=2000),
    offset: int = Query(default=0, ge=0),
) -> list[IPSummary]:
    stmt = select(MonitoredIP).order_by(MonitoredIP.current_bps.desc())
    if state:
        stmt = stmt.where(MonitoredIP.state == state)
    if pool_id:
        stmt = stmt.where(MonitoredIP.pool_id == pool_id)
    stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [IPSummary.model_validate(r) for r in rows]


@router.get("/blackholed", response_model=list[IPSummary])
async def list_blackholed(_: CurrentUser, db: DB) -> list[IPSummary]:
    rows = (
        await db.execute(
            select(MonitoredIP)
            .where(MonitoredIP.state == "BLACKHOLED")
            .order_by(MonitoredIP.blackholed_at.desc())
        )
    ).scalars().all()
    return [IPSummary.model_validate(r) for r in rows]


@router.get("/traffic/{ip_address}", response_model=IPTrafficHistory)
async def ip_history(
    ip_address: str,
    _: CurrentUser,
    db: DB,
    hours: int = Query(default=1, ge=1, le=24 * 7),
) -> IPTrafficHistory:
    ip = (
        await db.execute(select(MonitoredIP).where(MonitoredIP.ip_address == ip_address))
    ).scalar_one_or_none()
    if not ip:
        raise HTTPException(404, "IP not monitored")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(TrafficSample)
            .where(TrafficSample.ip_id == ip.id, TrafficSample.sampled_at >= since)
            .order_by(TrafficSample.sampled_at.asc())
        )
    ).scalars().all()

    return IPTrafficHistory(
        ip_id=ip.id,
        ip_address=str(ip.ip_address),
        state=ip.state,
        baseline_bps=ip.baseline_bps,
        current_bps=ip.current_bps,
        points=[
            IPTrafficPoint(
                sampled_at=r.sampled_at,
                bps_in=r.bps_in,
                bps_out=r.bps_out,
                pps_in=r.pps_in,
                pps_out=r.pps_out,
            )
            for r in rows
        ],
    )
