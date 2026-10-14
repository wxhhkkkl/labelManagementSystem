"""打印记录。每一次打印动作生成一条，append-only，不可更新或删除（FR-050）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

PrintType = Enum("first", "reprint", name="print_type")
PrintResult = Enum("succeeded", "failed", "timeout_reverted", name="print_result")


class PrintLog(PkMixin, TimestampMixin, Base):
    __tablename__ = "print_log"
    __table_args__ = (
        Index("ix_print_log_company_time", "company_id", "printed_at"),
        Index("ix_print_log_ws_time", "workstation_id", "printed_at"),
        Index("ix_print_log_operator_time", "operator_id", "printed_at"),
    )

    code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("code.id"), nullable=False)
    # 快照：码表变更后仍可追溯
    code_value: Mapped[str] = mapped_column(String(100), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("product.id"), nullable=False)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("company.id"), nullable=False)
    workstation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workstation.id"), nullable=False
    )
    operator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    printer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("template_version.id"), nullable=False
    )
    print_type: Mapped[str] = mapped_column(PrintType, nullable=False)
    result: Mapped[str] = mapped_column(PrintResult, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    printed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
