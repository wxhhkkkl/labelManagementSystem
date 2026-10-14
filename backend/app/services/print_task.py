"""T109 ~ T111：补打任务的领取、回报与过期清理（research.md R1）。

轮询模型下的关键点：**没有任务时不得产生任何写入**。工位端每 5 秒轮询一次，
若每次空轮询都写库，50 个工位就会把数据库打成每秒 10 次无谓写入。
"""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, ErrorCode
from app.models.base import utcnow
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.print_log import PrintLog
from app.models.print_task import PrintTask
from app.models.workstation import Workstation


def claim_tasks(db: Session, *, workstation_id: int, limit: int = 10) -> list[PrintTask]:
    """原子领取本工位的待执行任务。

    用 `FOR UPDATE SKIP LOCKED` 而不是"先查 id 再按时间戳回查"：
    MySQL 的 DATETIME 默认不存小数秒，时间戳回查会因截断而匹配不到。
    行锁方案还有一个好处——并发领取时后来者直接跳过已锁行，不需要重试。

    没有任务时**不产生任何写入**（R1 的明文要求：5 秒一次的轮询不能打成写热点）。
    """
    tasks = list(
        db.execute(
            select(PrintTask)
            .where(
                PrintTask.target_workstation_id == workstation_id,
                PrintTask.status == "pending",
            )
            .order_by(PrintTask.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    if not tasks:
        return []

    now = utcnow()
    for task in tasks:
        task.status = "claimed"
        task.claimed_at = now
    db.flush()
    return tasks


def report_result(
    db: Session,
    *,
    task_id: int,
    workstation_id: int,
    success: bool,
    operator_id: int,
    printer_name: str | None = None,
    failure_reason: str | None = None,
) -> PrintTask:
    """工位端回报补打结果（FR-054）。

    成功：码保持 `printed`，`reprint_count + 1`，写补打记录。
    失败：**不增加补打次数**——没打出来就不该算一次补打。
    """
    task = db.get(PrintTask, task_id)
    if task is None:
        raise ApiError(ErrorCode.NOT_FOUND, "任务不存在")
    if task.target_workstation_id != workstation_id:
        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "该任务不属于本工位")
    if task.status != "claimed":
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"任务当前状态为「{task.status}」，无法回报")

    code = db.get(Code, task.code_id)
    if code is None:
        raise ApiError(ErrorCode.NOT_FOUND, "任务关联的码不存在")

    workstation = db.get(Workstation, workstation_id)
    resolved_printer = printer_name or (workstation.printer_name if workstation else "") or ""
    now = utcnow()

    if success:
        # FR-077：已打印 --补打--> 已打印（补打次数 +1），状态本身不变
        code.reprint_count += 1
        task.status = "succeeded"
        db.add(
            PrintLog(
                code_id=code.id,
                code_value=code.code_value,
                product_id=code.product_id,
                company_id=code.company_id,
                workstation_id=workstation_id,
                operator_id=operator_id,
                printer_name=resolved_printer,
                template_version_id=task.template_version_id,
                print_type="reprint",
                result="succeeded",
                printed_at=now,
            )
        )
        db.add(
            CodeEvent(
                code_id=code.id,
                event_type="reprint",
                from_status="printed",
                to_status="printed",
                operator_id=operator_id,
                workstation_id=workstation_id,
                reason=task.reason,
                occurred_at=now,
            )
        )
    else:
        task.status = "failed"
        task.failure_reason = failure_reason
        db.add(
            PrintLog(
                code_id=code.id,
                code_value=code.code_value,
                product_id=code.product_id,
                company_id=code.company_id,
                workstation_id=workstation_id,
                operator_id=operator_id,
                printer_name=resolved_printer,
                template_version_id=task.template_version_id,
                print_type="reprint",
                result="failed",
                failure_reason=failure_reason,
                printed_at=now,
            )
        )

    task.finished_at = now
    db.flush()
    return task


def expire_stale_tasks(db: Session, *, ttl_seconds: int | None = None) -> int:
    """把长期无人领取的 pending 任务置为 expired（T111）。

    工位可能被停用或长期离线，任务会一直挂在 pending。不做清理的话，
    工位恢复后会把很久以前的补打任务翻出来执行——那已经没意义了。
    """
    ttl = ttl_seconds or get_settings().print_task_ttl_seconds
    threshold = utcnow() - timedelta(seconds=ttl)

    result = db.execute(
        update(PrintTask)
        .where(PrintTask.status == "pending", PrintTask.created_at < threshold)
        .values(status="expired", finished_at=utcnow())
    )
    db.flush()
    return result.rowcount or 0


def list_pending_for(db: Session, workstation_id: int) -> list[PrintTask]:
    return list(
        db.execute(
            select(PrintTask).where(
                PrintTask.target_workstation_id == workstation_id,
                PrintTask.status == "pending",
            )
        ).scalars()
    )
