"""create transit routes

Revision ID: 0006_create_transit_routes
Revises: 0005_transit_defaults
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_create_transit_routes"
down_revision = "0005_transit_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transit_routes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("transit_resource_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("landing_vps_id", sa.String(length=36), nullable=True),
        sa.Column("listen_port", sa.Integer(), nullable=False),
        sa.Column("target_host", sa.String(length=255), nullable=False),
        sa.Column("target_port", sa.Integer(), nullable=False),
        sa.Column("forwarding_method", sa.String(length=40), nullable=False),
        sa.Column("service_name", sa.String(length=160), nullable=False),
        sa.Column("service_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("share_link", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["landing_vps_id"], ["vps_servers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["transit_resource_id"],
            ["transit_resources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transit_routes_transit_resource_id", "transit_routes", ["transit_resource_id"])
    op.create_index("ix_transit_routes_node_id", "transit_routes", ["node_id"])
    op.create_index("ix_transit_routes_landing_vps_id", "transit_routes", ["landing_vps_id"])
    op.create_index("ix_transit_routes_status", "transit_routes", ["status"])
    op.create_index("ix_transit_routes_deleted_at", "transit_routes", ["deleted_at"])
    op.create_index(
        "ix_transit_routes_resource_port_active",
        "transit_routes",
        ["transit_resource_id", "listen_port", "status", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_transit_routes_resource_port_active", table_name="transit_routes")
    op.drop_index("ix_transit_routes_deleted_at", table_name="transit_routes")
    op.drop_index("ix_transit_routes_status", table_name="transit_routes")
    op.drop_index("ix_transit_routes_landing_vps_id", table_name="transit_routes")
    op.drop_index("ix_transit_routes_node_id", table_name="transit_routes")
    op.drop_index("ix_transit_routes_transit_resource_id", table_name="transit_routes")
    op.drop_table("transit_routes")
