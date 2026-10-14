"""操作日志。append-only（FR-060），保留期 ≥ 2 年（FR-063）。

写入入口只有 app/services/audit.py，该模块不暴露更新与删除方法。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

AuditResult = Enum("success", "denied", "failed", name="audit_result")


class AuditLog(PkMixin, TimestampMixin, Base):
    __tablename__ = "audit_log"

    operator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    # 角色快照：角色变更后仍可追溯当时的身份
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("company.id"))
    workstation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workstation.id")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    ip: Mapped[str | None] = mapped_column(String(64))
    # 越权请求以 denied 记录（FR-007）
    result: Mapped[str] = mapped_column(AuditResult, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
