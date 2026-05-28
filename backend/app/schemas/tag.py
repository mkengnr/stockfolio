import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, field_validator
import re


class TagCreateIn(BaseModel):
    name: str
    color: str = "#6366f1"
    description: str | None = None

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        if not re.match(r"^#[0-9a-fA-F]{6}$", v):
            raise ValueError("color must be a valid hex color (#rrggbb)")
        return v.lower()


class TagUpdateIn(BaseModel):
    name: str | None = None
    color: str | None = None
    description: str | None = None

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^#[0-9a-fA-F]{6}$", v):
            raise ValueError("color must be a valid hex color (#rrggbb)")
        return v.lower()


class TagShareUpdateIn(BaseModel):
    requires_auth: bool = True


class TagSummary(BaseModel):
    total_cost_basis: Decimal
    total_current_value: Decimal | None
    total_profit_loss: Decimal | None
    total_profit_loss_pct: Decimal | None
    holding_count: int


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    description: str | None
    share_token: str | None
    share_requires_auth: bool
    holding_ids: list[uuid.UUID] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class TagDetailOut(TagOut):
    summary: TagSummary | None = None
