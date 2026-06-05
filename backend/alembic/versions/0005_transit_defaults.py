"""set transit resource defaults

Revision ID: 0005_transit_defaults
Revises: 0004_create_transit_resources
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_transit_defaults"
down_revision = "0004_create_transit_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "transit_resources",
        "protocol_hint",
        existing_type=sa.String(length=24),
        server_default="unknown",
        existing_nullable=False,
    )
    op.alter_column(
        "transit_resources",
        "has_ssh",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.alter_column(
        "transit_resources",
        "status",
        existing_type=sa.String(length=24),
        server_default="active",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "transit_resources",
        "status",
        existing_type=sa.String(length=24),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "transit_resources",
        "has_ssh",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "transit_resources",
        "protocol_hint",
        existing_type=sa.String(length=24),
        server_default=None,
        existing_nullable=False,
    )
