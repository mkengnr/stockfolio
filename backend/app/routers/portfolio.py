import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.config import get_settings, parse_market_close_overrides
from app.database import get_db
from app.models.group import BuyLot, Label, RollupGroup, RollupGroupMember, SourceGroup
from app.models.holding import (
    Currency,
    Holding,
    Market,
    PrincipalFlow,
    Transaction as OrmTransaction,
    TransactionType,
)
from app.models.tag import HoldingTag, Tag
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.dashboard import (
    DashboardExchangeRate,
    DashboardGroupSummary,
    DashboardHistoryRow,
    DashboardHistorySeries,
    DashboardHoldingGroupBadge,
    DashboardHoldingRow,
    DashboardResponse,
    DashboardSummary,
    DisplayCurrency,
)
from app.schemas.portfolio import (
    PortfolioCurrencySummary,
    PortfolioHistoryOut,
    PortfolioHistoryPoint,
    PortfolioSummaryOut,
    ScopedPortfolioHistoryOut,
    ScopedPortfolioHistoryPoint,
    ScopedPortfolioHoldingOut,
    ScopedPortfolioHoldingsOut,
)
from app.services import lot_accounting
from app.services.exchange_rate import ExchangeRate, convert_money, get_usd_krw_rate
from app.services.lot_accounting import PortfolioScope, ScopeKind
from app.services.market_session import is_write_confirmed
from app.services.price_cache import get_price
from app.services.snapshot_service import backfill_recent_comparison_snapshots

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoricalPosition:
    quantity: Decimal = Decimal(0)
    avg_cost: Decimal = Decimal(0)

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.avg_cost


@dataclass(frozen=True)
class CurrentPriceQuote:
    price: Decimal | None
    price_date: date | None


def _apply_transaction(position: HistoricalPosition, transaction: OrmTransaction) -> HistoricalPosition:
    """Apply one transaction using the moving-average cost method."""
    if transaction.quantity <= 0:
        raise ValueError("Transaction quantity must be positive")

    if transaction.type == TransactionType.BUY:
        quantity = position.quantity + transaction.quantity
        cost_basis = position.cost_basis + (transaction.quantity * transaction.price)
        return HistoricalPosition(quantity=quantity, avg_cost=cost_basis / quantity)

    if transaction.type == TransactionType.SELL:
        if transaction.quantity > position.quantity:
            raise ValueError("Sell quantity exceeds available quantity")
        quantity = position.quantity - transaction.quantity
        avg_cost = Decimal(0) if quantity == 0 else position.avg_cost
        return HistoricalPosition(quantity=quantity, avg_cost=avg_cost)

    raise ValueError(f"Unsupported transaction type: {transaction.type}")


def _transaction_sort_key(transaction: OrmTransaction) -> tuple[date, datetime, str]:
    return (
        transaction.transaction_date,
        getattr(transaction, "created_at", datetime.min),
        str(getattr(transaction, "id", "")),
    )


def _build_portfolio_history(holdings: list[Holding]) -> PortfolioHistoryOut:
    """Aggregate close-price snapshots without mixing currencies."""
    totals: dict[Currency, dict[date, tuple[Decimal, Decimal]]] = {
        currency: {} for currency in Currency
    }

    for holding in holdings:
        transactions = sorted(holding.transactions, key=_transaction_sort_key)
        snapshots = sorted(holding.snapshots, key=lambda snapshot: snapshot.snapshot_date)
        position = HistoricalPosition()
        transaction_index = 0

        for snapshot in snapshots:
            while (
                transaction_index < len(transactions)
                and transactions[transaction_index].transaction_date <= snapshot.snapshot_date
            ):
                position = _apply_transaction(position, transactions[transaction_index])
                transaction_index += 1

            total_value, total_cost_basis = totals[holding.currency].get(
                snapshot.snapshot_date,
                (Decimal(0), Decimal(0)),
            )
            totals[holding.currency][snapshot.snapshot_date] = (
                total_value + (position.quantity * snapshot.close_price),
                total_cost_basis + position.cost_basis,
            )

        # Surface malformed transaction histories even when the invalid sell is
        # later than the most recent snapshot.
        while transaction_index < len(transactions):
            position = _apply_transaction(position, transactions[transaction_index])
            transaction_index += 1

    return PortfolioHistoryOut(
        series={
            currency: [
                PortfolioHistoryPoint(
                    snapshot_date=snapshot_date,
                    total_value=total_value,
                    total_cost_basis=total_cost_basis,
                )
                for snapshot_date, (total_value, total_cost_basis) in sorted(days.items())
            ]
            for currency, days in totals.items()
        }
    )


def _owned_tag_query(tag_id: uuid.UUID, user_id: uuid.UUID) -> Select[tuple[Tag]]:
    return select(Tag).where(Tag.id == tag_id).where(Tag.user_id == user_id)


def _holdings_query(user_id: uuid.UUID, tag_id: uuid.UUID | None) -> Select[tuple[Holding]]:
    query = (
        select(Holding)
        .where(Holding.user_id == user_id)
        .options(
            selectinload(Holding.transactions),
            selectinload(Holding.snapshots),
        )
    )
    if tag_id is not None:
        query = query.join(HoldingTag, HoldingTag.holding_id == Holding.id).where(
            HoldingTag.tag_id == tag_id
        )
    return query


def _scoped_holdings_query(
    user_id: uuid.UUID,
    *,
    include_inactive: bool = False,
) -> Select[tuple[Holding]]:
    query = (
        select(Holding)
        .where(Holding.user_id == user_id)
        .options(
            selectinload(Holding.transactions).selectinload(OrmTransaction.buy_lot),
            selectinload(Holding.transactions).selectinload(OrmTransaction.sell_allocations),
            selectinload(Holding.transactions).selectinload(OrmTransaction.transaction_labels),
            selectinload(Holding.snapshots),
            with_loader_criteria(
                OrmTransaction,
                OrmTransaction.user_id == user_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                BuyLot,
                BuyLot.user_id == user_id,
                include_aliases=True,
            ),
        )
    )
    if not include_inactive:
        query = query.where(Holding.is_active.is_(True))
    return query


