from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID


Currency = Literal["KRW", "USD"]
ScopeKind = Literal["all", "unclassified", "source", "rollup", "label"]
TransactionType = Literal["buy", "sell"]
PrincipalFlow = Literal["DEPOSIT", "REINVEST", "WITHDRAW"]
AccountingStatus = Literal["ok", "requires_review"]
ZERO = Decimal(0)


@dataclass(frozen=True)
class PortfolioScope:
    kind: ScopeKind
    id: UUID | None = None
    resolved_source_group_ids: frozenset[UUID] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.kind in {"source", "rollup", "label"} and self.id is None:
            raise ValueError(f"{self.kind} scope requires an id")
        if self.kind in {"all", "unclassified"} and self.id is not None:
            raise ValueError(f"{self.kind} scope does not accept an id")
        if self.kind != "rollup" and self.resolved_source_group_ids:
            raise ValueError("Resolved source group ids are only valid for rollup scope")


@dataclass(frozen=True)
class SellAllocationInput:
    buy_lot_id: UUID
    quantity: Decimal


@dataclass(frozen=True)
class Transaction:
    id: UUID
    holding_id: UUID
    ticker: str
    currency: Currency
    type: TransactionType
    quantity: Decimal
    price: Decimal
    transaction_date: date
    created_at: datetime
    principal_flow: PrincipalFlow | None = None
    source_group_id: UUID | None = None
    lot_id: UUID | None = None
    label_ids: frozenset[UUID] = field(default_factory=frozenset)
    allocations: tuple[SellAllocationInput, ...] = ()
    requires_review: bool = False


@dataclass(frozen=True)
class BuyLotState:
    id: UUID
    holding_id: UUID
    ticker: str
    currency: Currency
    source_group_id: UUID | None
    label_ids: frozenset[UUID]
    original_quantity: Decimal
    remaining_quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class ReplayResult:
    all_lots: dict[UUID, BuyLotState]
    lots: dict[UUID, BuyLotState]
    realized_profit_loss_by_currency: dict[Currency, Decimal]
    accounting_status: AccountingStatus = "ok"
    warnings: tuple[str, ...] = ()

    @property
    def realized_profit_loss(self) -> Decimal:
        """Return realized P/L when the replay contains at most one currency."""
        if len(self.realized_profit_loss_by_currency) > 1:
            raise ValueError("Realized profit/loss must be read separately by currency")
        return next(iter(self.realized_profit_loss_by_currency.values()), ZERO)


@dataclass(frozen=True)
class ScopedHolding:
    ticker: str
    currency: Currency
    remaining_quantity: Decimal
    remaining_cost_basis: Decimal
    current_price: Decimal | None
    current_value: Decimal | None
    unrealized_profit_loss: Decimal | None


@dataclass(frozen=True)
class PortfolioHistoryPoint:
    snapshot_date: date
    total_value: Decimal | None
    total_invested_principal: Decimal
    total_cost_basis: Decimal
    total_profit_loss: Decimal | None
    unavailable_price_count: int
    accounting_status: AccountingStatus = "ok"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioHistoryOut:
    series: dict[Currency, list[PortfolioHistoryPoint]]


ValidateSellAllocations = Callable[
    [Transaction, dict[UUID, BuyLotState], Sequence[SellAllocationInput]],
    None,
]
ReplayLots = Callable[[Sequence[Transaction], PortfolioScope], ReplayResult]
BuildCurrentPositions = Callable[
    [ReplayResult, Mapping[str, Decimal | None]],
    list[ScopedHolding],
]
BuildHistory = Callable[
    [
        Sequence[Transaction],
        Mapping[str, Mapping[date, Decimal]],
        PortfolioScope,
        Sequence[date] | None,
    ],
    PortfolioHistoryOut,
]


def _transaction_type(transaction: Transaction) -> str:
    return str(getattr(transaction.type, "value", transaction.type)).lower()


def _principal_flow(transaction: Transaction) -> str:
    flow = getattr(transaction, "principal_flow", None)
    if flow is None:
        return "DEPOSIT" if _transaction_type(transaction) == "buy" else "REINVEST"
    return str(getattr(flow, "value", flow)).upper()


