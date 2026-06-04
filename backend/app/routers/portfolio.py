import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.database import get_db
from app.models.group import BuyLot, Label, RollupGroup, RollupGroupMember, SourceGroup
from app.models.holding import Currency, Holding, PrincipalFlow, Transaction as OrmTransaction, TransactionType
from app.models.tag import HoldingTag, Tag
from app.models.user import User
from app.routers.deps import get_current_user
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
from app.services.lot_accounting import PortfolioScope, ScopeKind
from app.services.price_cache import get_price

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoricalPosition:
    quantity: Decimal = Decimal(0)
    avg_cost: Decimal = Decimal(0)

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.avg_cost


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
        total_profit_loss = (
            total_current_value - invested_principal
            if total_current_value is not None
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


async def _fetch_current_prices(tickers: set[str]) -> dict[str, Decimal | None]:
    ordered_tickers = sorted(tickers)
    results = await asyncio.gather(
        *(get_price(ticker) for ticker in ordered_tickers),
        return_exceptions=True,
    )
    prices = {}
    for ticker, result in zip(ordered_tickers, results):
        if isinstance(result, BaseException):
            logger.warning("price lookup failed for ticker=%s: %r", ticker, result)
            prices[ticker] = None
        else:
            prices[ticker] = result.price
    return prices


async def build_scoped_portfolio_dashboard(
    db: AsyncSession,
    user_id: uuid.UUID,
    scope: PortfolioScope,
) -> tuple[PortfolioSummaryOut, ScopedPortfolioHoldingsOut]:
    holdings = await _load_scoped_holdings(db, user_id)
    prices = await _fetch_current_prices(_scoped_price_tickers(holdings, scope))
    return _build_scoped_dashboard_payload(holdings, scope, prices)


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