async def resolve_portfolio_scope(
    db: AsyncSession,
    user_id: uuid.UUID,
    scope_kind: ScopeKind,
    scope_id: uuid.UUID | None = None,
) -> PortfolioScope:
    if scope_kind in {"all", "unclassified"}:
        if scope_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{scope_kind} scope does not accept scope_id",
            )
        return PortfolioScope(scope_kind)

    if scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{scope_kind} scope requires scope_id",
        )

    model = {
        "source": SourceGroup,
        "rollup": RollupGroup,
        "label": Label,
    }[scope_kind]
    result = await db.execute(
        select(model).where(model.id == scope_id).where(model.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        detail = {
            "source": "Source group not found",
            "rollup": "Rollup group not found",
            "label": "Label not found",
        }[scope_kind]
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    if scope_kind != "rollup":
        return PortfolioScope(scope_kind, scope_id)

    member_result = await db.execute(
        select(RollupGroupMember.source_group_id)
        .join(SourceGroup, SourceGroup.id == RollupGroupMember.source_group_id)
        .where(RollupGroupMember.rollup_group_id == scope_id)
        .where(SourceGroup.user_id == user_id)
    )
    return PortfolioScope(
        "rollup",
        scope_id,
        resolved_source_group_ids=frozenset(member_result.scalars().all()),
    )


def _orm_transactions(holdings: list[Holding]) -> list[lot_accounting.Transaction]:
    transactions = []
    for holding in holdings:
        for transaction in holding.transactions:
            transactions.append(
                lot_accounting.Transaction(
                    id=transaction.id,
                    holding_id=holding.id,
                    ticker=holding.ticker,
                    currency=holding.currency.value,
                    type=transaction.type.value.lower(),
                    quantity=transaction.quantity,
                    price=transaction.price,
                    transaction_date=transaction.transaction_date,
                    created_at=transaction.created_at,
                    principal_flow=_transaction_principal_flow(transaction).value,
                    source_group_id=transaction.source_group_id,
                    lot_id=transaction.buy_lot.id if transaction.buy_lot is not None else None,
                    label_ids=frozenset(
                        item.label_id for item in transaction.transaction_labels
                    ),
                    allocations=tuple(
                        lot_accounting.SellAllocationInput(
                            buy_lot_id=allocation.buy_lot_id,
                            quantity=allocation.quantity,
                        )
                        for allocation in transaction.sell_allocations
                    ),
                    requires_review=bool(transaction.requires_review),
                )
            )
    return transactions


def _transaction_principal_flow(transaction: OrmTransaction) -> PrincipalFlow:
    flow = getattr(transaction, "principal_flow", None)
    if isinstance(flow, PrincipalFlow):
        return flow
    if isinstance(flow, str):
        return PrincipalFlow(flow)
    return PrincipalFlow.DEPOSIT if transaction.type == TransactionType.BUY else PrincipalFlow.REINVEST


def _replay_by_currency(
    transactions: list[lot_accounting.Transaction],
    scope: PortfolioScope,
) -> dict[Currency, lot_accounting.ReplayResult]:
    return {
        currency: lot_accounting.replay(
            [
                transaction
                for transaction in transactions
                if transaction.currency == currency.value
            ],
            scope,
        )
        for currency in Currency
    }


def _trusted_scoped_positions(
    holdings: list[Holding],
    scope: PortfolioScope,
    current_prices: dict[str, Decimal | None],
) -> tuple[
    dict[Currency, lot_accounting.ReplayResult],
    list[lot_accounting.ScopedHolding],
]:
    replay_by_currency = _replay_by_currency(_orm_transactions(holdings), scope)
    positions = [
        position
        for replay_result in replay_by_currency.values()
        if replay_result.accounting_status == "ok"
        for position in lot_accounting.build_current_positions(replay_result, current_prices)
    ]
    return replay_by_currency, positions


def _scoped_price_tickers(holdings: list[Holding], scope: PortfolioScope) -> set[str]:
    active_holdings = [holding for holding in holdings if holding.is_active]
    _, positions = _trusted_scoped_positions(active_holdings, scope, {})
    return {position.ticker for position in positions}


def _build_scoped_dashboard_payload(
    holdings: list[Holding],
    scope: PortfolioScope,
    current_prices: dict[str, Decimal | None],
) -> tuple[PortfolioSummaryOut, ScopedPortfolioHoldingsOut]:
    active_holdings = [holding for holding in holdings if holding.is_active]
    replay_by_currency, positions = _trusted_scoped_positions(
        active_holdings,
        scope,
        current_prices,
    )
    review_currencies = {
        currency
        for currency, replay_result in replay_by_currency.items()
        if replay_result.accounting_status == "requires_review"
    }
    warnings = [
        warning
        for replay_result in replay_by_currency.values()
        for warning in replay_result.warnings
    ]
    unavailable_tickers = sorted(
        position.ticker for position in positions if position.current_price is None
    )
    warnings.extend(
        f"Current price unavailable for {ticker}" for ticker in unavailable_tickers
    )
    names = {
        (holding.currency, holding.ticker): holding.name for holding in active_holdings
    }
    holding_ids = {
        (holding.currency, holding.ticker): holding.id for holding in active_holdings
    }
    output_holdings = [
        ScopedPortfolioHoldingOut(
            holding_id=holding_ids[(Currency(position.currency), position.ticker)],
            ticker=position.ticker,
            name=names.get((Currency(position.currency), position.ticker)),
            currency=Currency(position.currency),
            remaining_quantity=position.remaining_quantity,
            remaining_cost_basis=position.remaining_cost_basis,
            current_price=position.current_price,
            current_value=position.current_value,
            unrealized_profit_loss=position.unrealized_profit_loss,
        )
        for position in positions
    ]

    currencies = {}
    for currency in Currency:
        if currency in review_currencies:
            currencies[currency] = PortfolioCurrencySummary(
                total_invested_principal=None,
                total_cost_basis=None,
                total_current_value=None,
                total_profit_loss=None,
                total_profit_loss_pct=None,
                holding_count=0,
            )
            continue
        currency_holdings = [
            holding for holding in output_holdings if holding.currency == currency
        ]
        if not currency_holdings:
            continue
        total_cost_basis = sum(
            (holding.remaining_cost_basis for holding in currency_holdings),
            Decimal(0),
        )
        has_prices = all(holding.current_value is not None for holding in currency_holdings)
        total_current_value = (
            sum(
                (holding.current_value for holding in currency_holdings),
                Decimal(0),
            )
            if has_prices
            else None
        )
        invested_principal = lot_accounting.invested_principal_by_currency(
            [
                transaction
                for transaction in _orm_transactions(active_holdings)
                if transaction.currency == currency.value
            ],
            scope,
        ).get(currency.value, Decimal(0))
        realized_profit_loss = Decimal(0)
        replay_result = replay_by_currency.get(currency)
        if replay_result is not None:
            realized_profit_loss = replay_result.realized_profit_loss_by_currency.get(
                currency.value, Decimal(0)
            )
        total_unrealized_profit_loss = (
            total_current_value - total_cost_basis
            if total_current_value is not None
            else None
        )
        # 총손익 = 평가손익 + 실현손익 (lot 기반이라 REINVEST로 투자원금이 0이어도 정확)
        total_profit_loss = (
            total_unrealized_profit_loss + realized_profit_loss
            if total_unrealized_profit_loss is not None
            else None
        )
        currencies[currency] = PortfolioCurrencySummary(
            total_invested_principal=invested_principal,
            total_cost_basis=total_cost_basis,
            total_current_value=total_current_value,
            total_profit_loss=total_profit_loss,
            total_profit_loss_pct=(
                total_profit_loss / invested_principal * 100
                if total_profit_loss is not None and invested_principal > 0
                else None
            ),
            holding_count=len(currency_holdings),
        )

    accounting_status = "requires_review" if review_currencies else "ok"
    summary = PortfolioSummaryOut(
        currencies=currencies,
        holding_count=len(output_holdings),
        accounting_status=accounting_status,
        warnings=warnings,
    )
    return (
        summary,
        ScopedPortfolioHoldingsOut(
            holdings=output_holdings,
            accounting_status=accounting_status,
            warnings=warnings,
        ),
    )


def _convert_display_money(
    amount: Decimal | None,
    from_currency: Currency,
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
) -> Decimal | None:
    if amount is None:
        return None
    try:
        return convert_money(amount, from_currency.value, display_currency, exchange_rate)
    except ValueError:
        return None


def _empty_dashboard_summary() -> DashboardSummary:
    return DashboardSummary(
        total_invested_principal=Decimal(0),
        total_cost_basis=Decimal(0),
        total_current_value=Decimal(0),
        total_current_value_change=None,
        total_current_value_change_pct=None,
        total_unrealized_profit_loss=Decimal(0),
        total_unrealized_profit_loss_pct=None,
        total_profit_loss=Decimal(0),
        total_profit_loss_pct=None,
    )


def _dashboard_summary_from_currency_summary(
    summary: PortfolioSummaryOut,
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
) -> DashboardSummary:
    included_currencies = [Currency.USD] if display_currency == "USD" else list(Currency)
    fields = (
        "total_invested_principal",
        "total_cost_basis",
        "total_current_value",
        "total_profit_loss",
    )
    totals: dict[str, Decimal] = {field: Decimal(0) for field in fields}
    saw_input_value: dict[str, bool] = {field: False for field in fields}
    saw_converted_value: dict[str, bool] = {field: False for field in fields}

    for currency in included_currencies:
        currency_summary = summary.currencies.get(currency)
        if currency_summary is None:
            continue
        for field in fields:
            value = getattr(currency_summary, field)
            if value is None:
                continue
            saw_input_value[field] = True
            converted = _convert_display_money(
                value,
                currency,
                display_currency,
                exchange_rate,
            )
            if converted is not None:
                totals[field] += converted
                saw_converted_value[field] = True

    if not any(saw_input_value.values()):
        return _empty_dashboard_summary()

    display_totals: dict[str, Decimal | None] = {
        field: totals[field] if saw_converted_value[field] else None
        for field in fields
    }
    invested_principal = display_totals["total_invested_principal"]
    cost_basis = display_totals["total_cost_basis"]
    current_value = display_totals["total_current_value"]
    unrealized_profit_loss = (
        current_value - cost_basis
        if current_value is not None and cost_basis is not None
        else None
    )
    profit_loss = display_totals["total_profit_loss"]
    return DashboardSummary(
        total_invested_principal=invested_principal,
        total_cost_basis=cost_basis,
        total_current_value=current_value,
        total_unrealized_profit_loss=unrealized_profit_loss,
        total_unrealized_profit_loss_pct=(
            unrealized_profit_loss / cost_basis * 100
            if (
                unrealized_profit_loss is not None
                and cost_basis is not None
                and cost_basis > 0
            )
            else None
        ),
        total_profit_loss=profit_loss,
        total_profit_loss_pct=(
            profit_loss / invested_principal * 100
            if (
                profit_loss is not None
                and invested_principal is not None
                and invested_principal > 0
            )
            else None
        ),
    )


def _dashboard_summary_has_values(summary: DashboardSummary) -> bool:
    return any(
        value not in (None, Decimal(0))
        for value in (
            summary.total_invested_principal,
            summary.total_cost_basis,
            summary.total_current_value,
            summary.total_profit_loss,
        )
    )


def _dashboard_current_price_as_of(current_price_dates: dict[str, date | None]) -> date | None:
    valid_dates = [price_date for price_date in current_price_dates.values() if price_date is not None]
    return min(valid_dates) if valid_dates else None


def _dashboard_dates_by_market(
    holdings: list[Holding],
    current_price_dates: dict[str, date | None] | None,
) -> tuple[dict[str, date], dict[str, date], list[str]]:
    """Per-market current-price date and its previous-trading-day comparison date.

    Korea and the US have different trading calendars (e.g. US Juneteenth), so a
    single date hides which market each price is as of. Expose both per market.
    """
    price_dates = current_price_dates or {}
    current_dates: dict[str, set[date]] = {}
    comparison_dates: dict[str, set[date]] = {}
    for holding in holdings:
        ticker_date = price_dates.get(holding.ticker)
        if ticker_date is None:
            continue
        market = _holding_market(holding).value
        current_dates.setdefault(market, set()).add(ticker_date)
        previous_dates = [
            snapshot.snapshot_date
            for snapshot in holding.snapshots
            if snapshot.snapshot_date < ticker_date
        ]
        if previous_dates:
            comparison_dates.setdefault(market, set()).add(max(previous_dates))

    current_by_market = {
        market: max(dates) for market, dates in current_dates.items()
    }
    comparison_by_market = {
        market: max(dates) for market, dates in comparison_dates.items()
    }
    warnings: list[str] = []
    for market, dates in current_dates.items():
        if len(dates) > 1:
            warnings.append(
                f"{market} 일부 종목의 현재가 기준일이 다릅니다: "
                f"{min(dates).isoformat()} ~ {max(dates).isoformat()}"
            )
    for market, dates in comparison_dates.items():
        if len(dates) > 1:
            warnings.append(
                f"{market} 일부 종목의 비교 기준일이 다릅니다: "
                f"{min(dates).isoformat()} ~ {max(dates).isoformat()}"
            )

    return current_by_market, comparison_by_market, warnings


def _previous_weekday(value: date) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _intraday_market_warnings(
    holdings: list[Holding],
    price_quotes: dict[str, CurrentPriceQuote],
    now: datetime,
    *,
    close_overrides: dict | None = None,
) -> list[str]:
    intraday_markets: set[str] = set()
    for holding in holdings:
        quote = price_quotes.get(holding.ticker)
        if quote is None or quote.price is None or quote.price_date is None:
            continue
        if not is_write_confirmed(
            holding.market,
            quote.price_date,
            now,
            close_overrides=close_overrides,
        ):
            intraday_markets.add(holding.market.value)
    return [
        f"{market} 장중 현재가입니다. 차트는 직전 확정 종가까지 표시됩니다."
        for market in sorted(intraday_markets)
    ]


def _holdings_needing_comparison_recovery(
    active_holdings: list,
    price_quotes: dict,
) -> list[tuple]:
    """Return (holding, price_date) pairs that need comparison snapshot recovery.

    For each holding, use the holding's own quote.price_date rather than a
    global current_price_as_of, so KRX and US holdings are evaluated against
    their respective market's latest price date.
    """
    needing = []
    for holding in active_holdings:
        quote = price_quotes.get(holding.ticker)
        if quote is None or quote.price_date is None:
            continue
        expected = _previous_weekday(quote.price_date)
        prior = [s.snapshot_date for s in holding.snapshots if s.snapshot_date < quote.price_date]
        if prior and max(prior) >= expected:
            continue
        needing.append((holding, quote.price_date))
    return needing


def _dashboard_comparison_as_of(
    history_rows: list[DashboardHistoryRow],
    current_price_as_of: date | None,
) -> date | None:
    if current_price_as_of is None:
        return None
    previous_dates = [
        row.snapshot_date
        for row in history_rows
        if row.group_kind == "total"
        and row.group_id is None
        and row.snapshot_date < current_price_as_of
        and row.total_value is not None
    ]
    return previous_dates[-1] if previous_dates else None


def _summary_with_holdings_value_change(
    summary: DashboardSummary,
    holding_rows: list["DashboardHoldingRow"],
) -> DashboardSummary:
    """Set 전일대비 as the sum of each holding's own-day change.

    Summing per-holding changes (each compared to its own market's previous
    trading day) keeps mixed-market portfolios consistent: the summary always
    equals the holdings table, instead of diffing against a single snapshot date.
    """
    changes = [
        row.current_value_change
        for row in holding_rows
        if row.current_value_change is not None
    ]
    change = sum(changes) if changes else None
    pct: Decimal | None = None
    current_value = summary.total_current_value
    if change is not None and current_value is not None:
        previous_value = current_value - change
        if previous_value != 0:
            pct = change / previous_value * 100
    return summary.model_copy(
        update={
            "total_current_value_change": change,
            "total_current_value_change_pct": pct,
        }
    )


def _source_group_scope(source_group: SourceGroup) -> PortfolioScope:
    return PortfolioScope("source", source_group.id)


def _rollup_group_scope(rollup_group: RollupGroup) -> PortfolioScope:
    return PortfolioScope(
        "rollup",
        rollup_group.id,
        resolved_source_group_ids=frozenset(
            member.source_group_id for member in rollup_group.members
        ),
    )


def _scope_display_summary(
    holdings: list[Holding],
    scope: PortfolioScope,
    current_prices: dict[str, Decimal | None],
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
) -> tuple[DashboardSummary, list[str]]:
    scoped_summary, _ = _build_scoped_dashboard_payload(holdings, scope, current_prices)
    return (
        _dashboard_summary_from_currency_summary(
            scoped_summary,
            display_currency,
            exchange_rate,
        ),
        scoped_summary.warnings,
    )


def _build_dashboard_groups(
    holdings: list[Holding],
    source_groups: list[SourceGroup],
    rollup_groups: list[RollupGroup],
    current_prices: dict[str, Decimal | None],
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
    *,
    current_price_as_of: date | None = None,
    current_price_dates: dict[str, date | None] | None = None,
    panel_source_groups: list[SourceGroup] | None = None,
    include_unclassified: bool = True,
) -> tuple[list[DashboardGroupSummary], list[str]]:
    groups: list[DashboardGroupSummary] = []
    warnings: list[str] = []

    for source_group in (
        source_groups if panel_source_groups is None else panel_source_groups
    ):
        scope = _source_group_scope(source_group)
        summary, scope_warnings = _scope_display_summary(
            holdings,
            scope,
            current_prices,
            display_currency,
            exchange_rate,
        )
        warnings.extend(scope_warnings)
        if _dashboard_summary_has_values(summary):
            groups.append(
                DashboardGroupSummary(
                    kind="source",
                    id=source_group.id,
                    name=source_group.name,
                    color=source_group.color,
                    source_group_ids=[source_group.id],
                    summary=summary,
                    holdings=_build_dashboard_holdings(
                        holdings,
                        source_groups,
                        current_prices,
                        display_currency,
                        exchange_rate,
                        scope=scope,
                        current_price_as_of=current_price_as_of,
                        current_price_dates=current_price_dates,
                    ),
                )
            )

    for rollup_group in rollup_groups:
        scope = _rollup_group_scope(rollup_group)
        summary, scope_warnings = _scope_display_summary(
            holdings,
            scope,
            current_prices,
            display_currency,
            exchange_rate,
        )
        warnings.extend(scope_warnings)
        if _dashboard_summary_has_values(summary):
            groups.append(
                DashboardGroupSummary(
                    kind="combined",
                    id=rollup_group.id,
                    name=rollup_group.name,
                    color=rollup_group.color,
                    source_group_ids=[
                        member.source_group_id for member in rollup_group.members
                    ],
                    summary=summary,
                    holdings=_build_dashboard_holdings(
                        holdings,
                        source_groups,
                        current_prices,
                        display_currency,
                        exchange_rate,
                        scope=scope,
                        current_price_as_of=current_price_as_of,
                        current_price_dates=current_price_dates,
                    ),
                )
            )

    if include_unclassified:
        scope = PortfolioScope("unclassified")
        summary, scope_warnings = _scope_display_summary(
            holdings,
            scope,
            current_prices,
            display_currency,
            exchange_rate,
        )
        warnings.extend(scope_warnings)
        if _dashboard_summary_has_values(summary):
            groups.append(
                DashboardGroupSummary(
                    kind="unclassified",
                    id=None,
                    name="미분류",
                    color=None,
                    summary=summary,
                    holdings=_build_dashboard_holdings(
                        holdings,
                        source_groups,
                        current_prices,
                        display_currency,
                        exchange_rate,
                        scope=scope,
                        current_price_as_of=current_price_as_of,
                        current_price_dates=current_price_dates,
                    ),
                )
            )

    return groups, warnings


def _history_rows_for_scope(
    holdings: list[Holding],
    scope: PortfolioScope,
    *,
    group_kind: str,
    group_id: uuid.UUID | None,
    group_name: str,
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
) -> list[DashboardHistoryRow]:
    history = _build_scoped_history(holdings, scope)
    rows: list[DashboardHistoryRow] = []
    included_currencies = [Currency.USD] if display_currency == "USD" else list(Currency)
    fields = (
        "total_value",
        "total_invested_principal",
        "total_cost_basis",
        "total_profit_loss",
    )
    by_date: dict[date, dict[str, dict[str, Decimal | bool]]] = {}

    for currency in included_currencies:
        for point in history.series.get(currency, []):
            meaningful_point = any(
                getattr(point, field) not in (None, Decimal(0))
                for field in fields
            )
            if not meaningful_point:
                continue

            date_state = by_date.setdefault(
                point.snapshot_date,
                {
                    "totals": {field: Decimal(0) for field in fields},
                    "saw_converted": {field: False for field in fields},
                },
            )
            totals = date_state["totals"]
            saw_converted = date_state["saw_converted"]
            for field in fields:
                value = getattr(point, field)
                if value is None:
                    continue
                converted = _convert_display_money(
                    value,
                    currency,
                    display_currency,
                    exchange_rate,
                )
                if converted is not None:
                    totals[field] += converted
                    saw_converted[field] = True

    for snapshot_date, date_state in sorted(by_date.items()):
        totals = date_state["totals"]
        saw_converted = date_state["saw_converted"]
        rows.append(
            DashboardHistoryRow(
                group_kind=group_kind,
                group_id=group_id,
                group_name=group_name,
                snapshot_date=snapshot_date,
                total_value=(
                    totals["total_value"] if saw_converted["total_value"] else None
                ),
                total_invested_principal=(
                    totals["total_invested_principal"]
                    if saw_converted["total_invested_principal"]
                    else None
                ),
                total_cost_basis=(
                    totals["total_cost_basis"]
                    if saw_converted["total_cost_basis"]
                    else None
                ),
                total_profit_loss=(
                    totals["total_profit_loss"]
                    if saw_converted["total_profit_loss"]
                    else None
                ),
            )
        )
    return rows


def _build_dashboard_history(
    holdings: list[Holding],
    groups: list[DashboardGroupSummary],
    source_groups: list[SourceGroup],
    rollup_groups: list[RollupGroup],
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
    *,
    total_scope: PortfolioScope = PortfolioScope("all"),
    include_unrepresented: bool = True,
) -> DashboardHistorySeries:
    rows = _history_rows_for_scope(
        holdings,
        total_scope,
        group_kind="total",
        group_id=None,
        group_name="전체",
        display_currency=display_currency,
        exchange_rate=exchange_rate,
    )
    rollup_by_id = {rollup.id: rollup for rollup in rollup_groups}
    for group in groups:
        if group.kind == "source":
            scope = PortfolioScope("source", group.id)
        elif group.kind == "combined":
            scope = _rollup_group_scope(rollup_by_id[group.id])
        else:
            scope = PortfolioScope("unclassified")
        rows.extend(
            _history_rows_for_scope(
                holdings,
                scope,
                group_kind=group.kind,
                group_id=group.id,
                group_name=group.name,
                display_currency=display_currency,
                exchange_rate=exchange_rate,
            )
        )
    if include_unrepresented:
        represented_source_ids = {
            group.id for group in groups if group.kind == "source"
        }
        for source_group in source_groups:
            if source_group.id in represented_source_ids:
                continue
            rows.extend(
                _history_rows_for_scope(
                    holdings,
                    _source_group_scope(source_group),
                    group_kind="source",
                    group_id=source_group.id,
                    group_name=source_group.name,
                    display_currency=display_currency,
                    exchange_rate=exchange_rate,
                )
            )
        if not any(group.kind == "unclassified" for group in groups):
            rows.extend(
                _history_rows_for_scope(
                    holdings,
                    PortfolioScope("unclassified"),
                    group_kind="unclassified",
                    group_id=None,
                    group_name="미분류",
                    display_currency=display_currency,
                    exchange_rate=exchange_rate,
                )
            )
    return DashboardHistorySeries(rows=rows)


def _holding_source_badges(
    holdings: list[Holding],
    source_groups: list[SourceGroup],
    scope: PortfolioScope,
) -> dict[tuple[Currency, str], list[DashboardHoldingGroupBadge]]:
    source_metadata = {
        source_group.id: source_group for source_group in source_groups
    }
    replay_by_currency = _replay_by_currency(
        _orm_transactions(holdings),
        PortfolioScope("all"),
    )
    quantities: dict[tuple[Currency, str, uuid.UUID | None], Decimal] = {}
    for currency, replay_result in replay_by_currency.items():
        if replay_result.accounting_status != "ok":
            continue
        for lot in replay_result.lots.values():
            if lot.remaining_quantity <= 0 or not _source_group_matches_scope(
                lot.source_group_id,
                scope,
            ):
                continue
            key = (currency, lot.ticker, lot.source_group_id)
            quantities[key] = quantities.get(key, Decimal(0)) + lot.remaining_quantity

    badges: dict[tuple[Currency, str], list[DashboardHoldingGroupBadge]] = {}
    for (currency, ticker, source_group_id), quantity in sorted(
        quantities.items(),
        key=lambda item: (
            item[0][0].value,
            item[0][1],
            item[0][2] is None,
            str(item[0][2]),
        ),
    ):
        source_group = (
            source_metadata.get(source_group_id) if source_group_id is not None else None
        )
        badges.setdefault((currency, ticker), []).append(
            DashboardHoldingGroupBadge(
                source_group_id=source_group_id,
                name=source_group.name if source_group is not None else "미분류",
                color=source_group.color if source_group is not None else None,
                remaining_quantity=quantity,
            )
        )
    return badges


def _source_group_matches_scope(
    source_group_id: uuid.UUID | None,
    scope: PortfolioScope,
) -> bool:
    if scope.kind == "all":
        return True
    if scope.kind == "unclassified":
        return source_group_id is None
    if scope.kind == "source":
        return source_group_id == scope.id
    if scope.kind == "rollup":
        return source_group_id in scope.resolved_source_group_ids
    if scope.kind == "label":
        # Label scopes cut across source groups; attaching source badges here
        # would expose the owner's full group taxonomy on label shares.
        return False
    raise ValueError(f"Unsupported portfolio scope: {scope.kind}")


def _holding_market(holding: Holding) -> Market:
    return holding.market


def _holding_previous_close_price(
    holding: Holding,
    reference_date: date,
) -> Decimal | None:
    previous_snapshots = [
        snapshot
        for snapshot in holding.snapshots
        if snapshot.snapshot_date < reference_date
    ]
    if not previous_snapshots:
        return None
    return max(previous_snapshots, key=lambda snapshot: snapshot.snapshot_date).close_price


def _dashboard_holding_value_change(
    holding: Holding,
    *,
    quantity: Decimal,
    current_value: Decimal | None,
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
    current_price_as_of: date | None,
) -> Decimal | None:
    if current_value is None:
        return None
    previous_close_price = _holding_previous_close_price(
        holding,
        current_price_as_of or date.today(),
    )
    if previous_close_price is None:
        return None
    previous_value = _convert_display_money(
        quantity * previous_close_price,
        holding.currency,
        display_currency,
        exchange_rate,
    )
    return current_value - previous_value if previous_value is not None else None


def _build_dashboard_holdings(
    holdings: list[Holding],
    source_groups: list[SourceGroup],
    current_prices: dict[str, Decimal | None],
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
    *,
    scope: PortfolioScope = PortfolioScope("all"),
    current_price_as_of: date | None = None,
    current_price_dates: dict[str, date | None] | None = None,
) -> list[DashboardHoldingRow]:
    price_dates = current_price_dates or {}
    _, scoped_holdings = _build_scoped_dashboard_payload(
        holdings,
        scope,
        current_prices,
    )
    names = {(holding.currency, holding.ticker): holding.name for holding in holdings}
    holding_ids = {(holding.currency, holding.ticker): holding.id for holding in holdings}
    holding_by_key = {(holding.currency, holding.ticker): holding for holding in holdings}
    markets = {
        (holding.currency, holding.ticker): _holding_market(holding)
        for holding in holdings
    }
    badges = _holding_source_badges(holdings, source_groups, scope)

    rows: list[DashboardHoldingRow] = []
    for holding in scoped_holdings.holdings:
        if display_currency == "USD" and holding.currency != Currency.USD:
            continue
        key = (holding.currency, holding.ticker)
        current_value = _convert_display_money(
            holding.current_value,
            holding.currency,
            display_currency,
            exchange_rate,
        )
        rows.append(
            DashboardHoldingRow(
                holding_id=holding_ids[key],
                ticker=holding.ticker,
                name=names.get(key),
                market=markets[key],
                currency=holding.currency,
                quantity=holding.remaining_quantity,
                remaining_cost_basis=_convert_display_money(
                    holding.remaining_cost_basis,
                    holding.currency,
                    display_currency,
                    exchange_rate,
                ),
                current_price=holding.current_price,
                current_value=current_value,
                current_value_change=_dashboard_holding_value_change(
                    holding_by_key[key],
                    quantity=holding.remaining_quantity,
                    current_value=current_value,
                    display_currency=display_currency,
                    exchange_rate=exchange_rate,
                    # Each holding compares against ITS OWN latest trading day, so
                    # mixed-market portfolios (e.g. KRX vs a US-holiday day) stay
                    # accurate instead of all using the global oldest date.
                    current_price_as_of=price_dates.get(holding.ticker) or current_price_as_of,
                ),
                unrealized_profit_loss=_convert_display_money(
                    holding.unrealized_profit_loss,
                    holding.currency,
                    display_currency,
                    exchange_rate,
                ),
                groups=badges.get(key, []),
            )
        )
    return rows


def _needs_exchange_warning(
    holdings: list[Holding],
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
) -> bool:
    return (
        display_currency == "KRW"
        and exchange_rate is None
        and any(holding.currency == Currency.USD for holding in holdings)
    )


def build_dashboard_response(
    *,
    holdings: list[Holding],
    source_groups: list[SourceGroup],
    rollup_groups: list[RollupGroup],
    current_prices: dict[str, Decimal | None],
    current_price_dates: dict[str, date | None] | None = None,
    display_currency: DisplayCurrency = "KRW",
    exchange_rate: ExchangeRate | None = None,
    warnings: list[str] | None = None,
    scope: PortfolioScope = PortfolioScope("all"),
    panel_source_groups: list[SourceGroup] | None = None,
) -> DashboardResponse:
    """Assemble the dashboard payload for both the owner and shared views.

    The owner view uses the defaults (all scope, every group panel). Shared
    views pass the share scope plus an explicit panel list so the same summary,
    history, and warning behavior applies to both.
    """
    active_holdings = [holding for holding in holdings if holding.is_active]
    summary_base, summary_warnings = _scope_display_summary(
        active_holdings,
        scope,
        current_prices,
        display_currency,
        exchange_rate,
    )
    output_warnings = list(warnings or [])
    output_warnings.extend(summary_warnings)
    if _needs_exchange_warning(holdings, display_currency, exchange_rate):
        output_warnings.append("USD/KRW exchange rate unavailable; USD values are omitted")

    current_price_as_of = _dashboard_current_price_as_of(current_price_dates or {})
    price_dates_by_market, comparison_dates_by_market, date_warnings = _dashboard_dates_by_market(
        active_holdings, current_price_dates
    )
    output_warnings.extend(date_warnings)
    groups, group_warnings = _build_dashboard_groups(
        active_holdings,
        source_groups,
        rollup_groups,
        current_prices,
        display_currency,
        exchange_rate,
        current_price_as_of=current_price_as_of,
        current_price_dates=current_price_dates,
        panel_source_groups=panel_source_groups,
        include_unclassified=panel_source_groups is None,
    )
    output_warnings.extend(group_warnings)

    history = _build_dashboard_history(
        holdings,
        groups,
        source_groups,
        rollup_groups,
        display_currency,
        exchange_rate,
        total_scope=scope,
        include_unrepresented=panel_source_groups is None,
    )
    comparison_as_of = _dashboard_comparison_as_of(history.rows, current_price_as_of)
    output_holdings = _build_dashboard_holdings(
        active_holdings,
        source_groups,
        current_prices,
        display_currency,
        exchange_rate,
        scope=scope,
        current_price_as_of=current_price_as_of,
        current_price_dates=current_price_dates,
    )
    # 전일대비는 종목별(각 시장 직전 거래일) 변화의 합으로 산출 — 요약·그룹·종목표가 일관.
    summary = _summary_with_holdings_value_change(summary_base, output_holdings)
    groups = [
        group.model_copy(
            update={"summary": _summary_with_holdings_value_change(group.summary, group.holdings)}
        )
        for group in groups
    ]

    return DashboardResponse(
        display_currency=display_currency,
        exchange_rate=(
            DashboardExchangeRate(
                base=exchange_rate.base,
                quote=exchange_rate.quote,
                rate=exchange_rate.rate,
                as_of=exchange_rate.as_of,
            )
            if exchange_rate is not None
            else None
        ),
        last_refreshed_at=datetime.now(timezone.utc),
        current_price_as_of=current_price_as_of,
        comparison_as_of=comparison_as_of,
        price_dates_by_market=price_dates_by_market,
        comparison_dates_by_market=comparison_dates_by_market,
        summary=summary,
        groups=groups,
        history=history,
        holdings=output_holdings,
        warnings=sorted(set(output_warnings)),
    )


async def _load_scoped_holdings(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    include_inactive: bool = False,
) -> list[Holding]:
    result = await db.execute(
        _scoped_holdings_query(user_id, include_inactive=include_inactive)
    )
    return list(result.scalars().all())


async def _load_dashboard_groups(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[list[SourceGroup], list[RollupGroup]]:
    source_result = await db.execute(
        select(SourceGroup).where(SourceGroup.user_id == user_id)
    )
    rollup_result = await db.execute(
        select(RollupGroup)
        .where(RollupGroup.user_id == user_id)
        .options(selectinload(RollupGroup.members))
    )
    return list(source_result.scalars().all()), list(rollup_result.scalars().all())


async def _fetch_current_prices(tickers: set[str]) -> dict[str, Decimal | None]:
    quotes = await _fetch_current_price_quotes(tickers)
    return {ticker: quote.price for ticker, quote in quotes.items()}


async def _fetch_current_price_quotes(tickers: set[str]) -> dict[str, CurrentPriceQuote]:
    ordered_tickers = sorted(tickers)
    results = await asyncio.gather(
        *(get_price(ticker) for ticker in ordered_tickers),
        return_exceptions=True,
    )
    quotes = {}
    for ticker, result in zip(ordered_tickers, results):
        if isinstance(result, BaseException):
            logger.warning("price lookup failed for ticker=%s: %r", ticker, result)
            quotes[ticker] = CurrentPriceQuote(price=None, price_date=None)
        else:
            quotes[ticker] = CurrentPriceQuote(price=result.price, price_date=result.price_date)
    return quotes


async def build_scoped_portfolio_dashboard(
    db: AsyncSession,
    user_id: uuid.UUID,
    scope: PortfolioScope,
) -> tuple[PortfolioSummaryOut, ScopedPortfolioHoldingsOut]:
    holdings = await _load_scoped_holdings(db, user_id)
    prices = await _fetch_current_prices(_scoped_price_tickers(holdings, scope))
    return _build_scoped_dashboard_payload(holdings, scope, prices)


def _scope_touches_transaction(transaction, scope: PortfolioScope) -> bool:
    if scope.kind == "all":
        return True
    if scope.kind == "unclassified":
        return transaction.source_group_id is None
    if scope.kind == "source":
        return transaction.source_group_id == scope.id
    if scope.kind == "rollup":
        return transaction.source_group_id in scope.resolved_source_group_ids
    if scope.kind == "label":
        return any(
            transaction_label.label_id == scope.id
            for transaction_label in transaction.transaction_labels
        )
    raise ValueError(f"Unsupported portfolio scope: {scope.kind}")


def _scope_relevant_holdings(
    holdings: list[Holding],
    scope: PortfolioScope,
) -> list[Holding]:
    """Keep only holdings that ever traded inside the scope.

    Shared views scope the data here, before any payload is built, so the
    public serializer is a second barrier rather than the only one.
    """
    return [
        holding
        for holding in holdings
        if any(
            _scope_touches_transaction(transaction, scope)
            for transaction in holding.transactions
        )
    ]


async def build_shared_portfolio_dashboard(
    db: AsyncSession,
    user_id: uuid.UUID,
    scope: PortfolioScope,
    display_currency: DisplayCurrency = "KRW",
) -> DashboardResponse:
    holdings = _scope_relevant_holdings(
        await _load_scoped_holdings(db, user_id, include_inactive=True),
        scope,
    )
    active_holdings = [holding for holding in holdings if holding.is_active]
    source_groups, _ = await _load_dashboard_groups(db, user_id)
    child_source_groups = (
        [
            source_group
            for source_group in source_groups
            if source_group.id in scope.resolved_source_group_ids
        ]
        if scope.kind == "rollup"
        else []
    )
    price_quotes = await _fetch_current_price_quotes(_scoped_price_tickers(active_holdings, scope))
    prices = {ticker: quote.price for ticker, quote in price_quotes.items()}
    price_dates = {ticker: quote.price_date for ticker, quote in price_quotes.items()}
    exchange_rate = None
    warnings: list[str] = []
    settings = get_settings()
    warnings.extend(
        _intraday_market_warnings(
            active_holdings,
            price_quotes,
            datetime.now(timezone.utc),
            close_overrides=parse_market_close_overrides(
                settings.market_close_overrides_raw
            ),
        )
    )
    if display_currency == "KRW" and any(holding.currency == Currency.USD for holding in holdings):
        try:
            exchange_rate = await asyncio.to_thread(get_usd_krw_rate)
        except Exception as exc:
            logger.warning("shared USD/KRW exchange rate lookup failed: %r", exc)
            warnings.append("USD/KRW exchange rate lookup failed")

    # Snapshot recovery (see build_portfolio_dashboard_response) is deliberately
    # skipped: a public share view must never write to the owner's data.
    return build_dashboard_response(
        holdings=holdings,
        source_groups=source_groups,
        rollup_groups=[],
        current_prices=prices,
        current_price_dates=price_dates,
        display_currency=display_currency,
        exchange_rate=exchange_rate,
        warnings=warnings,
        scope=scope,
        panel_source_groups=child_source_groups,
    )


def _build_scoped_history(
    holdings: list[Holding],
    scope: PortfolioScope,
) -> ScopedPortfolioHistoryOut:
    snapshot_dates = set()
    for holding in holdings:
        for snapshot in holding.snapshots:
            snapshot_dates.add(snapshot.snapshot_date)

    transactions = _orm_transactions(holdings)
    series = {}
    for currency in Currency:
        currency_holdings = [
            holding for holding in holdings if holding.currency == currency
        ]
        close_prices: dict[str, dict[date, Decimal]] = {
            holding.ticker: {} for holding in currency_holdings
        }
        for holding in currency_holdings:
            for snapshot in holding.snapshots:
                close_prices[holding.ticker][snapshot.snapshot_date] = snapshot.close_price
        history = lot_accounting.build_history(
            [
                transaction
                for transaction in transactions
                if transaction.currency == currency.value
            ],
            close_prices,
            scope,
            sorted(snapshot_dates),
        )
        points = []
        for point in history.series[currency.value]:
            requires_review = point.accounting_status == "requires_review"
            points.append(
                ScopedPortfolioHistoryPoint(
                    snapshot_date=point.snapshot_date,
                    total_value=None if requires_review else point.total_value,
                    total_invested_principal=None if requires_review else point.total_invested_principal,
                    total_cost_basis=None if requires_review else point.total_cost_basis,
                    total_profit_loss=None if requires_review else point.total_profit_loss,
                    unavailable_price_count=(
                        max(point.unavailable_price_count, 1)
                        if requires_review
                        else point.unavailable_price_count
                    ),
                    accounting_status=point.accounting_status,
                    warnings=list(point.warnings),
                )
            )
        series[currency] = points
    return ScopedPortfolioHistoryOut(series=series)


async def build_scoped_portfolio_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    scope: PortfolioScope,
) -> ScopedPortfolioHistoryOut:
    return _build_scoped_history(
        await _load_scoped_holdings(db, user_id, include_inactive=True),
        scope,
    )


async def build_portfolio_dashboard_response(
    db: AsyncSession,
    user_id: uuid.UUID,
    display_currency: DisplayCurrency = "KRW",
) -> DashboardResponse:
    holdings = await _load_scoped_holdings(db, user_id, include_inactive=True)
    active_holdings = [holding for holding in holdings if holding.is_active]
    source_groups, rollup_groups = await _load_dashboard_groups(db, user_id)
    price_quotes = await _fetch_current_price_quotes(
        _scoped_price_tickers(active_holdings, PortfolioScope("all"))
    )
    prices = {ticker: quote.price for ticker, quote in price_quotes.items()}
    price_dates = {ticker: quote.price_date for ticker, quote in price_quotes.items()}
    current_price_as_of = _dashboard_current_price_as_of(price_dates)
    exchange_rate = None
    warnings: list[str] = []
    settings = get_settings()
    warnings.extend(
        _intraday_market_warnings(
            active_holdings,
            price_quotes,
            datetime.now(timezone.utc),
            close_overrides=parse_market_close_overrides(
                settings.market_close_overrides_raw
            ),
        )
    )
    recovered_snapshot_count = 0
    if active_holdings:
        for holding, holding_price_date in _holdings_needing_comparison_recovery(active_holdings, price_quotes):
            try:
                recovered_snapshot_count += await backfill_recent_comparison_snapshots(
                    db, holding, current_price_date=holding_price_date,
                )
            except Exception as exc:
                logger.warning("recent comparison snapshot recovery failed for ticker=%s: %r", holding.ticker, exc)
                warnings.append(f"{holding.ticker} 직전 거래일 스냅샷 복구 실패")
        if recovered_snapshot_count:
            try:
                await db.commit()
            except IntegrityError:
                # Another dashboard request may have inserted the same dated snapshots.
                await db.rollback()
            holdings = await _load_scoped_holdings(db, user_id, include_inactive=True)
            active_holdings = [holding for holding in holdings if holding.is_active]
    if display_currency == "KRW" and any(
        holding.currency == Currency.USD for holding in holdings
    ):
        try:
            exchange_rate = await asyncio.to_thread(get_usd_krw_rate)
        except Exception as exc:
            logger.warning("USD/KRW exchange rate lookup failed: %r", exc)
            warnings.append("USD/KRW exchange rate lookup failed")
    return build_dashboard_response(
        holdings=holdings,
        source_groups=source_groups,
        rollup_groups=rollup_groups,
        current_prices=prices,
        current_price_dates=price_dates,
        display_currency=display_currency,
        exchange_rate=exchange_rate,
        warnings=warnings,
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_portfolio_dashboard(
    display_currency: DisplayCurrency = "KRW",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_portfolio_dashboard_response(
        db,
        current_user.id,
        display_currency,
    )


@router.get("/labels/{label_id}/dashboard", response_model=DashboardResponse)
async def get_label_dashboard(
    label_id: uuid.UUID,
    display_currency: DisplayCurrency = "KRW",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await resolve_portfolio_scope(db, current_user.id, "label", label_id)
    return await build_shared_portfolio_dashboard(db, current_user.id, scope, display_currency)


@router.get("/summary", response_model=PortfolioSummaryOut)
async def get_portfolio_summary(
    scope_kind: ScopeKind = "all",
    scope_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await resolve_portfolio_scope(db, current_user.id, scope_kind, scope_id)
    summary, _ = await build_scoped_portfolio_dashboard(db, current_user.id, scope)
    return summary


@router.get("/holdings", response_model=ScopedPortfolioHoldingsOut)
async def get_scoped_portfolio_holdings(
    scope_kind: ScopeKind = "all",
    scope_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await resolve_portfolio_scope(db, current_user.id, scope_kind, scope_id)
    _, holdings = await build_scoped_portfolio_dashboard(db, current_user.id, scope)
    return holdings


@router.get("/history", response_model=PortfolioHistoryOut | ScopedPortfolioHistoryOut)
async def get_portfolio_history(
    tag_id: uuid.UUID | None = None,
    scope_kind: ScopeKind | None = None,
    scope_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if tag_id is not None and scope_kind is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="tag_id cannot be combined with scope_kind",
        )
    if scope_kind is None and scope_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="scope_id requires scope_kind",
        )
    if scope_kind is not None:
        scope = await resolve_portfolio_scope(db, current_user.id, scope_kind, scope_id)
        return await build_scoped_portfolio_history(db, current_user.id, scope)

    if tag_id is not None:
        tag_result = await db.execute(_owned_tag_query(tag_id, current_user.id))
        if tag_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    result = await db.execute(_holdings_query(current_user.id, tag_id))
    return _build_portfolio_history(list(result.scalars().all()))
