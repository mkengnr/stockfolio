"""repair unambiguous sell allocations

Revision ID: e7a41c5d2f10
Revises: 0f4c2a1b9d3e
Create Date: 2026-06-10 00:00:00.000000

The group-lot expand migration flagged every legacy SELL as requires_review
because lot allocations could not be inferred in general. For the strictly
unambiguous subset there is exactly one possible allocation, so this data
repair resolves it automatically and leaves everything else flagged:

- the holding has exactly ONE buy lot,
- the holding has exactly ONE reviewed sell without allocations
  (avoids order-dependent math across multiple sells),
- the lot's remaining quantity covers the sell quantity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7a41c5d2f10'
down_revision: Union[str, None] = '0f4c2a1b9d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def repair_unambiguous_sell_allocations(connection) -> int:
    """Allocate single-lot reviewed sells; return how many were repaired."""
    candidates = connection.execute(
        sa.text(
            """
            SELECT sells.id AS sell_id, sells.quantity AS quantity, lots.id AS lot_id
            FROM transactions AS sells
            JOIN buy_lots AS lots ON lots.holding_id = sells.holding_id
            WHERE sells.type = 'SELL'
              AND sells.requires_review = true
              AND NOT EXISTS (
                  SELECT 1 FROM sell_lot_allocations AS allocations
                  WHERE allocations.sell_transaction_id = sells.id
              )
              AND lots.remaining_quantity >= sells.quantity
              AND (
                  SELECT COUNT(*) FROM buy_lots AS holding_lots
                  WHERE holding_lots.holding_id = sells.holding_id
              ) = 1
              AND (
                  SELECT COUNT(*) FROM transactions AS sibling_sells
                  WHERE sibling_sells.holding_id = sells.holding_id
                    AND sibling_sells.type = 'SELL'
                    AND sibling_sells.requires_review = true
              ) = 1
            """
        )
    ).all()

    for candidate in candidates:
        connection.execute(
            sa.text(
                """
                INSERT INTO sell_lot_allocations (
                    id, sell_transaction_id, buy_lot_id, quantity, created_at
                )
                VALUES (gen_random_uuid(), :sell_id, :lot_id, :quantity, now())
                """
            ),
            {
                "sell_id": candidate.sell_id,
                "lot_id": candidate.lot_id,
                "quantity": candidate.quantity,
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE buy_lots
                SET remaining_quantity = remaining_quantity - :quantity,
                    updated_at = now()
                WHERE id = :lot_id
                """
            ),
            {"lot_id": candidate.lot_id, "quantity": candidate.quantity},
        )
        connection.execute(
            sa.text("UPDATE transactions SET requires_review = false WHERE id = :sell_id"),
            {"sell_id": candidate.sell_id},
        )
    return len(candidates)


def upgrade() -> None:
    repair_unambiguous_sell_allocations(op.get_bind())


def downgrade() -> None:
    # Pure data repair: the created allocations are indistinguishable from
    # user-entered ones afterwards, so this is deliberately irreversible.
    pass
