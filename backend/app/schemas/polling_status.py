from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskStat(BaseModel):
    name: str
    label: str
    schedule_human: str
    schedule_sec: float | None = None     # interval period; None for cron
    last_run_at: datetime | None = None
    duration_ms: int | None = None
    next_run_eta_sec: float | None = None
    count: int = 0
    last_result: dict | None = None


class ExporterStat(BaseModel):
    exporter: str
    packets: int
    last_packet_at: datetime | None = None


class CHRFlowStatus(BaseModel):
    id: uuid.UUID
    name: str
    host: str
    status: str
    last_seen_at: datetime | None = None
    monitored_ip_count: int
    actively_flowing: int


class PollingStatus(BaseModel):
    poll_interval_sec: int
    last_poll_at: datetime | None = None
    last_poll_duration_ms: int | None = None
    last_poll_ips_evaluated: int | None = None
    last_poll_ips_with_data: int | None = None
    next_poll_eta_sec: float | None = None
    cycles_total: int = 0

    flow_packets_total: int = 0
    flow_records_total: int = 0
    flow_active_ips: int = 0
    last_flow_at: datetime | None = None
    flow_exporters: list[ExporterStat] = []

    tasks: list[TaskStat] = []
    chrs: list[CHRFlowStatus] = []
