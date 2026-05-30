from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MailConfigBase(BaseModel):
    smtp_host: str
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    from_address: str
    to_addresses: list[str] = []
    cc_addresses: list[str] = []
    use_tls: bool = True
    enabled: bool = True


class MailConfigUpdate(MailConfigBase):
    smtp_password: str | None = None


class MailConfigOut(MailConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    config_type: str
    has_password: bool = False
    updated_at: datetime


class TestEmailResult(BaseModel):
    ok: bool
    error: str | None = None
