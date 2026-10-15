"""账号服务（FR-004、FR-005）。

角色授权规则集中在 Scope.assert_role_assignable / resolve_target_company，
本模块不重复实现，避免两处规则走叉（FR-068 的同一原则）。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.core.scope import Scope
from app.core.security import hash_password, verify_password
from app.models.user import User

VALID_ROLES = ("hq_admin", "sub_admin", "operator")


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(ErrorCode.NOT_FOUND, "账号不存在")
    return user


def get_by_username(db: Session, username: str) -> User | None:
    return db.execute(select(User).where(User.username == username)).scalar_one_or_none()


def list_users(db: Session, scope: Scope, *, company_id: int | None = None) -> list[User]:
    stmt = select(User).order_by(User.username)
    # 组织隔离：非总部强制限定本公司（R7）
    stmt = scope.apply_company_filter(stmt, User.company_id)
    if not scope.is_hq:
        stmt = stmt.where(User.role == "operator")
    if company_id is not None:
        scope.assert_can_access_company(company_id)
        stmt = stmt.where(User.company_id == company_id)
    return list(db.execute(stmt).scalars())


def create_user(
    db: Session,
    scope: Scope,
    *,
    username: str,
    display_name: str,
    password: str,
    role: str,
    company_id: int | None = None,
) -> User:
    if role not in VALID_ROLES:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"未知角色：{role}")

    # FR-004：子公司管理员只能建本公司操作员
    scope.assert_role_assignable(role)

    target_company = scope.resolve_target_company(company_id)
    if role != "hq_admin" and target_company is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "非总部账号必须归属某个公司")
    if role == "hq_admin" and target_company is not None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "总部管理员不得归属分子公司")

    if get_by_username(db, username) is not None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"账号已存在：{username}")

    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
        role=role,
        company_id=target_company,
        status="active",
    )
    db.add(user)
    db.flush()
    return user


def _assert_can_touch(db: Session, scope: Scope, user: User) -> None:
    """子公司管理员只能改本公司操作员账号。"""
    if scope.is_hq:
        return
    if user.company_id != scope.user.company_id:
        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权操作其他公司的账号")
    if user.role != "operator":
        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权修改管理员账号")


def update_user(
    db: Session, scope: Scope, user_id: int, *, display_name=None, password=None
) -> User:
    user = get_user(db, user_id)
    _assert_can_touch(db, scope, user)
    if display_name is not None:
        user.display_name = display_name
    if password is not None:
        user.password_hash = hash_password(password)
    db.flush()
    return user


def disable_user(db: Session, scope: Scope, user_id: int) -> User:
    user = get_user(db, user_id)
    _assert_can_touch(db, scope, user)
    if user.id == scope.user.id:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "不能停用当前登录的账号")
    user.status = "disabled"
    db.flush()
    return user


def authenticate(db: Session, username: str, password: str) -> User:
    """登录校验。

    账号不存在与密码错误返回同一个错误码，避免账号枚举。
    账号停用单独返回 ACCOUNT_DISABLED，与契约一致。
    """
    user = get_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "账号或密码错误")
    if user.status != "active":
        raise ApiError(ErrorCode.ACCOUNT_DISABLED, "账号已停用")
    return user
