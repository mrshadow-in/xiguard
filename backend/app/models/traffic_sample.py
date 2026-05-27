"""Time-series traffic samples (partitioned by day)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrafficSample(Base):
    __tablename__ = "traffic_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitored_ips.id", ondelete="CASCADE"),
        nullable=False,
    )
    bps_in: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bps_out: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pps_in: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pps_out: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_traffic_ip_time", "ip_id", "sampled_at"),
        {"postgresql_partition_by": "RANGE (sampled_at)"},
    )
