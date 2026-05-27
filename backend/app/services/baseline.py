"""EWMA baseline calculation.

α = 2 / (span + 1) — for span=720 (1 hour at 5s polling), α ≈ 0.00277.

Warm-up: while we have fewer than ``span`` samples for an IP we use a
simple moving average (computed externally — here we just blend the new
sample at a higher α). The first sample becomes the initial baseline.

While an IP is BLACKHOLED its traffic is by definition zero on the path
we observe, so callers must NOT update the baseline in that state — that
is the caller's responsibility (see detector.evaluate).
"""
from __future__ import annotations

from app.config import settings


def alpha_for(span: int | None = None) -> float:
    s = int(span if span is not None else settings.baseline_ewma_span)
    return 2.0 / (s + 1)


def warmup_alpha(sample_count: int, span: int | None = None) -> float:
    """During warm-up, weight new samples more heavily (1/(n+1) ~= SMA)."""
    n = max(1, sample_count)
    return 1.0 / (n + 1)


def update_baseline(
    current_baseline: float,
    new_sample: float,
    sample_count: int,
    span: int | None = None,
) -> float:
    """Return the new baseline given the prior baseline and a fresh sample.

    sample_count is the count BEFORE this sample (0 for the first sample).
    """
    if new_sample < 0:
        new_sample = 0.0
    if sample_count <= 0 or current_baseline <= 0:
        return float(new_sample)
    span_val = int(span if span is not None else settings.baseline_ewma_span)
    if sample_count < span_val:
        a = warmup_alpha(sample_count, span_val)
    else:
        a = alpha_for(span_val)
    return a * new_sample + (1.0 - a) * current_baseline
