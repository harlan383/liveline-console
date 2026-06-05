"""add node share link

Revision ID: 0003_add_node_share_link
Revises: 0002_add_task_result_data
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_node_share_link"
down_revision = "0002_add_task_result_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("share_link", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "share_link")
