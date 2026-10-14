"""T063：码—产品绑定与换绑（FR-022 ~ FR-024）。

规则：
  * 导入时经"码—产品"对照关系完成绑定（FR-019，由 import_worker 落在 Code.product_id）
  * 导入后可在码池中按批次批量绑定或换绑（本模块）
  * 已分配的码 MUST NOT 换绑；已打印的码 MUST NOT 任何绑定变更（FR-023）
  * 一个码同一时间只属于一个产品（FR-024，由 product_id 单值外键保证）
"""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.base import utcnow
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.services import product as product_service

# 允许改绑的状态：仅尚未进入分配流程的码
REBINDABLE_STATUS = "unallocated"


@dataclass
class BindResult:
    rebound: int = 0
    skipped: int = 0
    skipped_reasons: list[str] = field(default_factory=list)


def bind_batch(
    db: Session,
    *,
    batch_id: int,
    product_id: int,
    operator_id: int | None = None,
    code_range_from: str | None = None,
    code_range_to: str | None = None,
) -> BindResult:
    """把某导入批次下仍可改绑的码批量绑定到指定产品。

    不可改绑的码**按行跳过**而不是整批拒绝：换绑是码池内的整理动作，
    已经分配出去的码不属于该批次的可操作范围，让整批失败反而阻塞正常整理。
    """
    product = product_service.get_product(db, product_id)
    if product.status != "active":
        raise ApiError(ErrorCode.VALIDATION_ERROR, "停用的产品不可绑定新码")

    stmt = select(Code).where(Code.import_batch_id == batch_id)
    if code_range_from:
        stmt = stmt.where(Code.code_value >= code_range_from)
    if code_range_to:
        stmt = stmt.where(Code.code_value <= code_range_to)
    codes = list(db.execute(stmt).scalars())

    result = BindResult()
    now = utcnow()
    for code in codes:
        if code.status != REBINDABLE_STATUS:
            result.skipped += 1
            if len(result.skipped_reasons) < 100:
                result.skipped_reasons.append(f"{code.code_value}（当前状态 {code.status}）")
            continue
        if code.product_id == product_id:
            continue
        code.product_id = product_id
        db.add(
            CodeEvent(
                code_id=code.id,
                event_type="bound",
                from_status=code.status,
                to_status=code.status,
                operator_id=operator_id,
                occurred_at=now,
            )
        )
        result.rebound += 1

    db.flush()
    return result


def bind_single(
    db: Session, *, code_value: str, product_id: int, operator_id: int | None = None
) -> Code:
    """单个码换绑。已分配或已打印的码一律拒绝（FR-023）。"""
    product = product_service.get_product(db, product_id)
    if product.status != "active":
        raise ApiError(ErrorCode.VALIDATION_ERROR, "停用的产品不可绑定新码")

    code = db.execute(select(Code).where(Code.code_value == code_value)).scalar_one_or_none()
    if code is None:
        raise ApiError(ErrorCode.NOT_FOUND, "码不存在")
    if code.status != REBINDABLE_STATUS:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"码当前状态为「{code.status}」，不允许变更绑定",
        )

    code.product_id = product_id
    db.add(
        CodeEvent(
            code_id=code.id,
            event_type="bound",
            from_status=code.status,
            to_status=code.status,
            operator_id=operator_id,
            occurred_at=utcnow(),
        )
    )
    db.flush()
    return code


def count_by_batch(db: Session, batch_id: int) -> dict[str, int]:
    """按状态汇总某批次的码，供导入结果展示。"""
    rows = db.execute(
        select(Code.status, func.count())
        .where(Code.import_batch_id == batch_id)
        .group_by(Code.status)
    ).all()
    return {status: int(count) for status, count in rows}
