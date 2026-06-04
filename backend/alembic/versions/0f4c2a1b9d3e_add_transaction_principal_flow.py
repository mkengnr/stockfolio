"""add transaction principal flow

Revision ID: 0f4c2a1b9d3e
Revises: 8b0f6baf8b2a
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0f4c2a1b9d3e"
down_revision: Union[str, None] = "8b0f6baf8b2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


principal_flow_enum = sa.Enum("DEPOSIT", "REINVEST", "WITHDRAW", name="principalflow")


def upgrade() -> None:
    principal_flow_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "transactions",
        sa.Column(
            "principal_flow",
            principal_flow_enum,
            nullable=False,
            server_default="REINVEST",
        ),
    )


def downgrade() -> None:
    op.drop_column("transactions", "principal_flow")
    principal_flow_enum.drop(op.get_bind(), checkfirst=True)
