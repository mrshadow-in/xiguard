"""IP pool (CIDR block assigned to a CHR node)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import CIDR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.chr_node import CHRNode
    from app.models.monitored_ip import MonitoredIP


class IPPool(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ip_pools"

    chr_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chr_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    cidr: Mapped[str] = mapped_column(CIDR, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    eval_window_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    auto_blackhole: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    blackhole_duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=600)

    chr_node: Mapped["CHRNode"] = relationship("CHRNode", back_populates="pools")
    ips: Mapped[list["MonitoredIP"]] = relationship(
        "MonitoredIP", back_populates="pool", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_ip_pools_chr", "chr_node_id"),)
