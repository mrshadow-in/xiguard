"""Traffic polling orchestrator.

For each active CHR, takes an /ip/accounting/snapshot and aggregates
inbound bytes per destination IP. Returns a dict {ip_string: bps_in}
computed from the delta since the last snapshot was taken (RouterOS
``/ip accounting`` snapshots are themselves deltas if you call ``take``
on a regular interval, so we use the snapshot values directly and
divide by the configured poll interval).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings
from app.models.chr_node import CHRNode
from app.services.chr_api import CHRClient

logger = logging.getLogger(__name__)


@dataclass
class PerIPSample:
    bps_in: int
    bps_out: int
    pps_in: int
    pps_out: int


@dataclass
class CHRPollResult:
    chr_id: str
    ok: bool
    samples: dict[str, PerIPSample]
    error: str | None = None
    polled_at: datetime | None = None


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _aggregate(rows: list[dict], interval_sec: int) -> dict[str, PerIPSample]:
    """Aggregate accounting rows by destination IP and convert to bps/pps."""
    per_ip: dict[str, dict[str, int]] = {}
    for row in rows:
        dst = row.get("dst-address") or row.get("dst")
        src = row.get("src-address") or row.get("src")
        if not dst:
            continue
        bytes_ = _to_int(row.get("bytes"))
        packets = _to_int(row.get("packets"))
        per_ip.setdefault(dst, {"b_in": 0, "p_in": 0, "b_out": 0, "p_out": 0})
        per_ip[dst]["b_in"] += bytes_
        per_ip[dst]["p_in"] += packets
        if src:
            per_ip.setdefault(src, {"b_in": 0, "p_in": 0, "b_out": 0, "p_out": 0})
            per_ip[src]["b_out"] += bytes_
            per_ip[src]["p_out"] += packets

    out: dict[str, PerIPSample] = {}
    iv = max(1, int(interval_sec))
    for ip, counters in per_ip.items():
        out[ip] = PerIPSample(
            bps_in=(counters["b_in"] * 8) // iv,
            bps_out=(counters["b_out"] * 8) // iv,
            pps_in=counters["p_in"] // iv,
            pps_out=counters["p_out"] // iv,
        )
    return out


async def poll_chr(chr_node: CHRNode) -> CHRPollResult:
    polled_at = datetime.now(timezone.utc)
    try:
        async with CHRClient.from_node(chr_node) as api:
            rows = await api.accounting_snapshot()
    except Exception as e:  # noqa: BLE001
        logger.warning("CHR poll failed: %s — %s", chr_node.name, e)
        return CHRPollResult(
            chr_id=str(chr_node.id), ok=False, samples={}, error=str(e), polled_at=polled_at
        )

    samples = _aggregate(rows, settings.poll_interval_sec)
    return CHRPollResult(
        chr_id=str(chr_node.id), ok=True, samples=samples, polled_at=polled_at
    )
