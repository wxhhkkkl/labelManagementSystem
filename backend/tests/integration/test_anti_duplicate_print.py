"""T080：防重复打印 —— 系统的核心控制点（FR-042 / FR-043）。

这是整个项目最不能失败的断言：一码正常只允许打印一次。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.code import Code
from app.models.user import User
from app.models.workstation import Workstation
from app.services import printing
from tests.helpers import make_printable

pytestmark = pytest.mark.integration


@pytest.fixture
def printable(db: Session, product, hq_company, import_batch, template_version, hq_admin, workstation):
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["D001", "D002", "D003"],
    )
    return ["D001", "D002", "D003"]


def _print_and_confirm(db, workstation: Workstation, operator: User, value: str) -> None:
    """走完一次正常打印：预占 -> 确认成功。"""
    accepted, rejected = printing.preempt(
        db, workstation=workstation, operator_id=operator.id, code_values=[value]
    )
    assert not rejected, rejected
    printing.confirm(
        db,
        workstation=workstation,
        operator_id=operator.id,
        results=[{"code_value": value, "outcome": "succeeded", "printer_name": "Zebra ZD421"}],
    )


class TestPrintedCodeIsRejected:
    def test_second_print_of_a_printed_code_is_rejected(
        self, db: Session, workstation, operator, hq_admin, printable
    ):
        _print_and_confirm(db, workstation, operator, "D001")

        accepted, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["D001"]
        )

        assert accepted == []
        assert len(rejected) == 1
        assert rejected[0].error_code == "CODE_ALREADY_PRINTED"

    def test_code_state_unchanged_after_rejection(
        self, db: Session, workstation, operator, printable
    ):
        _print_and_confirm(db, workstation, operator, "D002")

        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["D002"]
        )

        code = db.execute(select(Code).where(Code.code_value == "D002")).scalar_one()
        assert code.status == "printed"
        assert code.print_count == 1
        assert code.locked_at is None, "被拒的重复打印不得留下锁"

    def test_voided_code_rejected_with_its_own_error(
        self, db: Session, workstation, operator, printable
    ):
        code = db.execute(select(Code).where(Code.code_value == "D003")).scalar_one()
        code.status = "voided"
        db.flush()

        _, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["D003"]
        )
        assert rejected[0].error_code == "CODE_VOIDED"

    def test_never_allocated_code_cannot_be_printed(
        self, db: Session, workstation, operator, product, import_batch
    ):
        """池中未分配的码不属于任何公司，因此按"不属于本公司"拒绝。

        归属校验刻意排在状态机之前：这样不会告诉调用方"这个码存在但它还没分配"，
        池内码的存在性不该通过打印接口被探测到。
        """
        db.add(
            Code(
                code_value="POOLONLY",
                status="unallocated",
                product_id=product.id,
                import_batch_id=import_batch.id,
            )
        )
        db.flush()

        _, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["POOLONLY"]
        )
        assert rejected[0].error_code == "FORBIDDEN_SCOPE"

    def test_unknown_code_is_404(self, db: Session, workstation, operator):
        _, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["NOPE"]
        )
        assert rejected[0].error_code == "NOT_FOUND"

    def test_code_of_another_company_is_rejected(
        self, db: Session, workstation, operator, other_company, printable
    ):
        code = db.execute(select(Code).where(Code.code_value == "D001")).scalar_one()
        code.company_id = other_company.id
        db.flush()

        _, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["D001"]
        )
        assert rejected[0].error_code == "FORBIDDEN_SCOPE"


class TestPrintRecordIsWritten:
    """FR-050：每一次打印动作都留记录。"""

    def test_success_writes_a_first_print_log(
        self, db: Session, workstation, operator, printable
    ):
        from app.models.print_log import PrintLog

        _print_and_confirm(db, workstation, operator, "D001")

        logs = list(db.execute(select(PrintLog)).scalars())
        assert len(logs) == 1
        log = logs[0]
        assert log.print_type == "first"
        assert log.result == "succeeded"
        assert log.code_value == "D001"
        # SC-006：可追溯到操作员 + 工位 + 打印机
        assert log.operator_id == operator.id
        assert log.workstation_id == workstation.id
        assert log.printer_name == "Zebra ZD421"

    def test_confirm_increments_print_count(
        self, db: Session, workstation, operator, printable
    ):
        _print_and_confirm(db, workstation, operator, "D002")
        code = db.execute(select(Code).where(Code.code_value == "D002")).scalar_one()
        assert code.print_count == 1
        assert code.reprint_count == 0
        assert code.last_printed_workstation_id == workstation.id


class TestBatchPartialFailure:
    """FR-049：批量任务逐码独立，部分失败不影响其余。"""

    def test_mixed_batch_accepts_the_good_ones(
        self, db: Session, workstation, operator, printable
    ):
        _print_and_confirm(db, workstation, operator, "D001")

        accepted, rejected = printing.preempt(
            db,
            workstation=workstation,
            operator_id=operator.id,
            code_values=["D002", "D001", "D003"],
        )

        assert {a.code_value for a in accepted} == {"D002", "D003"}
        assert [r.code_value for r in rejected] == ["D001"]

    def test_duplicate_value_within_one_request_is_rejected(
        self, db: Session, workstation, operator, printable
    ):
        accepted, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["D001", "D001"]
        )
        assert len(accepted) == 1
        assert rejected[0].error_code == "CODE_LOCKED"


class TestDisabledWorkstation:
    def test_disabled_workstation_cannot_print(
        self, db: Session, workstation, operator, printable
    ):
        workstation.status = "disabled"
        db.flush()

        with pytest.raises(ApiError) as exc:
            printing.preempt(
                db, workstation=workstation, operator_id=operator.id, code_values=["D001"]
            )
        assert exc.value.error_code == "WORKSTATION_DISABLED"

    def test_workstation_of_disabled_company_cannot_print(
        self, db: Session, workstation, operator, hq_company, printable
    ):
        hq_company.status = "disabled"
        db.flush()

        with pytest.raises(ApiError) as exc:
            printing.preempt(
                db, workstation=workstation, operator_id=operator.id, code_values=["D001"]
            )
        assert exc.value.error_code == "WORKSTATION_DISABLED"
