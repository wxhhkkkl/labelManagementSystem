"""首次打印的日期与每日流水号快照；补打复用，不依赖工位本地计数。"""

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PrintDailyCounter(Base):
    __tablename__ = "print_daily_counter"
    print_date: Mapped[date] = mapped_column(Date, primary_key=True)
    last_number: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PrintIdentity(Base):
    __tablename__ = "print_identity"
    __table_args__ = (
        UniqueConstraint("print_date", "serial_no", name="uq_print_identity_daily_serial"),
    )
    code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("code.id"), primary_key=True)
    print_date: Mapped[date] = mapped_column(Date, nullable=False)
    serial_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
