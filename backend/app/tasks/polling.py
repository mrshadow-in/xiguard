"""Periodic polling + per-IP evaluation cycle."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import SessionLocal
from app.models.alert import (
    ALERT_BLACKHOLE_APPLIED,
    ALERT_BLACKHOLE_FAILED,
    ALERT_DDOS,
    ALERT_RECOVERED,
    Alert,
)
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.models.traffic_sample import TrafficSample
from app.services import alerter
from app.services.detector import evaluate
from app.services.mitigator import push_blackhole
from app.services.poller import poll_chr
from app.services.pubsub import CH_ALERTS, CH_STATE, CH_TRAFFIC, get_redis, publish
from app.tasks._runner import run
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.polling.poll_all_chrs")
def poll_all_chrs() -> dict:
    return run(_poll_all_chrs())


async def _poll_all_chrs() -> dict:
    async with SessionLocal() as session:
        chrs = (await session.execute(select(CHRNode))).scalars().all()
        if not chrs:
            return {"chrs": 0, "ips_evaluated": 0}

        results = await asyncio.gather(*(poll_chr(c) for c in chrs))

        for chr_node, result in zip(chrs, results):
            chr_node.last_seen_at = result.polled_at or datetime.now(timezone.utc)
            chr_node.status = "online" if result.ok else "offline"
        await session.commit()

        ips_evaluated = 0
        for chr_node, result in zip(chrs, results):
            if not result.ok:
                continue
            ips_evaluated += await _process_chr_samples(session, chr_node, result)

        return {"chrs": len(chrs), "ips_evaluated": ips_evaluated}


async def _process_chr_samples(session, chr_node: CHRNode, result) -> int:
    """For each known monitored IP whose sample we got, run the detector."""
    sample_map = result.samples
    if not sample_map:
        return 0

    pools = (
        await session.execute(select(IPPool).where(IPPool.chr_node_id == chr_node.id))
    ).scalars().all()
    if not pools:
        return 0
    pool_ids = [p.id for p in pools]
    pool_by_id = {p.id: p for p in pools}

    monitored = (
        await session.execute(
            select(MonitoredIP).where(MonitoredIP.pool_id.in_(pool_ids))
        )
    ).scalars().all()

    polled_at = result.polled_at or datetime.now(timezone.utc)
    redis = get_redis()
    evaluated = 0
    traffic_rows: list[dict] = []

    for ip in monitored:
        sample = sample_map.get(ip.ip_address)
        if sample is None:
            continue
        evaluated += 1
        pool = pool_by_id[ip.pool_id]

        decision = evaluate(ip, pool, sample.bps_in, now=polled_at)

        prior_state = ip.state
        ip.state = decision.new_state
        ip.baseline_bps = int(decision.new_baseline_bps)
        ip.current_bps = sample.bps_in
        ip.current_pps = sample.pps_in
        ip.sample_count = decision.new_sample_count
        ip.spike_start = decision.spike_start
        ip.blackholed_at = decision.blackholed_at
        ip.recovering_at = decision.recovering_at
        ip.last_spike_at = decision.last_spike_at
        ip.updated_at = polled_at

        traffic_rows.append(
            {
                "ip_id": ip.id,
                "bps_in": sample.bps_in,
                "bps_out": sample.bps_out,
                "pps_in": sample.pps_in,
                "pps_out": sample.pps_out,
                "sampled_at": polled_at,
            }
        )

        await publish(
            CH_TRAFFIC,
            {
                "ip": ip.ip_address,
                "bps_in": sample.bps_in,
                "bps_out": sample.bps_out,
                "pps_in": sample.pps_in,
                "baseline_bps": ip.baseline_bps,
                "state": ip.state,
                "chr_node": chr_node.name,
                "pool": str(pool.cidr),
            },
        )

        if prior_state != ip.state:
            await publish(
                CH_STATE,
                {
                    "ip": ip.ip_address,
                    "old_state": prior_state,
                    "new_state": ip.state,
                    "timestamp": polled_at.isoformat(),
                },
            )

        # ── Alert emission ────────────────────────────────────────────
        if decision.should_emit_alert and not await alerter.is_deduplicated(redis, ip.ip_address):
            multiplier = (sample.bps_in / max(1, ip.baseline_bps)) if ip.baseline_bps else 0
            alert = Alert(
                ip_id=ip.id,
                type=ALERT_DDOS,
                severity="critical" if multiplier >= float(pool.multiplier) * 3 else "warning",
                baseline_bps=ip.baseline_bps,
                peak_bps=sample.bps_in,
                action_taken="auto_blackhole" if decision.should_apply_blackhole else "alert_only",
            )
            session.add(alert)
            await session.flush()
            await alerter.mark_alerted(redis, ip.ip_address)

            hosting_ok, isp_ok = await alerter.dispatch_ddos_alert(
                session,
                alert_id=str(alert.id),
                ip=ip.ip_address,
                pool_cidr=str(pool.cidr),
                chr_name=chr_node.name,
                chr_host=chr_node.host,
                baseline_bps=int(ip.baseline_bps or 0),
                peak_bps=int(sample.bps_in),
                multiplier=float(multiplier),
                configured_multiplier=float(pool.multiplier),
                action="Auto-Blackhole Applied" if decision.should_apply_blackhole else "Alert Only",
                blackhole_expires_at=None,
            )
            alert.hosting_email_sent = hosting_ok
            alert.isp_email_sent = isp_ok
            await publish(
                CH_ALERTS,
                {
                    "id": str(alert.id),
                    "ip": ip.ip_address,
                    "severity": alert.severity,
                    "type": alert.type,
                    "baseline_bps": alert.baseline_bps,
                    "peak_bps": alert.peak_bps,
                    "multiplier": multiplier,
                    "action_taken": alert.action_taken,
                    "timestamp": polled_at.isoformat(),
                },
            )

        # ── Auto-blackhole push ───────────────────────────────────────
        if decision.should_apply_blackhole:
            ok = await push_blackhole(ip.ip_address, chr_node)
            session.add(
                Alert(
                    ip_id=ip.id,
                    type=ALERT_BLACKHOLE_APPLIED if ok else ALERT_BLACKHOLE_FAILED,
                    severity="info" if ok else "critical",
                    action_taken="auto_blackhole" if ok else "blackhole_failed",
                )
            )

        # ── Recovery emission ─────────────────────────────────────────
        if decision.should_emit_recovery:
            session.add(
                Alert(
                    ip_id=ip.id,
                    type=ALERT_RECOVERED,
                    severity="info",
                    action_taken="recovered",
                )
            )
            await alerter.dispatch_recovery(
                session,
                ip=ip.ip_address,
                pool_cidr=str(pool.cidr),
                chr_name=chr_node.name,
                baseline_bps=int(ip.baseline_bps or 0),
                current_bps=int(sample.bps_in),
            )

    if traffic_rows:
        await session.execute(pg_insert(TrafficSample).values(traffic_rows))

    await session.commit()
    return evaluated
