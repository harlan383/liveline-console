"""initial stage 0 schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("admin_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("result", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_admin_id", "audit_logs", ["admin_id"])

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("admin_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token_hash", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["admin_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token_hash"),
    )
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])

    op.create_table(
        "vps_servers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False),
        sa.Column("ssh_username", sa.String(length=80), nullable=False),
        sa.Column("ssh_key_fingerprint", sa.String(length=255), nullable=True),
        sa.Column("os_name", sa.String(length=120), nullable=True),
        sa.Column("os_version", sa.String(length=120), nullable=True),
        sa.Column("xray_installed", sa.Boolean(), nullable=False),
        sa.Column("xray_config_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("ssh_host_key_fingerprint", sa.String(length=255), nullable=True),
        sa.Column("last_known_config_hash", sa.String(length=255), nullable=True),
        sa.Column("last_known_meta_hash", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vps_id", sa.String(length=36), nullable=False),
        sa.Column("node_name", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("protocol", sa.String(length=40), nullable=False),
        sa.Column("transport", sa.String(length=40), nullable=True),
        sa.Column("security", sa.String(length=40), nullable=False),
        sa.Column("flow", sa.String(length=80), nullable=True),
        sa.Column("xray_port", sa.Integer(), nullable=True),
        sa.Column("uuid", sa.String(length=80), nullable=True),
        sa.Column("reality_public_key", sa.Text(), nullable=True),
        sa.Column("reality_short_id", sa.String(length=80), nullable=True),
        sa.Column("sni", sa.String(length=255), nullable=True),
        sa.Column("dest", sa.String(length=255), nullable=True),
        sa.Column("fingerprint", sa.String(length=80), nullable=True),
        sa.Column("service_status", sa.String(length=80), nullable=True),
        sa.Column("connectivity_status", sa.String(length=80), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_remote_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["vps_id"], ["vps_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nodes_vps_id", "nodes", ["vps_id"])
    op.create_index(
        "uq_nodes_one_not_deleted_per_vps",
        "nodes",
        ["vps_id"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vps_id", sa.String(length=36), nullable=True),
        sa.Column("node_id", sa.String(length=36), nullable=True),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("current_step", sa.String(length=120), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vps_id"], ["vps_servers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_node_id", "tasks", ["node_id"])
    op.create_index("ix_tasks_vps_id", "tasks", ["vps_id"])

    op.create_table(
        "task_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("level", sa.String(length=24), nullable=False),
        sa.Column("step", sa.String(length=120), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_logs_task_id", "task_logs", ["task_id"])

    op.create_table(
        "vps_task_locks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vps_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("lock_type", sa.String(length=24), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_token", sa.String(length=160), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vps_id"], ["vps_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vps_task_locks_task_id", "vps_task_locks", ["task_id"])
    op.create_index("ix_vps_task_locks_vps_id", "vps_task_locks", ["vps_id"])


def downgrade() -> None:
    op.drop_index("ix_vps_task_locks_vps_id", table_name="vps_task_locks")
    op.drop_index("ix_vps_task_locks_task_id", table_name="vps_task_locks")
    op.drop_table("vps_task_locks")
    op.drop_index("ix_task_logs_task_id", table_name="task_logs")
    op.drop_table("task_logs")
    op.drop_index("ix_tasks_vps_id", table_name="tasks")
    op.drop_index("ix_tasks_node_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("uq_nodes_one_not_deleted_per_vps", table_name="nodes")
    op.drop_index("ix_nodes_vps_id", table_name="nodes")
    op.drop_table("nodes")
    op.drop_table("vps_servers")
    op.drop_index("ix_admin_sessions_admin_id", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index("ix_audit_logs_admin_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("admin_users")
