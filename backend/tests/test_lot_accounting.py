from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.holding import TransactionType as OrmTransactionType
from app.services.lot_accounting import (
    PortfolioScope,
    ReplayResult,
    SellAllocationInput,
    Transaction,
    build_current_positions,
    build_history,
    replay,
)


SAVINGS = UUID("00000000-0000-0000-0000-000000000001")
EMERGENCY = UUID("00000000-0000-0000-0000-000000000002")
FAMILY = UUID("00000000-0000-0000-0000-000000000003")
LONG_TERM = UUID("00000000-0000-0000-0000-000000000004")
SAVINGS_LOT = UUID("10000000-0000-0000-0000-000000000001")
EMERGENCY_LOT = UUID("10000000-0000-0000-0000-000000000002")
SECOND_SAVINGS_LOT = UUID("10000000-0000-0000-0000-000000000003")


def _at(day: str, seconds: int = 0) -> datetime:
    return datetime.fromisoformat(f"{day}T09:00:00") + timedelta(seconds=seconds)


def buy(
    day: str,
    *,
    transaction_id: UUID,
    lot_id: UUID | None,
    quantity: str,
    price: str,
    ticker: str = "005930",
    currency: str = "KRW",
    source_group_id: UUID | None = SAVINGS,
    label_ids: frozenset[UUID] = frozenset(),
    requires_review: bool = False,
    created_at: datetime | None = None,
    principal_flow: str | None = None,
) -> Transaction:
    return Transaction(
        id=transaction_id,
        holding_id=UUID("20000000-0000-0000-0000-000000000001"),
        ticker=ticker,
        currency=currency,
        type="buy",
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=date.fromisoformat(day),
        created_at=created_at or _at(day),
        lot_id=lot_id,
        source_group_id=source_group_id,
        label_ids=label_ids,
        requires_review=requires_review,
        principal_flow=principal_flow,
    )


def sell(
    day: str,
    *,
    transaction_id: UUID,
    quantity: str,
    price: str,
    allocations: list[tuple[UUID, str]],
    ticker: str = "005930",
    currency: str = "KRW",
    source_group_id: UUID | None = SAVINGS,
    label_ids: frozenset[UUID] = frozenset(),
    requires_review: bool = False,
    created_at: datetime | None = None,
) -> Transaction:
    return Transaction(
        id=transaction_id,
        holding_id=UUID("20000000-0000-0000-0000-000000000001"),
        ticker=ticker,
        currency=currency,
        type="sell",
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=date.fromisoformat(day),
        created_at=created_at or _at(day),
        source_group_id=source_group_id,
        label_ids=label_ids,
        requires_review=requires_review,
        allocations=tuple(
            SellAllocationInput(buy_lot_id=lot_id, quantity=Decimal(allocation_quantity))
            for lot_id, allocation_quantity in allocations
        ),
    )


def test_classified_and_unclassified_buys_are_selected_by_scope():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
        buy(
            "2026-01-02",
            transaction_id=UUID(int=2),
            lot_id=EMERGENCY_LOT,
            quantity="2",
            price="90000",
            source_group_id=None,
        ),
    ]

    all_result = replay(transactions, PortfolioScope("all"))
    unclassified_result = replay(transactions, PortfolioScope("unclassified"))

    assert set(all_result.lots) == {SAVINGS_LOT, EMERGENCY_LOT}
    assert set(unclassified_result.lots) == {EMERGENCY_LOT}


def test_same_ticker_in_two_sources_stays_separate_under_source_scope():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
        buy(
            "2026-01-02",
            transaction_id=UUID(int=2),
            lot_id=EMERGENCY_LOT,
            quantity="2",
            price="90000",
            source_group_id=EMERGENCY,
        ),
    ]

    positions = build_current_positions(
        replay(transactions, PortfolioScope("source", SAVINGS)),
        {"005930": Decimal("100000")},
    )

    assert len(positions) == 1
    assert positions[0].remaining_quantity == Decimal("1")
    assert positions[0].remaining_cost_basis == Decimal("80000")


