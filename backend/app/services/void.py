"""T107：码作废（FR-057 ~ FR-060）。

作废是**终态**：作废后的码不可见、不可打印、不可恢复（FR-059）。
因此这里的处理原则是"宁可整批拒绝，也不要部分成功"——除了已作废码的幂等跳过。
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.base import utcnow
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.user import User

HQ_ADMIN = "hq_admin"
SUB_ADMIN = "sub_admin"


@dataclass
class VoidResult:
    voided: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _assert_can_void(user: User, code: Code) -> None:
    """作废权限（FR-057）。子公司管理员仅限本公司码。"""
    if user.role == HQ_ADMIN:
        return
    if user.role == SUB_ADMIN and code.company_id == user.company_id:
        return
    raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权对该码执行作废")


def void_codes(db: Session, *, code_values: list[str], reason: str, user: User) -> VoidResult:
    if reason is None or reason.strip() == "":
        raise ApiError(ErrorCode.REASON_REQUIRED, "作废必须填写原因")

    unique_values = list(dict.fromkeys(code_values))
    if not unique_values:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "未指定要作废的码")

    codes = list(
        db.execute(select(Code).where(Code.code_value.in_(unique_values))).scalars()
    )
    found = {c.code_value for c in codes}
    missing = [v for v in unique_values if v not in found]
    if missing:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"以下码不存在：{', '.join(missing[:5])}",
            {"missing": missing[:20]},
        )

    # 权限**先整体校验**：混入他公司的码时整体拒绝，不做部分成功。
    # 部分成功会让调用方以为整批都作废了，而实际只作废了一部分。
    for code in codes:
        _assert_can_void(user, code)

    result = VoidResult()
    now = utcnow()
    trimmed = reason.strip()

    for code in codes:
        if code.status == "voided":
            # 幂等：重复作废不报错，但也不重复写事件
            result.skipped.append(code.code_value)
            continue

        from_status = code.status
        code.status = "voided"
        code.voided_at = now
        code.voided_by = user.id
        code.void_reason = trimmed
        # 作废后不再占用工位锁
        code.locked_at = None
        code.locked_workstation_id = None

        db.add(
            CodeEvent(
                code_id=code.id,
                event_type="voided",
                from_status=from_status,
                to_status="voided",
                operator_id=user.id,
                workstation_id=code.last_printed_workstation_id,
                reason=trimmed,
                occurred_at=now,
            )
        )
        result.voided.append(code.code_value)

    db.flush()
    return result
