"""replace global UNIQUE on monitored_ips.ip_address with per-pool composite

Revision ID: 0002_per_pool_unique_ip
Revises: 0001_initial
Create Date: 2026-05-30

Keep revision IDs ≤32 chars: alembic_version.version_num is VARCHAR(32)
by default. The previous id (0002_monitored_ips_per_pool_unique, 36
chars) raised StringDataRightTruncation on the final
UPDATE alembic_version, and because Postgres rolls back the whole
transaction on failure the DDL never landed.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_per_pool_unique_ip"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("monitored_ips_ip_address_key", "monitored_ips", type_="unique")
    op.create_unique_constraint(
        "uq_monitored_ips_pool_ip",
        "monitored_ips",
        ["pool_id", "ip_address"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_monitored_ips_pool_ip", "monitored_ips", type_="unique")
    op.create_unique_constraint(
        "monitored_ips_ip_address_key",
        "monitored_ips",
        ["ip_address"],
    )
