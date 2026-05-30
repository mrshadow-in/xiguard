"""Real-time monitoring endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select, text

from app.api.deps import CurrentUser, DB
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.models.traffic_sample import TrafficSample
from app.schemas.ip_pool import IPSummary, WhitelistUpdate
from app.schemas.monitoring import (
    AggregatePoint,
    AggregateSeries,
    IPTrafficHistory,
    IPTrafficPoint,
    MonitoringOverview,
)

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

    # Adaptive bucketing so a /7d view doesn't return ~120k points.
    bucket_sec = _bucket_for_hours(hours)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = text(
        """
        SELECT date_bin(make_interval(secs => :bucket), sampled_at,
                        TIMESTAMPTZ '2000-01-01') AS bucket,
               MAX(bps_in)::BIGINT  AS bps_in,
               MAX(bps_out)::BIGINT AS bps_out,
               MAX(pps_in)::BIGINT  AS pps_in,
               MAX(pps_out)::BIGINT AS pps_out
        FROM traffic_samples
        WHERE ip_id = :ip_id AND sampled_at >= :since
        GROUP BY bucket
        ORDER BY bucket ASC
        """
    )
    rows = (
        await db.execute(stmt, {"bucket": bucket_sec, "ip_id": ip.id, "since": since})
    ).all()

    pool = await db.get(IPPool, ip.pool_id)
    chr_node = await db.get(CHRNode, pool.chr_node_id) if pool else None

    return IPTrafficHistory(
        ip_id=ip.id,
        ip_address=str(ip.ip_address),
        state=ip.state,
        baseline_bps=ip.baseline_bps,
        current_bps=ip.current_bps,
        pool_cidr=str(pool.cidr) if pool else None,
        chr_name=chr_node.name if chr_node else None,
        chr_id=chr_node.id if chr_node else None,
        blackholed_at=ip.blackholed_at,
        last_spike_at=ip.last_spike_at,
        is_whitelisted=bool(ip.is_whitelisted),
        whitelist_note=ip.whitelist_note,
        points=[
            IPTrafficPoint(
                sampled_at=r.bucket,
                bps_in=int(r.bps_in or 0),
                bps_out=int(r.bps_out or 0),
                pps_in=int(r.pps_in or 0),
                pps_out=int(r.pps_out or 0),
            )
            for r in rows
        ],
    )


def _bucket_for_hours(hours: int) -> int:
    """Sample bucket size in seconds, chosen so the chart stays under ~700 points."""
    if hours <= 1:
        return 5          # native polling cadence
    if hours <= 6:
        return 30
    if hours <= 24:
        return 60
    if hours <= 24 * 3:
        return 5 * 60
    return 15 * 60


@router.get("/aggregate", response_model=AggregateSeries)
async def aggregate_traffic(
    _: CurrentUser,
    db: DB,
    hours: int = Query(default=1, ge=1, le=24 * 7),
) -> AggregateSeries:
    """Sum bps/pps across ALL monitored IPs, time-bucketed for a chart."""
    bucket_sec = _bucket_for_hours(hours)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = text(
        """
        WITH per_ip_bucket AS (
            SELECT ip_id,
                   date_bin(make_interval(secs => :bucket), sampled_at,
                            TIMESTAMPTZ '2000-01-01') AS bucket,
                   MAX(bps_in)  AS bps_in,
                   MAX(bps_out) AS bps_out,
                   MAX(pps_in)  AS pps_in,
                   MAX(pps_out) AS pps_out
            FROM traffic_samples
            WHERE sampled_at >= :since
            GROUP BY ip_id, bucket
        )
        SELECT bucket,
               SUM(bps_in)::BIGINT       AS bps_in,
               SUM(bps_out)::BIGINT      AS bps_out,
               SUM(pps_in)::BIGINT       AS pps_in,
               SUM(pps_out)::BIGINT      AS pps_out,
               COUNT(DISTINCT ip_id)::INT AS ip_count
        FROM per_ip_bucket
        GROUP BY bucket
        ORDER BY bucket ASC
        """
    )
    rows = (await db.execute(stmt, {"bucket": bucket_sec, "since": since})).all()

    cur_in = await db.scalar(select(func.coalesce(func.sum(MonitoredIP.current_bps), 0))) or 0
    cur_out_row = await db.execute(
        text("SELECT COALESCE(SUM(bps_out), 0)::BIGINT FROM traffic_samples WHERE sampled_at >= NOW() - INTERVAL '15 seconds'")
    )
    cur_out = int(cur_out_row.scalar() or 0)

    return AggregateSeries(
        hours=hours,
        bucket_seconds=bucket_sec,
        points=[
            AggregatePoint(
                bucket=r.bucket,
                bps_in=int(r.bps_in or 0),
                bps_out=int(r.bps_out or 0),
                pps_in=int(r.pps_in or 0),
                pps_out=int(r.pps_out or 0),
                ip_count=int(r.ip_count or 0),
            )
            for r in rows
        ],
        current_total_bps_in=int(cur_in),
        current_total_bps_out=cur_out,
    )


@router.put("/ips/{ip_address}/whitelist", response_model=IPSummary)
async def set_whitelist(
    ip_address: str, payload: WhitelistUpdate, _: CurrentUser, db: DB
) -> IPSummary:
    """Toggle the per-IP whitelist flag. Whitelisted IPs still alert + email
    on spike but are NEVER blackholed by the detector."""
    rows = (
        await db.execute(select(MonitoredIP).where(MonitoredIP.ip_address == ip_address))
    ).scalars().all()
    if not rows:
        raise HTTPException(404, "IP not monitored")
    # If the IP exists in more than one pool we apply the flag to all of them.
    for r in rows:
        r.is_whitelisted = payload.is_whitelisted
        r.whitelist_note = payload.note
    await db.commit()
    return IPSummary.model_validate(rows[0])
