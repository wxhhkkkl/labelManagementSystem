"""T104：补打、作废、任务轮询接口契约测试（contracts/admin-api.md、workstation-api.md）。"""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.user import User
from app.models.workstation import Workstation
from tests.conftest import auth_header
from tests.helpers import make_printed

pytestmark = pytest.mark.contract


@pytest.fixture
def printed(db: Session, product, hq_company, import_batch, template_version, hq_admin, workstation, operator):
    make_printed(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        workstation=workstation,
        values=["C001", "C002", "C003"],
    )
    workstation.last_heartbeat_at = utcnow()
    db.flush()
    return ["C001", "C002", "C003"]


def _reprint(client, user, code_value, reason="标签破损"):
    return client.post(
        f"/api/v1/codes/{code_value}/reprint",
        headers=auth_header(user),
        json={"reason": reason},
    )


class TestReprintEndpoint:
    def test_creates_a_task_for_the_original_workstation(
        self, client, hq_admin: User, workstation, printed
    ):
        resp = _reprint(client, hq_admin, "C001")

        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {
            "task_id",
            "code_value",
            "target_workstation_id",
            "target_workstation_name",
            "status",
        }
        assert body["code_value"] == "C001"
        assert body["target_workstation_id"] == workstation.id
        assert body["status"] == "pending"

    def test_missing_reason_is_400(self, client, hq_admin: User, printed):
        resp = client.post(
            "/api/v1/codes/C001/reprint", headers=auth_header(hq_admin), json={"reason": ""}
        )
        assert resp.status_code == 422  # pydantic 的 min_length 先拦下空串

    def test_blank_reason_is_rejected(self, client, hq_admin: User, printed):
        resp = client.post(
            "/api/v1/codes/C001/reprint", headers=auth_header(hq_admin), json={"reason": "   "}
        )
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "REASON_REQUIRED"

    def test_allocated_code_is_409(self, client, db: Session, hq_admin, printed):
        from sqlalchemy import select

        from app.models.code import Code

        code = db.execute(select(Code).where(Code.code_value == "C002")).scalar_one()
        code.status = "allocated"
        db.flush()

        resp = _reprint(client, hq_admin, "C002")
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "CODE_NOT_PRINTED"

    def test_offline_workstation_is_409_and_leaves_state(
        self, client, db: Session, hq_admin, workstation, printed
    ):
        from sqlalchemy import select

        from app.models.code import Code
        from app.models.print_task import PrintTask

        workstation.last_heartbeat_at = utcnow() - timedelta(seconds=300)
        db.flush()

        resp = _reprint(client, hq_admin, "C003")
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "WORKSTATION_OFFLINE"

        code = db.execute(select(Code).where(Code.code_value == "C003")).scalar_one()
        assert code.status == "printed"
        assert list(db.execute(select(PrintTask)).scalars()) == []

    def test_operator_gets_403(self, client, operator: User, printed):
        assert _reprint(client, operator, "C001").status_code == 403

    def test_unknown_code_is_404(self, client, hq_admin: User, workstation, printed):
        assert _reprint(client, hq_admin, "NOPE").status_code == 404

    def test_requires_authentication(self, client, printed):
        resp = client.post("/api/v1/codes/C001/reprint", json={"reason": "x"})
        assert resp.status_code == 401


