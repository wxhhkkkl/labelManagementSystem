"""T141：码全生命周期时间线（FR-064）。

数据源是 `CodeEvent` 而不是 `AuditLog`：两者的可见范围不同——
审计日志仅总部可查（FR-062），而码时间线要按数据归属可见。
混用会导致越权，或者该看的人看不到（见 plan.md 对 CodeEvent 存在的说明）。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.allocation_order import AllocationOrder
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.company import Company
from app.models.product import Product
from app.models.template import TemplateVersion
from app.models.user import User
from app.models.workstation import Workstation

# 事件类型 → 展示用文案。顺序即时间线可读性的基础。
EVENT_LABELS: dict[str, str] = {
    "imported": "导入",
    "bound": "绑定产品",
    "allocated": "分配",
    "reclaimed": "回收",
    "print_started": "开始打印",
    "printed": "打印完成",
    "print_failed": "打印失败",
    "reprint": "补打",
    "voided": "作废",
    "timeout_reverted": "超时回退",
}

STATUS_LABELS: dict[str, str] = {
    "unallocated": "待分配",
    "allocated": "已分配",
    "printing": "打印中",
    "printed": "已打印",
    "voided": "已作废",
}


@dataclass
class TimelineEntry:
    event_type: str
    label: str
    from_status: str | None
    from_status_label: str | None
    to_status: str | None
    to_status_label: str | None
    operator_name: str | None
    workstation_name: str | None
    reason: str | None
    occurred_at: object


@dataclass
class CodeDetail:
    code_value: str
    status: str
    status_label: str
    product_name: str | None
    company_name: str | None
    allocation_order_no: str | None
    template_version_id: int | None
    print_count: int
    reprint_count: int
    void_reason: str | None
    timeline: list[TimelineEntry]


def _label(mapping: dict[str, str], key: str | None) -> str | None:
    if key is None:
        return None
    return mapping.get(key, key)


def build(db: Session, code: Code) -> CodeDetail:
    """组装一个码的完整时间线。

    时间线按发生时间正序——追溯是"从头看下来"的动作。
    """
    events = list(
        db.execute(
            select(CodeEvent)
            .where(CodeEvent.code_id == code.id)
            .order_by(CodeEvent.occurred_at, CodeEvent.id)
        ).scalars()
    )

    operator_ids = {e.operator_id for e in events if e.operator_id}
    workstation_ids = {e.workstation_id for e in events if e.workstation_id}

    operator_names: dict[int, str] = {}
    if operator_ids:
        operator_names = dict(
            db.execute(
                select(User.id, User.display_name).where(User.id.in_(operator_ids))
            ).all()
        )
    workstation_names: dict[int, str] = {}
    if workstation_ids:
        workstation_names = dict(
            db.execute(
                select(Workstation.id, Workstation.name).where(
                    Workstation.id.in_(workstation_ids)
                )
            ).all()
        )

    order = (
        db.get(AllocationOrder, code.current_allocation_order_id)
        if code.current_allocation_order_id
        else None
    )

    timeline = [
        TimelineEntry(
            event_type=event.event_type,
            label=_label(EVENT_LABELS, event.event_type) or event.event_type,
            from_status=event.from_status,
            from_status_label=_label(STATUS_LABELS, event.from_status),
            to_status=event.to_status,
            to_status_label=_label(STATUS_LABELS, event.to_status),
            operator_name=operator_names.get(event.operator_id) if event.operator_id else None,
            workstation_name=(
                workstation_names.get(event.workstation_id) if event.workstation_id else None
            ),
            reason=event.reason,
            occurred_at=event.occurred_at,
        )
        for event in events
    ]

    product = db.get(Product, code.product_id) if code.product_id else None
    company = db.get(Company, code.company_id) if code.company_id else None

    return CodeDetail(
        code_value=code.code_value,
        status=code.status,
        status_label=_label(STATUS_LABELS, code.status) or code.status,
        product_name=product.name if product else None,
        company_name=company.name if company else None,
        allocation_order_no=order.order_no if order else None,
        template_version_id=order.template_version_id if order else None,
        print_count=code.print_count,
        reprint_count=code.reprint_count,
        void_reason=code.void_reason,
        timeline=timeline,
    )


def get_code(db: Session, code_value: str) -> Code:
    code = db.execute(select(Code).where(Code.code_value == code_value)).scalar_one_or_none()
    if code is None:
        raise ApiError(ErrorCode.NOT_FOUND, "码不存在")
    return code


def template_of(db: Session, detail: CodeDetail) -> TemplateVersion | None:
    if detail.template_version_id is None:
        return None
    return db.get(TemplateVersion, detail.template_version_id)
