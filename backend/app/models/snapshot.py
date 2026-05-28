import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Date, DateTime, Numeric, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    __table_args__ = (UniqueConstraint("holding_id", "snapshot_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    holding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("holdings.id", ondelete="CASCADE"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    close_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    holding: Mapped["Holding"] = relationship(back_populates="snapshots")
