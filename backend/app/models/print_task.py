"""打印任务（当前仅补打）。

补打是唯一由服务端主动发起、需工位端执行的场景（FR-055）。工位端以 5 秒周期
轮询领取（research.md R1），领取为原子 UPDATE，避免重复领取。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

PrintTaskType = Enum("reprint", name="print_task_type")
PrintTaskStatus = Enum(
    "pending", "claimed", "succeeded", "failed", "expired", name="print_task_status"
)


class PrintTask(PkMixin, TimestampMixin, Base):
    __tablename__ = "print_task"
    __table_args__ = (
        # 轮询领取的主查询路径，必须高效
        Index("ix_print_task_ws_status", "target_workstation_id", "status"),
    )

    task_type: Mapped[str] = mapped_column(PrintTaskType, nullable=False, default="reprint")
    code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("code.id"), nullable=False)
    # 补打目标工位 = 该码的 last_printed_workstation_id
    target_workstation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workstation.id"), nullable=False
    )
    template_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("template_version.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    status: Mapped[str] = mapped_column(PrintTaskStatus, nullable=False, default="pending")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
