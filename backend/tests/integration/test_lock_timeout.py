"""T086：打印中超时回退（FR-047 / FR-048）。

工位软件崩溃或回执丢失时，码会卡在 `printing`：既不能再打印、也不在"已分配未打印"里，
等于凭空消失。超时回退把它放回可打印状态。

**已知取舍**：若实际已出纸而回执丢失，回退后会造成重复出纸。spec 明确接受这个风险，
代价是必须留下 timeout_reverted 记录供审计——最后的用例专门锁住这一点。
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.print_log import PrintLog
from app.models.print_task import PrintTask  # noqa: F401  (确保映射已加载)
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
        values=["T001", "T002", "T003"],
    )
    return ["T001", "T002", "T003"]


def _age_lock(db: Session, code_value: str, seconds: int) -> None:
    """把码的锁定时间往前推，模拟长时间未确认。"""
    code = db.execute(select(Code).where(Code.code_value == code_value)).scalar_one()
    code.locked_at = utcnow() - timedelta(seconds=seconds)
    db.flush()


class TestOverdueLocksAreReverted:
    def test_expired_lock_returns_to_allocated(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T001"]
        )
        _age_lock(db, "T001", 3600)  # 远超默认 300 秒

        reverted = printing.sweep_expired(db)

        assert reverted == 1
        code = db.execute(select(Code).where(Code.code_value == "T001")).scalar_one()
        assert code.status == "allocated"
        assert code.locked_at is None
        assert code.locked_workstation_id is None

    def test_timeout_revert_does_not_count_as_reprint(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T002"]
        )
        _age_lock(db, "T002", 3600)

        printing.sweep_expired(db)

        code = db.execute(select(Code).where(Code.code_value == "T002")).scalar_one()
        assert code.print_count == 0
        assert code.reprint_count == 0, "超时回退不是补打（FR-048）"

    def test_reverted_code_can_be_printed_again(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T003"]
        )
        _age_lock(db, "T003", 3600)
        printing.sweep_expired(db)

        accepted, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T003"]
        )
        assert not rejected
        assert accepted[0].code_value == "T003"


class TestFreshLocksAreKept:
    def test_recent_lock_is_not_swept(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T001"]
        )
        _age_lock(db, "T001", 5)  # 刚刚锁定

        assert printing.sweep_expired(db) == 0
        code = db.execute(select(Code).where(Code.code_value == "T001")).scalar_one()
        assert code.status == "printing"

    def test_custom_threshold_is_honoured(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T002"]
        )
        _age_lock(db, "T002", 30)

        assert printing.sweep_expired(db, timeout_seconds=60) == 0
        assert printing.sweep_expired(db, timeout_seconds=10) == 1

    def test_allocated_and_printed_codes_are_untouched(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T001"]
        )
        printing.confirm(
            db,
            workstation=workstation,
            operator_id=operator.id,
            results=[{"code_value": "T001", "outcome": "succeeded"}],
        )

        assert printing.sweep_expired(db) == 0
        states = {c.code_value: c.status for c in db.execute(select(Code)).scalars()}
        assert states["T001"] == "printed"
        assert states["T002"] == "allocated"


class TestTimeoutLeavesAnAuditTrail:
    """spec 接受的重复出纸风险，靠这条记录事后可查。"""

    def test_writes_timeout_reverted_print_log(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T001"]
        )
        _age_lock(db, "T001", 3600)

        printing.sweep_expired(db)

        log = db.execute(
            select(PrintLog).where(PrintLog.result == "timeout_reverted")
        ).scalar_one()
        assert log.code_value == "T001"

    def test_print_log_is_attributed_to_the_operator_who_started_it(
        self, db: Session, workstation, operator, printable
    ):
        """系统动作也要归到发起打印的操作员名下，否则 SC-006 的可追溯性会缺口。"""
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T002"]
        )
        _age_lock(db, "T002", 3600)

        printing.sweep_expired(db)

        log = db.execute(
            select(PrintLog).where(PrintLog.result == "timeout_reverted")
        ).scalar_one()
        assert log.operator_id == operator.id
        assert log.workstation_id == workstation.id

    def test_writes_timeout_reverted_code_event(
        self, db: Session, workstation, operator, printable
    ):
        printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["T003"]
        )
        _age_lock(db, "T003", 3600)

        printing.sweep_expired(db)

        event = db.execute(
            select(CodeEvent).where(CodeEvent.event_type == "timeout_reverted")
        ).scalar_one()
        assert event.from_status == "printing"
        assert event.to_status == "allocated"
