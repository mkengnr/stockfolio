import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.holding import PrincipalFlow, TransactionType


class TransactionListItemOut(BaseModel):
    id: uuid.UUID
    holding_id: uuid.UUID
    ticker: str
    holding_name: str
    type: TransactionType
    transaction_date: date
    quantity: Decimal
    price: Decimal
    amount: Decimal
    principal_flow: PrincipalFlow
    source_group_id: uuid.UUID | None
    source_group_name: str | None
    label_ids: list[uuid.UUID]
    label_names: list[str]
    requires_review: bool
    created_at: datetime


class TransactionListOut(BaseModel):
    transactions: list[TransactionListItemOut]


class TransactionUpdateIn(BaseModel):
    transaction_date: date | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    principal_flow: PrincipalFlow | None = None
    source_group_id: uuid.UUID | None = None
    label_ids: list[uuid.UUID] | None = None

    @field_validator("label_ids")
    @classmethod
    def reject_duplicate_labels(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("label_ids must not contain duplicates")
        return value
