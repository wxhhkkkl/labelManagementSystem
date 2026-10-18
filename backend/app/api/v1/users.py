"""账号接口（FR-004、FR-005）。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import AnyAdmin, ClientIp
from app.core.scope import Scope
from app.schemas.org import UserCreate, UserOut, UserUpdate
from app.services import audit
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["org"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[UserOut])
def list_users(user: AnyAdmin, db: DbSession, company_id: int | None = None):
    scope = Scope(user)
    return user_service.list_users(db, scope, company_id=company_id)


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, user: AnyAdmin, db: DbSession, ip: ClientIp):
    scope = Scope(user)
    created = user_service.create_user(db, scope, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.ACCOUNT_CHANGE,
        result=audit.AuditResult.SUCCESS,
        company_id=created.company_id,
        target_type="user",
        target_id=created.id,
        ip=ip,
    )
    db.commit()
    return created


@router.put("/{user_id}", response_model=UserOut)
@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, user: AnyAdmin, db: DbSession, ip: ClientIp):
    scope = Scope(user)
    updated = user_service.update_user(db, scope, user_id, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.ACCOUNT_CHANGE,
        result=audit.AuditResult.SUCCESS,
        company_id=updated.company_id,
        target_type="user",
        target_id=updated.id,
        ip=ip,
    )
    db.commit()
    return updated


@router.post("/{user_id}/disable", response_model=UserOut)
def disable_user(user_id: int, user: AnyAdmin, db: DbSession, ip: ClientIp):
    scope = Scope(user)
    updated = user_service.disable_user(db, scope, user_id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.ACCOUNT_CHANGE,
        result=audit.AuditResult.SUCCESS,
        company_id=updated.company_id,
        target_type="user",
        target_id=updated.id,
        ip=ip,
    )
    db.commit()
    return updated
