"""T082：打印确认与失败回退（FR-045 / FR-046 / FR-050）。

关键区别：**失败回退不算补打**。补打是管理员对已打印码的例外操作；
缺纸、离线这类打印失败只是本次没打成，reprint_count 必须保持不动。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.print_log import PrintLog
from app.models.user import User
from app.models.workstation import Workstation
from app.services import printing
from tests.helpers import make_printable

pytestmark = pytest.mark.integration


@pytest.fixture
def printable(db: Session, product, hq_company, import_batch, template_version, hq_admin):
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["P001", "P002", "P003"],
    )
    return ["P001", "P002", "P003"]


def _preempt(db, workstation, operator, *values):
    accepted, rejected = printing.preempt(
        db, workstation=workstation, operator_id=operator.id, code_values=list(values)
    )
    assert not rejected, rejected
    return accepted


class TestSuccessfulConfirmation:
    def test_marks_printed_and_counts(
        self, db: Session, workstation, operator, printable
    ):
        _preempt(db, workstation, operator, "P001")

        confirmed, rejected = printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[{"code_value": "P001", "outcome": "succeeded", "printer_name": "Zebra ZD421"}],
        )

        assert confirmed == ["P001"]
        assert rejected == []
        code = db.execute(select(Code).where(Code.code_value == "P001")).scalar_one()
        assert code.status == "printed"
        assert code.print_count == 1
        assert code.reprint_count == 0
        assert code.last_printed_workstation_id == workstation.id
        assert code.locked_at is None and code.locked_workstation_id is None

    def test_returns_template_payload_before_confirmation(
        self, db: Session, workstation, operator, printable, template_version
    ):
        accepted = _preempt(db, workstation, operator, "P002")
        payload = accepted[0]
        assert payload.template_version_id == template_version.id
        assert payload.elements_json["paper_width_mm"] == 60
        # 动态字段由服务端填充（FR-037）
        assert payload.data["code_value"] == "P002"
        assert payload.data["product_name"] == "500ml 矿泉水"
        assert payload.data["company_name"] == "华东分公司"
        # 批次号取分配单号，不是导入批次号（用户确认的口径）
        assert payload.data["batch_no"].startswith("ALL")


class TestFailureRollback:
    def test_failed_outcome_returns_code_to_allocated(
        self, db: Session, workstation, operator, printable
    ):
        _preempt(db, workstation, operator, "P001")

        confirmed, _ = printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[
                {"code_value": "P001", "outcome": "failed", "failure_reason": "打印机缺纸"}
            ],
        )

        assert confirmed == ["P001"]
        code = db.execute(select(Code).where(Code.code_value == "P001")).scalar_one()
        assert code.status == "allocated"
        assert code.locked_at is None and code.locked_workstation_id is None
        assert code.print_count == 0

    def test_failure_does_not_count_as_reprint(
        self, db: Session, workstation, operator, printable
    ):
        """FR-046 的核心断言。"""
        _preempt(db, workstation, operator, "P002")
        printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[{"code_value": "P002", "outcome": "failed"}],
        )

        code = db.execute(select(Code).where(Code.code_value == "P002")).scalar_one()
        assert code.reprint_count == 0

    def test_failed_code_can_be_printed_again(
        self, db: Session, workstation, operator, printable
    ):
        _preempt(db, workstation, operator, "P003")
        printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[{"code_value": "P003", "outcome": "failed"}],
        )

        accepted, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["P003"]
        )
        assert not rejected
        assert accepted[0].code_value == "P003"

    def test_failure_is_logged_with_reason(
        self, db: Session, workstation, operator, printable
    ):
        _preempt(db, workstation, operator, "P001")
        printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[
                {"code_value": "P001", "outcome": "failed", "failure_reason": "打印机缺纸"}
            ],
        )

        log = db.execute(select(PrintLog)).scalar_one()
        assert log.result == "failed"
        assert log.failure_reason == "打印机缺纸"
        assert log.operator_id == operator.id


class TestConfirmGuards:
    """FR-044 的延伸：只有持有锁的工位能确认。"""

    def test_another_workstation_cannot_confirm(
        self, db: Session, workstation, operator, printable, hq_company
    ):
        other_ws = Workstation(
            code="W002", name="二号工位", company_id=hq_company.id, status="active"
        )
        db.add(other_ws)
        db.flush()

        _preempt(db, workstation, operator, "P001")
        confirmed, rejected = printing.confirm(
            db,
            workstation=other_ws,
            operator_id=operator.id,
            results=[{"code_value": "P001", "outcome": "succeeded"}],
        )

        assert confirmed == []
        assert rejected[0].error_code == "CODE_LOCKED"
        code = db.execute(select(Code).where(Code.code_value == "P001")).scalar_one()
        assert code.status == "printing", "被拒的确认不得改变码状态"

    def test_cannot_confirm_a_code_that_was_never_preempted(
        self, db: Session, workstation, operator, printable
    ):
        confirmed, rejected = printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[{"code_value": "P002", "outcome": "succeeded"}],
        )
        assert confirmed == []
        assert rejected[0].error_code == "CODE_LOCKED"

    def test_cannot_confirm_twice(
        self, db: Session, workstation, operator, printable
    ):
        _preempt(db, workstation, operator, "P003")
        printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[{"code_value": "P003", "outcome": "succeeded"}],
        )

        confirmed, rejected = printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[{"code_value": "P003", "outcome": "succeeded"}],
        )
        assert confirmed == []
        assert rejected[0].error_code == "CODE_LOCKED"
        code = db.execute(select(Code).where(Code.code_value == "P003")).scalar_one()
        assert code.print_count == 1, "重复确认不得把次数刷上去"


class TestBatchConfirmation:
    def test_partial_batch_confirmation_is_independent(
        self, db: Session, workstation, operator, printable
    ):
        _preempt(db, workstation, operator, "P001", "P002")

        confirmed, rejected = printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[
                {"code_value": "P001", "outcome": "succeeded"},
                {"code_value": "P002", "outcome": "failed", "failure_reason": "缺纸"},
            ],
        )

        assert set(confirmed) == {"P001", "P002"}
        assert rejected == []
        states = {
            c.code_value: c.status for c in db.execute(select(Code)).scalars()
        }
        assert states == {"P001": "printed", "P002": "allocated", "P003": "allocated"}

    def test_writes_an_event_per_code(
        self, db: Session, workstation, operator, printable
    ):
        _preempt(db, workstation, operator, "P001", "P002")
        printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[
                {"code_value": "P001", "outcome": "succeeded"},
                {"code_value": "P002", "outcome": "failed"},
            ],
        )

        events = {
            e.event_type
            for e in db.execute(
                select(CodeEvent).where(CodeEvent.event_type.in_(["printed", "print_failed"]))
            ).scalars()
        }
        assert events == {"printed", "print_failed"}


class TestDisabledCompanyBlocksConfirmation:
    def test_company_disabled_mid_flight_blocks_confirm(
        self, db: Session, workstation, operator, printable, hq_company
    ):
        from app.core.errors import ApiError

        _preempt(db, workstation, operator, "P001")
        hq_company.status = "disabled"
        db.flush()

        with pytest.raises(ApiError) as exc:
            printing.confirm(
                db,
                workstation=workstation,
                operator_id=operator.id,
                results=[{"code_value": "P001", "outcome": "succeeded"}],
            )
        assert exc.value.error_code == "WORKSTATION_DISABLED"
