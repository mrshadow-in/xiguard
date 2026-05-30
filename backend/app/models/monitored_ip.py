"""Per-IP monitored endpoint, traffic state, and state machine."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._mixins import UUIDPKMixin

if TYPE_CHECKING:
    from app.models.ip_pool import IPPool


IP_STATES = ("NORMAL", "ALERT", "BLACKHOLED", "RECOVERING")


class MonitoredIP(UUIDPKMixin, Base):
    __tablename__ = "monitored_ips"

    pool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ip_pools.id", ondelete="CASCADE"),
        nullable=False,
    )
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="NORMAL")
    baseline_bps: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_bps: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_pps: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sample_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    spike_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_spike_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blackholed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovering_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_whitelisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    whitelist_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    pool: Mapped["IPPool"] = relationship("IPPool", back_populates="ips")

    __table_args__ = (
        Index("idx_monitored_ips_pool", "pool_id"),
        Index(
            "idx_monitored_ips_state",
            "state",
            postgresql_where=text("state != 'NORMAL'"),
        ),
        Index(
            "idx_monitored_ips_blackholed",
            "blackholed_at",
            postgresql_where=text("state = 'BLACKHOLED'"),
        ),
        UniqueConstraint("pool_id", "ip_address", name="uq_monitored_ips_pool_ip"),
    )
