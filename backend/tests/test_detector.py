"""Detector state machine: NORMAL → ALERT → BLACKHOLED → RECOVERING → NORMAL."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.detector import State, evaluate
from tests.conftest import make_ip, make_pool


def _t(seconds: int = 0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)


def test_normal_stays_normal_when_below_threshold():
    pool = make_pool(multiplier=3.0)
    ip = make_ip(state=State.NORMAL.value, baseline_bps=1_000_000, sample_count=1000)
    d = evaluate(ip, pool, bps_in=2_000_000, now=_t())
    assert d.new_state == "NORMAL"
    assert d.spike_start is None
    assert not d.should_emit_alert


def test_spike_starts_timer_then_alerts_after_eval_window():
    pool = make_pool(multiplier=3.0, eval_window_sec=30, auto_blackhole=False)
    ip = make_ip(state=State.NORMAL.value, baseline_bps=1_000_000, sample_count=1000)

    # First over-threshold sample: starts the spike timer but does NOT alert yet.
    d = evaluate(ip, pool, bps_in=10_000_000, now=_t(0))
    assert d.new_state == "NORMAL"
    assert d.spike_start == _t(0)
    assert not d.should_emit_alert

    # Move ip forward to mid-spike — still not enough sustained time.
    ip.spike_start = d.spike_start
    d = evaluate(ip, pool, bps_in=10_000_000, now=_t(15))
    assert d.new_state == "NORMAL"
    assert not d.should_emit_alert

    # After eval_window seconds of sustained spike, transition to ALERT.
    d = evaluate(ip, pool, bps_in=10_000_000, now=_t(30))
    assert d.new_state == "ALERT"
    assert d.should_emit_alert


def test_sustained_spike_with_auto_blackhole_goes_straight_to_blackholed():
    pool = make_pool(multiplier=3.0, eval_window_sec=30, auto_blackhole=True)
    ip = make_ip(
        state=State.NORMAL.value,
        baseline_bps=1_000_000,
        sample_count=1000,
        spike_start=_t(0),
    )
    d = evaluate(ip, pool, bps_in=10_000_000, now=_t(30))
    assert d.new_state == "BLACKHOLED"
    assert d.should_emit_alert
    assert d.should_apply_blackhole
    assert d.blackholed_at == _t(30)


def test_spike_below_threshold_resets_timer():
    pool = make_pool(multiplier=3.0, eval_window_sec=30)
    ip = make_ip(
        state=State.NORMAL.value,
        baseline_bps=1_000_000,
        sample_count=1000,
        spike_start=_t(0),
    )
    d = evaluate(ip, pool, bps_in=1_500_000, now=_t(15))
    assert d.new_state == "NORMAL"
    assert d.spike_start is None


def test_blackhole_expires_to_recovering():
    pool = make_pool(blackhole_duration_sec=600)
    ip = make_ip(
        state=State.BLACKHOLED.value,
        baseline_bps=1_000_000,
        sample_count=2000,
        blackholed_at=_t(0),
    )
    d = evaluate(ip, pool, bps_in=0, now=_t(601))
    assert d.new_state == "RECOVERING"
    assert d.should_lift_blackhole
    assert d.blackholed_at is None


def test_blackhole_does_not_update_baseline():
    pool = make_pool()
    ip = make_ip(
        state=State.BLACKHOLED.value,
        baseline_bps=5_000_000,
        sample_count=2000,
        blackholed_at=_t(0),
    )
    d = evaluate(ip, pool, bps_in=0, now=_t(60))
    # Baseline must NOT be pulled toward zero while blackholed.
    assert d.new_baseline_bps == 5_000_000
    assert d.new_sample_count == 2000


def test_recovering_with_spike_returns_to_alert_and_blackhole():
    pool = make_pool(multiplier=3.0, auto_blackhole=True)
    ip = make_ip(
        state=State.RECOVERING.value,
        baseline_bps=1_000_000,
        sample_count=2000,
        recovering_at=_t(0),
    )
    d = evaluate(ip, pool, bps_in=10_000_000, now=_t(10))
    assert d.new_state == "BLACKHOLED"
    assert d.should_apply_blackhole
    assert d.should_emit_alert


def test_recovering_normalizes_after_observation_window(monkeypatch):
    # default_recovery_observation_sec defaults to 60.
    from app.services import detector
    monkeypatch.setattr(detector.settings, "default_recovery_observation_sec", 60)

    pool = make_pool()
    ip = make_ip(
        state=State.RECOVERING.value,
        baseline_bps=1_000_000,
        sample_count=2000,
        recovering_at=_t(0),
    )
    d = evaluate(ip, pool, bps_in=500_000, now=_t(65))
    assert d.new_state == "NORMAL"
    assert d.should_emit_recovery
    assert d.recovering_at is None
