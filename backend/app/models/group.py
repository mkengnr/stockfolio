import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceGroup(Base):
    __tablename__ = "source_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True, index=True)
    share_requires_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="source_groups")
    memberships: Mapped[list["RollupGroupMember"]] = relationship(
        back_populates="source_group", passive_deletes="all"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="source_group", passive_deletes="all"
    )
    buy_lots: Mapped[list["BuyLot"]] = relationship(
        back_populates="source_group", passive_deletes="all"
    )


class RollupGroup(Base):
    __tablename__ = "rollup_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True, index=True)
    share_requires_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="rollup_groups")
    members: Mapped[list["RollupGroupMember"]] = relationship(
        back_populates="rollup_group", passive_deletes="all"
    )


class RollupGroupMember(Base):
    __tablename__ = "rollup_group_members"

    rollup_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rollup_groups.id", ondelete="RESTRICT"), primary_key=True
    )
    source_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_groups.id", ondelete="RESTRICT"), primary_key=True, index=True
    )

    rollup_group: Mapped["RollupGroup"] = relationship(back_populates="members")
    source_group: Mapped["SourceGroup"] = relationship(back_populates="memberships")


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True, index=True)
    share_requires_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="labels")
    transaction_labels: Mapped[list["TransactionLabel"]] = relationship(
        back_populates="label", passive_deletes="all"
    )


class BuyLot(Base):
    __tablename__ = "buy_lots"
    __table_args__ = (
        CheckConstraint("original_quantity > 0"),
        CheckConstraint("remaining_quantity >= 0"),
        CheckConstraint("remaining_quantity <= original_quantity"),
        CheckConstraint("unit_price > 0"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    holding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_groups.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    original_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="buy_lot")
    holding: Mapped["Holding"] = relationship(back_populates="buy_lots")
    user: Mapped["User"] = relationship(back_populates="buy_lots")
    source_group: Mapped["SourceGroup | None"] = relationship(back_populates="buy_lots")
    sell_allocations: Mapped[list["SellLotAllocation"]] = relationship(
        back_populates="buy_lot", passive_deletes="all"
    )


class SellLotAllocation(Base):
    __tablename__ = "sell_lot_allocations"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        UniqueConstraint("sell_transaction_id", "buy_lot_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sell_transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    buy_lot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("buy_lots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sell_transaction: Mapped["Transaction"] = relationship(back_populates="sell_allocations")
    buy_lot: Mapped["BuyLot"] = relationship(back_populates="sell_allocations")


class TransactionLabel(Base):
    __tablename__ = "transaction_labels"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("labels.id", ondelete="RESTRICT"), primary_key=True, index=True
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="transaction_labels")
    label: Mapped["Label"] = relationship(back_populates="transaction_labels")
