"""Daily-snapshot reconciliation CLI.

Usage (dry-run, default — prints plan, no DB change):
    python scripts/reconcile_daily_snapshots.py [--since DAYS]

Usage (apply — writes to DB):
    python scripts/reconcile_daily_snapshots.py --apply [--since DAYS]

For each active holding this script:
  1. Fetches provider OHLC bars for the window
     (first_buy_date → safe_query_end, or --since N days)
  2. Classifies existing rows vs provider-derived values (delete/add/update/keep)
  3. [dry-run] Prints the plan
  4. [--apply] Rebuilds snapshots using rebuild_holding_snapshots (ledger-based)
     and deletes rows whose dates are absent from the provider window.

Only classify_snapshot_rows is unit-tested (pure function, no DB/network).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Mapping

logger = logging.getLogger("reconcile_daily_snapshots")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
DB_NUMERIC_QUANTUM = Decimal("0.000001")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Pure classifier — unit-tested
# ---------------------------------------------------------------------------

def classify_snapshot_rows(
    existing_rows: Mapping[date, tuple[Decimal, Decimal]],
    provider_rows: Mapping[date, tuple[Decimal, Decimal]],
) -> dict[str, list[date]]:
    """Classify stored rows against provider-derived close/value rows.

    Returns:
        delete: dates in DB but not in provider (e.g. holidays mis-stored)
        add:    dates in provider but missing from DB (gaps)
        update: dates present in both whose close or ledger value differs
        keep:   dates present in both with identical close and value
    All lists are sorted ascending.
    """
    existing = set(existing_rows)
    provider = set(provider_rows)
    shared = existing & provider
    def db_row(row: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
        return (
            row[0].quantize(DB_NUMERIC_QUANTUM, rounding=ROUND_HALF_UP),
            row[1].quantize(DB_NUMERIC_QUANTUM, rounding=ROUND_HALF_UP),
        )

    update = sorted(
        snapshot_date
        for snapshot_date in shared
        if db_row(existing_rows[snapshot_date]) != db_row(provider_rows[snapshot_date])
    )
    return {
        "delete": sorted(existing - provider),
        "add": sorted(provider - existing),
        "update": update,
        "keep": sorted(shared - set(update)),
    }


# ---------------------------------------------------------------------------
# Async main — DB + network; NOT unit-tested
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile daily_snapshots vs price provider (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to DB (default: dry-run, print plan only).",
    )
    parser.add_argument(
        "--since",
        type=int,
        default=None,
        metavar="DAYS",
        help="Restrict window to the last N days instead of full history.",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    mode_label = "DRY-RUN" if dry_run else "APPLY"
    print(f"\n=== reconcile_daily_snapshots [{mode_label}] ===\n")

    # Import DB / service modules here so the pure classifier can be imported
    # without setting up the full app environment.
    os.chdir(BACKEND_DIR)
    try:
        from sqlalchemy import select, delete as sa_delete
        from sqlalchemy.orm import selectinload

        from app.database import AsyncSessionLocal
        from app.models.holding import Holding
        from app.models.snapshot import DailySnapshot
        from app.services import stock_fetcher
        from app.services.market_session import safe_query_end
        from app.services.snapshot_service import _build_snapshot_values, rebuild_holding_snapshots
    except ImportError as exc:
        logger.error(
            "Could not import app modules. Run from the repo root with the "
            "backend venv active (e.g. backend/.venv/bin/python scripts/reconcile_daily_snapshots.py).\n"
            "Import error: %s",
            exc,
        )
        sys.exit(1)

    now: datetime = datetime.now(tz=timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Holding)
            .where(Holding.is_active == True)  # noqa: E712
            .options(selectinload(Holding.transactions))
        )
        holdings = list(result.scalars().all())

    if not holdings:
        print("No active holdings found.")
        return

    print(f"Found {len(holdings)} active holding(s).\n")

    total_add = 0
    total_update = 0
    total_delete = 0
    total_keep = 0

    for holding in holdings:
        ticker = holding.ticker
        try:
            # Determine window
            end_date: date = safe_query_end(holding.market, now)
            if args.since is not None:
                start_date = max(holding.first_buy_date, end_date - timedelta(days=args.since))
            else:
                start_date = holding.first_buy_date

            if start_date > end_date:
                print(f"  [{ticker}] window empty (start={start_date} > end={end_date}), skip.")
                continue

            # Fetch provider bars (network call)
            bars = await asyncio.to_thread(
                stock_fetcher.get_price_history, ticker, start_date, end_date
            )
            expected_values = _build_snapshot_values(holding.transactions, bars)
            provider_rows = {
                value.snapshot_date: (value.close_price, value.total_value)
                for value in expected_values
            }

            # Load every stored row from the requested start onward. Rows later
            # than the provider-safe end are precisely the unconfirmed/future
            # rows this tool must disclose (and remove) during reconciliation.
            async with AsyncSessionLocal() as db:
                snap_result = await db.execute(
                    select(
                        DailySnapshot.snapshot_date,
                        DailySnapshot.close_price,
                        DailySnapshot.total_value,
                    )
                    .where(DailySnapshot.holding_id == holding.id)
                    .where(DailySnapshot.snapshot_date >= start_date)
                )
                existing_rows = {
                    row.snapshot_date: (row.close_price, row.total_value)
                    for row in snap_result.all()
                }

            plan = classify_snapshot_rows(existing_rows, provider_rows)
            n_add = len(plan["add"])
            n_del = len(plan["delete"])
            n_update = len(plan["update"])
            n_keep = len(plan["keep"])

            total_add += n_add
            total_update += n_update
            total_delete += n_del
            total_keep += n_keep

            print(
                f"  [{ticker}] market={holding.market.value}  "
                f"window={start_date}→{end_date}  "
                f"keep={n_keep}  add={n_add}  update={n_update}  delete={n_del}"
            )
            if plan["add"]:
                print(f"    ADD   : {plan['add'][:10]}{'…' if n_add > 10 else ''}")
            if plan["delete"]:
                print(f"    DELETE: {plan['delete'][:10]}{'…' if n_del > 10 else ''}")
            if plan["update"]:
                print(f"    UPDATE: {plan['update'][:10]}{'…' if n_update > 10 else ''}")

            if not dry_run and (n_add > 0 or n_update > 0 or n_del > 0):
                async with AsyncSessionLocal() as db:
                    # Re-load holding with transactions for rebuild
                    h_result = await db.execute(
                        select(Holding)
                        .where(Holding.id == holding.id)
                        .options(selectinload(Holding.transactions))
                    )
                    h = h_result.scalar_one()

                    # 1. Rebuild (ledger-based) covers all add/update within window
                    rebuilt = await rebuild_holding_snapshots(
                        db, h,
                        start=start_date,
                        end=end_date,
                    )

                    # 2. Delete rows whose dates are absent from the provider
                    #    (rebuild only inserts/replaces; orphaned non-provider dates
                    #    may remain if a holiday was previously stored.)
                    if plan["delete"]:
                        await db.execute(
                            sa_delete(DailySnapshot)
                            .where(DailySnapshot.holding_id == h.id)
                            .where(DailySnapshot.snapshot_date.in_(plan["delete"]))
                        )

                    await db.commit()
                print(f"    → applied: rebuilt={rebuilt}  deleted={n_del}")

        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] error during reconcile: %r", ticker, exc)
            continue

    print(
        f"\nSummary: total keep={total_keep}  add={total_add}  "
        f"update={total_update}  delete={total_delete}  "
        f"[{mode_label}]"
    )
    if dry_run and (total_add > 0 or total_update > 0 or total_delete > 0):
        print("Re-run with --apply to write changes to DB.")


if __name__ == "__main__":
    asyncio.run(main())
