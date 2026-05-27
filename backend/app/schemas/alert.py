from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ip_id: uuid.UUID
    ip_address: str | None = None
    pool_cidr: str | None = None
    chr_name: str | None = None
    type: str
    severity: str
    baseline_bps: int | None = None
    peak_bps: int | None = None
    action_taken: str | None = None
    hosting_email_sent: bool
    isp_email_sent: bool
    acknowledged: bool
    acknowledged_by: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class AlertStats(BaseModel):
    total_24h: int
    critical_24h: int
    warning_24h: int
    info_24h: int
    by_day: list[dict]  # [{date, count}]
