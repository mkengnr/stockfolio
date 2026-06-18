"""add share description fields

Revision ID: 37d9fb2c4c1a
Revises: e7a41c5d2f10
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "37d9fb2c4c1a"
down_revision: Union[str, None] = "e7a41c5d2f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("source_groups", "rollup_groups", "labels", "tags"):
        op.add_column(table_name, sa.Column("share_description", sa.Text(), nullable=True))


def downgrade() -> None:
    for table_name in ("tags", "labels", "rollup_groups", "source_groups"):
        op.drop_column(table_name, "share_description")
