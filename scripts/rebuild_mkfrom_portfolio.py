"""Rebuild mkfrom@gmail.com portfolio data from the June 2026 import table."""
import asyncio
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.group import BuyLot, Label, RollupGroup, RollupGroupMember, SellLotAllocation, SourceGroup
from app.models.holding import Currency, Holding, Market, PrincipalFlow, Transaction, TransactionType
from app.models.user import User
from app.services.snapshot_service import backfill_holding_snapshots


USER_EMAIL = "mkfrom@gmail.com"

STOCKS = {
    "SK하이닉스": ("000660", "SK하이닉스"),
    "TIGER 200": ("102110", "TIGER 200"),
    "삼성전자": ("005930", "삼성전자"),
    "한미반도체": ("042700", "한미반도체"),
    "HD현대중공업": ("329180", "HD현대중공업"),
    "HD한국조선해양": ("009540", "HD한국조선해양"),
    "TIGER 코스닥150": ("232080", "TIGER 코스닥150"),
    "미래에셋벤처투자": ("100790", "미래에셋벤처투자"),
    "브이엠": ("089970", "브이엠"),
    "TIGER 삼성전자단일종목레버리지": ("0195R0", "TIGER 삼성전자단일종목레버리지"),
    "TIGER SK하이닉스단일종목레버리지": ("0195S0", "TIGER SK하이닉스단일종목레버리지"),
}

ROWS = [
    ("모음통장", "BUY", "2025-10-30", "SK하이닉스", "17", "556000", "DEPOSIT"),
    ("모음통장", "BUY", "2025-10-30", "TIGER 200", "93", "58120", "DEPOSIT"),
    ("모음통장", "SELL", "2025-12-16", "SK하이닉스", "10", "537000", "WITHDRAW"),
    ("모음통장", "BUY", "2026-03-24", "삼성전자", "31", "187900", "DEPOSIT"),
    ("긴급통장", "BUY", "2026-05-13", "SK하이닉스", "10", "1887000", "DEPOSIT"),
    ("긴급통장", "BUY", "2026-05-13", "한미반도체", "3", "392000", "DEPOSIT"),
    ("긴급통장", "BUY", "2026-05-26", "HD현대중공업", "11", "720000", "DEPOSIT"),
    ("긴급통장", "BUY", "2026-05-26", "HD한국조선해양", "22", "440500", "DEPOSIT"),
    ("긴급통장", "BUY", "2026-05-26", "TIGER 코스닥150", "18", "20570", "DEPOSIT"),
    ("긴급통장", "SELL", "2026-05-26", "한미반도체", "3", "325500", "REINVEST"),
    ("긴급통장", "BUY", "2026-05-27", "미래에셋벤처투자", "7", "57400", "REINVEST"),
    ("긴급통장", "BUY", "2026-05-27", "브이엠", "6", "65800", "REINVEST"),
    ("긴급통장", "SELL", "2026-06-02", "HD현대중공업", "11", "657000", "REINVEST"),
    ("긴급통장", "SELL", "2026-06-02", "HD한국조선해양", "22", "388000", "REINVEST"),
    ("긴급통장", "BUY", "2026-06-02", "SK하이닉스", "3", "2340000", "REINVEST"),
    ("긴급통장", "BUY", "2026-06-02", "삼성전자", "24", "357000", "REINVEST"),
    ("긴급통장", "BUY", "2026-06-02", "TIGER 삼성전자단일종목레버리지", "3", "28200", "REINVEST"),
    ("긴급통장", "BUY", "2026-06-02", "TIGER SK하이닉스단일종목레버리지", "2", "24800", "REINVEST"),
]


def _created_at(tx_date: date, index: int) -> datetime:
    return datetime.combine(tx_date, time(9, 0), tzinfo=timezone.utc).replace(minute=index)


def _recalculate_holding_after_buy(holding: Holding, quantity: Decimal, price: Decimal) -> None:
    total_cost = holding.quantity * holding.avg_price + quantity * price
    holding.quantity += quantity
    holding.avg_price = total_cost / holding.quantity


