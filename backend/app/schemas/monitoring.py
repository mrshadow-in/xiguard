from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MonitoringOverview(BaseModel):
    total_chr_nodes: int
    online_chr_nodes: int
    total_pools: int
    total_ips: int
    alert_count: int
    blackhole_count: int
    last_poll_at: datetime | None = None


class IPTrafficPoint(BaseModel):
    sampled_at: datetime
    bps_in: int
    bps_out: int
    pps_in: int
    pps_out: int


class IPTrafficHistory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ip_id: uuid.UUID
    ip_address: str
    state: str
    baseline_bps: int
    current_bps: int
    points: list[IPTrafficPoint]
