"""用户。三角色：总部管理员 / 子公司管理员 / 工位操作员。

账号停用 MUST 在每次请求时实时校验（research.md R4），不能只依赖令牌过期。
"""

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

UserRole = Enum("hq_admin", "sub_admin", "operator", name="user_role")
UserStatus = Enum("active", "disabled", name="user_status")


class User(PkMixin, TimestampMixin, Base):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(UserRole, nullable=False)
    # 仅 hq_admin 可为 NULL（data-model.md 规则）
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("company.id"))
    status: Mapped[str] = mapped_column(UserStatus, nullable=False, default="active")