def test_selected_lot_partial_and_full_sells_use_actual_purchase_price():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="2",
            price="80000",
        ),
        buy(
            "2026-01-02",
            transaction_id=UUID(int=2),
            lot_id=EMERGENCY_LOT,
            quantity="2",
            price="90000",
            source_group_id=EMERGENCY,
        ),
        sell(
            "2026-02-01",
            transaction_id=UUID(int=3),
            quantity="1",
            price="100000",
            allocations=[(SAVINGS_LOT, "1")],
        ),
        sell(
            "2026-02-02",
            transaction_id=UUID(int=4),
            quantity="1",
            price="110000",
            allocations=[(SAVINGS_LOT, "1")],
        ),
    ]

    result = replay(transactions, PortfolioScope("all"))

    assert result.realized_profit_loss == Decimal("50000")
    assert result.all_lots[SAVINGS_LOT].remaining_quantity == Decimal("0")
    assert result.all_lots[EMERGENCY_LOT].remaining_quantity == Decimal("2")


def test_sell_can_span_multiple_selected_lots_in_one_source():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
        buy(
            "2026-01-02",
            transaction_id=UUID(int=2),
            lot_id=SECOND_SAVINGS_LOT,
            quantity="2",
            price="90000",
        ),
        sell(
            "2026-02-01",
            transaction_id=UUID(int=3),
            quantity="2",
            price="100000",
            allocations=[(SAVINGS_LOT, "1"), (SECOND_SAVINGS_LOT, "1")],
        ),
    ]

    result = replay(transactions, PortfolioScope("all"))

    assert result.realized_profit_loss == Decimal("30000")
    assert result.all_lots[SAVINGS_LOT].remaining_quantity == Decimal("0")
    assert result.all_lots[SECOND_SAVINGS_LOT].remaining_quantity == Decimal("1")


def test_sell_rejects_lot_from_another_source_group():
    with pytest.raises(ValueError, match="selected source group"):
        replay(
            [
                buy(
                    "2026-01-01",
                    transaction_id=UUID(int=1),
                    lot_id=SAVINGS_LOT,
                    quantity="1",
                    price="80000",
                ),
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="1",
                    price="100000",
                    source_group_id=EMERGENCY,
                    allocations=[(SAVINGS_LOT, "1")],
                ),
            ],
            PortfolioScope("all"),
        )


def test_sell_rejects_quantity_above_selected_lot_remaining_quantity():
    with pytest.raises(ValueError, match="remaining quantity"):
        replay(
            [
                buy(
                    "2026-01-01",
                    transaction_id=UUID(int=1),
                    lot_id=SAVINGS_LOT,
                    quantity="1",
                    price="80000",
                ),
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="2",
                    price="100000",
                    allocations=[(SAVINGS_LOT, "2")],
                ),
            ],
            PortfolioScope("all"),
        )


def test_sell_rejects_allocations_whose_sum_differs_from_sell_quantity():
    with pytest.raises(ValueError, match="equal sell quantity"):
        replay(
            [
                buy(
                    "2026-01-01",
                    transaction_id=UUID(int=1),
                    lot_id=SAVINGS_LOT,
                    quantity="2",
                    price="80000",
                ),
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="2",
                    price="100000",
                    allocations=[(SAVINGS_LOT, "1")],
                ),
            ],
            PortfolioScope("all"),
        )


def test_sell_rejects_duplicate_allocations():
    with pytest.raises(ValueError, match="same buy lot"):
        replay(
            [
                buy(
                    "2026-01-01",
                    transaction_id=UUID(int=1),
                    lot_id=SAVINGS_LOT,
                    quantity="2",
                    price="80000",
                ),
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="2",
                    price="100000",
                    allocations=[(SAVINGS_LOT, "1"), (SAVINGS_LOT, "1")],
                ),
            ]
        )