class TestVoidEndpoint:
    def test_batch_void_returns_both_lists(self, client, hq_admin: User, printed):
        resp = client.post(
            "/api/v1/codes/void",
            headers=auth_header(hq_admin),
            json={"code_values": ["C001", "C002"], "reason": "整批报废"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"voided", "skipped"}
        assert sorted(body["voided"]) == ["C001", "C002"]
        assert body["skipped"] == []

    def test_blank_reason_is_rejected(self, client, hq_admin: User, printed):
        resp = client.post(
            "/api/v1/codes/void",
            headers=auth_header(hq_admin),
            json={"code_values": ["C001"], "reason": "   "},
        )
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "REASON_REQUIRED"

    def test_empty_code_list_is_422(self, client, hq_admin: User):
        resp = client.post(
            "/api/v1/codes/void",
            headers=auth_header(hq_admin),
            json={"code_values": [], "reason": "x"},
        )
        assert resp.status_code == 422

    def test_already_voided_is_reported_as_skipped(self, client, hq_admin: User, printed):
        client.post(
            "/api/v1/codes/void",
            headers=auth_header(hq_admin),
            json={"code_values": ["C001"], "reason": "第一次"},
        )
        resp = client.post(
            "/api/v1/codes/void",
            headers=auth_header(hq_admin),
            json={"code_values": ["C001", "C002"], "reason": "第二次"},
        )
        body = resp.json()
        assert body["voided"] == ["C002"]
        assert body["skipped"] == ["C001"]


class TestTaskPolling:
    def test_workstation_claims_its_task(
        self, client, hq_admin, operator: User, workstation, printed
    ):
        _reprint(client, hq_admin, "C001")

        resp = client.get(
            f"/api/v1/workstation/tasks?workstation_id={workstation.id}",
            headers=auth_header(operator),
        )
        assert resp.status_code == 200

        tasks = resp.json()["tasks"]
        assert len(tasks) == 1
        assert set(tasks[0]) == {
            "task_id",
            "task_type",
            "code_value",
            "template_version_id",
            "elements_json",
            "data",
            "product_name",
            "company_name",
            "reason",
        }
        assert tasks[0]["code_value"] == "C001"
        assert tasks[0]["reason"] == "标签破损"
        # 模板内容随任务下发，工位端拿到就能直接渲染，无需再取一次模板
        assert tasks[0]["elements_json"]["paper_width_mm"] == 60
        assert tasks[0]["data"]["code_value"] == "C001"

    def test_empty_poll_returns_empty_list(
        self, client, operator: User, workstation
    ):
        resp = client.get(
            f"/api/v1/workstation/tasks?workstation_id={workstation.id}",
            headers=auth_header(operator),
        )
        assert resp.status_code == 200
        assert resp.json()["tasks"] == []

    def test_second_poll_returns_nothing(self, client, hq_admin, operator, workstation, printed):
        _reprint(client, hq_admin, "C001")
        url = f"/api/v1/workstation/tasks?workstation_id={workstation.id}"

        client.get(url, headers=auth_header(operator))
        again = client.get(url, headers=auth_header(operator))
        assert again.json()["tasks"] == []

    def test_other_company_workstation_is_forbidden(
        self, client, db: Session, operator: User, other_company
    ):
        foreign = Workstation(code="W900", name="他公司工位", company_id=other_company.id)
        db.add(foreign)
        db.flush()

        resp = client.get(
            f"/api/v1/workstation/tasks?workstation_id={foreign.id}",
            headers=auth_header(operator),
        )
        assert resp.status_code == 403

    def test_result_report_on_success_increments_reprint_count(
        self, client, db: Session, hq_admin, operator, workstation, printed
    ):
        task_id = _reprint(client, hq_admin, "C001").json()["task_id"]
        client.get(
            f"/api/v1/workstation/tasks?workstation_id={workstation.id}",
            headers=auth_header(operator),
        )

        resp = client.post(
            f"/api/v1/workstation/tasks/{task_id}/result?workstation_id={workstation.id}",
            headers=auth_header(operator),
            json={"result": "succeeded"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "succeeded"
        assert body["reprint_count"] == 1

    def test_result_report_on_failure_does_not_increment(
        self, client, hq_admin, operator, workstation, printed
    ):
        task_id = _reprint(client, hq_admin, "C002").json()["task_id"]
        client.get(
            f"/api/v1/workstation/tasks?workstation_id={workstation.id}",
            headers=auth_header(operator),
        )

        resp = client.post(
            f"/api/v1/workstation/tasks/{task_id}/result?workstation_id={workstation.id}",
            headers=auth_header(operator),
            json={"result": "failed", "failure_reason": "缺纸"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
        assert resp.json()["reprint_count"] == 0

    def test_reporting_without_claiming_is_rejected(
        self, client, hq_admin, operator, workstation, printed
    ):
        task_id = _reprint(client, hq_admin, "C003").json()["task_id"]
        resp = client.post(
            f"/api/v1/workstation/tasks/{task_id}/result?workstation_id={workstation.id}",
            headers=auth_header(operator),
            json={"result": "succeeded"},
        )
        assert resp.status_code == 422


class TestLedger:
    def test_ledger_lists_reprints_and_voids(self, client, hq_admin: User, printed):
        _reprint(client, hq_admin, "C001")
        client.post(
            "/api/v1/codes/void",
            headers=auth_header(hq_admin),
            json={"code_values": ["C002"], "reason": "报废"},
        )

        body = client.get("/api/v1/reprints", headers=auth_header(hq_admin)).json()
        kinds = {entry["kind"] for entry in body}
        assert kinds == {"reprint", "void"}

        reprint_entry = next(e for e in body if e["kind"] == "reprint")
        assert reprint_entry["reason"] == "标签破损"
        void_entry = next(e for e in body if e["kind"] == "void")
        assert void_entry["reason"] == "报废"

    def test_sub_admin_sees_only_own_company(
        self, client, db: Session, hq_admin, sub_admin, other_company, other_sub_admin, printed, product, import_batch
    ):
        from app.models.code import Code

        # 造一个属于他公司的已作废码
        foreign = Code(
            code_value="FOREIGN-L",
            status="voided",
            product_id=product.id,
            company_id=other_company.id,
            import_batch_id=import_batch.id,
            voided_at=utcnow(),
            void_reason="他公司报废",
        )
        db.add(foreign)
        db.flush()

        client.post(
            "/api/v1/codes/void",
            headers=auth_header(hq_admin),
            json={"code_values": ["C001"], "reason": "本公司报废"},
        )

        body = client.get("/api/v1/reprints", headers=auth_header(sub_admin)).json()
        assert all(e["code_value"] != "FOREIGN-L" for e in body)

        other = client.get("/api/v1/reprints", headers=auth_header(other_sub_admin)).json()
        assert all(e["code_value"] != "C001" for e in other)
