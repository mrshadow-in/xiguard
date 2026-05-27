"""SMTP mail configuration — one row per NOC group (hosting | isp)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import UUIDPKMixin

MAIL_HOSTING_NOC = "hosting_noc"
MAIL_ISP_NOC = "isp_noc"


class MailConfig(UUIDPKMixin, Base):
    __tablename__ = "mail_configs"

    config_type: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_pass_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    to_addresses: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cc_addresses: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
        nullable=False,
    )
