"""审计日志接口（FR-061 / FR-062）。

**仅总部管理员可查**，且只读——服务层不提供任何修改或删除入口（FR-060）。
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import HqAdmin
from app.schemas.audit import AuditLogOut
from app.services import audit

router = APIRouter(prefix="/audit-logs", tags=["audit"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    user: HqAdmin,
    db: DbSession,
    role: str | None = None,
    company_id: int | None = None,
    action: str | None = None,
    result: str | None = Query(default=None, pattern="^(success|denied|failed)$"),
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    return audit.query_logs(
        db,
        role=role,
        company_id=company_id,
        action=action,
        result=result,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