def _transaction_sort_key(transaction: Transaction) -> tuple[date, datetime, str]:
    return (transaction.transaction_date, transaction.created_at, str(transaction.id))


def _validate_transaction_amounts(transaction: Transaction) -> None:
    if transaction.quantity <= ZERO:
        raise ValueError("Transaction quantity must be positive")
    if transaction.price <= ZERO:
        raise ValueError("Transaction price must be positive")


def validate_sell_allocations(
    transaction: Transaction,
    lots: dict[UUID, BuyLotState],
    allocations: Sequence[SellAllocationInput],
) -> None:
    if not allocations:
        raise ValueError("Sell must allocate at least one buy lot")
    if sum((allocation.quantity for allocation in allocations), ZERO) != transaction.quantity:
        raise ValueError("Sell allocation quantities must equal sell quantity")

    seen_lot_ids: set[UUID] = set()
    for allocation in allocations:
        if allocation.quantity <= ZERO:
            raise ValueError("Sell allocation quantity must be positive")
        if allocation.buy_lot_id in seen_lot_ids:
            raise ValueError("Sell cannot allocate the same buy lot more than once")
        seen_lot_ids.add(allocation.buy_lot_id)

        lot = lots.get(allocation.buy_lot_id)
        if lot is None:
            raise ValueError("Selected buy lot does not exist")
        if lot.source_group_id != transaction.source_group_id:
            raise ValueError("Selected buy lot does not belong to selected source group")
        if (
            lot.holding_id != transaction.holding_id
            or lot.ticker != transaction.ticker
            or lot.currency != transaction.currency
        ):
            raise ValueError("Selected buy lot does not belong to sold holding")
        if allocation.quantity > lot.remaining_quantity:
            raise ValueError("Sell allocation exceeds selected lot remaining quantity")


def _lot_matches_scope(lot: BuyLotState, scope: PortfolioScope) -> bool:
    if scope.kind == "all":
        return True
    if scope.kind == "unclassified":
        return lot.source_group_id is None
    if scope.kind == "source":
        return lot.source_group_id == scope.id
    if scope.kind == "rollup":
        return lot.source_group_id in scope.resolved_source_group_ids
    if scope.kind == "label":
        return scope.id in lot.label_ids
    raise ValueError(f"Unsupported portfolio scope: {scope.kind}")


def _transaction_matches_principal_scope(transaction: Transaction, scope: PortfolioScope) -> bool:
    if scope.kind == "all":
        return True
    if scope.kind == "unclassified":
        return transaction.source_group_id is None
    if scope.kind == "source":
        return transaction.source_group_id == scope.id
    if scope.kind == "rollup":
        return transaction.source_group_id in scope.resolved_source_group_ids
    if scope.kind == "label":
        return scope.id in transaction.label_ids
    raise ValueError(f"Unsupported portfolio scope: {scope.kind}")


def invested_principal_by_currency(
    transactions: Sequence[Transaction],
    scope: PortfolioScope = PortfolioScope("all"),
) -> dict[Currency, Decimal]:
    totals: dict[Currency, Decimal] = {}
    for transaction in sorted(transactions, key=_transaction_sort_key):
        if not _transaction_matches_principal_scope(transaction, scope):
            continue
        amount = transaction.quantity * transaction.price
        flow = _principal_flow(transaction)
        transaction_type = _transaction_type(transaction)
        if flow == "DEPOSIT" and transaction_type == "buy":
            totals[transaction.currency] = totals.get(transaction.currency, ZERO) + amount
        elif flow == "WITHDRAW" and transaction_type == "sell":
            totals[transaction.currency] = totals.get(transaction.currency, ZERO) - amount
    return totals


def _selected_realized_profit_loss(
    transactions: Sequence[Transaction],
    all_lots: Mapping[UUID, BuyLotState],
    scope: PortfolioScope,
) -> dict[Currency, Decimal]:
    totals: dict[Currency, Decimal] = {}
    for transaction in transactions:
        if _transaction_type(transaction) != "sell":
            continue
        if scope.kind == "label" and scope.id not in transaction.label_ids:
            continue

        for allocation in transaction.allocations:
            lot = all_lots[allocation.buy_lot_id]
            if scope.kind != "label" and not _lot_matches_scope(lot, scope):
                continue
            profit_loss = allocation.quantity * (transaction.price - lot.unit_price)
            totals[transaction.currency] = totals.get(transaction.currency, ZERO) + profit_loss
    return totals


