from __future__ import annotations

from pydantic import BaseModel, Field


class BlackholeRequest(BaseModel):
    ip: str = Field(min_length=7, max_length=45)
    reason: str | None = None


class ActionResult(BaseModel):
    ok: bool
    ip: str
    state: str
    error: str | None = None
