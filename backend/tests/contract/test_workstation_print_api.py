"""T084：工位端打印接口契约测试（contracts/workstation-api.md）。

含 T083 的核心用例：确认请求来自非持锁工位时返回 CODE_LOCKED。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.user import User
from app.models.workstation import Workstation
from tests.conftest import auth_header
from tests.helpers import make_printable

pytestmark = pytest.mark.contract


@pytest.fixture
def printable(db: Session, product, hq_company, import_batch, template_version, hq_admin):
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["K001", "K002", "K003"],
    )
    return ["K001", "K002", "K003"]


def _print(client, operator, workstation_id, values):
    return client.post(
        "/api/v1/workstation/print",
        headers=auth_header(operator),
        json={"workstation_id": workstation_id, "code_values": values, "printer_name": "Zebra ZD421"},
    )


class TestListPrintableCodes:
    def test_lists_own_company_codes(
        self, client, operator: User, workstation, product, printable
    ):
        resp = client.get(
            f"/api/v1/workstation/codes?workstation_id={workstation.id}&product_id={product.id}",
            headers=auth_header(operator),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert {i["code_value"] for i in body["items"]} == {"K001", "K002", "K003"}
        # 契约明确声明可见范围是整个公司
        assert "共享" in body["screen_scope_note"]

    def test_printed_codes_drop_out_of_the_list(
        self, client, db: Session, operator, workstation, product, printable
    ):
        _print(client, operator, workstation.id, ["K001"])
        client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [{"code_value": "K001", "outcome": "succeeded"}],
            },
        )

        body = client.get(
            f"/api/v1/workstation/codes?workstation_id={workstation.id}&product_id={product.id}",
            headers=auth_header(operator),
        ).json()
        assert {i["code_value"] for i in body["items"]} == {"K002", "K003"}

    def test_other_company_workstation_is_forbidden(
        self, client, db: Session, operator: User, other_company
    ):
        foreign = Workstation(code="W900", name="他公司工位", company_id=other_company.id)
        db.add(foreign)
        db.flush()

        resp = client.get(
            f"/api/v1/workstation/codes?workstation_id={foreign.id}&product_id=1",
            headers=auth_header(operator),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"

    def test_unknown_workstation_is_404(self, client, operator: User):
        resp = client.get(
            "/api/v1/workstation/codes?workstation_id=999999&product_id=1",
            headers=auth_header(operator),
        )
        assert resp.status_code == 404


class TestScanSingleCode:
    def test_returns_printable_code(
        self, client, operator: User, workstation, printable
    ):
        resp = client.get(
            f"/api/v1/workstation/codes/K001?workstation_id={workstation.id}",
            headers=auth_header(operator),
        )
        assert resp.status_code == 200
        assert resp.json()["code_value"] == "K001"
        assert resp.json()["status"] == "allocated"

    def test_already_printed_code_is_rejected(
        self, client, operator, workstation, printable
    ):
        _print(client, operator, workstation.id, ["K002"])
        client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [{"code_value": "K002", "outcome": "succeeded"}],
            },
        )

        resp = client.get(
            f"/api/v1/workstation/codes/K002?workstation_id={workstation.id}",
            headers=auth_header(operator),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "CODE_ALREADY_PRINTED"


class TestPreemptEndpoint:
    def test_response_shape(self, client, operator: User, workstation, printable):
        resp = _print(client, operator, workstation.id, ["K001"])
        assert resp.status_code == 200

        body = resp.json()
        assert set(body) == {"accepted", "rejected"}
        item = body["accepted"][0]
        # 工位端拿这些字段去渲染（contracts/template-rendering.md）
        assert set(item) == {"code_value", "template_version_id", "elements_json", "data"}
        assert item["code_value"] == "K001"
        assert item["data"]["code_value"] == "K001"
        assert item["data"]["batch_no"].startswith("ALL")
        assert "paper_width_mm" in item["elements_json"]

    def test_printed_code_comes_back_as_rejected_not_error(
        self, client, operator, workstation, printable
    ):
        _print(client, operator, workstation.id, ["K003"])
        client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [{"code_value": "K003", "outcome": "succeeded"}],
            },
        )

        resp = _print(client, operator, workstation.id, ["K003"])
        assert resp.status_code == 200, "逐码失败用 200 + rejected 表达，不是整体报错"
        assert resp.json()["accepted"] == []
        assert resp.json()["rejected"][0]["error_code"] == "CODE_ALREADY_PRINTED"

    def test_mixed_batch_returns_both_lists(self, client, operator, workstation, printable):
        resp = _print(client, operator, workstation.id, ["K001", "NOT-EXIST"])
        body = resp.json()
        assert [a["code_value"] for a in body["accepted"]] == ["K001"]
        assert [r["code_value"] for r in body["rejected"]] == ["NOT-EXIST"]

    def test_empty_code_list_is_rejected(self, client, operator, workstation):
        resp = client.post(
            "/api/v1/workstation/print",
            headers=auth_header(operator),
            json={"workstation_id": workstation.id, "code_values": []},
        )
        assert resp.status_code == 422

    def test_requires_authentication(self, client, workstation):
        resp = client.post(
            "/api/v1/workstation/print",
            json={"workstation_id": workstation.id, "code_values": ["K001"]},
        )
        assert resp.status_code == 401


class TestConfirmEndpoint:
    def test_success_marks_printed(self, client, db: Session, operator, workstation, printable):
        _print(client, operator, workstation.id, ["K001"])

        resp = client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [
                    {
                        "code_value": "K001",
                        "outcome": "succeeded",
                        "printer_name": "Zebra ZD421",
                    }
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["confirmed"] == ["K001"]

        code = db.execute(select(Code).where(Code.code_value == "K001")).scalar_one()
        assert code.status == "printed"
        assert code.print_count == 1

    def test_failure_returns_code_to_allocated(
        self, client, db: Session, operator, workstation, printable
    ):
        _print(client, operator, workstation.id, ["K002"])

        resp = client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [
                    {"code_value": "K002", "outcome": "failed", "failure_reason": "缺纸"}
                ],
            },
        )
        assert resp.status_code == 200

        code = db.execute(select(Code).where(Code.code_value == "K002")).scalar_one()
        assert code.status == "allocated"
        assert code.reprint_count == 0, "失败回退不算补打（FR-046）"

    def test_invalid_outcome_is_422(self, client, operator, workstation, printable):
        resp = client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [{"code_value": "K001", "outcome": "maybe"}],
            },
        )
        assert resp.status_code == 422


class TestConfirmFromNonHoldingWorkstation:
    """T083：确认请求必须来自持有锁的同一工位。"""

    def test_other_workstation_gets_code_locked(
        self, client, db: Session, operator, workstation, printable, hq_company
    ):
        other = Workstation(
            code="W900", name="别的工位", company_id=hq_company.id, status="active"
        )
        db.add(other)
        db.flush()

        _print(client, operator, workstation.id, ["K001"])

        resp = client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": other.id,
                "results": [{"code_value": "K001", "outcome": "succeeded"}],
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["confirmed"] == []
        assert body["rejected"][0]["error_code"] == "CODE_LOCKED"

        # 被拒的确认不得改变码状态
        code = db.execute(select(Code).where(Code.code_value == "K001")).scalar_one()
        assert code.status == "printing"

    def test_confirm_without_prior_preempt_is_rejected(
        self, client, operator, workstation, printable
    ):
        resp = client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [{"code_value": "K003", "outcome": "succeeded"}],
            },
        )
        body = resp.json()
        assert body["confirmed"] == []
        assert body["rejected"][0]["error_code"] == "CODE_LOCKED"

    def test_confirm_on_other_company_workstation_is_forbidden(
        self, client, db: Session, operator, workstation, printable, other_company
    ):
        foreign = Workstation(code="W901", name="他公司工位", company_id=other_company.id)
        db.add(foreign)
        db.flush()

        _print(client, operator, workstation.id, ["K001"])
        resp = client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": foreign.id,
                "results": [{"code_value": "K001", "outcome": "succeeded"}],
            },
        )
        assert resp.status_code == 403

class TestCurrentTemplate:
    def test_preview_does_not_reserve_code_or_serial(
        self, client, db, operator, workstation, product, printable, template_version
    ):
        from app.models.print_identity import PrintIdentity
        from app.models.template import TemplateVersion
        from sqlalchemy import func
        template_version.elements_json = {
            'paper_width_mm': 40, 'paper_height_mm': 55,
            'elements': [{'type': 'date', 'x': 1, 'y': 1, 'font_size': 3},
                         {'type': 'serial', 'x': 1, 'y': 5, 'font_size': 3}]
        }
        db.flush()
        # 产品已有新版时仍展示分配单冻结的旧版。
        db.add(TemplateVersion(
            template_id=template_version.template_id, version_no=template_version.version_no + 1,
            paper_width_mm=60, paper_height_mm=80,
            elements_json={'paper_width_mm': 60, 'paper_height_mm': 80, 'elements': []}
        ))
        db.flush()
        before = db.scalar(select(func.count()).select_from(PrintIdentity))
        response = client.get(
            f'/api/v1/workstation/template?workstation_id={workstation.id}&product_id={product.id}',
            headers=auth_header(operator),
        )
        assert response.status_code == 200
        body = response.json()
        assert body['version_no'] == template_version.version_no
        assert body['data']['code_value'] == 'K001'
        assert body['elements_json'] == template_version.elements_json
        assert not body['data'].get('serial_no')
        assert db.scalar(select(func.count()).select_from(PrintIdentity)) == before
        assert db.scalar(select(Code).where(Code.code_value == 'K001')).status == 'allocated'

    def test_empty_queue(self, client, operator, workstation, product):
        response = client.get(
            f'/api/v1/workstation/template?workstation_id={workstation.id}&product_id={product.id}',
            headers=auth_header(operator),
        )
        assert response.status_code == 200
        assert response.json() is None

    def test_other_company_forbidden(self, client, db, operator, other_company, product):
        station = Workstation(code='PREVIEW-OTHER', name='其他公司', company_id=other_company.id)
        db.add(station)
        db.flush()
        response = client.get(
            f'/api/v1/workstation/template?workstation_id={station.id}&product_id={product.id}',
            headers=auth_header(operator),
        )
        assert response.status_code == 403