def test_sell_rejects_nonpositive_allocation():
    with pytest.raises(ValueError, match="positive"):
        replay(
            [
                buy(
                    "2026-01-01",
                    transaction_id=UUID(int=1),
                    lot_id=SAVINGS_LOT,
                    quantity="2",
                    price="80000",
                ),
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="1",
                    price="100000",
                    allocations=[(SAVINGS_LOT, "1"), (SECOND_SAVINGS_LOT, "0")],
                ),
            ]
        )


def test_sell_rejects_nonexistent_lot():
    with pytest.raises(ValueError, match="does not exist"):
        replay(
            [
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="1",
                    price="100000",
                    allocations=[(SAVINGS_LOT, "1")],
                ),
            ]
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("holding_id", UUID("20000000-0000-0000-0000-000000000099")),
        ("ticker", "AAPL"),
        ("currency", "USD"),
    ],
)
def test_sell_rejects_lot_from_wrong_holding_ticker_or_currency(field, value):
    invalid_sell = replace(
        sell(
            "2026-02-01",
            transaction_id=UUID(int=2),
            quantity="1",
            price="100000",
            allocations=[(SAVINGS_LOT, "1")],
        ),
        **{field: value},
    )

    with pytest.raises(ValueError, match="sold holding"):
        replay(
            [
                buy(
                    "2026-01-01",
                    transaction_id=UUID(int=1),
                    lot_id=SAVINGS_LOT,
                    quantity="1",
                    price="80000",
                ),
                invalid_sell,
            ]
        )


def test_sell_without_allocations_still_rejects_new_transaction():
    with pytest.raises(ValueError, match="at least one buy lot"):
        replay(
            [
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="1",
                    price="100000",
                    allocations=[],
                ),
            ]
        )


def test_legacy_unresolved_sell_is_skipped_and_marks_replay_for_review():
    result = replay(
        [
            buy(
                "2026-01-01",
                transaction_id=UUID(int=1),
                lot_id=SAVINGS_LOT,
                quantity="2",
                price="80000",
            ),
            sell(
                "2026-02-01",
                transaction_id=UUID(int=2),
                quantity="1",
                price="100000",
                allocations=[],
                requires_review=True,
            ),
        ]
    )

    assert result.accounting_status == "requires_review"
    assert result.warnings
    assert result.all_lots[SAVINGS_LOT].remaining_quantity == Decimal("2")
    assert result.realized_profit_loss == Decimal("0")


def test_current_positions_rejects_replay_that_requires_review():
    result = replay(
        [
            sell(
                "2026-02-01",
                transaction_id=UUID(int=2),
                quantity="1",
                price="100000",
                allocations=[],
                requires_review=True,
            ),
        ]
    )

    with pytest.raises(ValueError, match="requires review"):
        build_current_positions(result, {})


def test_buy_requires_explicit_lot_id():
    with pytest.raises(ValueError, match="Buy requires a lot id"):
        replay(
            [
                buy(
                    "2026-01-01",
                    transaction_id=UUID(int=1),
                    lot_id=None,
                    quantity="1",
                    price="80000",
                ),
            ]
        )


@pytest.mark.parametrize("transaction_type", [OrmTransactionType.BUY, OrmTransactionType.SELL])
def test_replay_normalizes_uppercase_orm_transaction_types(transaction_type):
    buy_transaction = replace(
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
        type=OrmTransactionType.BUY,
    )
    transactions = [buy_transaction]
    if transaction_type == OrmTransactionType.SELL:
        transactions.append(
            replace(
                sell(
                    "2026-02-01",
                    transaction_id=UUID(int=2),
                    quantity="1",
                    price="100000",
                    allocations=[(SAVINGS_LOT, "1")],
                ),
                type=transaction_type,
            )
        )

    result = replay(transactions)

    assert result.all_lots[SAVINGS_LOT].remaining_quantity == (
        Decimal("0") if transaction_type == OrmTransactionType.SELL else Decimal("1")
    )


