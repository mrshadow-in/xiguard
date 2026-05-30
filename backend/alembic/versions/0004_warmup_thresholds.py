"""add warmup + min-baseline + min-spike thresholds, SAMPLING state

Revision ID: 0004_warmup_thresholds
Revises: 0003_ip_whitelist
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_warmup_thresholds"
down_revision: Union[str, None] = "0003_ip_whitelist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ip_pools",
        sa.Column(
            "warmup_samples",
            sa.Integer,
            nullable=False,
            server_default=sa.text("120"),
        ),
    )
    op.add_column(
        "ip_pools",
        sa.Column(
            "min_baseline_bps",
            sa.BigInteger,
            nullable=False,
            server_default=sa.text("1000000"),
        ),
    )
    op.add_column(
        "ip_pools",
        sa.Column(
            "min_spike_bps",
            sa.BigInteger,
            nullable=False,
            server_default=sa.text("10000000"),
        ),
    )

    # Existing NORMAL IPs with too few samples should be re-armed: send
    # them back to SAMPLING so they finish the warmup window before the
    # detector can fire on them.
    op.execute(
        """
        UPDATE monitored_ips
           SET state = 'SAMPLING'
         WHERE state = 'NORMAL'
           AND sample_count < 120
        """
    )

    # New rows default to SAMPLING.
    op.alter_column(
        "monitored_ips",
        "state",
        server_default=sa.text("'SAMPLING'"),
    )


def downgrade() -> None:
    op.alter_column(
        "monitored_ips",
        "state",
        server_default=sa.text("'NORMAL'"),
    )
    op.execute("UPDATE monitored_ips SET state = 'NORMAL' WHERE state = 'SAMPLING'")
    op.drop_column("ip_pools", "min_spike_bps")
    op.drop_column("ip_pools", "min_baseline_bps")
    op.drop_column("ip_pools", "warmup_samples")
