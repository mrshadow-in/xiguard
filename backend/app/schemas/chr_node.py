from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CHRNodeBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    api_port: int = Field(default=8728, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    use_ssl: bool = False
    description: str | None = None


class CHRNodeCreate(CHRNodeBase):
    password: str = Field(min_length=1)


class CHRNodeUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    api_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_ssl: bool | None = None
    description: str | None = None


class CHRNodeOut(CHRNodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    last_seen_at: datetime | None = None
    created_at: datetime
    pool_count: int = 0
    monitored_ip_count: int = 0


class CHRNodeTestResult(BaseModel):
    ok: bool
    routeros_version: str | None = None
    uptime: str | None = None
    error: str | None = None
