"""分配单。携带打印模板版本（FR-027、FR-035）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

AllocationStatus = Enum("active", "reclaimed", name="allocation_status")


class AllocationOrder(PkMixin, TimestampMixin, Base):
    __tablename__ = "allocation_order"

    order_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("company.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("product.id"), nullable=False)
    code_count: Mapped[int] = mapped_column(Integer, nullable=False)
    code_range_from: Mapped[str | None] = mapped_column(String(100))
    code_range_to: Mapped[str | None] = mapped_column(String(100))
    template_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("template_version.id"), nullable=False
    )
    allocated_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(AllocationStatus, nullable=False, default="active")
