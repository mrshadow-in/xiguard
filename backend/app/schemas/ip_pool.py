from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IPPoolBase(BaseModel):
    cidr: str = Field(min_length=9)  # e.g. "1.2.3.0/24"
    description: str | None = None
    multiplier: float = Field(default=3.0, gt=1.0)
    eval_window_sec: int = Field(default=30, ge=5, le=600)
    auto_blackhole: bool = True
    blackhole_duration_sec: int = Field(default=600, ge=10)


class IPPoolCreate(IPPoolBase):
    chr_node_id: uuid.UUID


class IPPoolUpdate(BaseModel):
    cidr: str | None = None
    description: str | None = None
    multiplier: float | None = Field(default=None, gt=1.0)
    eval_window_sec: int | None = Field(default=None, ge=5, le=600)
    auto_blackhole: bool | None = None
    blackhole_duration_sec: int | None = Field(default=None, ge=10)


class IPPoolOut(IPPoolBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chr_node_id: uuid.UUID
    created_at: datetime
    ip_count: int = 0
    alert_count: int = 0
    blackhole_count: int = 0


class IPSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ip_address: str
    state: str
    baseline_bps: int
    current_bps: int
    current_pps: int
    spike_start: datetime | None = None
    blackholed_at: datetime | None = None