def test_same_day_transactions_replay_in_stable_created_at_order():
    day = "2026-01-01"
    transactions = [
        sell(
            day,
            transaction_id=UUID(int=2),
            quantity="1",
            price="100000",
            allocations=[(SAVINGS_LOT, "1")],
            created_at=_at(day, 1),
        ),
        buy(
            day,
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
            created_at=_at(day),
        ),
    ]

    result = replay(transactions, PortfolioScope("all"))

    assert result.all_lots[SAVINGS_LOT].remaining_quantity == Decimal("0")


def test_same_day_same_creation_time_transactions_use_id_as_tie_breaker():
    day = "2026-01-01"
    created_at = _at(day)
    transactions = [
        sell(
            day,
            transaction_id=UUID(int=2),
            quantity="1",
            price="100000",
            allocations=[(SAVINGS_LOT, "1")],
            created_at=created_at,
        ),
        buy(
            day,
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
            created_at=created_at,
        ),
    ]

    result = replay(transactions, PortfolioScope("all"))

    assert result.all_lots[SAVINGS_LOT].remaining_quantity == Decimal("0")


def test_rollup_scope_selects_each_member_source_lot_once():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
        buy(
            "2026-01-02",
            transaction_id=UUID(int=2),
            lot_id=EMERGENCY_LOT,
            quantity="2",
            price="90000",
            source_group_id=EMERGENCY,
        ),
    ]

    result = replay(
        transactions,
        PortfolioScope(
            "rollup",
            FAMILY,
            resolved_source_group_ids=frozenset({SAVINGS, EMERGENCY}),
        ),
    )

    assert set(result.lots) == {SAVINGS_LOT, EMERGENCY_LOT}
    assert build_current_positions(result, {"005930": Decimal("100000")})[
        0
    ].remaining_quantity == Decimal("3")


def test_empty_rollup_scope_selects_no_lots():
    result = replay(
        [
            buy(
                "2026-01-01",
                transaction_id=UUID(int=1),
                lot_id=SAVINGS_LOT,
                quantity="1",
                price="80000",
            ),
        ],
        PortfolioScope("rollup", FAMILY),
    )

    assert result.lots == {}


def test_non_rollup_scope_rejects_resolved_source_group_ids():
    with pytest.raises(ValueError, match="rollup scope"):
        PortfolioScope("all", resolved_source_group_ids=frozenset({SAVINGS}))


def test_label_scope_replays_only_transactions_carrying_label():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="2",
            price="80000",
            label_ids=frozenset({LONG_TERM}),
        ),
        buy(
            "2026-01-02",
            transaction_id=UUID(int=2),
            lot_id=SECOND_SAVINGS_LOT,
            quantity="1",
            price="90000",
        ),
        sell(
            "2026-02-01",
            transaction_id=UUID(int=3),
            quantity="1",
            price="100000",
            allocations=[(SAVINGS_LOT, "1")],
            label_ids=frozenset({LONG_TERM}),
        ),
    ]

    result = replay(transactions, PortfolioScope("label", LONG_TERM))

    assert set(result.lots) == {SAVINGS_LOT}
    assert result.lots[SAVINGS_LOT].remaining_quantity == Decimal("1")
    assert result.realized_profit_loss == Decimal("20000")


def test_label_scope_realized_profit_loss_uses_labeled_sell_even_when_buy_is_unlabeled():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
        sell(
            "2026-02-01",
            transaction_id=UUID(int=2),
            quantity="1",
            price="100000",
            allocations=[(SAVINGS_LOT, "1")],
            label_ids=frozenset({LONG_TERM}),
        ),
    ]

    result = replay(transactions, PortfolioScope("label", LONG_TERM))

    assert result.realized_profit_loss == Decimal("20000")


def test_realized_profit_loss_scalar_rejects_multiple_currency_keys_including_zero():
    result = ReplayResult(
        all_lots={},
        lots={},
        realized_profit_loss_by_currency={
            "KRW": Decimal("20000"),
            "USD": Decimal("0"),
        },
    )

    with pytest.raises(ValueError, match="separately by currency"):
        _ = result.realized_profit_loss


