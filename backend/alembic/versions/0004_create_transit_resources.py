"""create transit resources

Revision ID: 0004_create_transit_resources
Revises: 0003_add_node_share_link
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_create_transit_resources"
down_revision = "0003_add_node_share_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transit_resources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("entry_host", sa.String(length=255), nullable=True),
        sa.Column("entry_port", sa.Integer(), nullable=True),
        sa.Column("entry_region", sa.String(length=120), nullable=True),
        sa.Column("exit_region", sa.String(length=120), nullable=True),
        sa.Column("bandwidth_mbps", sa.Integer(), nullable=True),
        sa.Column("traffic_limit_gb", sa.Numeric(12, 2), nullable=True),
        sa.Column("traffic_used_gb", sa.Numeric(12, 2), nullable=True),
        sa.Column("protocol_hint", sa.String(length=24), nullable=False),
        sa.Column("has_ssh", sa.Boolean(), nullable=False),
        sa.Column("ssh_host", sa.String(length=255), nullable=True),
        sa.Column("ssh_port", sa.Integer(), nullable=True),
        sa.Column("ssh_username", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transit_resources_resource_type", "transit_resources", ["resource_type"])
    op.create_index("ix_transit_resources_status", "transit_resources", ["status"])
    op.create_index("ix_transit_resources_deleted_at", "transit_resources", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_transit_resources_deleted_at", table_name="transit_resources")
    op.drop_index("ix_transit_resources_status", table_name="transit_resources")
    op.drop_index("ix_transit_resources_resource_type", table_name="transit_resources")
    op.drop_table("transit_resources")
