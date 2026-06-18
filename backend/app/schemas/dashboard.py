from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import BaseModel, Field

from app.models.holding import Currency, Market


DisplayCurrency = Literal["KRW", "USD"]
DashboardGroupKind = Literal["source", "combined", "unclassified"]
DashboardHistoryGroupKind = Literal["total", "source", "combined", "unclassified"]


class DashboardExchangeRate(BaseModel):
    base: str
    quote: str
    rate: Decimal
    as_of: datetime


class DashboardSummary(BaseModel):
    total_invested_principal: Decimal | None
    total_cost_basis: Decimal | None
    total_current_value: Decimal | None
    total_current_value_change: Decimal | None = None
    total_current_value_change_pct: Decimal | None = None
    total_unrealized_profit_loss: Decimal | None = None
    total_unrealized_profit_loss_pct: Decimal | None = None
    total_profit_loss: Decimal | None
    total_profit_loss_pct: Decimal | None


class DashboardGroupSummary(BaseModel):
    kind: DashboardGroupKind
    id: uuid.UUID | None
    name: str
    color: str | None
    source_group_ids: list[uuid.UUID] = Field(default_factory=list)
    summary: DashboardSummary
    holdings: list["DashboardHoldingRow"] = Field(default_factory=list)


class DashboardHoldingGroupBadge(BaseModel):
    source_group_id: uuid.UUID | None
    name: str
    color: str | None
    remaining_quantity: Decimal


class DashboardHoldingRow(BaseModel):
    holding_id: uuid.UUID
    ticker: str
    name: str | None
    market: Market
    currency: Currency
    quantity: Decimal
    remaining_cost_basis: Decimal | None
    current_price: Decimal | None
    current_value: Decimal | None
    current_value_change: Decimal | None = None
    unrealized_profit_loss: Decimal | None
    groups: list[DashboardHoldingGroupBadge]


class DashboardHistoryRow(BaseModel):
    group_kind: DashboardHistoryGroupKind
    group_id: uuid.UUID | None
    group_name: str
    snapshot_date: date
    total_value: Decimal | None
    total_invested_principal: Decimal | None
    total_cost_basis: Decimal | None
    total_profit_loss: Decimal | None


class DashboardHistorySeries(BaseModel):
    rows: list[DashboardHistoryRow]


class DashboardResponse(BaseModel):
    display_currency: DisplayCurrency
    exchange_rate: DashboardExchangeRate | None
    last_refreshed_at: datetime
    current_price_as_of: date | None
    comparison_as_of: date | None
    summary: DashboardSummary
    groups: list[DashboardGroupSummary]
    history: DashboardHistorySeries
    holdings: list[DashboardHoldingRow]
    warnings: list[str]
