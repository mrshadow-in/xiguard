"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "chr_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("api_port", sa.Integer, nullable=False, server_default="8728"),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("password_enc", sa.LargeBinary, nullable=False),
        sa.Column("use_ssl", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.String(1024)),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_table(
        "ip_pools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("chr_node_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chr_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cidr", postgresql.CIDR, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("multiplier", sa.Float, nullable=False, server_default="3.0"),
        sa.Column("eval_window_sec", sa.Integer, nullable=False, server_default="30"),
        sa.Column("auto_blackhole", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("blackhole_duration_sec", sa.Integer, nullable=False, server_default="600"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_ip_pools_chr", "ip_pools", ["chr_node_id"])

    op.create_table(
        "monitored_ips",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ip_pools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ip_address", postgresql.INET, nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="NORMAL"),
        sa.Column("baseline_bps", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("current_bps", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("current_pps", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("sample_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("spike_start", sa.DateTime(timezone=True)),
        sa.Column("last_spike_at", sa.DateTime(timezone=True)),
        sa.Column("blackholed_at", sa.DateTime(timezone=True)),
        sa.Column("recovering_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_monitored_ips_pool", "monitored_ips", ["pool_id"])
    op.execute(
        "CREATE INDEX idx_monitored_ips_state ON monitored_ips(state) "
        "WHERE state != 'NORMAL'"
    )
    op.execute(
        "CREATE INDEX idx_monitored_ips_blackholed ON monitored_ips(blackholed_at) "
        "WHERE state = 'BLACKHOLED'"
    )

    # Partitioned traffic_samples table.
    op.execute(
        """
        CREATE TABLE traffic_samples (
            id BIGSERIAL,
            ip_id UUID NOT NULL REFERENCES monitored_ips(id) ON DELETE CASCADE,
            bps_in BIGINT NOT NULL,
            bps_out BIGINT NOT NULL,
            pps_in BIGINT NOT NULL,
            pps_out BIGINT NOT NULL,
            sampled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, sampled_at)
        ) PARTITION BY RANGE (sampled_at);
        """
    )
    op.execute("CREATE INDEX idx_traffic_ip_time ON traffic_samples (ip_id, sampled_at DESC)")
    # Default catch-all partition; the cleanup task creates daily partitions on a rolling basis.
    op.execute(
        """
        CREATE TABLE traffic_samples_default PARTITION OF traffic_samples DEFAULT;
        """
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ip_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("monitored_ips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("baseline_bps", sa.BigInteger),
        sa.Column("peak_bps", sa.BigInteger),
        sa.Column("action_taken", sa.String(30)),
        sa.Column("hosting_email_sent", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("isp_email_sent", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_alerts_ip", "alerts", ["ip_id", "created_at"])
    op.create_index("idx_alerts_created", "alerts", ["created_at"])

    op.create_table(
        "mail_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("config_type", sa.String(20), nullable=False, unique=True),
        sa.Column("smtp_host", sa.String(255), nullable=False, server_default=""),
        sa.Column("smtp_port", sa.Integer, nullable=False, server_default="587"),
        sa.Column("smtp_user", sa.String(255)),
        sa.Column("smtp_pass_enc", sa.LargeBinary),
        sa.Column("from_address", sa.String(255), nullable=False, server_default=""),
        sa.Column("to_addresses", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("cc_addresses", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("use_tls", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_login", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("details", postgresql.JSONB),
        sa.Column("ip_address", postgresql.INET),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_audit_time", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_time", "audit_log")
    op.drop_table("audit_log")
    op.drop_table("users")
    op.drop_table("mail_configs")
    op.drop_index("idx_alerts_created", "alerts")
    op.drop_index("idx_alerts_ip", "alerts")
    op.drop_table("alerts")
    op.execute("DROP TABLE IF EXISTS traffic_samples CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_monitored_ips_blackholed")
    op.execute("DROP INDEX IF EXISTS idx_monitored_ips_state")
    op.drop_index("idx_monitored_ips_pool", "monitored_ips")
    op.drop_table("monitored_ips")
    op.drop_index("idx_ip_pools_chr", "ip_pools")
    op.drop_table("ip_pools")
    op.drop_table("chr_nodes")
