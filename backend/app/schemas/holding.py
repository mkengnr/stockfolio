import uuid
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.models.holding import Market, Currency, TransactionType


class SellLotAllocationIn(BaseModel):
    buy_lot_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class SellLotAllocationOut(BaseModel):
    buy_lot_id: uuid.UUID
    quantity: Decimal

    model_config = {"from_attributes": True}


class BuyLotOut(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    source_group_id: uuid.UUID | None
    original_quantity: Decimal
    remaining_quantity: Decimal
    unit_price: Decimal
    transaction_date: date


class TransactionIn(BaseModel):
    type: TransactionType
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    transaction_date: date
    source_group_id: uuid.UUID | None = None
    label_ids: list[uuid.UUID] = Field(default_factory=list)
    sell_allocations: list[SellLotAllocationIn] = Field(default_factory=list)

    @field_validator("label_ids")
    @classmethod
    def reject_duplicate_labels(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("label_ids must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_sell_allocations(self):
        if self.type == TransactionType.SELL and not self.sell_allocations:
            raise ValueError("SELL transactions require sell_allocations")
        if self.type == TransactionType.BUY and self.sell_allocations:
            raise ValueError("BUY transactions must not include sell_allocations")
        return self


class TransactionOut(BaseModel):
    id: uuid.UUID
    type: TransactionType
    quantity: Decimal
    price: Decimal
    transaction_date: date
    created_at: datetime
    source_group_id: uuid.UUID | None
    label_ids: list[uuid.UUID]
    requires_review: bool
    buy_lot: BuyLotOut | None
    sell_allocations: list[SellLotAllocationOut]


class HoldingCreateIn(BaseModel):
    ticker: str
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)  # 최초 매수 단가
    transaction_date: date
    notes: str | None = None
    source_group_id: uuid.UUID | None = None
    label_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("label_ids")
    @classmethod
    def reject_duplicate_labels(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("label_ids must not contain duplicates")
        return value


class TransactionClassificationIn(BaseModel):
    source_group_id: uuid.UUID | None = None
    label_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("label_ids")
    @classmethod
    def reject_duplicate_labels(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("label_ids must not contain duplicates")
        return value


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
