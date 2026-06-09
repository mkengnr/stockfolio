import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.portfolio import (
    PortfolioSummaryOut,
    ScopedPortfolioHistoryOut,
    PublicScopedPortfolioHoldingsOut,
)
from app.models.holding import Currency, Market
from app.schemas.dashboard import DashboardSummary, DisplayCurrency


DEFAULT_COLOR = "#6366f1"


def _trim_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("name must not be empty")
    if len(value) > 50:
        raise ValueError("name must not exceed 50 characters")
    return value


def _validate_hex_color(value: str) -> str:
    if not re.match(r"^#[0-9a-fA-F]{6}$", value):
        raise ValueError("color must be a valid hex color (#rrggbb)")
    return value.lower()


class GroupMetadataCreateIn(BaseModel):
    name: str
    color: str = DEFAULT_COLOR
    description: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _trim_name(value)

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        return _validate_hex_color(value)


class GroupMetadataUpdateIn(BaseModel):
    name: str | None = None
    color: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _trim_name(value) if value is not None else None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        return _validate_hex_color(value) if value is not None else None


class SourceGroupCreateIn(GroupMetadataCreateIn):
    pass


class SourceGroupUpdateIn(GroupMetadataUpdateIn):
    pass


class LabelCreateIn(GroupMetadataCreateIn):
    pass


class LabelUpdateIn(GroupMetadataUpdateIn):
    pass


class RollupGroupCreateIn(GroupMetadataCreateIn):
    source_group_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("source_group_ids")
    @classmethod
    def validate_unique_members(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("source_group_ids must not contain duplicates")
        return value


class RollupGroupUpdateIn(GroupMetadataUpdateIn):
    source_group_ids: list[uuid.UUID] | None = None

    @field_validator("source_group_ids")
    @classmethod
    def validate_unique_members(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("source_group_ids must not contain duplicates")
        return value


class ShareUpdateIn(BaseModel):
    requires_auth: bool = True

    model_config = {"extra": "forbid"}


class GroupMetadataOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    description: str | None
    share_token: str | None
    share_requires_auth: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceGroupOut(GroupMetadataOut):
    pass


class LabelOut(GroupMetadataOut):
    pass


class RollupGroupOut(GroupMetadataOut):
    source_group_ids: list[uuid.UUID]


class SharedGroupOut(BaseModel):
    """Public group metadata without internal entity, member, or token IDs."""

    kind: Literal["source", "rollup", "label"]
    name: str
    color: str
    description: str | None
    summary: PortfolioSummaryOut
    holdings: PublicScopedPortfolioHoldingsOut
    history: ScopedPortfolioHistoryOut
    dashboard: "SharedDashboardOut"


class SharedDashboardHoldingGroupBadgeOut(BaseModel):
    name: str
    color: str | None
    remaining_quantity: Decimal


class SharedDashboardHoldingOut(BaseModel):
    ticker: str
    name: str | None
    market: Market
    currency: Currency
    quantity: Decimal
    remaining_cost_basis: Decimal | None
    current_price: Decimal | None
    current_value: Decimal | None
    unrealized_profit_loss: Decimal | None
    groups: list[SharedDashboardHoldingGroupBadgeOut]


class SharedDashboardGroupOut(BaseModel):
    key: str
    kind: Literal["source"]
    name: str
    color: str | None
    summary: DashboardSummary
    holdings: list[SharedDashboardHoldingOut]


class SharedDashboardHistoryRowOut(BaseModel):
    group_key: str
    group_kind: Literal["total", "source"]
    group_name: str
    snapshot_date: date
    total_value: Decimal | None
    total_invested_principal: Decimal | None
    total_cost_basis: Decimal | None
    total_profit_loss: Decimal | None


class SharedDashboardHistoryOut(BaseModel):
    rows: list[SharedDashboardHistoryRowOut]


class SharedDashboardOut(BaseModel):
    display_currency: DisplayCurrency
    summary: DashboardSummary
    groups: list[SharedDashboardGroupOut]
    history: SharedDashboardHistoryOut
    holdings: list[SharedDashboardHoldingOut]
