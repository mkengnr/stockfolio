import uuid
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, field_validator
from app.models.holding import Market, Currency, TransactionType


class TransactionIn(BaseModel):
    type: TransactionType
    quantity: Decimal
    price: Decimal
    transaction_date: date


class TransactionOut(BaseModel):
    id: uuid.UUID
    type: TransactionType
    quantity: Decimal
    price: Decimal
    transaction_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class HoldingCreateIn(BaseModel):
    ticker: str
    quantity: Decimal
    price: Decimal  # 최초 매수 단가
    transaction_date: date
    notes: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


class HoldingUpdateIn(BaseModel):
    notes: str | None = None
    name: str | None = None


class SnapshotOut(BaseModel):
    snapshot_date: date
    close_price: Decimal
    total_value: Decimal

    model_config = {"from_attributes": True}


class HoldingOut(BaseModel):
    id: uuid.UUID
    ticker: str
    market: Market
    name: str
    quantity: Decimal
    avg_price: Decimal
    currency: Currency
    first_buy_date: date
    notes: str | None
    is_active: bool
    created_at: datetime

    # computed at query time (not stored)
    current_price: Decimal | None = None
    current_value: Decimal | None = None
    profit_loss: Decimal | None = None
    profit_loss_pct: Decimal | None = None
    cost_basis: Decimal | None = None

    model_config = {"from_attributes": True}


class HoldingDetailOut(HoldingOut):
    transactions: list[TransactionOut] = []
    snapshots: list[SnapshotOut] = []
    tags: list[uuid.UUID] = []