def _label_lots(
    transactions: Sequence[Transaction],
    all_lots: Mapping[UUID, BuyLotState],
    scope: PortfolioScope,
) -> dict[UUID, BuyLotState]:
    lots = {
        lot_id: replace(lot, remaining_quantity=lot.original_quantity)
        for lot_id, lot in all_lots.items()
        if _lot_matches_scope(lot, scope)
    }
    for transaction in transactions:
        if _transaction_type(transaction) != "sell" or scope.id not in transaction.label_ids:
            continue
        for allocation in transaction.allocations:
            lot = lots.get(allocation.buy_lot_id)
            if lot is None:
                continue
            if allocation.quantity > lot.remaining_quantity:
                raise ValueError("Label-scoped sell exceeds selected lot remaining quantity")
            lots[lot.id] = replace(
                lot,
                remaining_quantity=lot.remaining_quantity - allocation.quantity,
            )
    return lots


def replay(
    transactions: Sequence[Transaction],
    scope: PortfolioScope = PortfolioScope("all"),
) -> ReplayResult:
    ordered_transactions = sorted(transactions, key=_transaction_sort_key)
    all_lots: dict[UUID, BuyLotState] = {}
    warnings: list[str] = []

    for transaction in ordered_transactions:
        _validate_transaction_amounts(transaction)
        transaction_type = _transaction_type(transaction)
        if transaction_type == "buy":
            lot_id = transaction.lot_id
            if lot_id is None:
                raise ValueError("Buy requires a lot id")
            if lot_id in all_lots:
                raise ValueError("Buy lot id must be unique")
            all_lots[lot_id] = BuyLotState(
                id=lot_id,
                holding_id=transaction.holding_id,
                ticker=transaction.ticker,
                currency=transaction.currency,
                source_group_id=transaction.source_group_id,
                label_ids=transaction.label_ids,
                original_quantity=transaction.quantity,
                remaining_quantity=transaction.quantity,
                unit_price=transaction.price,
            )
        elif transaction_type == "sell":
            if not transaction.allocations and transaction.requires_review:
                warnings.append(
                    f"Sell transaction {transaction.id} requires review: "
                    "lot allocations are missing"
                )
                continue
            validate_sell_allocations(transaction, all_lots, transaction.allocations)
            for allocation in transaction.allocations:
                lot = all_lots[allocation.buy_lot_id]
                all_lots[lot.id] = replace(
                    lot,
                    remaining_quantity=lot.remaining_quantity - allocation.quantity,
                )
        else:
            raise ValueError(f"Unsupported transaction type: {transaction.type}")

    if scope.kind == "label":
        lots = _label_lots(ordered_transactions, all_lots, scope)
    else:
        lots = {
            lot_id: lot
            for lot_id, lot in all_lots.items()
            if _lot_matches_scope(lot, scope)
        }
    return ReplayResult(
        all_lots=all_lots,
        lots=lots,
        realized_profit_loss_by_currency=_selected_realized_profit_loss(
            ordered_transactions,
            all_lots,
            scope,
        ),
        accounting_status="requires_review" if warnings else "ok",
        warnings=tuple(warnings),
    )


