"""Shared pytest fixtures."""
from __future__ import annotations

import base64
import os
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch):
    # 32-byte zero key just for tests.
    key = base64.b64encode(b"\x00" * 32).decode("ascii")
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    # Force reload of crypto module's cached key.
    from app.services import crypto
    crypto._KEY = None
    yield
    crypto._KEY = None


def make_pool(**overrides) -> SimpleNamespace:
    base = dict(
        id="pool-1",
        chr_node_id="chr-1",
        cidr="10.0.0.0/24",
        multiplier=3.0,
        eval_window_sec=30,
        auto_blackhole=True,
        blackhole_duration_sec=600,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_ip(**overrides) -> SimpleNamespace:
    base = dict(
        id="ip-1",
        pool_id="pool-1",
        ip_address="10.0.0.5",
        state="NORMAL",
        baseline_bps=0,
        current_bps=0,
        current_pps=0,
        sample_count=0,
        spike_start=None,
        last_spike_at=None,
        blackholed_at=None,
        recovering_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)
