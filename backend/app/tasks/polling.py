"""Per-IP polling cycle.

We no longer poll each CHR — traffic data is fed by the flow-collector
service over UDP NetFlow and aggregated into Redis. The cycle:

  1. Load every MonitoredIP (plus its pool + CHR) from the DB
  2. For each IP, atomically read+reset its Redis flow counters
  3. Run the detector
  4. Persist sample, update IP state, publish pubsub, dispatch alerts,
     push blackhole if needed
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.services import stats
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
from app.services.poller import sample_ip
from app.services.pubsub import CH_ALERTS, CH_STATE, CH_TRAFFIC, get_redis, publish
from app.tasks._runner import run
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.polling.poll_all_chrs")
def poll_all_chrs() -> dict:
    return run(_cycle())


async def _cycle() -> dict:
    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    redis = get_redis()
    evaluated = 0
    ips_with_data = 0
    traffic_rows: list[dict] = []

    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(MonitoredIP).options(
                    selectinload(MonitoredIP.pool).selectinload(IPPool.chr_node)
                )
            )
        ).scalars().all()
        if not rows:
            return {"ips_evaluated": 0}

        # Drain each unique IP's Redis counter exactly once, then apply the
        # same sample to every MonitoredIP row sharing that address. This is
        # what lets two pools (possibly on different CHRs) monitor the same
        # IP without one starving the other's read.
        unique_ips = {ip.ip_address for ip in rows}
        sample_by_ip = {addr: await sample_ip(addr, redis) for addr in unique_ips}

        for ip in rows:
            pool: IPPool = ip.pool
            chr_node: CHRNode = pool.chr_node
            sample = sample_by_ip[ip.ip_address]
            evaluated += 1
            if sample.bps_in > 0 or sample.bps_out > 0:
                ips_with_data += 1

            decision = evaluate(ip, pool, sample.bps_in, now=now)

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
            ip.updated_at = now

            traffic_rows.append(
                {
                    "ip_id": ip.id,
                    "bps_in": sample.bps_in,
                    "bps_out": sample.bps_out,
                    "pps_in": sample.pps_in,
                    "pps_out": sample.pps_out,
                    "sampled_at": now,
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
                        "timestamp": now.isoformat(),
                    },
                )

            if decision.should_emit_alert and not await alerter.is_deduplicated(
                redis, ip.ip_address
            ):
                multiplier = (
                    (sample.bps_in / max(1, ip.baseline_bps)) if ip.baseline_bps else 0
                )
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
                        "timestamp": now.isoformat(),
                    },
                )

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

    duration_ms = int((time.perf_counter() - started) * 1000)
    result = {"ips_evaluated": evaluated, "ips_with_data": ips_with_data}
    await stats.record_task("poll_all_chrs", duration_ms=duration_ms, result=result, redis=redis)
    return result
