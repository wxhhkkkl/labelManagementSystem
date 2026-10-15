"""T087 ~ T092：打印链路（FR-039 ~ FR-050）。

这是系统的核心控制点。三条硬约束：

1. **一码一打**：码由 `allocated` 经"预占"进入 `printing`，确认后才 `printed`；
   对已打印的码再次发起打印一律拒绝（FR-042 / FR-043）。
2. **并发安全**：同一码的并发预占由行锁保证只有一方成功（FR-044）。
3. **逐码独立**：批量任务里单个码失败不影响其余码（FR-049）。

预占与确认都按"每条码一个 savepoint"处理，这样单条失败只回滚它自己。
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, ErrorCode
from app.models.allocation_order import AllocationOrder
from app.models.base import utcnow
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.company import Company
from app.models.print_log import PrintLog
from app.models.template import TemplateVersion
from app.models.workstation import Workstation
from app.services import code_state, template_resolver
from app.services.print_identity import business_date, lock_daily_counter, requires_identity

logger = logging.getLogger(__name__)


@dataclass
class AcceptedPrint:
    code_value: str
    template_version_id: int
    elements_json: dict
    data: dict[str, str]


@dataclass
class RejectedPrint:
    code_value: str
    error_code: str
    message: str


@dataclass
class LockedCode:
    id: int
    code_value: str


# ---------------------------------------------------------------- 查询


def list_printable_codes(
    db: Session, *, company_id: int, product_id: int, page: int = 1, page_size: int = 50
) -> tuple[list[Code], int]:
    """本公司"已分配未打印"的码（FR-039）。

    码在公司内**全部工位共享**，因此只按 company_id 过滤，
    MUST NOT 按 workstation_id 过滤（见 spec 澄清记录）。
    """
    from sqlalchemy import func

    base = select(Code).where(
        Code.company_id == company_id,
        Code.product_id == product_id,
        Code.status == "allocated",
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = list(
        db.execute(base.order_by(Code.code_value).offset((page - 1) * page_size).limit(page_size))
        .scalars()
    )
    return rows, total


def get_code_for_print(db: Session, *, code_value: str, company_id: int) -> Code:
    """扫码定位（FR-040）。不可打印时抛出对应错误码。"""
    code = db.execute(select(Code).where(Code.code_value == code_value)).scalar_one_or_none()
    if code is None:
        raise ApiError(ErrorCode.NOT_FOUND, "码不存在")
    if code.company_id != company_id:
        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "该码不属于本公司")

    # 用状态机给出准确的错误码（已打印 / 已作废 / 未锁定等）
    code_state.assert_action(code.status, "print")
    return code


# ---------------------------------------------------------------- 预占


def _assert_workstation_usable(db: Session, workstation: Workstation) -> None:
    if workstation.status != "active":
        raise ApiError(ErrorCode.WORKSTATION_DISABLED, "工位已停用")
    company = db.get(Company, workstation.company_id)
    if company is not None and company.status != "active":
        raise ApiError(ErrorCode.WORKSTATION_DISABLED, "工位所属公司已停用")


def preempt(
    db: Session,
    *,
    workstation: Workstation,
    operator_id: int,
    code_values: list[str],
) -> tuple[list[AcceptedPrint], list[RejectedPrint]]:
    """打印预占：`allocated` -> `printing`（FR-041 / FR-042）。

    逐码独立处理，单条失败只回滚它自己（FR-049）。
    """
    _assert_workstation_usable(db, workstation)

    print_day = business_date()
    if code_values:
        documents = db.scalars(
            select(TemplateVersion.elements_json)
            .join(AllocationOrder, AllocationOrder.template_version_id == TemplateVersion.id)
            .join(Code, Code.current_allocation_order_id == AllocationOrder.id)
            .where(Code.code_value.in_(code_values), Code.company_id == workstation.company_id)
        ).all()
        if any(requires_identity(document) for document in documents):
            lock_daily_counter(db, print_day)

    accepted: list[AcceptedPrint] = []
    rejected: list[RejectedPrint] = []
    seen: set[str] = set()

    for value in code_values:
        if value in seen:
            rejected.append(
                RejectedPrint(value, ErrorCode.CODE_LOCKED, "同一请求中重复提交了该码")
            )
            continue
        seen.add(value)

        try:
            with db.begin_nested():
                # 行锁：并发下第二个事务会在这里等待，随后看到 status 已是 printing，
                # 由状态机给出 CODE_LOCKED（FR-044）
                code = db.execute(
                    select(Code).where(Code.code_value == value).with_for_update()
                ).scalar_one_or_none()
                if code is None:
                    raise ApiError(ErrorCode.NOT_FOUND, "码不存在")
                # 归属校验刻意排在状态机之前：池中未分配的码 company_id 为空，
                # 会落到这里而不是"状态不允许"。这样打印接口不会成为探测池内码的通道。
                if code.company_id != workstation.company_id:
                    raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "该码不属于本公司")

                target = code_state.assert_action(code.status, "print")
                payload = template_resolver.resolve_for_code(db, code, print_day=print_day)

                code.status = target
                code.locked_at = utcnow()
                code.locked_workstation_id = workstation.id
                db.add(
                    CodeEvent(
                        code_id=code.id,
                        event_type="print_started",
                        from_status="allocated",
                        to_status=target,
                        operator_id=operator_id,
                        workstation_id=workstation.id,
                        occurred_at=utcnow(),
                    )
                )

            accepted.append(
                AcceptedPrint(
                    code_value=value,
                    template_version_id=payload.template_version_id,
                    elements_json=payload.elements_json,
                    data=payload.data,
                )
            )
        except ApiError as exc:
            rejected.append(RejectedPrint(value, exc.error_code, exc.message))

    return accepted, rejected


def _reprint_operator(db: Session, code_id: int) -> int | None:
    """找出最近一次开始打印该码的操作员。

    超时回退是系统动作，但它源自某位操作员的预占。把记录归到该操作员名下，
    才能保住 SC-006「可追溯到操作员 + 工位 + 打印机」这条要求。
    """
    return db.execute(
        select(CodeEvent.operator_id)
        .where(CodeEvent.code_id == code_id, CodeEvent.event_type == "print_started")
        .order_by(CodeEvent.occurred_at.desc())
        .limit(1)
    ).scalar_one_or_none()


# ---------------------------------------------------------------- 确认


def confirm(
    db: Session,
    *,
    workstation: Workstation,
    operator_id: int,
    results: list[dict],
) -> tuple[list[str], list[RejectedPrint]]:
    """确认打印结果（FR-045 / FR-046 / FR-050）。

    succeeded -> printed 且 print_count+1
    failed    -> 回退 allocated，且**不计补打次数**
    """
    _assert_workstation_usable(db, workstation)

    done: list[str] = []
    rejected: list[RejectedPrint] = []

    for item in results:
        value = item["code_value"]
        outcome = item["outcome"]
        try:
            with db.begin_nested():
                code = db.execute(
                    select(Code).where(Code.code_value == value).with_for_update()
                ).scalar_one_or_none()
                if code is None:
                    raise ApiError(ErrorCode.NOT_FOUND, "码不存在")

                # 只有持有该码锁的工位才能确认——否则别的工位能替它"确认成功"
                if code.status != "printing" or code.locked_workstation_id != workstation.id:
                    raise ApiError(ErrorCode.CODE_LOCKED, "该码未被本工位锁定，无法确认")

                printer_name = item.get("printer_name") or workstation.printer_name or ""
                template_version_id = _current_template_version(db, code)
                now = utcnow()

                if outcome == "succeeded":
                    target = code_state.assert_action("printing", "confirm")
                    code.status = target
                    code.print_count += 1
                    code.last_printed_workstation_id = workstation.id
                    event_type, result, failure_reason = "printed", "succeeded", None
                else:
                    target = code_state.assert_action("printing", "fail")
                    code.status = target
                    # 明确失败后下次首次打印重新取当天编号；已消耗的编号不回收。
                    from app.models.print_identity import PrintIdentity
                    identity = db.get(PrintIdentity, code.id)
                    if identity is not None and code.print_count == 0:
                        db.delete(identity)
                    # 失败回退不是补打，reprint_count 保持不动（FR-046）
                    event_type = "print_failed"
                    result = "failed"
                    failure_reason = item.get("failure_reason")

                db.add(
                    PrintLog(
                        code_id=code.id,
                        code_value=code.code_value,
                        product_id=code.product_id,
                        company_id=code.company_id,
                        workstation_id=workstation.id,
                        operator_id=operator_id,
                        printer_name=printer_name,
                        template_version_id=template_version_id,
                        print_type="first",
                        result=result,
                        failure_reason=failure_reason,
                        printed_at=now,
                    )
                )
                db.add(
                    CodeEvent(
                        code_id=code.id,
                        event_type=event_type,
                        from_status="printing",
                        to_status=target,
                        operator_id=operator_id,
                        workstation_id=workstation.id,
                        reason=failure_reason,
                        occurred_at=now,
                    )
                )

                code.locked_at = None
                code.locked_workstation_id = None

            done.append(value)
        except ApiError as exc:
            rejected.append(RejectedPrint(value, exc.error_code, exc.message))

    return done, rejected


def _current_template_version(db: Session, code: Code) -> int:
    from app.models.allocation_order import AllocationOrder

    order = (
        db.get(AllocationOrder, code.current_allocation_order_id)
        if code.current_allocation_order_id
        else None
    )
    if order is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "该码没有关联分配单")
    return order.template_version_id


# ---------------------------------------------------------------- 超时回退


def sweep_expired(db: Session, *, timeout_seconds: int | None = None) -> int:
    """把超时未确认的 `printing` 码回退为 `allocated`（FR-047 / FR-048）。

    回退后码可再次正常打印，且**不计补打次数**。
    已知风险（spec 已接受）：若打印机实际已出纸而回执丢失，回退会导致重复出纸；
    因此这里 MUST 写下 timeout_reverted 记录，让该情形事后可审计。
    """
    seconds = timeout_seconds or get_settings().print_lock_timeout_seconds
    threshold = utcnow() - timedelta(seconds=seconds)

    codes = list(
        db.execute(
            select(Code)
            .where(Code.status == "printing", Code.locked_at.is_not(None), Code.locked_at < threshold)
            .with_for_update(skip_locked=True)
        ).scalars()
    )

    now = utcnow()
    for code in codes:
        workstation_id = code.locked_workstation_id
        from_status = code.status
        code.status = "allocated"
        code.locked_at = None
        code.locked_workstation_id = None

        operator_id = _reprint_operator(db, code.id)
        if workstation_id is None or code.company_id is None or operator_id is None:
            # 正常路径不会走到这里：printing 必然来自一次预占，而预占会写
            # print_started 事件（带操作员）并记录工位。真出现说明数据异常，
            # 此时宁可不写记录，也不要伪造一条指向不存在行的记录。
            logger.warning(
                "跳过超时回退的打印记录（缺少工位/公司/操作员）: code=%s", code.code_value
            )
        else:
            workstation = db.get(Workstation, workstation_id)
            db.add(
                PrintLog(
                    code_id=code.id,
                    code_value=code.code_value,
                    product_id=code.product_id,
                    company_id=code.company_id,
                    workstation_id=workstation_id,
                    operator_id=operator_id,
                    printer_name=(workstation.printer_name if workstation else "") or "",
                    template_version_id=_current_template_version(db, code),
                    print_type="first",
                    result="timeout_reverted",
                    failure_reason=f"打印中超过 {seconds} 秒未确认，系统自动回退",
                    printed_at=now,
                )
            )

        db.add(
            CodeEvent(
                code_id=code.id,
                event_type="timeout_reverted",
                from_status=from_status,
                to_status="allocated",
                workstation_id=workstation_id,
                reason="超时未确认，系统自动回退",
                occurred_at=now,
            )
        )

    db.flush()
    return len(codes)
