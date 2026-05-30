"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(default="postgresql+asyncpg://xiguard:xiguard@localhost:5432/xiguard")
    database_sync_url: str = Field(default="postgresql+psycopg://xiguard:xiguard@localhost:5432/xiguard")

    # Redis / Celery
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")

    # Security
    secret_key: str = Field(default="dev-secret-do-not-use-in-prod")
    encryption_key: str = Field(default="")  # base64-encoded 32-byte key
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="changeme_admin")
    session_ttl_sec: int = Field(default=86400)

    # Detection defaults
    default_multiplier: float = Field(default=3.0)
    default_eval_window_sec: int = Field(default=30)
    default_blackhole_duration_sec: int = Field(default=600)
    default_recovery_observation_sec: int = Field(default=60)
    baseline_ewma_span: int = Field(default=720)
    alert_dedup_window_sec: int = Field(default=300)

    # Polling
    poll_interval_sec: int = Field(default=5)
    poll_timeout_sec: int = Field(default=4)

    # Retention
    traffic_retention_days: int = Field(default=30)
    alert_retention_days: int = Field(default=90)
    audit_retention_days: int = Field(default=365)

    # Organization metadata
    org_name: str = Field(default="Your Organization")
    org_as_number: int = Field(default=0)
    org_noc_email: str = Field(default="noc@example.com")
    org_noc_phone: str = Field(default="")
    org_website: str = Field(default="")

    # FastAPI
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    cors_origins: str = Field(default="http://localhost:3000")
    log_level: str = Field(default="INFO")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