def _recalculate_holding_after_sell(holding: Holding, quantity: Decimal) -> None:
    holding.quantity -= quantity
    if holding.quantity == 0:
        holding.avg_price = Decimal(0)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == USER_EMAIL))
        ).scalar_one_or_none()
        if user is None:
            raise RuntimeError(f"User not found: {USER_EMAIL}")

        rollup_ids = select(RollupGroup.id).where(RollupGroup.user_id == user.id)
        await db.execute(delete(RollupGroupMember).where(RollupGroupMember.rollup_group_id.in_(rollup_ids)))
        await db.execute(delete(Holding).where(Holding.user_id == user.id))
        await db.execute(delete(RollupGroup).where(RollupGroup.user_id == user.id))
        await db.execute(delete(Label).where(Label.user_id == user.id))
        await db.execute(delete(SourceGroup).where(SourceGroup.user_id == user.id))
        await db.flush()

        groups = {
            "모음통장": SourceGroup(id=uuid.uuid4(), user_id=user.id, name="모음통장"),
            "긴급통장": SourceGroup(id=uuid.uuid4(), user_id=user.id, name="긴급통장"),
        }
        for group in groups.values():
            db.add(group)
        await db.flush()

        holdings: dict[str, Holding] = {}
        lots_by_ticker_group: dict[tuple[str, str], list[BuyLot]] = {}

        for index, (group_name, tx_type, tx_date_raw, stock_name, quantity_raw, price_raw, flow_raw) in enumerate(ROWS):
            ticker, display_name = STOCKS[stock_name]
            tx_date = date.fromisoformat(tx_date_raw)
            quantity = Decimal(quantity_raw)
            price = Decimal(price_raw)
            group = groups[group_name]

            holding = holdings.get(ticker)
            if holding is None:
                holding = Holding(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    ticker=ticker,
                    market=Market.KRX,
                    name=display_name,
                    quantity=Decimal(0),
                    avg_price=Decimal(0),
                    currency=Currency.KRW,
                    first_buy_date=tx_date,
                    notes=None,
                    is_active=True,
                    transactions=[],
                    buy_lots=[],
                )
                holdings[ticker] = holding
                db.add(holding)
            elif tx_type == "BUY" and holding.first_buy_date > tx_date:
                holding.first_buy_date = tx_date

            tx = Transaction(
                id=uuid.uuid4(),
                holding_id=holding.id,
                user_id=user.id,
                source_group_id=group.id,
                type=TransactionType(tx_type),
                quantity=quantity,
                price=price,
                transaction_date=tx_date,
                principal_flow=PrincipalFlow(flow_raw),
                created_at=_created_at(tx_date, index),
                requires_review=False,
                transaction_labels=[],
                sell_allocations=[],
            )
            holding.transactions.append(tx)
            db.add(tx)

            if tx.type == TransactionType.BUY:
                lot = BuyLot(
                    id=uuid.uuid4(),
                    transaction_id=tx.id,
                    holding_id=holding.id,
                    user_id=user.id,
                    source_group_id=group.id,
                    original_quantity=quantity,
                    remaining_quantity=quantity,
                    unit_price=price,
                )
                tx.buy_lot = lot
                holding.buy_lots.append(lot)
                lots_by_ticker_group.setdefault((ticker, group_name), []).append(lot)
                db.add(lot)
                _recalculate_holding_after_buy(holding, quantity, price)
            else:
                remaining_to_allocate = quantity
                for lot in lots_by_ticker_group.get((ticker, group_name), []):
                    if remaining_to_allocate == 0:
                        break
                    if lot.remaining_quantity <= 0:
                        continue
                    allocation_quantity = min(lot.remaining_quantity, remaining_to_allocate)
                    lot.remaining_quantity -= allocation_quantity
                    remaining_to_allocate -= allocation_quantity
                    allocation = SellLotAllocation(
                        id=uuid.uuid4(),
                        sell_transaction_id=tx.id,
                        buy_lot_id=lot.id,
                        quantity=allocation_quantity,
                    )
                    tx.sell_allocations.append(allocation)
                    db.add(allocation)
                if remaining_to_allocate != 0:
                    raise RuntimeError(f"Insufficient lot quantity for {stock_name} / {group_name}")
                _recalculate_holding_after_sell(holding, quantity)

        await db.flush()
        for holding in holdings.values():
            try:
                await backfill_holding_snapshots(db, holding)
            except Exception as exc:
                print(f"snapshot backfill failed for {holding.ticker}: {exc}")

        await db.commit()
        print(f"Rebuilt {len(holdings)} holdings and {len(ROWS)} transactions for {USER_EMAIL}")


if __name__ == "__main__":
    asyncio.run(main())
