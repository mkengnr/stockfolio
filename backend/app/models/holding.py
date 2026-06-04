import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Date, Numeric, ForeignKey, Enum as SAEnum, func, false, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.database import Base


class Market(str, enum.Enum):
    KRX = "KRX"
    US = "US"


class Currency(str, enum.Enum):
    KRW = "KRW"
    USD = "USD"


class TransactionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class PrincipalFlow(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    REINVEST = "REINVEST"
    WITHDRAW = "WITHDRAW"


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[Market] = mapped_column(SAEnum(Market), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency), nullable=False)
    first_buy_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="holdings")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="holding",
        cascade="all, delete-orphan",
        order_by="(Transaction.transaction_date, Transaction.created_at)",
    )
    holding_tags: Mapped[list["HoldingTag"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["DailySnapshot"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan"
    )
    buy_lots: Mapped[list["BuyLot"]] = relationship(back_populates="holding", passive_deletes="all")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    holding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("holdings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_groups.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    principal_flow: Mapped[PrincipalFlow] = mapped_column(
        SAEnum(PrincipalFlow), nullable=False, default=PrincipalFlow.REINVEST
    )
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    holding: Mapped["Holding"] = relationship(back_populates="transactions")
    source_group: Mapped["SourceGroup | None"] = relationship(back_populates="transactions")
    buy_lot: Mapped["BuyLot | None"] = relationship(back_populates="transaction", passive_deletes="all")
    sell_allocations: Mapped[list["SellLotAllocation"]] = relationship(
        back_populates="sell_transaction", passive_deletes="all"
    )
    transaction_labels: Mapped[list["TransactionLabel"]] = relationship(
        back_populates="transaction", passive_deletes="all"
    )
