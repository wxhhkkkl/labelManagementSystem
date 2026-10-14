"""T033：码状态机。逐条覆盖 FR-078 的八条合法流转与 FR-079 的非法流转拒绝。

先写并运行至失败，再由 app/services/code_state.py 实现至通过。
"""

import pytest

from app.core.errors import ApiError, ErrorCode
from app.services.code_state import (
    ALLOCATED,
    PRINTED,
    PRINTING,
    UNALLOCATED,
    VOIDED,
    assert_action,
    can_perform,
)


class TestLegalTransitions:
    """FR-078 列举的八条合法流转，一条一个用例。"""

    def test_unallocated_allocate_to_allocated(self):
        assert assert_action(UNALLOCATED, "allocate") == ALLOCATED

    def test_allocated_print_to_printing(self):
        assert assert_action(ALLOCATED, "print") == PRINTING

    def test_printing_confirm_to_printed(self):
        assert assert_action(PRINTING, "confirm") == PRINTED

    def test_printing_fail_back_to_allocated(self):
        assert assert_action(PRINTING, "fail") == ALLOCATED

    def test_printing_timeout_back_to_allocated(self):
        assert assert_action(PRINTING, "timeout") == ALLOCATED

    def test_printed_reprint_stays_printed(self):
        # 补打后仍是"已打印"，只累加补打次数
        assert assert_action(PRINTED, "reprint", reason="标签破损") == PRINTED

    def test_allocated_reclaim_to_unallocated(self):
        assert assert_action(ALLOCATED, "reclaim") == UNALLOCATED

    @pytest.mark.parametrize("status", [UNALLOCATED, ALLOCATED, PRINTED])
    def test_void_from_three_statuses(self, status):
        assert assert_action(status, "void", reason="整批报废") == VOIDED


class TestVoidedIsTerminal:
    """FR-059：已作废为终态，不得流转到任何状态。"""

    @pytest.mark.parametrize(
        "action", ["allocate", "print", "confirm", "fail", "timeout", "reprint", "void"]
    )
    def test_no_action_leaves_voided(self, action):
        with pytest.raises(ApiError) as exc:
            assert_action(VOIDED, action, reason="尝试任何动作")
        assert exc.value.error_code == ErrorCode.CODE_VOIDED

    def test_reclaim_from_voided_rejected(self):
        with pytest.raises(ApiError) as exc:
            assert_action(VOIDED, "reclaim")
        assert exc.value.error_code == ErrorCode.CODE_VOIDED


class TestIllegalTransitions:
    """FR-079：不在 FR-078 列举范围内的流转一律拒绝。"""

    def test_printing_a_printed_code(self):
        # FR-043：核心控制点
        with pytest.raises(ApiError) as exc:
            assert_action(PRINTED, "print")
        assert exc.value.error_code == ErrorCode.CODE_ALREADY_PRINTED

    def test_printing_a_code_already_printing(self):
        # FR-044：并发抢占的落败方
        with pytest.raises(ApiError) as exc:
            assert_action(PRINTING, "print")
        assert exc.value.error_code == ErrorCode.CODE_LOCKED

    def test_reprint_on_non_printed_code(self):
        # FR-051：补打只作用于已打印的码
        for status in (UNALLOCATED, ALLOCATED, PRINTING):
            with pytest.raises(ApiError) as exc:
                assert_action(status, "reprint", reason="理由")
            assert exc.value.error_code == ErrorCode.CODE_NOT_PRINTED

    def test_print_unallocated_code(self):
        # 未分配的码不可打印，但用普通校验错误而非"已打印"
        with pytest.raises(ApiError) as exc:
            assert_action(UNALLOCATED, "print")
        assert exc.value.error_code == ErrorCode.VALIDATION_ERROR

    def test_reclaim_printed_code(self):
        # FR-030：已打印的码不可回收
        with pytest.raises(ApiError) as exc:
            assert_action(PRINTED, "reclaim")
        assert exc.value.error_code == ErrorCode.VALIDATION_ERROR

    def test_unknown_action_rejected(self):
        with pytest.raises(ApiError):
            assert_action(ALLOCATED, "teleport")


class TestReasonGuard:
    """FR-053 / FR-058：补打与作废必填原因。"""

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_reprint_requires_reason(self, blank):
        with pytest.raises(ApiError) as exc:
            assert_action(PRINTED, "reprint", reason=blank)
        assert exc.value.error_code == ErrorCode.REASON_REQUIRED

    @pytest.mark.parametrize("blank", [None, "", "  "])
    def test_void_requires_reason(self, blank):
        with pytest.raises(ApiError) as exc:
            assert_action(PRINTED, "void", reason=blank)
        assert exc.value.error_code == ErrorCode.REASON_REQUIRED

    def test_other_actions_need_no_reason(self):
        assert assert_action(ALLOCATED, "print") == PRINTING


class TestCanPerform:
    """供接口层做前置判断，避免用异常控制流程。"""

    def test_true_for_legal(self):
        assert can_perform(ALLOCATED, "print") is True
        assert can_perform(PRINTED, "reprint") is True

    def test_false_for_illegal(self):
        assert can_perform(PRINTED, "print") is False
        assert can_perform(VOIDED, "allocate") is False
