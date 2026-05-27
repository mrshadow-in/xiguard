"""Celery app + Beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "chrguard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.polling",
        "app.tasks.recovery",
        "app.tasks.cleanup",
        "app.tasks.health",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=2,
    task_routes={
        "app.tasks.polling.*": {"queue": "default"},
        "app.tasks.recovery.*": {"queue": "critical"},
        "app.tasks.cleanup.*": {"queue": "default"},
        "app.tasks.health.*": {"queue": "default"},
    },
    beat_schedule={
        "poll-all-chrs": {
            "task": "app.tasks.polling.poll_all_chrs",
            "schedule": float(settings.poll_interval_sec),
        },
        "check-blackhole-expiry": {
            "task": "app.tasks.recovery.check_blackhole_expiry",
            "schedule": 30.0,
        },
        "health-check-chrs": {
            "task": "app.tasks.health.health_check_chrs",
            "schedule": 60.0,
        },
        "cleanup-old-data": {
            "task": "app.tasks.cleanup.cleanup_old_data",
            "schedule": crontab(hour=3, minute=0),
        },
        "ensure-traffic-partitions": {
            "task": "app.tasks.cleanup.ensure_partitions",
            "schedule": crontab(hour=0, minute=5),
        },
    },
)
