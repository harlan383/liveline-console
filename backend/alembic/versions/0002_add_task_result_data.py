"""add task result data

Revision ID: 0002_add_task_result_data
Revises: 0001_initial_schema
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_add_task_result_data"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("result_data", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "result_data")
