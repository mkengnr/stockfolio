from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.holding import Currency


class PortfolioHistoryPoint(BaseModel):
    snapshot_date: date
    total_value: Decimal
    total_cost_basis: Decimal


class PortfolioHistoryOut(BaseModel):
    series: dict[Currency, list[PortfolioHistoryPoint]]
