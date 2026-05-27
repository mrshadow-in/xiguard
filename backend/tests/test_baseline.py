"""EWMA baseline math + warm-up behavior."""
from __future__ import annotations

import pytest

from app.services import baseline


def test_first_sample_becomes_baseline():
    # sample_count=0 means there is no prior baseline
    assert baseline.update_baseline(0.0, 1000.0, sample_count=0) == 1000.0


def test_warmup_blends_more_aggressively_than_ewma():
    # After 5 samples, warmup alpha = 1/(5+1) ≈ 0.167.
    # Steady EWMA alpha at span=720 ≈ 0.00277.
    # New sample 2000 with prior baseline 1000 should pull MUCH harder during warmup.
    warm = baseline.update_baseline(1000.0, 2000.0, sample_count=5, span=720)
    cold = baseline.update_baseline(1000.0, 2000.0, sample_count=720, span=720)
    assert warm > cold
    assert 1100 < warm < 1300
    # Cold/steady EWMA barely moves the baseline.
    assert 1000 < cold < 1010


def test_baseline_converges_to_constant_source():
    # If we feed the same value over and over, the baseline should converge to it.
    b = 0.0
    for i in range(2000):
        b = baseline.update_baseline(b, 5_000_000.0, sample_count=i, span=720)
    assert abs(b - 5_000_000.0) < 50_000


def test_negative_sample_clamped_to_zero():
    b = baseline.update_baseline(100.0, -50.0, sample_count=10, span=720)
    assert b < 100.0  # decayed toward zero
    assert b >= 0.0


def test_alpha_formula():
    assert baseline.alpha_for(720) == pytest.approx(2 / 721)
    assert baseline.alpha_for(1) == pytest.approx(2 / 2)
