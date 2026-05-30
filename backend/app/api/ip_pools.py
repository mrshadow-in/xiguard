"""CRUD for IP pools + pool detail with member IPs."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.schemas.ip_pool import IPPoolCreate, IPPoolOut, IPPoolUpdate, IPSummary
from app.services.pool_sync import sync_pool_ips

router = APIRouter()


async def _stats(db, pool: IPPool) -> tuple[int, int, int]:
    counts = await db.execute(
        select(MonitoredIP.state, func.count(MonitoredIP.id))
        .where(MonitoredIP.pool_id == pool.id)
        .group_by(MonitoredIP.state)
    )
    total = 0
    alerting = 0
    blackholed = 0
    for state, n in counts:
        total += n
        if state == "ALERT":
            alerting += n
        elif state == "BLACKHOLED":
            blackholed += n
    return total, alerting, blackholed


async def _to_out(db, pool: IPPool) -> IPPoolOut:
    total, alerting, blackholed = await _stats(db, pool)
    out = IPPoolOut.model_validate(pool)
    out.cidr = str(pool.cidr)
    out.ip_count = total
    out.alert_count = alerting
    out.blackhole_count = blackholed
    return out


@router.get("", response_model=list[IPPoolOut])
async def list_pools(_: CurrentUser, db: DB) -> list[IPPoolOut]:
    rows = (await db.execute(select(IPPool).order_by(IPPool.cidr))).scalars().all()
    return [await _to_out(db, p) for p in rows]


@router.post("", response_model=IPPoolOut, status_code=status.HTTP_201_CREATED)
async def create_pool(payload: IPPoolCreate, _: CurrentUser, db: DB) -> IPPoolOut:
    pool = IPPool(
        chr_node_id=payload.chr_node_id,
        cidr=payload.cidr,
        description=payload.description,
        multiplier=payload.multiplier,
        eval_window_sec=payload.eval_window_sec,
        auto_blackhole=payload.auto_blackhole,
        blackhole_duration_sec=payload.blackhole_duration_sec,
    )
    db.add(pool)
    await db.commit()
    await db.refresh(pool)
    try:
        await sync_pool_ips(db, pool)
        await db.commit()
    except ValueError as e:
        raise HTTPException(422, str(e))
    return await _to_out(db, pool)


@router.get("/{pool_id}", response_model=IPPoolOut)
async def get_pool(pool_id: uuid.UUID, _: CurrentUser, db: DB) -> IPPoolOut:
    pool = await db.get(IPPool, pool_id)
    if not pool:
        raise HTTPException(404, "Pool not found")
    return await _to_out(db, pool)


@router.put("/{pool_id}", response_model=IPPoolOut)
async def update_pool(
    pool_id: uuid.UUID, payload: IPPoolUpdate, _: CurrentUser, db: DB
) -> IPPoolOut:
    pool = await db.get(IPPool, pool_id)
    if not pool:
        raise HTTPException(404, "Pool not found")
    data = payload.model_dump(exclude_unset=True)
    cidr_changed = "cidr" in data and data["cidr"] != str(pool.cidr)
    for k, v in data.items():
        setattr(pool, k, v)
    await db.commit()
    if cidr_changed:
        try:
            await sync_pool_ips(db, pool)
            await db.commit()
        except ValueError as e:
            raise HTTPException(422, str(e))
    await db.refresh(pool)
    return await _to_out(db, pool)


@router.delete("/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pool(pool_id: uuid.UUID, _: CurrentUser, db: DB) -> None:
    pool = await db.get(IPPool, pool_id)
    if not pool:
        raise HTTPException(404, "Pool not found")
    await db.delete(pool)
    await db.commit()


@router.get("/{pool_id}/ips", response_model=list[IPSummary])
async def list_pool_ips(
    pool_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    state: str | None = Query(default=None),
    limit: int = Query(default=500, le=5000),
    offset: int = Query(default=0, ge=0),
) -> list[IPSummary]:
    stmt = select(MonitoredIP).where(MonitoredIP.pool_id == pool_id).order_by(MonitoredIP.ip_address)
    if state:
        stmt = stmt.where(MonitoredIP.state == state)
    stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [IPSummary.model_validate(r) for r in rows]


@router.post("/{pool_id}/sync")
async def resync_pool(pool_id: uuid.UUID, _: CurrentUser, db: DB) -> dict:
    pool = await db.get(IPPool, pool_id)
    if not pool:
        raise HTTPException(404, "Pool not found")
    try:
        added, removed = await sync_pool_ips(db, pool)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await db.commit()
    return {"added": added, "removed": removed}
