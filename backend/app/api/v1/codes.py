"""码查询接口（FR-011 码池查询）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, CurrentUser, HqAdmin
from app.core.scope import Scope
from app.models.code import Code
from app.models.workstation import Workstation
from app.schemas.allocation import CodeOut
from app.schemas.audit import CodeDetailOut, TimelineEntryOut
from app.schemas.common import Page
from app.schemas.reprint import ReprintRequest, ReprintTaskOut, VoidRequest, VoidResponse
from app.services import audit, code_timeline
from app.services import reprint as reprint_service
from app.services import void as void_service

router = APIRouter(prefix="/codes", tags=["code"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=Page[CodeOut])
def list_codes(
    user: CurrentUser,
    db: DbSession,
    batch_id: int | None = None,
    product_id: int | None = None,
    status: str | None = None,
    company_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    """按批次/产品/状态筛选码。

    组织隔离（R7）：非总部角色强制限定本公司。总部查询"未分配"的码时
    company_id 为空，这类码本就不属于任何公司，总部可见。
    """
    scope = Scope(user)
    stmt = select(Code)

    scope_id = scope.scope_company_id
    if scope_id is not None:
        stmt = stmt.where(Code.company_id == scope_id)
    elif company_id is not None:
        scope.assert_can_access_company(company_id)
        stmt = stmt.where(Code.company_id == company_id)

    if batch_id is not None:
        stmt = stmt.where(Code.import_batch_id == batch_id)
    if product_id is not None:
        stmt = stmt.where(Code.product_id == product_id)
    if status is not None:
        stmt = stmt.where(Code.status == status)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    rows = db.execute(
        stmt.order_by(Code.id).offset((page - 1) * page_size).limit(page_size)
    ).scalars()

    return Page[CodeOut](
        items=[CodeOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{code_value}/reprint", response_model=ReprintTaskOut)
def request_reprint(
    code_value: str,
    payload: ReprintRequest,
    user: CurrentUser,
    db: DbSession,
    ip: ClientIp,
) -> ReprintTaskOut:
    """对已打印的码发起补打（FR-051 ~ FR-056）。

    成功时只创建派发任务——真正出纸由原工位在下一次轮询时领取执行。
    目标工位不可用时返回 409，且**码状态保持不变**。
    """
    # 校验失败时服务在写入前就抛错，这里不需要 rollback
    task = reprint_service.request_reprint(
        db, code_value=code_value, reason=payload.reason, user=user
    )

    workstation = db.get(Workstation, task.target_workstation_id)
    code = db.get(Code, task.code_id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.REPRINT,
        result=audit.AuditResult.SUCCESS,
        company_id=code.company_id if code else None,
        target_type="print_task",
        target_id=task.id,
        ip=ip,
    )
    db.commit()

    return ReprintTaskOut(
        task_id=task.id,
        code_value=code.code_value if code else code_value,
        target_workstation_id=task.target_workstation_id,
        target_workstation_name=workstation.name if workstation else None,
        status=task.status,
    )


@router.post("/void", response_model=VoidResponse)
def void_codes(payload: VoidRequest, user: HqAdmin, db: DbSession, ip: ClientIp) -> VoidResponse:
    """批量作废（FR-057 ~ FR-060）。

    混入他公司码整体拒绝；混入已作废码按幂等跳过并在 `skipped` 中列出。
    """
    result = void_service.void_codes(
        db, code_values=payload.code_values, reason=payload.reason, user=user
    )

    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.VOID,
        result=audit.AuditResult.SUCCESS,
        target_type="code",
        ip=ip,
    )
    db.commit()
    return VoidResponse(voided=result.voided, skipped=result.skipped)


@router.get("/{code_value}", response_model=CodeDetailOut)
def get_code_detail(code_value: str, user: HqAdmin, db: DbSession) -> CodeDetailOut:
    """码详情与全生命周期时间线（FR-064）。

    可见范围按**数据归属**判定，与审计日志（仅总部可查）不同：
    子公司管理员与工位操作员都能查本公司的码。
    """
    code = code_timeline.get_code(db, code_value)
    scope = Scope(user)
    scope.assert_can_access_company(code.company_id)

    detail = code_timeline.build(db, code)
    return CodeDetailOut(
        **{**vars(detail), "timeline": [TimelineEntryOut(**vars(e)) for e in detail.timeline]}
    )
