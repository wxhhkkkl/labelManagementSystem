"""公司。总部是隐式节点，不占 Company 记录（总部管理员以 company_id IS NULL 表示）。"""

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PkMixin, TimestampMixin

CompanyStatus = Enum("active", "disabled", name="company_status")


class Company(PkMixin, TimestampMixin, Base):
    __tablename__ = "company"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(CompanyStatus, nullable=False, default="active")

    workstations: Mapped[list["Workstation"]] = relationship(back_populates="company")  # noqa: F821
