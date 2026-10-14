"""T100：补打派发与离线拒绝（FR-055 / FR-056，research.md R1）。

这是轮询模型的验证重点：补打**必须落回原工位**，且原工位不可用时
必须拒绝**且不改变码状态**——否则码会卡在半截状态。
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.base import utcnow
from app.models.code import Code
from app.models.print_task import PrintTask
from app.models.user import User
from app.models.workstation import Workstation
from app.services import print_task as task_service
from app.services import reprint as reprint_service
from tests.helpers import make_printable, make_printed

pytestmark = pytest.mark.integration


@pytest.fixture
def printed(db: Session, product, hq_company, import_batch, template_version, hq_admin, workstation, operator):
    make_printed(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        workstation=workstation,
        values=["R001", "R002", "R003"],
    )
    return ["R001", "R002", "R003"]


def _heartbeat(db: Session, workstation: Workstation) -> None:
    workstation.last_heartbeat_at = utcnow()
    db.flush()


def _go_offline(db: Session, workstation: Workstation, seconds: int = 120) -> None:
    workstation.last_heartbeat_at = utcnow() - timedelta(seconds=seconds)
    db.flush()


class TestDispatchToOriginalWorkstation:
    def test_task_targets_the_workstation_that_printed_it(
        self, db: Session, hq_admin: User, workstation, printed
    ):
        _heartbeat(db, workstation)

        task = reprint_service.request_reprint(
            db, code_value="R001", reason="标签破损", user=hq_admin
        )

        assert task.target_workstation_id == workstation.id
        assert task.task_type == "reprint"
        assert task.status == "pending"
        assert task.reason == "标签破损"

    def test_task_carries_the_allocation_template_version(
        self, db: Session, hq_admin, workstation, printed, template_version
    ):
        _heartbeat(db, workstation)
        task = reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)
        assert task.template_version_id == template_version.id

    def test_code_status_is_untouched_by_the_request(
        self, db: Session, hq_admin, workstation, printed
    ):
        """补打次数在工位端回报成功后才 +1，请求本身不改状态。"""
        _heartbeat(db, workstation)
        reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)

        code = db.execute(select(Code).where(Code.code_value == "R001")).scalar_one()
        assert code.status == "printed"
        assert code.reprint_count == 0


class TestOfflineRejection:
    def test_offline_workstation_is_rejected(self, db: Session, hq_admin, workstation, printed):
        _go_offline(db, workstation)

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)
        assert exc.value.error_code == "WORKSTATION_OFFLINE"

    def test_rejected_request_leaves_no_task_and_no_state_change(
        self, db: Session, hq_admin, workstation, printed
    ):
        """FR-056 的关键断言：拒绝时不留任何痕迹。"""
        _go_offline(db, workstation)

        with pytest.raises(ApiError):
            reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)

        assert list(db.execute(select(PrintTask)).scalars()) == []
        code = db.execute(select(Code).where(Code.code_value == "R001")).scalar_one()
        assert code.status == "printed"
        assert code.reprint_count == 0

    def test_never_reported_workstation_is_offline(
        self, db: Session, hq_admin, workstation, printed
    ):
        workstation.last_heartbeat_at = None
        db.flush()

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)
        assert exc.value.error_code == "WORKSTATION_OFFLINE"

    def test_disabled_workstation_is_rejected_as_disabled_not_offline(
        self, db: Session, hq_admin, workstation, printed
    ):
        _heartbeat(db, workstation)
        workstation.status = "disabled"
        db.flush()

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)
        assert exc.value.error_code == "WORKSTATION_DISABLED"

    def test_disabled_company_is_rejected(
        self, db: Session, hq_admin, workstation, printed, hq_company
    ):
        _heartbeat(db, workstation)
        hq_company.status = "disabled"
        db.flush()

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)
        assert exc.value.error_code == "WORKSTATION_DISABLED"

    def test_recovering_heartbeat_allows_reprint(
        self, db: Session, hq_admin, workstation, printed
    ):
        _go_offline(db, workstation)
        with pytest.raises(ApiError):
            reprint_service.request_reprint(db, code_value="R002", reason="破损", user=hq_admin)

        _heartbeat(db, workstation)
        task = reprint_service.request_reprint(db, code_value="R002", reason="破损", user=hq_admin)
        assert task.target_workstation_id == workstation.id


class TestNonPrintedCodes:
    def test_allocated_code_cannot_be_reprinted(
        self, db: Session, hq_admin, workstation, product, import_batch, hq_company, template_version
    ):
        make_printable(
            db,
            product=product,
            batch=import_batch,
            company=hq_company,
            operator_id=hq_admin.id,
            values=["A100"],
        )
        _heartbeat(db, workstation)

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="A100", reason="破损", user=hq_admin)
        assert exc.value.error_code == "CODE_NOT_PRINTED"

    def test_voided_code_cannot_be_reprinted(self, db: Session, hq_admin, workstation, printed):
        _heartbeat(db, workstation)
        code = db.execute(select(Code).where(Code.code_value == "R003")).scalar_one()
        code.status = "voided"
        db.flush()

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="R003", reason="破损", user=hq_admin)
        assert exc.value.error_code == "CODE_NOT_PRINTED"

    def test_unknown_code_is_404(self, db: Session, hq_admin, workstation):
        _heartbeat(db, workstation)
        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="NOPE", reason="x", user=hq_admin)
        assert exc.value.error_code == "NOT_FOUND"


class TestTaskClaiming:
    def test_claiming_marks_the_task_claimed(self, db: Session, hq_admin, workstation, printed):
        _heartbeat(db, workstation)
        reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)

        claimed = task_service.claim_tasks(db, workstation_id=workstation.id)

        assert len(claimed) == 1
        assert claimed[0].status == "claimed"
        assert claimed[0].claimed_at is not None

    def test_claiming_twice_returns_nothing_the_second_time(
        self, db: Session, hq_admin, workstation, printed
    ):
        _heartbeat(db, workstation)
        reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)

        task_service.claim_tasks(db, workstation_id=workstation.id)
        again = task_service.claim_tasks(db, workstation_id=workstation.id)

        assert again == []

    def test_no_pending_tasks_returns_empty_without_writing(self, db: Session, workstation):
        """R1：5 秒一次的轮询，空轮询不得产生写入。"""
        before = list(db.execute(select(PrintTask)).scalars())
        claimed = task_service.claim_tasks(db, workstation_id=workstation.id)
        after = list(db.execute(select(PrintTask)).scalars())
        assert claimed == []
        assert before == after

    def test_other_workstation_cannot_claim(
        self, db: Session, hq_admin, workstation, printed, hq_company
    ):
        other = Workstation(code="W900", name="别的工位", company_id=hq_company.id)
        db.add(other)
        db.flush()

        _heartbeat(db, workstation)
        reprint_service.request_reprint(db, code_value="R001", reason="破损", user=hq_admin)

        assert task_service.claim_tasks(db, workstation_id=other.id) == []
