"""DDoS alert records."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._mixins import UUIDPKMixin

# alert.type values
ALERT_DDOS = "ddos_detected"
ALERT_BLACKHOLE_APPLIED = "blackhole_applied"
ALERT_RECOVERED = "recovered"
ALERT_CHR_OFFLINE = "chr_offline"
ALERT_BLACKHOLE_FAILED = "blackhole_failed"


class Alert(UUIDPKMixin, Base):
    __tablename__ = "alerts"

    ip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitored_ips.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # critical | warning | info
    baseline_bps: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    peak_bps: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hosting_email_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    isp_email_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_alerts_ip", "ip_id", "created_at"),
        Index("idx_alerts_created", "created_at"),
    )
