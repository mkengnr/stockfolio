from datetime import date
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import BaseModel

from app.models.holding import Currency


AccountingStatus = Literal["ok", "requires_review"]


class PortfolioHistoryPoint(BaseModel):
    snapshot_date: date
    total_value: Decimal
    total_cost_basis: Decimal


class PortfolioHistoryOut(BaseModel):
    series: dict[Currency, list[PortfolioHistoryPoint]]


class PortfolioCurrencySummary(BaseModel):
    total_invested_principal: Decimal | None
    total_cost_basis: Decimal | None
    total_current_value: Decimal | None
    total_profit_loss: Decimal | None
    total_profit_loss_pct: Decimal | None
    holding_count: int


class PortfolioSummaryOut(BaseModel):
    currencies: dict[Currency, PortfolioCurrencySummary]
    holding_count: int
    accounting_status: AccountingStatus
    warnings: list[str]


class PublicScopedPortfolioHoldingOut(BaseModel):
    ticker: str
    name: str | None
    currency: Currency
    remaining_quantity: Decimal
    remaining_cost_basis: Decimal
    current_price: Decimal | None
    current_value: Decimal | None
    unrealized_profit_loss: Decimal | None


class ScopedPortfolioHoldingOut(PublicScopedPortfolioHoldingOut):
    holding_id: uuid.UUID


class ScopedPortfolioHoldingsOut(BaseModel):
    holdings: list[ScopedPortfolioHoldingOut]
    accounting_status: AccountingStatus
    warnings: list[str]


class ScopedPortfolioHistoryPoint(BaseModel):
    snapshot_date: date
    total_value: Decimal | None
    total_invested_principal: Decimal | None
    total_cost_basis: Decimal | None
    total_profit_loss: Decimal | None
    unavailable_price_count: int
    accounting_status: AccountingStatus
    warnings: list[str]


class ScopedPortfolioHistoryOut(BaseModel):
    series: dict[Currency, list[ScopedPortfolioHistoryPoint]]
