"""add vps server management fields

Revision ID: 0007_vps_mgmt_fields
Revises: 0006_create_transit_routes
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_vps_mgmt_fields"
down_revision = "0006_create_transit_routes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vps_servers", sa.Column("name", sa.String(length=120), nullable=True))
    op.add_column("vps_servers", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "vps_servers",
        sa.Column("last_ssh_check_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vps_servers",
        sa.Column(
            "last_ssh_status",
            sa.String(length=24),
            nullable=False,
            server_default="unchecked",
        ),
    )
    op.add_column("vps_servers", sa.Column("last_ssh_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("vps_servers", "last_ssh_error")
    op.drop_column("vps_servers", "last_ssh_status")
    op.drop_column("vps_servers", "last_ssh_check_at")
    op.drop_column("vps_servers", "notes")
    op.drop_column("vps_servers", "name")
