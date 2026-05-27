"""poller._aggregate converts accounting rows into per-IP bps/pps."""
from __future__ import annotations

from app.services.poller import _aggregate


def test_aggregate_sums_bytes_and_packets_per_dst():
    rows = [
        {"src-address": "1.2.3.4", "dst-address": "10.0.0.5", "bytes": "1000", "packets": "10"},
        {"src-address": "1.2.3.5", "dst-address": "10.0.0.5", "bytes": "500", "packets": "5"},
        {"src-address": "1.2.3.6", "dst-address": "10.0.0.6", "bytes": "200", "packets": "2"},
    ]
    out = _aggregate(rows, interval_sec=5)
    # 10.0.0.5: 1500 bytes over 5s → 2400 bps_in, 15 packets → 3 pps_in
    assert out["10.0.0.5"].bps_in == (1500 * 8) // 5
    assert out["10.0.0.5"].pps_in == 15 // 5
    assert out["10.0.0.6"].bps_in == (200 * 8) // 5


def test_aggregate_handles_missing_dst_gracefully():
    rows = [
        {"src-address": "1.2.3.4", "bytes": "100", "packets": "1"},
        {"dst-address": "10.0.0.5", "bytes": "200", "packets": "2"},
    ]
    out = _aggregate(rows, interval_sec=1)
    assert "10.0.0.5" in out
    assert out["10.0.0.5"].bps_in == 200 * 8
    # src-only row counts as bps_out for that src.
    assert out["1.2.3.4"].bps_out == 100 * 8
