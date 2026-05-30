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
    ALERT_DDOS,
    ALERT_RECOVERED,
    Alert,
)
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.models.traffic_sample import TrafficSample
from app.services.detector import evaluate
from app.services.poller import sample_ip
from app.services.pubsub import CH_STATE, CH_TRAFFIC, get_redis, publish
from app.tasks._runner import run
from app.tasks.alert_dispatch import dispatch_ddos_email, dispatch_recovery_email
from app.tasks.celery_app import celery_app
from app.tasks.mitigation import push_blackhole_now

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

            # ── Mitigation fast-path ────────────────────────────────────
            # NEVER block on RouterOS API or SMTP here. The polling cycle
            # must finish in milliseconds so detection keeps firing for
            # every other IP during the same attack. Dispatch the side
            # effects to dedicated workers and trust them to catch up.
            multiplier = (
                (sample.bps_in / max(1, ip.baseline_bps)) if ip.baseline_bps else 0
            )

            if decision.should_apply_blackhole:
                # Optimistically state-transition; mitigation task will
                # roll back to ALERT + write a blackhole_failed Alert if
                # the route doesn't actually land on the CHR.
                push_blackhole_now.apply_async(
                    kwargs={"ip_id": str(ip.id), "chr_id": str(chr_node.id)},
                    queue="critical",
                    priority=9,
                )

            if decision.should_emit_alert:
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
                # Email + dedup + WS publish happens in the email-queue
                # worker so SMTP latency can never block detection.
                dispatch_ddos_email.apply_async(
                    kwargs={"alert_id": str(alert.id), "multiplier": float(multiplier)},
                    queue="email",
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
                dispatch_recovery_email.apply_async(
                    kwargs={"ip_id": str(ip.id)},
                    queue="email",
                )

        if traffic_rows:
            await session.execute(pg_insert(TrafficSample).values(traffic_rows))

        await session.commit()

    duration_ms = int((time.perf_counter() - started) * 1000)
    result = {"ips_evaluated": evaluated, "ips_with_data": ips_with_data}
    await stats.record_task("poll_all_chrs", duration_ms=duration_ms, result=result, redis=redis)
    return result
