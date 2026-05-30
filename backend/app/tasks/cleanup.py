"""Data retention + rolling daily partition maintenance for traffic_samples."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.services import stats
from app.tasks._runner import run
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.cleanup.ensure_partitions")
def ensure_partitions() -> dict:
    return run(_ensure_partitions())


async def _ensure_partitions() -> dict:
    """Create today + next 2 days of partitions, drop ones older than retention."""
    started = time.perf_counter()
    created = 0
    dropped = 0
    today = datetime.now(timezone.utc).date()

    async with SessionLocal() as session:
        for offset in range(0, 3):
            d = today + timedelta(days=offset)
            d_next = d + timedelta(days=1)
            name = f"traffic_samples_{d.strftime('%Y%m%d')}"
            stmt = text(
                f"""
                CREATE TABLE IF NOT EXISTS {name}
                PARTITION OF traffic_samples
                FOR VALUES FROM ('{d.isoformat()}') TO ('{d_next.isoformat()}')
                """
            )
            await session.execute(stmt)
            created += 1

        # Drop partitions older than the retention window.
        cutoff = today - timedelta(days=settings.traffic_retention_days)
        rows = await session.execute(
            text(
                """
                SELECT inhrelid::regclass::text AS name
                FROM pg_inherits
                WHERE inhparent = 'traffic_samples'::regclass
                """
            )
        )
        for (name,) in rows:
            base = name.split(".")[-1]
            if not base.startswith("traffic_samples_") or base == "traffic_samples_default":
                continue
            datepart = base.removeprefix("traffic_samples_")
            try:
                d = datetime.strptime(datepart, "%Y%m%d").date()
            except ValueError:
                continue
            if d < cutoff:
                await session.execute(text(f"DROP TABLE IF EXISTS {base}"))
                dropped += 1

        await session.commit()
    duration_ms = int((time.perf_counter() - started) * 1000)
    result = {"created": created, "dropped": dropped}
    await stats.record_task("ensure_partitions", duration_ms=duration_ms, result=result)
    return result


@celery_app.task(name="app.tasks.cleanup.cleanup_old_data")
def cleanup_old_data() -> dict:
    return run(_cleanup_old_data())


async def _cleanup_old_data() -> dict:
    started = time.perf_counter()
    async with SessionLocal() as session:
        alert_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.alert_retention_days)
        audit_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audit_retention_days)
        a = await session.execute(
            text("DELETE FROM alerts WHERE created_at < :cutoff"), {"cutoff": alert_cutoff}
        )
        b = await session.execute(
            text("DELETE FROM audit_log WHERE created_at < :cutoff"), {"cutoff": audit_cutoff}
        )
        await session.commit()
    duration_ms = int((time.perf_counter() - started) * 1000)
    result = {"alerts_deleted": a.rowcount or 0, "audit_deleted": b.rowcount or 0}
    await stats.record_task("cleanup_old_data", duration_ms=duration_ms, result=result)
    return result
