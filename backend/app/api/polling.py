"""GET /api/polling-status — runtime overview of polling, NetFlow, Celery tasks."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB
from app.config import settings
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.schemas.polling_status import (
    CHRFlowStatus,
    ExporterStat,
    PollingStatus,
    TaskStat,
)
from app.services import stats

router = APIRouter()


# Beat-schedule definitions kept in sync with app/tasks/celery_app.py.
_TASKS = [
    ("poll_all_chrs", "Per-IP traffic poll", float(settings.poll_interval_sec), f"every {settings.poll_interval_sec}s"),
    ("check_blackhole_expiry", "Blackhole expiry sweep", 30.0, "every 30s"),
    ("health_check_chrs", "CHR health probe", 60.0, "every 60s"),
    ("ensure_partitions", "Traffic partition maint.", None, "daily 00:05 UTC"),
    ("cleanup_old_data", "Retention cleanup", None, "daily 03:00 UTC"),
]


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _eta_seconds(last_at: datetime | None, period_sec: float | None) -> float | None:
    if last_at is None or period_sec is None:
        return None
    now = datetime.now(timezone.utc)
    elapsed = (now - last_at).total_seconds()
    remaining = period_sec - elapsed
    return max(0.0, remaining)


@router.get("", response_model=PollingStatus)
async def polling_status(_: CurrentUser, db: DB) -> PollingStatus:
    # ── task stats ─────────────────────────────────────────────────────
    task_views: list[TaskStat] = []
    poll_task_data = None
    for name, label, period, human in _TASKS:
        raw = await stats.read_task(name)
        last_at = _parse_iso(raw["last_at"])
        ts = TaskStat(
            name=name,
            label=label,
            schedule_human=human,
            schedule_sec=period,
            last_run_at=last_at,
            duration_ms=raw["duration_ms"],
            next_run_eta_sec=_eta_seconds(last_at, period),
            count=raw["count"],
            last_result=raw["result"],
        )
        task_views.append(ts)
        if name == "poll_all_chrs":
            poll_task_data = ts

    # ── flow collector meta ───────────────────────────────────────────
    flow_meta = await stats.read_flow_meta()
    flow_exporters_raw = await stats.read_flow_exporters()
    active_ip_set = await stats.active_flow_ip_set()
    flow_exporters = [
        ExporterStat(
            exporter=e["exporter"],
            packets=e["packets"],
            last_packet_at=_parse_iso(e["last_packet_at"]),
        )
        for e in flow_exporters_raw
    ]

    # ── per-CHR flow visibility ───────────────────────────────────────
    chr_rows = (await db.execute(select(CHRNode).order_by(CHRNode.name))).scalars().all()
    chr_views: list[CHRFlowStatus] = []
    for chr_node in chr_rows:
        ip_rows = (
            await db.execute(
                select(MonitoredIP.ip_address)
                .join(IPPool, IPPool.id == MonitoredIP.pool_id)
                .where(IPPool.chr_node_id == chr_node.id)
            )
        ).all()
        all_ips = {str(r[0]) for r in ip_rows}
        flowing = len(all_ips & active_ip_set)
        chr_views.append(
            CHRFlowStatus(
                id=chr_node.id,
                name=chr_node.name,
                host=chr_node.host,
                status=chr_node.status,
                last_seen_at=chr_node.last_seen_at,
                monitored_ip_count=len(all_ips),
                actively_flowing=flowing,
            )
        )

    last_poll_at = poll_task_data.last_run_at if poll_task_data else None
    last_result = (poll_task_data.last_result if poll_task_data else None) or {}
    return PollingStatus(
        poll_interval_sec=settings.poll_interval_sec,
        last_poll_at=last_poll_at,
        last_poll_duration_ms=poll_task_data.duration_ms if poll_task_data else None,
        last_poll_ips_evaluated=last_result.get("ips_evaluated"),
        last_poll_ips_with_data=last_result.get("ips_with_data"),
        next_poll_eta_sec=poll_task_data.next_run_eta_sec if poll_task_data else None,
        cycles_total=poll_task_data.count if poll_task_data else 0,
        flow_packets_total=flow_meta["packets"],
        flow_records_total=flow_meta["records"],
        flow_active_ips=len(active_ip_set),
        last_flow_at=_parse_iso(flow_meta["last_packet_at"]),
        flow_exporters=flow_exporters,
        tasks=task_views,
        chrs=chr_views,
    )
