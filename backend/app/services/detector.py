"""Per-IP spike detection and state machine.

States: SAMPLING → NORMAL → ALERT → BLACKHOLED → RECOVERING → NORMAL

`SAMPLING` is the warmup window every newly-monitored IP must complete
before the detector is allowed to fire. While in SAMPLING the baseline
is updated but no spike is reported and no email/blackhole is dispatched.
Once `sample_count >= pool.warmup_samples` the IP graduates to NORMAL
and detection becomes active.

To stop the detector from chasing background noise, three per-pool
floors gate every spike decision:

  - pool.multiplier         current must exceed baseline * multiplier
  - pool.min_baseline_bps   the baseline itself must be at least this big
  - pool.min_spike_bps      the current sample must be at least this big

A 50 kbps "baseline" times a 3× multiplier is a 150 kbps "threshold" —
useless at NOC scale and the source of every false positive. Both
floors must be satisfied for `is_spiking` to be true.

Transitions are derived purely from the current sample, the IP's prior
state, and timing fields. The detector returns a ``DetectorDecision``
describing what the caller (the polling task) should do — it does NOT
mutate the DB, push routes, or send emails itself.
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
    SAMPLING = "SAMPLING"
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
    armed: bool = False                    # SAMPLING → NORMAL (warmup complete)


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
    state = ip.state or State.SAMPLING.value
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

    # Every other state updates the baseline with the new sample.
    decision.new_baseline_bps = baseline_svc.update_baseline(
        current_baseline=baseline,
        new_sample=bps_in,
        sample_count=samples,
        span=settings.baseline_ewma_span,
    )
    decision.new_sample_count = samples + 1

    warmup_target = max(1, int(getattr(pool, "warmup_samples", 120)))

    # ── SAMPLING ────────────────────────────────────────────────────────
    # Quietly learn the baseline; never alert, never blackhole. Graduate to
    # NORMAL once we have at least warmup_samples observations.
    if state == State.SAMPLING.value:
        if decision.new_sample_count >= warmup_target:
            decision.new_state = State.NORMAL.value
            decision.armed = True
        return decision

    # Threshold uses the PRIOR baseline so a single huge sample can't pull the
    # threshold along with it and mask the spike.
    reference_baseline = baseline if samples > 0 else float(bps_in)
    threshold = reference_baseline * float(pool.multiplier)

    # Both floors must clear OR we don't consider it a real spike.
    min_baseline = int(getattr(pool, "min_baseline_bps", 0) or 0)
    min_spike = int(getattr(pool, "min_spike_bps", 0) or 0)
    is_spiking = (
        reference_baseline >= min_baseline
        and bps_in >= min_spike
        and bps_in > threshold
    )

    # Whitelisted IPs still alert + email but are NEVER blackholed.
    blackhole_allowed = bool(pool.auto_blackhole) and not bool(getattr(ip, "is_whitelisted", False))

    # ── NORMAL ──────────────────────────────────────────────────────────
    if state == State.NORMAL.value:
        if is_spiking:
            if spike_start is None:
                decision.spike_start = now
            elif (now - spike_start).total_seconds() >= pool.eval_window_sec:
                decision.new_state = State.ALERT.value
                decision.last_spike_at = now
                decision.should_emit_alert = True
                if blackhole_allowed:
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
            if blackhole_allowed:
                decision.new_state = State.BLACKHOLED.value
                decision.blackholed_at = now
                decision.spike_start = None
                decision.should_apply_blackhole = True
        else:
            decision.new_state = State.RECOVERING.value
            decision.recovering_at = now
            decision.spike_start = None
        return decision

    # ── RECOVERING ──────────────────────────────────────────────────────
    if state == State.RECOVERING.value:
        if is_spiking:
            decision.new_state = State.ALERT.value
            decision.spike_start = now
            decision.last_spike_at = now
            decision.recovering_at = None
            decision.should_emit_alert = True
            if blackhole_allowed:
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
