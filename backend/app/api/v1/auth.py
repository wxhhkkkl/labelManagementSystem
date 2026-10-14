"""T026：认证接口（契约：contracts/auth-api.md）。"""

from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import ClientIp, CurrentUser
from app.core.errors import ApiError, ErrorCode
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.company import Company
from app.models.user import User
from app.models.workstation import Workstation, WorkstationOperator
from app.schemas.auth import LoginRequest, LoginResponse, MeCompany, MeUser, MeWorkstation
from app.schemas.auth import RefreshRequest
from app.services import audit
from app.services import user as user_service
from app.services.user import get_by_username

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


def _build_me(db: Session, user: User) -> MeUser:
    company = db.get(Company, user.company_id) if user.company_id else None
    workstations: list[MeWorkstation] = []
    if user.role == "operator":
        rows = db.execute(
            select(Workstation)
            .join(WorkstationOperator, WorkstationOperator.workstation_id == Workstation.id)
            .where(WorkstationOperator.user_id == user.id)
            .order_by(Workstation.code)
        ).scalars()
        workstations = [MeWorkstation.model_validate(ws) for ws in rows]

    return MeUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        company_id=user.company_id,
        company=MeCompany.model_validate(company) if company else None,
        workstations=workstations,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: DbSession, ip: ClientIp) -> LoginResponse:
    """登录。成功与失败都写审计（FR-061）。

    已知限制：账号不存在时无法归因操作人（AuditLog.operator_id 为 NOT NULL），
    该情形的失败不落审计。密码错误与账号停用均可归因，正常记录。
    """
    known_user = get_by_username(db, payload.username)

    try:
        user = user_service.authenticate(db, payload.username, payload.password)
    except ApiError as exc:
        if known_user is not None:
            audit.record(
                db,
                operator_id=known_user.id,
                role=known_user.role,
                action=audit.AuditAction.LOGIN,
                result=audit.AuditResult.FAILED,
                company_id=known_user.company_id,
                ip=ip,
            )
            db.commit()
        db.rollback()
        raise exc

    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.LOGIN,
        result=audit.AuditResult.SUCCESS,
        company_id=user.company_id,
        ip=ip,
    )
    db.commit()

    return LoginResponse(
        access_token=create_access_token(user.id, user.role, user.company_id),
        refresh_token=create_refresh_token(user.id, user.role, user.company_id),
        expires_in=get_settings().access_token_seconds,
        user=_build_me(db, user),
    )


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: DbSession) -> dict:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.InvalidTokenError as exc:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "刷新令牌无效") from exc

    user = db.get(User, int(claims["sub"]))
    if user is None:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "账号不存在")
    # 与 deps.get_current_user 一致：实时校验状态，不依赖令牌有效期
    if user.status != "active":
        raise ApiError(ErrorCode.ACCOUNT_DISABLED, "账号已停用")

    return {
        "access_token": create_access_token(user.id, user.role, user.company_id),
        "expires_in": get_settings().access_token_seconds,
    }


@router.get("/me", response_model=MeUser)
def me(user: CurrentUser, db: DbSession) -> MeUser:
    return _build_me(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, db: DbSession, ip: ClientIp) -> Response:
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.LOGOUT,
        result=audit.AuditResult.SUCCESS,
        company_id=user.company_id,
        ip=ip,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
