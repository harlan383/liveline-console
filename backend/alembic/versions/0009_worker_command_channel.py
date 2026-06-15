"""worker command channel foundation

Revision ID: 0009_worker_command_channel
Revises: 0008_worker_foundation
Create Date: 2026-06-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_worker_command_channel"
down_revision = "0008_worker_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_commands",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("worker_id", sa.String(length=36), nullable=False),
        sa.Column("server_type", sa.String(length=16), nullable=True),
        sa.Column("server_id", sa.String(length=36), nullable=True),
        sa.Column("command_type", sa.String(length=40), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_commands_worker_id", "worker_commands", ["worker_id"])
    op.create_index("ix_worker_commands_server_type", "worker_commands", ["server_type"])
    op.create_index("ix_worker_commands_server_id", "worker_commands", ["server_id"])
    op.create_index("ix_worker_commands_command_type", "worker_commands", ["command_type"])
    op.create_index("ix_worker_commands_status", "worker_commands", ["status"])
    op.create_index("ix_worker_commands_lease_until", "worker_commands", ["lease_until"])
    op.create_index("ix_worker_commands_completed_at", "worker_commands", ["completed_at"])
    op.create_index("ix_worker_commands_created_at", "worker_commands", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_commands_created_at", table_name="worker_commands")
    op.drop_index("ix_worker_commands_completed_at", table_name="worker_commands")
    op.drop_index("ix_worker_commands_lease_until", table_name="worker_commands")
    op.drop_index("ix_worker_commands_status", table_name="worker_commands")
    op.drop_index("ix_worker_commands_command_type", table_name="worker_commands")
    op.drop_index("ix_worker_commands_server_id", table_name="worker_commands")
    op.drop_index("ix_worker_commands_server_type", table_name="worker_commands")
    op.drop_index("ix_worker_commands_worker_id", table_name="worker_commands")
    op.drop_table("worker_commands")
