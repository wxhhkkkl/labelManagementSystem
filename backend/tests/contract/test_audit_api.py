"""T139：审计日志与码详情接口契约测试（contracts/admin-api.md 报表与审计小节）。"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import auth_header
from tests.helpers import make_printable

pytestmark = pytest.mark.integration


@pytest.fixture
def code_in_pool(db: Session, product, hq_company, import_batch, template_version, hq_admin):
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["CT01"],
    )
    return "CT01"


class TestAuditLogEndpoint:
    def test_response_shape(self, client, hq_admin: User, code_in_pool):
        """任何一次成功请求都会留下审计记录，这里复用登录的那条。"""
        client.post("/api/v1/auth/login", json={"username": "hq", "password": "pw123456"})

        rows = client.get("/api/v1/audit-logs", headers=auth_header(hq_admin)).json()
        assert rows
        assert set(rows[0]) == {
            "id",
            "operator_id",
            "role",
            "company_id",
            "workstation_id",
            "action",
            "target_type",
            "target_id",
            "ip",
            "result",
            "occurred_at",
        }

    def test_login_is_recorded(self, client, db: Session, hq_admin, code_in_pool):
        client.post("/api/v1/auth/login", json={"username": "hq", "password": "pw123456"})
        rows = client.get("/api/v1/audit-logs?action=login", headers=auth_header(hq_admin)).json()
        assert any(r["action"] == "login" and r["result"] == "success" for r in rows)

    def test_business_write_is_recorded(self, client, hq_admin, code_in_pool):
        """关键业务动作确实落进了审计——以创建产品为例验证埋点生效。"""
        created = client.post(
            "/api/v1/products",
            headers=auth_header(hq_admin),
            json={"code": "AUD-P", "name": "审计验证产品"},
        )
        assert created.status_code == 201

        rows = client.get(
            "/api/v1/audit-logs?action=product.change", headers=auth_header(hq_admin)
        ).json()
        assert any(r["target_id"] == created.json()["id"] for r in rows)

    def test_pagination_params(self, client, hq_admin: User, code_in_pool):
        resp = client.get(
            "/api/v1/audit-logs?limit=1&offset=0", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 200
        assert len(resp.json()) <= 1

    def test_limit_upper_bound(self, client, hq_admin: User):
        assert (
            client.get("/api/v1/audit-logs?limit=99999", headers=auth_header(hq_admin)).status_code
            == 422
        )


class TestCodeDetailEndpoint:
    def test_response_shape(self, client, hq_admin: User, code_in_pool):
        resp = client.get(f"/api/v1/codes/{code_in_pool}", headers=auth_header(hq_admin))
        assert resp.status_code == 200

        body = resp.json()
        assert set(body) == {
            "code_value",
            "status",
            "status_label",
            "product_name",
            "company_name",
            "allocation_order_no",
            "template_version_id",
            "print_count",
            "reprint_count",
            "void_reason",
            "timeline",
        }

    def test_timeline_entry_shape(self, client, hq_admin: User, code_in_pool):
        body = client.get(f"/api/v1/codes/{code_in_pool}", headers=auth_header(hq_admin)).json()
        assert body["timeline"]

        entry = body["timeline"][0]
        assert set(entry) == {
            "event_type",
            "label",
            "from_status",
            "from_status_label",
            "to_status",
            "to_status_label",
            "operator_name",
            "workstation_name",
            "reason",
            "occurred_at",
        }
        assert entry["event_type"] == "imported"
        assert entry["to_status_label"] == "待分配"

    def test_timeline_is_chronological(self, client, hq_admin: User, code_in_pool):
        body = client.get(f"/api/v1/codes/{code_in_pool}", headers=auth_header(hq_admin)).json()
        times = [e["occurred_at"] for e in body["timeline"]]
        assert times == sorted(times)

    def test_unknown_code_is_404(self, client, hq_admin: User):
        assert (
            client.get("/api/v1/codes/NOPE", headers=auth_header(hq_admin)).status_code == 404
        )

    def test_requires_authentication(self, client, code_in_pool):
        assert client.get(f"/api/v1/codes/{code_in_pool}").status_code == 401
