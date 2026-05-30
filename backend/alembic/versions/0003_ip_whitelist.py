"""add is_whitelisted + whitelist_note to monitored_ips

Revision ID: 0003_ip_whitelist
Revises: 0002_per_pool_unique_ip
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ip_whitelist"
down_revision: Union[str, None] = "0002_per_pool_unique_ip"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitored_ips",
        sa.Column(
            "is_whitelisted",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "monitored_ips",
        sa.Column("whitelist_note", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitored_ips", "whitelist_note")
    op.drop_column("monitored_ips", "is_whitelisted")
