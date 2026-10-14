"""打印模板与模板版本。

版本不可变：修改模板 MUST 新建 TemplateVersion 并递增 version_no（FR-033）。
被分配单或打印任务引用后置 frozen=true（FR-034）。
"""

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PkMixin, TimestampMixin

TemplateStatus = Enum("active", "disabled", name="template_status")


class Template(PkMixin, TimestampMixin, Base):
    __tablename__ = "template"

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(TemplateStatus, nullable=False, default="active")

    versions: Mapped[list["TemplateVersion"]] = relationship(
        back_populates="template", order_by="TemplateVersion.version_no"
    )


class TemplateVersion(PkMixin, TimestampMixin, Base):
    __tablename__ = "template_version"
    __table_args__ = (
        UniqueConstraint("template_id", "version_no", name="uq_template_version_no"),
    )

    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("template.id"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    paper_width_mm: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    paper_height_mm: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    # 元素数组，渲染语义见 contracts/template-rendering.md
    elements_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    template: Mapped["Template"] = relationship(back_populates="versions")
