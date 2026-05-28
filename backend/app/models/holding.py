import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Date, Numeric, ForeignKey, Enum as SAEnum, func, Text
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
        back_populates="holding", cascade="all, delete-orphan", order_by="Transaction.transaction_date"
    )
    holding_tags: Mapped[list["HoldingTag"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["DailySnapshot"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    holding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("holdings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    holding: Mapped["Holding"] = relationship(back_populates="transactions")
