"""工位接口（FR-002、FR-003）。

总部管理员可管任意公司工位；子公司管理员仅限本公司（Scope 强制）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import AnyAdmin, ClientIp
from app.core.scope import Scope
from app.models.company import Company
from app.models.workstation import Workstation
from app.schemas.org import WorkstationCreate, WorkstationOut, WorkstationUpdate
from app.services import audit
from app.services import workstation as ws_service

router = APIRouter(prefix="/workstations", tags=["org"])

DbSession = Annotated[Session, Depends(get_db)]


def serialize(db: Session, ws: Workstation) -> WorkstationOut:
    company = db.get(Company, ws.company_id)
    return WorkstationOut(
        id=ws.id,
        code=ws.code,
        name=ws.name,
        company_id=ws.company_id,
        company_name=company.name if company else None,
        printer_name=ws.printer_name,
        status=ws.status,
        last_heartbeat_at=ws.last_heartbeat_at,
        online=ws_service.is_online(ws),
        machine_bound=ws.machine_id is not None,
        operator_ids=ws_service.get_operator_ids(db, ws.id),
    )


@router.get("", response_model=list[WorkstationOut])
def list_workstations(user: AnyAdmin, db: DbSession, company_id: int | None = None):
    scope = Scope(user)
    rows = ws_service.list_workstations(db, scope, company_id=company_id)
    return [serialize(db, ws) for ws in rows]


@router.post("", response_model=WorkstationOut, status_code=201)
def create_workstation(payload: WorkstationCreate, user: AnyAdmin, db: DbSession, ip: ClientIp):
    scope = Scope(user)
    ws = ws_service.create_workstation(db, scope, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.WORKSTATION_CHANGE,
        result=audit.AuditResult.SUCCESS,
        company_id=ws.company_id,
        target_type="workstation",
        target_id=ws.id,
        ip=ip,
    )
    db.commit()
    return serialize(db, ws)


@router.put("/{workstation_id}", response_model=WorkstationOut)
@router.patch("/{workstation_id}", response_model=WorkstationOut)
def update_workstation(
    workstation_id: int,
    payload: WorkstationUpdate,
    user: AnyAdmin,
    db: DbSession,
    ip: ClientIp,
):
    scope = Scope(user)
    ws = ws_service.update_workstation(db, scope, workstation_id, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.WORKSTATION_CHANGE,
        result=audit.AuditResult.SUCCESS,
        company_id=ws.company_id,
        target_type="workstation",
        target_id=ws.id,
        ip=ip,
    )
    db.commit()
    return serialize(db, ws)


@router.post("/{workstation_id}/disable", response_model=WorkstationOut)
def disable_workstation(workstation_id: int, user: AnyAdmin, db: DbSession, ip: ClientIp):
    scope = Scope(user)
    ws = ws_service.disable_workstation(db, scope, workstation_id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.WORKSTATION_CHANGE,
        result=audit.AuditResult.SUCCESS,
        company_id=ws.company_id,
        target_type="workstation",
        target_id=ws.id,
        ip=ip,
    )
    db.commit()
    return serialize(db, ws)


@router.post("/{workstation_id}/unbind", response_model=WorkstationOut)
def unbind_workstation(workstation_id: int, user: AnyAdmin, db: DbSession, ip: ClientIp):
    ws = ws_service.unbind_workstation(db, Scope(user), workstation_id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action="workstation_unbind",
        result=audit.AuditResult.SUCCESS,
        company_id=ws.company_id,
        workstation_id=ws.id,
        target_type="workstation",
        target_id=ws.id,
        ip=ip,
    )
    db.commit()
    return serialize(db, ws)