def build_current_positions(
    replay_result: ReplayResult,
    current_prices: Mapping[str, Decimal | None],
    *,
    allow_requires_review: bool = False,
) -> list[ScopedHolding]:
    if replay_result.accounting_status == "requires_review" and not allow_requires_review:
        raise ValueError("Replay requires review before current positions can be trusted")

    totals: dict[tuple[Currency, str], tuple[Decimal, Decimal]] = {}
    for lot in replay_result.lots.values():
        if lot.remaining_quantity == ZERO:
            continue
        key = (lot.currency, lot.ticker)
        quantity, cost_basis = totals.get(key, (ZERO, ZERO))
        totals[key] = (
            quantity + lot.remaining_quantity,
            cost_basis + lot.remaining_quantity * lot.unit_price,
        )

    positions = []
    for (currency, ticker), (quantity, cost_basis) in sorted(totals.items()):
        current_price = current_prices.get(ticker)
        current_value = quantity * current_price if current_price is not None else None
        positions.append(
            ScopedHolding(
                ticker=ticker,
                currency=currency,
                remaining_quantity=quantity,
                remaining_cost_basis=cost_basis,
                current_price=current_price,
                current_value=current_value,
                unrealized_profit_loss=(
                    current_value - cost_basis if current_value is not None else None
                ),
            )
        )
    return positions


def _prior_closes(
    close_prices: Mapping[str, Mapping[date, Decimal]],
    snapshot_date: date,
) -> dict[str, Decimal | None]:
    return {
        ticker: next(
            (
                close
                for close_date, close in sorted(prices.items(), reverse=True)
                if close_date <= snapshot_date
            ),
            None,
        )
        for ticker, prices in close_prices.items()
    }


def build_history(
    transactions: Sequence[Transaction],
    close_prices: Mapping[str, Mapping[date, Decimal]],
    scope: PortfolioScope = PortfolioScope("all"),
    snapshot_dates: Sequence[date] | None = None,
) -> PortfolioHistoryOut:
    if snapshot_dates is None:
        snapshot_dates = sorted(
            {
                snapshot_date
                for ticker_closes in close_prices.values()
                for snapshot_date in ticker_closes
            }
        )
    else:
        snapshot_dates = sorted(set(snapshot_dates))
    series: dict[Currency, list[PortfolioHistoryPoint]] = {"KRW": [], "USD": []}
    for snapshot_date in snapshot_dates:
        transactions_until_date = [
            transaction
            for transaction in transactions
            if transaction.transaction_date <= snapshot_date
        ]
        replay_result = replay(
            transactions_until_date,
            scope,
        )
        invested_principal = invested_principal_by_currency(transactions_until_date, scope)
        requires_review = replay_result.accounting_status == "requires_review"
        totals: dict[Currency, tuple[Decimal, Decimal, int, int]] = {
            "KRW": (ZERO, ZERO, 0, 0),
            "USD": (ZERO, ZERO, 0, 0),
        }
        for position in build_current_positions(
            replay_result,
            _prior_closes(close_prices, snapshot_date),
            allow_requires_review=True,
        ):
            total_value, total_cost_basis, unavailable_price_count, priced_count = totals[
                position.currency
            ]
            if position.current_value is None:
                # A held position with no prior close cannot be valued. Exclude its
                # value AND cost basis so value minus cost stays consistent over the
                # priced subset, and surface the gap via unavailable_price_count
                # instead of nulling the whole currency series.
                totals[position.currency] = (
                    total_value,
                    total_cost_basis,
                    unavailable_price_count + 1,
                    priced_count,
                )
            else:
                totals[position.currency] = (
                    total_value + position.current_value,
                    total_cost_basis + position.remaining_cost_basis,
                    unavailable_price_count,
                    priced_count + 1,
                )

        for currency in ("KRW", "USD"):
            total_value, total_cost_basis, unavailable_price_count, priced_count = totals[
                currency
            ]
            # Null the aggregate only when nothing can be valued at all: the replay
            # needs review, or every held position lacks a prior close.
            value_unreliable = requires_review or (
                unavailable_price_count > 0 and priced_count == 0
            )
            series[currency].append(
                PortfolioHistoryPoint(
                    snapshot_date=snapshot_date,
                    total_value=None if value_unreliable else total_value,
                    total_invested_principal=invested_principal.get(currency, ZERO),
                    total_cost_basis=total_cost_basis,
                    total_profit_loss=(
                        None
                        if value_unreliable
                        else total_value - total_cost_basis
                    ),
                    unavailable_price_count=unavailable_price_count + int(requires_review),
                    accounting_status=replay_result.accounting_status,
                    warnings=replay_result.warnings,
                )
            )
    return PortfolioHistoryOut(series=series)
