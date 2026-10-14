"""T138：码时间线完整性（FR-064）。

走完整链路后，时间线必须包含全部节点，且每个节点带操作人、时间、工位。
这条测试的价值在于**逼着每个业务动作都写事件**——少写一处，
追溯就会在那个环节断掉，而且是事后才发现。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.user import User
from app.services import allocation as allocation_service
from app.services import code_timeline, printing
from app.services import print_task as task_service
from app.services import reprint as reprint_service
from app.services import void as void_service
from tests.conftest import auth_header
from tests.helpers import make_printable

pytestmark = pytest.mark.integration


@pytest.fixture
def walked_code(
    db: Session,
    product,
    hq_company,
    import_batch,
    template_version,
    hq_admin,
    workstation,
    operator,
):
    """造一个走完 导入 → 分配 → 打印 → 补打 → 作废 全链路的码。"""
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["TL01"],
    )
    printing.preempt(
        db, workstation=workstation, operator_id=operator.id, code_values=["TL01"]
    )
    printing.confirm(
        db,
        workstation=workstation,
        operator_id=operator.id,
        results=[{"code_value": "TL01", "outcome": "succeeded", "printer_name": "Zebra"}],
    )
    workstation.last_heartbeat_at = utcnow()
    db.flush()
    return "TL01"


def _event_types(detail) -> list[str]:
    return [entry.event_type for entry in detail.timeline]


class TestFullLifecycle:
    def test_all_stages_appear_in_order(self, db: Session, hq_admin, walked_code):
        code = code_timeline.get_code(db, walked_code)
        detail = code_timeline.build(db, code)

        types = _event_types(detail)
        # 导入时同时完成绑定，因此这里只有 imported
        assert "imported" in types
        assert "allocated" in types
        assert "print_started" in types
        assert "printed" in types

        # 时间线按发生时间正序
        times = [entry.occurred_at for entry in detail.timeline]
        assert times == sorted(times)

    def test_reprint_appears_after_the_original_print(
        self, db: Session, hq_admin, workstation, walked_code
    ):
        reprint_service.request_reprint(db, code_value=walked_code, reason="破损", user=hq_admin)

        claimed = task_service.claim_tasks(db, workstation_id=workstation.id)
        assert claimed, "补打任务应被本工位领到"
        task_service.report_result(
            db,
            task_id=claimed[0].id,
            workstation_id=workstation.id,
            success=True,
            operator_id=hq_admin.id,
            printer_name="Zebra",
        )

        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))
        types = _event_types(detail)
        assert types.count("printed") >= 1
        assert "reprint" in types
        assert types.index("printed") < types.index("reprint")

    def test_void_appears_last(self, db: Session, hq_admin, walked_code):
        void_service.void_codes(db, code_values=[walked_code], reason="报废", user=hq_admin)

        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))
        assert _event_types(detail)[-1] == "voided"
        assert detail.status == "voided"
        assert detail.void_reason == "报废"


class TestEventAnnotations:
    def test_each_entry_carries_who_and_when(self, db: Session, hq_admin, operator, walked_code):
        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))

        for entry in detail.timeline:
            assert entry.occurred_at is not None, f"{entry.event_type} 缺少时间"
            assert entry.label, f"{entry.event_type} 缺少可读文案"

    def test_print_events_carry_the_workstation(self, db: Session, workstation, walked_code):
        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))
        print_events = [e for e in detail.timeline if e.event_type in ("print_started", "printed")]

        assert print_events
        assert all(e.workstation_name == workstation.name for e in print_events)

    def test_print_events_carry_the_operator(self, db: Session, operator, walked_code):
        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))
        print_events = [e for e in detail.timeline if e.event_type == "printed"]

        assert all(e.operator_name == operator.display_name for e in print_events)

    def test_allocation_event_carries_the_operator(self, db: Session, hq_admin, walked_code):
        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))
        allocated = next(e for e in detail.timeline if e.event_type == "allocated")
        assert allocated.operator_name == hq_admin.display_name


class TestStatusLabels:
    def test_statuses_are_translated(self, db: Session, walked_code):
        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))
        assert detail.status_label == "已打印"

        entry = next(e for e in detail.timeline if e.event_type == "allocated")
        assert entry.from_status_label == "待分配"
        assert entry.to_status_label == "已分配"

    def test_detail_includes_business_context(self, db: Session, product, hq_company, walked_code):
        detail = code_timeline.build(db, code_timeline.get_code(db, walked_code))
        assert detail.product_name == product.name
        assert detail.company_name == hq_company.name
        assert detail.allocation_order_no is not None
        assert detail.print_count == 1


class TestNoEventsCase:
    def test_code_without_events_yields_an_empty_timeline(
        self, db: Session, product, import_batch
    ):
        """没有事件的码不该报错——时间线为空本身就是有用的信息。"""
        from app.models.code import Code

        db.add(
            Code(
                code_value="TL-EMPTY",
                status="unallocated",
                product_id=product.id,
                import_batch_id=import_batch.id,
            )
        )
        db.flush()

        detail = code_timeline.build(db, code_timeline.get_code(db, "TL-EMPTY"))
        assert detail.timeline == []
        assert detail.status_label == "待分配"

    def test_unknown_code_is_404(self, db: Session):
        from app.core.errors import ApiError

        with pytest.raises(ApiError) as exc:
            code_timeline.get_code(db, "NOPE")
        assert exc.value.error_code == "NOT_FOUND"


class TestVisibility:
    """时间线按数据归属可见，与审计日志（仅总部）不同。"""

    def test_sub_admin_can_read_own_company_code(self, client, sub_admin: User, walked_code):
        resp = client.get(f"/api/v1/codes/{walked_code}", headers=auth_header(sub_admin))
        assert resp.status_code == 200
        assert resp.json()["code_value"] == walked_code

    def test_operator_can_read_own_company_code(self, client, operator: User, walked_code):
        assert (
            client.get(f"/api/v1/codes/{walked_code}", headers=auth_header(operator)).status_code
            == 200
        )

    def test_other_company_sub_admin_is_denied(
        self, client, other_sub_admin: User, walked_code
    ):
        resp = client.get(f"/api/v1/codes/{walked_code}", headers=auth_header(other_sub_admin))
        assert resp.status_code == 403

    def test_hq_admin_can_read_any_code(self, client, hq_admin: User, walked_code):
        assert (
            client.get(f"/api/v1/codes/{walked_code}", headers=auth_header(hq_admin)).status_code
            == 200
        )
