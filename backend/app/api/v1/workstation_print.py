"""工位端打印接口（FR-039 ~ FR-046，契约：contracts/workstation-api.md）。

安全边界：业务数据一律经此获取，工位软件 MUST NOT 直接访问数据库（FR-076）。
工位标识来自请求，但**归属校验在服务端**——不能靠客户端自报。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, CurrentUser
from app.core.errors import ApiError, ErrorCode
from app.models.user import User
from app.models.workstation import Workstation
from app.schemas.printing import (
    AcceptedPrintOut,
    ConfirmRequest,
    ConfirmResponse,
    PrintableCodeOut,
    PrintableCodePage,
    PrintRequest,
    PrintResponse,
    RejectedPrintOut,
)
from app.services import audit, printing

router = APIRouter(prefix="/workstation", tags=["workstation"])

DbSession = Annotated[Session, Depends(get_db)]


def _workstation_for(db: Session, user: User, workstation_id: int) -> Workstation:
    """取工位并校验归属。非总部用户只能操作本公司的工位。"""
    workstation = db.get(Workstation, workstation_id)
    if workstation is None:
        raise ApiError(ErrorCode.NOT_FOUND, "工位不存在")
    if user.role != "hq_admin" and workstation.company_id != user.company_id:
        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权操作其他公司的工位")
    return workstation


@router.get("/codes", response_model=PrintableCodePage)
def list_codes(
    user: CurrentUser,
    db: DbSession,
    workstation_id: int,
    product_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """按产品查看本公司"已分配未打印"的码（FR-039）。"""
    workstation = _workstation_for(db, user, workstation_id)
    rows, total = printing.list_printable_codes(
        db,
        company_id=workstation.company_id,
        product_id=product_id,
        page=page,
        page_size=page_size,
    )
    return PrintableCodePage(
        total=total,
        items=[PrintableCodeOut(code_value=c.code_value, product_id=c.product_id) for c in rows],
    )


@router.get("/codes/{code_value}")
def get_code(
    code_value: str, user: CurrentUser, db: DbSession, workstation_id: int
) -> dict:
    """扫码定位单个码（FR-040）。不可打印时返回对应错误码。"""
    workstation = _workstation_for(db, user, workstation_id)
    code = printing.get_code_for_print(
        db, code_value=code_value, company_id=workstation.company_id
    )
    return {"code_value": code.code_value, "product_id": code.product_id, "status": code.status}


@router.post("/print", response_model=PrintResponse)
def start_print(
    payload: PrintRequest, user: CurrentUser, db: DbSession, ip: ClientIp
) -> PrintResponse:
    """预占打印（FR-041 / FR-042 / FR-044）。

    逐码独立处理：部分失败不回滚已接受的部分（FR-049）。
    """
    workstation = _workstation_for(db, user, payload.workstation_id)
    accepted, rejected = printing.preempt(
        db,
        workstation=workstation,
        operator_id=user.id,
        code_values=payload.code_values,
    )

    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.PRINT,
        result=audit.AuditResult.SUCCESS if accepted else audit.AuditResult.FAILED,
        company_id=workstation.company_id,
        workstation_id=workstation.id,
        target_type="code",
        ip=ip,
    )
    db.commit()

    return PrintResponse(
        accepted=[AcceptedPrintOut(**vars(item)) for item in accepted],
        rejected=[RejectedPrintOut(**vars(item)) for item in rejected],
    )


@router.post("/print/confirm", response_model=ConfirmResponse)
def confirm_print(
    payload: ConfirmRequest, user: CurrentUser, db: DbSession, ip: ClientIp
) -> ConfirmResponse:
    """确认打印结果（FR-045 / FR-046 / FR-050）。

    只有持有该码锁的同一工位才能确认。
    """
    workstation = _workstation_for(db, user, payload.workstation_id)
    confirmed, rejected = printing.confirm(
        db,
        workstation=workstation,
        operator_id=user.id,
        results=[item.model_dump() for item in payload.results],
    )

    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.PRINT,
        result=audit.AuditResult.SUCCESS if confirmed else audit.AuditResult.FAILED,
        company_id=workstation.company_id,
        workstation_id=workstation.id,
        target_type="code",
        ip=ip,
    )
    db.commit()

    return ConfirmResponse(
        confirmed=confirmed, rejected=[RejectedPrintOut(**vars(item)) for item in rejected]
    )
