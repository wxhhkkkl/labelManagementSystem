"""工位软件侧接口（契约：contracts/workstation-api.md）。

本阶段只实现工位绑定与心跳——它们是 US1 的一部分（FR-069）。
可打印码、打印、补打任务轮询等归 US4/US5，见 tasks.md。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, CurrentUser
from app.core.machine import check_bound_machine
from app.core.scope import Scope
from app.models.code import Code
from app.models.company import Company
from app.models.product import Product
from app.models.workstation import Workstation
from app.schemas.reprint import TaskItemOut, TaskListOut, TaskResultOut, TaskResultRequest
from app.services import audit
from app.services import print_task as print_task_service
from app.services import workstation as ws_service

router = APIRouter(
    prefix="/workstation", tags=["workstation"], dependencies=[Depends(check_bound_machine)]
)

DbSession = Annotated[Session, Depends(get_db)]


class BindRequest(BaseModel):
    workstation_id: int
    machine_id: UUID


class BindResponse(BaseModel):
    workstation_id: int
    name: str
    company_id: int
    printer_name: str | None = None


class HeartbeatRequest(BaseModel):
    workstation_id: int
    print_service_ok: bool = True


@router.post("/bind", response_model=BindResponse)
def bind(payload: BindRequest, user: CurrentUser, db: DbSession, ip: ClientIp) -> BindResponse:
    """工位软件首次配置时声明本机代表的工位。

    校验：归属公司（越权 -> FORBIDDEN_SCOPE）、工位或公司停用（-> WORKSTATION_DISABLED）。
    成功后写 Workstation.bound_at 并刷新心跳，避免刚绑定就被判离线。
    """
    ws = ws_service.bind_workstation(db, user, payload.workstation_id, str(payload.machine_id))
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
    return BindResponse(
        workstation_id=ws.id,
        name=ws.name,
        company_id=ws.company_id,
        printer_name=ws.printer_name,
    )


@router.get("/available", response_model=list[BindResponse])
def available(user: CurrentUser, db: DbSession):
    company = db.get(Company, user.company_id) if user.company_id else None
    if company is None or company.status != "active":
        return []
    rows = db.scalars(
        select(Workstation)
        .where(
            Workstation.company_id == company.id,
            Workstation.status == "active",
            Workstation.machine_id.is_(None),
        )
        .order_by(Workstation.code)
    ).all()
    return [
        BindResponse(
            workstation_id=ws.id,
            name=ws.name,
            company_id=ws.company_id,
            printer_name=ws.printer_name,
        )
        for ws in rows
    ]


@router.get("/binding", response_model=BindResponse | None)
def machine_binding(machine_id: UUID, user: CurrentUser, db: DbSession):
    ws = db.scalar(select(Workstation).where(Workstation.machine_id == str(machine_id)))
    if ws is None:
        return None
    company = db.get(Company, ws.company_id)
    if ws.company_id != user.company_id:
        from app.core.errors import ApiError, ErrorCode

        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "本机已绑定其他企业工位，请使用该企业账号登录")
    if ws.status != "active" or company is None or company.status != "active":
        from app.core.errors import ApiError, ErrorCode

        raise ApiError(ErrorCode.WORKSTATION_DISABLED, "本机绑定的工位或企业已停用")
    return BindResponse(
        workstation_id=ws.id, name=ws.name, company_id=ws.company_id, printer_name=ws.printer_name
    )


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(payload: HeartbeatRequest, user: CurrentUser, db: DbSession) -> Response:
    """上报在线（research.md R1）。离线判定由服务端按心跳时间计算。"""
    scope = Scope(user)
    ws = ws_service.get_workstation(db, payload.workstation_id)
    scope.assert_can_access_company(ws.company_id)
    ws_service.record_heartbeat(db, payload.workstation_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- 补打任务轮询


def _task_item(db: Session, task) -> TaskItemOut:
    from app.models.template import TemplateVersion
    from app.services import template_resolver

    code = db.get(Code, task.code_id)
    product = db.get(Product, code.product_id) if code else None
    company = db.get(Company, code.company_id) if code and code.company_id else None
    version = db.get(TemplateVersion, task.template_version_id)

    return TaskItemOut(
        task_id=task.id,
        task_type=task.task_type,
        code_value=code.code_value if code else "",
        template_version_id=task.template_version_id,
        elements_json=version.elements_json if version else {},
        data=template_resolver.dynamic_fields_for(db, code) if code else {},
        product_name=product.name if product else "",
        company_name=company.name if company else "",
        reason=task.reason,
    )


@router.get("/tasks", response_model=TaskListOut)
def list_tasks(
    user: CurrentUser, db: DbSession, workstation_id: int, limit: int = 10
) -> TaskListOut:
    """ "领取"本工位的待执行补打任务（FR-055）。

    采用原子领取（research.md R1）：并发时每个任务只会被一方拿到。
    **没有任务时不做任何写入**——5 秒一次的轮询不能把库打成写热点。
    """
    scope = Scope(user)
    workstation = ws_service.get_workstation(db, workstation_id)
    scope.assert_can_access_company(workstation.company_id)

    claimed = print_task_service.claim_tasks(db, workstation_id=workstation_id, limit=limit)
    if claimed:
        db.commit()
    return TaskListOut(tasks=[_task_item(db, task) for task in claimed])


@router.post("/tasks/{task_id}/result", response_model=TaskResultOut)
def report_task_result(
    task_id: int,
    payload: TaskResultRequest,
    user: CurrentUser,
    db: DbSession,
    workstation_id: int,
    ip: ClientIp,
) -> TaskResultOut:
    """回报补打结果（FR-054）。

    成功时补打次数 +1 并写记录；失败时**不增加补打次数**——没打出来就不算一次补打。
    """
    scope = Scope(user)
    workstation = ws_service.get_workstation(db, workstation_id)
    scope.assert_can_access_company(workstation.company_id)

    task = print_task_service.report_result(
        db,
        task_id=task_id,
        workstation_id=workstation_id,
        success=payload.result == "succeeded",
        operator_id=user.id,
        printer_name=workstation.printer_name,
        failure_reason=payload.failure_reason,
    )
    code = db.get(Code, task.code_id)

    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.REPRINT,
        result=audit.AuditResult.SUCCESS
        if payload.result == "succeeded"
        else audit.AuditResult.FAILED,
        company_id=code.company_id if code else None,
        workstation_id=workstation.id,
        target_type="print_task",
        target_id=task.id,
        ip=ip,
    )
    db.commit()

    return TaskResultOut(
        task_id=task.id,
        status=task.status,
        reprint_count=code.reprint_count if code else 0,
    )


class PrinterRequest(BaseModel):
    workstation_id: int
    printer_name: str = Field(min_length=1, max_length=255)


class PrinterResponse(BaseModel):
    workstation_id: int
    printer_name: str | None


@router.put("/printer", response_model=PrinterResponse)
def set_printer(
    payload: PrinterRequest, user: CurrentUser, db: DbSession, ip: ClientIp
) -> PrinterResponse:
    """保存本工位的默认打印机（FR-070）。

    打印机清单由工位端从操作系统读取（MUST NOT 由服务端提供），
    服务端只负责把选中的名字记到工位上——后续打印记录会带上它。
    """
    scope = Scope(user)
    workstation = ws_service.get_workstation(db, payload.workstation_id)
    scope.assert_can_access_company(workstation.company_id)

    workstation.printer_name = payload.printer_name.strip()
    db.flush()

    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.WORKSTATION_CHANGE,
        result=audit.AuditResult.SUCCESS,
        company_id=workstation.company_id,
        workstation_id=workstation.id,
        target_type="workstation",
        target_id=workstation.id,
        ip=ip,
    )
    db.commit()
    return PrinterResponse(workstation_id=workstation.id, printer_name=workstation.printer_name)
