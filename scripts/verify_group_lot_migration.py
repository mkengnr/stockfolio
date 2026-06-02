#!/usr/bin/env python3
"""Report group/lot migration health without modifying the database."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
DETAIL_LIMIT = 20


def _load_app_database() -> tuple[Any, Any, Any]:
    """Load the app database objects with backend/.env as the active env file."""
    sys.path.insert(0, str(BACKEND_DIR))
    original_cwd = Path.cwd()
    os.chdir(BACKEND_DIR)
    try:
        from app.database import AsyncSessionLocal, engine
        from sqlalchemy import text
    finally:
        os.chdir(original_cwd)
    return AsyncSessionLocal, engine, text


async def _count(session: Any, text: Any, table_name: str) -> int:
    result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return int(result.scalar_one())


async def _rows(session: Any, text: Any, statement: str) -> list[dict[str, Any]]:
    result = await session.execute(text(statement))
    return [dict(row) for row in result.mappings().all()]


def _print_count_line(label: str, counts: tuple[int, ...]) -> None:
    print(f"  {label}: {' / '.join(str(count) for count in counts)}")


def _print_mismatches(label: str, rows: list[dict[str, Any]]) -> None:
    print(f"  {label}: {len(rows)}")
    for row in rows[:DETAIL_LIMIT]:
        print(f"    - {row['relation']}: {row['relation_id']} ({row['detail']})")
    if len(rows) > DETAIL_LIMIT:
        print(f"    - ... {len(rows) - DETAIL_LIMIT} more")


async def _collect_cross_owner_mismatches(session: Any, text: Any) -> list[dict[str, Any]]:
    return await _rows(
        session,
        text,
        """
        SELECT
            'legacy holding_tags' AS relation,
            holding_tags.holding_id::text || ' / ' || holding_tags.tag_id::text AS relation_id,
            format('holding owner=%s, tag owner=%s', holdings.user_id, tags.user_id) AS detail
        FROM holding_tags
        JOIN holdings ON holdings.id = holding_tags.holding_id
        JOIN tags ON tags.id = holding_tags.tag_id
        WHERE holdings.user_id <> tags.user_id

        UNION ALL

        SELECT
            'holding -> transaction',
            transactions.id::text,
            format('holding owner=%s, transaction owner=%s', holdings.user_id, transactions.user_id)
        FROM transactions
        JOIN holdings ON holdings.id = transactions.holding_id
        WHERE holdings.user_id <> transactions.user_id

        UNION ALL

        SELECT
            'transaction -> source group',
            transactions.id::text,
            format('transaction owner=%s, source group owner=%s', transactions.user_id, source_groups.user_id)
        FROM transactions
        JOIN source_groups ON source_groups.id = transactions.source_group_id
        WHERE transactions.user_id <> source_groups.user_id

        UNION ALL

        SELECT
            'rollup -> source group',
            rollup_group_members.rollup_group_id::text || ' / ' || rollup_group_members.source_group_id::text,
            format('rollup owner=%s, source group owner=%s', rollup_groups.user_id, source_groups.user_id)
        FROM rollup_group_members
        JOIN rollup_groups ON rollup_groups.id = rollup_group_members.rollup_group_id
        JOIN source_groups ON source_groups.id = rollup_group_members.source_group_id
        WHERE rollup_groups.user_id <> source_groups.user_id

        UNION ALL

        SELECT
            'transaction -> label',
            transaction_labels.transaction_id::text || ' / ' || transaction_labels.label_id::text,
            format('transaction owner=%s, label owner=%s', transactions.user_id, labels.user_id)
        FROM transaction_labels
        JOIN transactions ON transactions.id = transaction_labels.transaction_id
        JOIN labels ON labels.id = transaction_labels.label_id
        WHERE transactions.user_id <> labels.user_id

        UNION ALL

        SELECT
            'buy lot -> holding',
            buy_lots.id::text,
            format('buy lot owner=%s, holding owner=%s', buy_lots.user_id, holdings.user_id)
        FROM buy_lots
        JOIN holdings ON holdings.id = buy_lots.holding_id
        WHERE buy_lots.user_id <> holdings.user_id

        UNION ALL

        SELECT
            'buy lot -> transaction',
            buy_lots.id::text,
            format('buy lot owner=%s, transaction owner=%s', buy_lots.user_id, transactions.user_id)
        FROM buy_lots
        JOIN transactions ON transactions.id = buy_lots.transaction_id
        WHERE buy_lots.user_id <> transactions.user_id

        UNION ALL

        SELECT
            'buy lot -> source group',
            buy_lots.id::text,
            format('buy lot owner=%s, source group owner=%s', buy_lots.user_id, source_groups.user_id)
        FROM buy_lots
        JOIN source_groups ON source_groups.id = buy_lots.source_group_id
        WHERE buy_lots.user_id <> source_groups.user_id

        UNION ALL

        SELECT
            'sell allocation -> buy lot',
            sell_lot_allocations.id::text,
            format('sell transaction owner=%s, buy lot owner=%s', transactions.user_id, buy_lots.user_id)
        FROM sell_lot_allocations
        JOIN transactions ON transactions.id = sell_lot_allocations.sell_transaction_id
        JOIN buy_lots ON buy_lots.id = sell_lot_allocations.buy_lot_id
        WHERE transactions.user_id <> buy_lots.user_id

        ORDER BY relation, relation_id
        """,
    )


async def _collect_remaining_quantity_mismatches(session: Any, text: Any) -> list[dict[str, Any]]:
    return await _rows(
        session,
        text,
        """
        SELECT
            'buy lot remaining quantity' AS relation,
            buy_lots.id::text AS relation_id,
            format(
                'stored=%s, expected=%s, original=%s, allocated=%s',
                buy_lots.remaining_quantity,
                buy_lots.original_quantity - COALESCE(SUM(sell_lot_allocations.quantity), 0),
                buy_lots.original_quantity,
                COALESCE(SUM(sell_lot_allocations.quantity), 0)
            ) AS detail
        FROM buy_lots
        LEFT JOIN sell_lot_allocations ON sell_lot_allocations.buy_lot_id = buy_lots.id
        GROUP BY buy_lots.id
        HAVING buy_lots.remaining_quantity
            <> buy_lots.original_quantity - COALESCE(SUM(sell_lot_allocations.quantity), 0)
        ORDER BY buy_lots.id
        """,
    )


async def run_verification() -> int:
    AsyncSessionLocal, engine, text = _load_app_database()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))

            users = await _count(session, text, "users")
            holdings = await _count(session, text, "holdings")
            transactions = await _count(session, text, "transactions")
            holding_tags = await _count(session, text, "holding_tags")
            source_groups = await _count(session, text, "source_groups")
            rollups = await _count(session, text, "rollup_groups")
            labels = await _count(session, text, "labels")
            buy_lots = await _count(session, text, "buy_lots")
            sell_allocations = await _count(session, text, "sell_lot_allocations")

            unclassified_lots_result = await session.execute(
                text("SELECT COUNT(*) FROM buy_lots WHERE source_group_id IS NULL")
            )
            unclassified_lots = int(unclassified_lots_result.scalar_one())
            review_transactions_result = await session.execute(
                text("SELECT COUNT(*) FROM transactions WHERE requires_review")
            )
            review_transactions = int(review_transactions_result.scalar_one())

            cross_owner_mismatches = await _collect_cross_owner_mismatches(session, text)
            remaining_quantity_mismatches = await _collect_remaining_quantity_mismatches(session, text)
    finally:
        await engine.dispose()

    print("Stockfolio group/lot migration verification")
    print()
    print("Inventory")
    _print_count_line("users / holdings / transactions", (users, holdings, transactions))
    _print_count_line("legacy holding_tags", (holding_tags,))
    _print_count_line("source groups / rollups / labels", (source_groups, rollups, labels))
    _print_count_line("buy lots / sell allocations", (buy_lots, sell_allocations))
    print()
    print("Operational queues (normal, review as needed)")
    _print_count_line("unclassified lots", (unclassified_lots,))
    _print_count_line("requires_review transactions", (review_transactions,))
    print()
    print("Integrity checks")
    _print_mismatches("cross-owner relation mismatches", cross_owner_mismatches)
    _print_mismatches("buy-lot remaining quantity mismatches", remaining_quantity_mismatches)
    print()

    mismatch_count = len(cross_owner_mismatches) + len(remaining_quantity_mismatches)
    if mismatch_count:
        print(f"FAIL: {mismatch_count} integrity mismatch(es) found.")
        return 1

    print("PASS: no integrity mismatches found.")
    return 0


def main() -> int:
    try:
        return asyncio.run(run_verification())
    except Exception as exc:
        print(f"ERROR: verification could not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
