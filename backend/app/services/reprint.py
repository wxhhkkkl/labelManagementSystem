"""T106：补打请求（FR-051 ~ FR-056）。

补打是"一码一打"规则下**唯一**被允许的再次打印途径，因此这里有三道硬约束：

1. 只有 `printed` 的码可以补打（FR-051）
2. 必须填写原因（FR-053）
3. 目标工位不可用（离线 / 已停用 / 公司停用）时**拒绝**，且**不得改变码状态**（FR-056）

第 3 条尤其要紧：拒绝时要原样退出，不能留下任何半截状态，
否则码会卡在既没补打、也不在原状态的尴尬位置。
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, ErrorCode
from app.models.allocation_order import AllocationOrder
from app.models.base import utcnow
from app.models.code import Code
from app.models.company import Company
from app.models.print_task import PrintTask
from app.models.user import User
from app.models.workstation import Workstation
from app.services import template as template_service

HQ_ADMIN = "hq_admin"
SUB_ADMIN = "sub_admin"


def _assert_can_reprint(user: User, code: Code) -> None:
    """补打权限（FR-051 / FR-052）。

    已确认下沉到子公司管理员，无需总部审批；工位操作员没有补打权限。
    """
    if user.role == "operator":
        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "工位操作员没有补打权限")
    if user.role == HQ_ADMIN:
        return
    if user.role == SUB_ADMIN and code.company_id == user.company_id:
        return
    raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权对该码执行补打")


def resolve_target_workstation(db: Session, code: Code) -> Workstation:
    """补打派发目标 = 该码最近一次打印的工位（FR-055）。

    发起补打的管理员**不需要**选择工位或打印机。
    """
    if code.last_printed_workstation_id is None:
        raise ApiError(
            ErrorCode.WORKSTATION_OFFLINE,
            "该码没有可用的原工位记录，无法派发补打",
        )
    workstation = db.get(Workstation, code.last_printed_workstation_id)
    if workstation is None:
        raise ApiError(ErrorCode.WORKSTATION_OFFLINE, "原工位不存在")
    return workstation


def assert_workstation_available(db: Session, workstation: Workstation) -> None:
    """目标工位可用性校验（FR-056）。

    离线判定走心跳超时（research.md R1）：轮询模型下没有长连接可断，
    只能靠"多久没上报心跳"推断。
    """
    if workstation.status != "active":
        raise ApiError(ErrorCode.WORKSTATION_DISABLED, "原工位已停用，无法补打")

    company = db.get(Company, workstation.company_id)
    if company is not None and company.status != "active":
        raise ApiError(ErrorCode.WORKSTATION_DISABLED, "原工位所属公司已停用，无法补打")

    threshold = timedelta(seconds=get_settings().offline_threshold_seconds)
    last = workstation.last_heartbeat_at
    if last is None or utcnow() - last > threshold:
        raise ApiError(
            ErrorCode.WORKSTATION_OFFLINE,
            f"原工位已离线（超过 {get_settings().offline_threshold_seconds} 秒未上报心跳），无法补打",
        )


def _template_version_for(db: Session, code: Code) -> int:
    order = (
        db.get(AllocationOrder, code.current_allocation_order_id)
        if code.current_allocation_order_id
        else None
    )
    if order is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "该码没有关联分配单，无法确定模板版本")
    return order.template_version_id


def request_reprint(db: Session, *, code_value: str, reason: str, user: User) -> PrintTask:
    """管理员发起补打，生成下发给原工位的任务。

    注意：这里**不改变码状态**。码保持 `printed`，补打次数在工位端回报成功后才 +1。
    """
    code = db.execute(select(Code).where(Code.code_value == code_value)).scalar_one_or_none()
    if code is None:
        raise ApiError(ErrorCode.NOT_FOUND, "码不存在")

    _assert_can_reprint(user, code)

    if code.status != "printed":
        raise ApiError(
            ErrorCode.CODE_NOT_PRINTED,
            f"只有已打印的码可以补打，该码当前状态为「{code.status}」",
        )

    if reason is None or reason.strip() == "":
        raise ApiError(ErrorCode.REASON_REQUIRED, "补打必须填写原因")

    workstation = resolve_target_workstation(db, code)
    # 目标不可用时直接抛错：调用方不会走到下面的写库，码状态自然保持不变
    assert_workstation_available(db, workstation)

    template_version_id = _template_version_for(db, code)
    # 补打任务引用了该版本，同样触发冻结（FR-034 的"被 PrintTask 引用"分支）
    template_service.freeze_version(db, template_version_id)

    task = PrintTask(
        task_type="reprint",
        code_id=code.id,
        target_workstation_id=workstation.id,
        template_version_id=template_version_id,
        reason=reason.strip(),
        created_by=user.id,
        status="pending",
    )
    db.add(task)
    db.flush()
    return task
