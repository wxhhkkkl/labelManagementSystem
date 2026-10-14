"""码生命周期事件。支撑 FR-064 的码时间线。

不能复用 AuditLog：AuditLog 仅总部管理员可查（FR-062），而码时间线需按数据归属可见，
两者访问规则不同，混用会导致越权或该看的人看不到（见 plan.md 复杂度说明）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

CodeEventType = Enum(
    "imported",
    "bound",
    "allocated",
    "reclaimed",
    "print_started",
    "printed",
    "print_failed",
    "reprint",
    "voided",
    "timeout_reverted",
    name="code_event_type",
)


class CodeEvent(PkMixin, TimestampMixin, Base):
    __tablename__ = "code_event"
    __table_args__ = (Index("ix_code_event_code_time", "code_id", "occurred_at"),)

    code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("code.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(CodeEventType, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    # 系统动作为 NULL
    operator_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("user.id"))
    workstation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workstation.id")
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
