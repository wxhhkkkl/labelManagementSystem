"""工位与"工位—操作员"绑定。

last_heartbeat_at 超过 offline_threshold_seconds 即判定离线（research.md R1），
该判定只由服务端计算，不信任客户端自报的在线状态（FR-056）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PkMixin, TimestampMixin

WorkstationStatus = Enum("active", "disabled", name="workstation_status")


class Workstation(PkMixin, TimestampMixin, Base):
    __tablename__ = "workstation"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_workstation_company_code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("company.id"), nullable=False)
    printer_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(WorkstationStatus, nullable=False, default="active")
    bound_at: Mapped[datetime | None] = mapped_column(DateTime)
    machine_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    company: Mapped["Company"] = relationship(back_populates="workstations")  # noqa: F821
    operators: Mapped[list["WorkstationOperator"]] = relationship(
        back_populates="workstation", cascade="all, delete-orphan"
    )


class WorkstationOperator(Base):
    """工位与操作员的多对多绑定（FR-005）。"""

    __tablename__ = "workstation_operator"
    __table_args__ = (
        UniqueConstraint("workstation_id", "user_id", name="uq_workstation_operator"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workstation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workstation.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id"), nullable=False, index=True
    )

    workstation: Mapped["Workstation"] = relationship(back_populates="operators")
