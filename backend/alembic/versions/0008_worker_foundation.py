"""worker token register heartbeat foundation

Revision ID: 0008_worker_foundation
Revises: 0007_vps_mgmt_fields
Create Date: 2026-06-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_worker_foundation"
down_revision = "0007_vps_mgmt_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("server_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_worker_tokens_token_hash", "worker_tokens", ["token_hash"])
    op.create_index("ix_worker_tokens_role", "worker_tokens", ["role"])
    op.create_index("ix_worker_tokens_status", "worker_tokens", ["status"])
    op.create_index("ix_worker_tokens_expires_at", "worker_tokens", ["expires_at"])
    op.create_index("ix_worker_tokens_created_by", "worker_tokens", ["created_by"])
    op.create_index("ix_worker_tokens_server_id", "worker_tokens", ["server_id"])

    op.create_table(
        "workers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("server_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("public_ip", sa.String(length=45), nullable=True),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("interface_name", sa.String(length=80), nullable=True),
        sa.Column("worker_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("worker_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workers_server_id", "workers", ["server_id"])
    op.create_index("ix_workers_role", "workers", ["role"])
    op.create_index("ix_workers_status", "workers", ["status"])
    op.create_index("ix_workers_last_heartbeat_at", "workers", ["last_heartbeat_at"])


def downgrade() -> None:
    op.drop_index("ix_workers_last_heartbeat_at", table_name="workers")
    op.drop_index("ix_workers_status", table_name="workers")
    op.drop_index("ix_workers_role", table_name="workers")
    op.drop_index("ix_workers_server_id", table_name="workers")
    op.drop_table("workers")

    op.drop_index("ix_worker_tokens_server_id", table_name="worker_tokens")
    op.drop_index("ix_worker_tokens_created_by", table_name="worker_tokens")
    op.drop_index("ix_worker_tokens_expires_at", table_name="worker_tokens")
    op.drop_index("ix_worker_tokens_status", table_name="worker_tokens")
    op.drop_index("ix_worker_tokens_role", table_name="worker_tokens")
    op.drop_index("ix_worker_tokens_token_hash", table_name="worker_tokens")
    op.drop_table("worker_tokens")
