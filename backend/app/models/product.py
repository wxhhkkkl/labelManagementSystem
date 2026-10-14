"""产品。由总部统一管理，code 全局唯一。"""

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

ProductStatus = Enum("active", "disabled", name="product_status")


class Product(PkMixin, TimestampMixin, Base):
    __tablename__ = "product"

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    spec: Mapped[str | None] = mapped_column(String(255))
    default_template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("template.id", use_alter=True, name="fk_product_default_template")
    )
    status: Mapped[str] = mapped_column(ProductStatus, nullable=False, default="active")
