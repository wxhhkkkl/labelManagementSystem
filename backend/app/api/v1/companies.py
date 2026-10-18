"""公司接口（FR-001、FR-003）。仅总部管理员可写。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, HqAdmin
from app.schemas.org import CompanyCreate, CompanyOut, CompanyUpdate
from app.services import audit, company as company_service

router = APIRouter(prefix="/companies", tags=["org"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[CompanyOut])
def list_companies(user: HqAdmin, db: DbSession, keyword: str | None = None):
    return company_service.list_companies(db, keyword=keyword)


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(payload: CompanyCreate, user: HqAdmin, db: DbSession, ip: ClientIp):
    company = company_service.create_company(db, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.COMPANY_CHANGE,
        result=audit.AuditResult.SUCCESS,
        target_type="company",
        target_id=company.id,
        ip=ip,
    )
    db.commit()
    return company


@router.put("/{company_id}", response_model=CompanyOut)
@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int, payload: CompanyUpdate, user: HqAdmin, db: DbSession, ip: ClientIp
):
    company = company_service.update_company(db, company_id, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.COMPANY_CHANGE,
        result=audit.AuditResult.SUCCESS,
        target_type="company",
        target_id=company.id,
        ip=ip,
    )
    db.commit()
    return company


@router.post("/{company_id}/disable", response_model=CompanyOut)
def disable_company(company_id: int, user: HqAdmin, db: DbSession, ip: ClientIp):
    company = company_service.disable_company(db, company_id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.COMPANY_CHANGE,
        result=audit.AuditResult.SUCCESS,
        target_type="company",
        target_id=company.id,
        ip=ip,
    )
    db.commit()
    return company
