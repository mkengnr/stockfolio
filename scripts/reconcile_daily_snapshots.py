"""Daily-snapshot reconciliation CLI.

Usage (dry-run, default — prints plan, no DB change):
    python scripts/reconcile_daily_snapshots.py [--since DAYS]

Usage (apply — writes to DB):
    python scripts/reconcile_daily_snapshots.py --apply [--since DAYS]

For each active holding this script:
  1. Fetches provider OHLC bars for the window
     (first_buy_date → safe_query_end, or --since N days)
  2. Classifies existing snapshot rows vs provider dates (delete/add/keep)
  3. [dry-run] Prints the plan
  4. [--apply] Rebuilds snapshots using rebuild_holding_snapshots (ledger-based)
     and deletes rows whose dates are absent from the provider window.

Only classify_snapshot_rows is unit-tested (pure function, no DB/network).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timezone, timedelta

logger = logging.getLogger("reconcile_daily_snapshots")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


# ---------------------------------------------------------------------------
# Pure classifier — unit-tested
# ---------------------------------------------------------------------------

def classify_snapshot_rows(
    existing_dates: set[date],
    provider_bar_dates: set[date],
) -> dict[str, list[date]]:
    """Classify snapshot rows vs provider trading-day dates.

    Returns:
        delete: dates in DB but not in provider (e.g. holidays mis-stored)
        add:    dates in provider but missing from DB (gaps)
        keep:   dates in both
    All lists are sorted ascending.
    """
    existing = set(existing_dates)
    provider = set(provider_bar_dates)
    return {
        "delete": sorted(existing - provider),
        "add": sorted(provider - existing),
        "keep": sorted(existing & provider),
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
    try:
        from sqlalchemy import select, delete as sa_delete
        from sqlalchemy.orm import selectinload

        from app.database import AsyncSessionLocal
        from app.models.holding import Holding
        from app.models.snapshot import DailySnapshot
        from app.services import stock_fetcher
        from app.services.market_session import safe_query_end
        from app.services.snapshot_service import rebuild_holding_snapshots
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
            provider_dates: set[date] = {bar.date for bar in bars}

            # Load existing snapshot dates for this window
            async with AsyncSessionLocal() as db:
                snap_result = await db.execute(
                    select(DailySnapshot.snapshot_date)
                    .where(DailySnapshot.holding_id == holding.id)
                    .where(DailySnapshot.snapshot_date >= start_date)
                    .where(DailySnapshot.snapshot_date <= end_date)
                )
                existing_dates: set[date] = set(snap_result.scalars().all())

            plan = classify_snapshot_rows(existing_dates, provider_dates)
            n_add = len(plan["add"])
            n_del = len(plan["delete"])
            n_keep = len(plan["keep"])

            total_add += n_add
            total_delete += n_del
            total_keep += n_keep

            print(
                f"  [{ticker}] market={holding.market.value}  "
                f"window={start_date}→{end_date}  "
                f"keep={n_keep}  add={n_add}  delete={n_del}"
            )
            if plan["add"]:
                print(f"    ADD   : {plan['add'][:10]}{'…' if n_add > 10 else ''}")
            if plan["delete"]:
                print(f"    DELETE: {plan['delete'][:10]}{'…' if n_del > 10 else ''}")

            if not dry_run and (n_add > 0 or n_del > 0):
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
        f"\nSummary: total keep={total_keep}  add={total_add}  delete={total_delete}  "
        f"[{mode_label}]"
    )
    if dry_run and (total_add > 0 or total_delete > 0):
        print("Re-run with --apply to write changes to DB.")


if __name__ == "__main__":
    asyncio.run(main())
