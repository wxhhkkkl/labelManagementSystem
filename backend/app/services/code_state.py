"""T034：码状态机。

集中定义合法流转表与守卫条件。任何流转都必须经过这里，MUST NOT 在业务代码中
直接赋值 Code.status —— 否则 FR-078/FR-079 无法被单点保证与测试。
"""

from app.core.errors import ApiError, ErrorCode

UNALLOCATED = "unallocated"
ALLOCATED = "allocated"
PRINTING = "printing"
PRINTED = "printed"
VOIDED = "voided"

ALL_STATUSES = (UNALLOCATED, ALLOCATED, PRINTING, PRINTED, VOIDED)

# FR-078 的八条合法流转。键为 (当前状态, 动作)，值为目标状态。
TRANSITIONS: dict[tuple[str, str], str] = {
    (UNALLOCATED, "allocate"): ALLOCATED,
    (ALLOCATED, "print"): PRINTING,
    (PRINTING, "confirm"): PRINTED,
    (PRINTING, "fail"): ALLOCATED,
    (PRINTING, "timeout"): ALLOCATED,
    (PRINTED, "reprint"): PRINTED,  # 补打后仍为已打印，仅累加补打次数
    (ALLOCATED, "reclaim"): UNALLOCATED,
    # 作废：三个来源状态共用一条规则
    (UNALLOCATED, "void"): VOIDED,
    (ALLOCATED, "void"): VOIDED,
    (PRINTED, "void"): VOIDED,
}

# 需要填写原因的动作（FR-053 补打、FR-058 作废）
REASON_REQUIRED_ACTIONS = frozenset({"reprint", "void"})

# 非法流转时给出的错误码。未列出的一律用 VALIDATION_ERROR。
_ILLEGAL_ERROR_CODES: dict[tuple[str, str], str] = {
    (PRINTED, "print"): ErrorCode.CODE_ALREADY_PRINTED,
    (PRINTING, "print"): ErrorCode.CODE_LOCKED,
    (UNALLOCATED, "reprint"): ErrorCode.CODE_NOT_PRINTED,
    (ALLOCATED, "reprint"): ErrorCode.CODE_NOT_PRINTED,
    (PRINTING, "reprint"): ErrorCode.CODE_NOT_PRINTED,
    (VOIDED, "void"): ErrorCode.CODE_VOIDED,
}

_ILLEGAL_MESSAGE = "当前状态为「{status}」，不允许执行「{action}」操作"


def _is_blank(reason: str | None) -> bool:
    return reason is None or reason.strip() == ""


def _resolve(status: str, action: str, reason: str | None) -> str:
    if status not in ALL_STATUSES:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"未知的码状态：{status}")

    # FR-059：已作废是终态，先于一切判断
    if status == VOIDED:
        raise ApiError(ErrorCode.CODE_VOIDED, "该码已作废，不可再执行任何操作")

    target = TRANSITIONS.get((status, action))
    if target is None:
        code = _ILLEGAL_ERROR_CODES.get((status, action), ErrorCode.VALIDATION_ERROR)
        raise ApiError(code, _ILLEGAL_MESSAGE.format(status=status, action=action))

    if action in REASON_REQUIRED_ACTIONS and _is_blank(reason):
        label = "补打" if action == "reprint" else "作废"
        raise ApiError(ErrorCode.REASON_REQUIRED, f"{label}必须填写原因")

    return target


def assert_action(status: str, action: str, reason: str | None = None) -> str:
    """校验流转并返回目标状态；非法流转抛 ApiError。"""
    return _resolve(status, action, reason)


def can_perform(status: str, action: str) -> bool:
    """流转是否合法（不含原因守卫），供接口层做前置判断。"""
    return TRANSITIONS.get((status, action)) is not None