def test_history_keeps_krw_and_usd_separate_and_carries_only_prior_close():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
        buy(
            "2026-01-01",
            transaction_id=UUID(int=2),
            lot_id=EMERGENCY_LOT,
            quantity="2",
            price="10",
            ticker="AAPL",
            currency="USD",
            source_group_id=EMERGENCY,
        ),
    ]
    closes = {
        "005930": {
            date(2026, 1, 1): Decimal("90000"),
            date(2026, 1, 3): Decimal("95000"),
        },
        "AAPL": {
            date(2026, 1, 2): Decimal("12"),
            date(2026, 1, 4): Decimal("13"),
        },
    }

    result = build_history(transactions, closes, PortfolioScope("all"))

    assert [point.total_value for point in result.series["KRW"]] == [
        Decimal("90000"),
        Decimal("90000"),
        Decimal("95000"),
        Decimal("95000"),
    ]
    assert [point.total_value for point in result.series["USD"]] == [
        None,
        Decimal("24"),
        Decimal("24"),
        Decimal("26"),
    ]
    assert result.series["KRW"][0].total_profit_loss == Decimal("10000")
    assert result.series["USD"][0].total_profit_loss is None
    assert result.series["USD"][0].unavailable_price_count == 1


def test_history_profit_uses_remaining_cost_basis_for_reinvest_buys():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
            principal_flow="REINVEST",
        ),
    ]
    closes = {"005930": {date(2026, 1, 1): Decimal("90000")}}

    result = build_history(transactions, closes, PortfolioScope("all"))

    point = result.series["KRW"][0]
    assert point.total_invested_principal == Decimal("0")
    assert point.total_cost_basis == Decimal("80000")
    assert point.total_profit_loss == Decimal("10000")


def test_history_keeps_zero_totals_when_currency_has_no_active_positions():
    transactions = [
        buy(
            "2026-01-01",
            transaction_id=UUID(int=1),
            lot_id=SAVINGS_LOT,
            quantity="1",
            price="80000",
        ),
    ]
    closes = {"005930": {date(2026, 1, 1): Decimal("90000")}}

    result = build_history(transactions, closes, PortfolioScope("all"))

    usd_point = result.series["USD"][0]
    assert usd_point.total_value == Decimal("0")
    assert usd_point.total_profit_loss == Decimal("0")
    assert usd_point.unavailable_price_count == 0


def test_history_uses_requested_dates_when_all_quotes_fail():
    result = build_history(
        [
            buy(
                "2026-01-01",
                transaction_id=UUID(int=1),
                lot_id=SAVINGS_LOT,
                quantity="1",
                price="80000",
            ),
        ],
        {},
        PortfolioScope("all"),
        snapshot_dates=[date(2026, 1, 2)],
    )

    krw_point = result.series["KRW"][0]
    assert krw_point.snapshot_date == date(2026, 1, 2)
    assert krw_point.total_value is None
    assert krw_point.total_profit_loss is None
    assert krw_point.unavailable_price_count > 0


def test_history_marks_values_unreliable_after_legacy_unresolved_sell():
    result = build_history(
        [
            buy(
                "2026-01-01",
                transaction_id=UUID(int=1),
                lot_id=SAVINGS_LOT,
                quantity="2",
                price="80000",
            ),
            sell(
                "2026-02-01",
                transaction_id=UUID(int=2),
                quantity="1",
                price="100000",
                allocations=[],
                requires_review=True,
            ),
        ],
        {"005930": {date(2026, 2, 1): Decimal("90000")}},
        PortfolioScope("all"),
    )

    krw_point = result.series["KRW"][0]
    assert krw_point.accounting_status == "requires_review"
    assert krw_point.warnings
    assert krw_point.total_value is None
    assert krw_point.total_profit_loss is None
    assert krw_point.unavailable_price_count > 0
