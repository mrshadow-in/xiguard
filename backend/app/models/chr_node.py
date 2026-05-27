"""CHR (Cloud Hosted Router) node."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.ip_pool import IPPool


class CHRNode(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "chr_nodes"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    api_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8728)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pools: Mapped[list["IPPool"]] = relationship(
        "IPPool", back_populates="chr_node", cascade="all, delete-orphan"
    )
