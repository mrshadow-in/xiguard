"""Per-IP spike detection and state machine.

States: NORMAL → ALERT → BLACKHOLED → RECOVERING → NORMAL

Transitions are derived purely from the current sample, the IP's prior state,
and timing fields. The detector returns a ``DetectorDecision`` describing
what the caller (the polling task) should do — it does NOT mutate the DB,
push routes, or send emails itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from app.config import settings
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.services import baseline as baseline_svc


class State(str, Enum):
    NORMAL = "NORMAL"
    ALERT = "ALERT"
    BLACKHOLED = "BLACKHOLED"
    RECOVERING = "RECOVERING"


@dataclass
class DetectorDecision:
    new_state: str
    new_baseline_bps: float
    new_sample_count: int
    spike_start: Optional[datetime]
    blackholed_at: Optional[datetime]
    recovering_at: Optional[datetime]
    last_spike_at: Optional[datetime]
    should_emit_alert: bool = False        # NORMAL/RECOVERING → ALERT, sustained spike
    should_apply_blackhole: bool = False   # auto_blackhole + just transitioned to BLACKHOLED
    should_lift_blackhole: bool = False    # BLACKHOLED → RECOVERING (duration expired)
    should_emit_recovery: bool = False     # RECOVERING → NORMAL


def _now() -> datetime:
    return datetime.now(timezone.utc)


def evaluate(
    ip: MonitoredIP,
    pool: IPPool,
    bps_in: int,
    now: datetime | None = None,
) -> DetectorDecision:
    """Evaluate one polling cycle for one IP."""
    now = now or _now()
    state = ip.state or State.NORMAL.value
    spike_start = ip.spike_start
    blackholed_at = ip.blackholed_at
    recovering_at = ip.recovering_at
    last_spike_at = ip.last_spike_at
    baseline = float(ip.baseline_bps or 0)
    samples = int(ip.sample_count or 0)

    decision = DetectorDecision(
        new_state=state,
        new_baseline_bps=baseline,
        new_sample_count=samples,
        spike_start=spike_start,
        blackholed_at=blackholed_at,
        recovering_at=recovering_at,
        last_spike_at=last_spike_at,
    )

    # ── BLACKHOLED ──────────────────────────────────────────────────────
    # Traffic is dropped at the CHR; do not update baseline. Lift after duration.
    if state == State.BLACKHOLED.value:
        if blackholed_at is not None:
            duration = timedelta(seconds=pool.blackhole_duration_sec)
            if now - blackholed_at >= duration:
                decision.new_state = State.RECOVERING.value
                decision.blackholed_at = None
                decision.recovering_at = now
                decision.should_lift_blackhole = True
        return decision

    # For NORMAL / ALERT / RECOVERING we update the baseline with the new sample.
    decision.new_baseline_bps = baseline_svc.update_baseline(
        current_baseline=baseline,
        new_sample=bps_in,
        sample_count=samples,
        span=settings.baseline_ewma_span,
    )
    decision.new_sample_count = samples + 1

    # Threshold uses the PRIOR baseline so a single huge sample can't pull the
    # threshold along with it and mask the spike.
    reference_baseline = baseline if samples > 0 else float(bps_in)
    threshold = reference_baseline * float(pool.multiplier)
    is_spiking = bps_in > threshold and reference_baseline > 0

    # ── NORMAL ──────────────────────────────────────────────────────────
    if state == State.NORMAL.value:
        if is_spiking:
            if spike_start is None:
                decision.spike_start = now
            elif (now - spike_start).total_seconds() >= pool.eval_window_sec:
                decision.new_state = State.ALERT.value
                decision.last_spike_at = now
                decision.should_emit_alert = True
                if pool.auto_blackhole:
                    decision.new_state = State.BLACKHOLED.value
                    decision.blackholed_at = now
                    decision.spike_start = None
                    decision.should_apply_blackhole = True
        else:
            decision.spike_start = None
        return decision

    # ── ALERT ───────────────────────────────────────────────────────────
    if state == State.ALERT.value:
        if is_spiking:
            decision.last_spike_at = now
            if pool.auto_blackhole:
                decision.new_state = State.BLACKHOLED.value
                decision.blackholed_at = now
                decision.spike_start = None
                decision.should_apply_blackhole = True
        else:
            # Traffic dropped without a blackhole; go straight to RECOVERING.
            decision.new_state = State.RECOVERING.value
            decision.recovering_at = now
            decision.spike_start = None
        return decision

    # ── RECOVERING ──────────────────────────────────────────────────────
    if state == State.RECOVERING.value:
        if is_spiking:
            # Spike returned — re-enter ALERT (and possibly blackhole again).
            decision.new_state = State.ALERT.value
            decision.spike_start = now
            decision.last_spike_at = now
            decision.recovering_at = None
            decision.should_emit_alert = True
            if pool.auto_blackhole:
                decision.new_state = State.BLACKHOLED.value
                decision.blackholed_at = now
                decision.spike_start = None
                decision.should_apply_blackhole = True
        else:
            observation = settings.default_recovery_observation_sec
            if recovering_at is not None and (now - recovering_at).total_seconds() >= observation:
                decision.new_state = State.NORMAL.value
                decision.recovering_at = None
                decision.should_emit_recovery = True
        return decision

    return decision
