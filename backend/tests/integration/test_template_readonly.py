"""T118：模板对子公司与工位端只读（FR-036）。

"模板统一"的前提是子公司改不了它。只读不是靠前端藏按钮——
按钮藏得住，请求藏不住。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import auth_header

pytestmark = pytest.mark.integration

ELEMENTS = [{"type": "qrcode", "x": 2, "y": 2, "size": 15}]
PAYLOAD = {"paper_width_mm": 60, "paper_height_mm": 40, "elements": ELEMENTS}


@pytest.fixture
def template(db: Session):
    from app.services import template as template_service

    created, _ = template_service.create_template(
        db, code="RO1", name="只读测试模板", paper_width_mm=60, paper_height_mm=40, elements=ELEMENTS
    )
    db.flush()
    return created


class TestReadIsAllowed:
    def test_sub_admin_can_list_templates(self, client, sub_admin: User, template):
        resp = client.get("/api/v1/templates", headers=auth_header(sub_admin))
        assert resp.status_code == 200
        assert any(t["code"] == "RO1" for t in resp.json())

    def test_sub_admin_can_read_versions(self, client, sub_admin: User, template):
        resp = client.get(
            f"/api/v1/templates/{template.id}/versions", headers=auth_header(sub_admin)
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_operator_can_read_templates(self, client, operator: User, template):
        """工位端要知道自己被分配的是哪套模板。"""
        assert client.get("/api/v1/templates", headers=auth_header(operator)).status_code == 200


class TestWritesAreDenied:
    def test_sub_admin_cannot_create_template(self, client, sub_admin: User):
        resp = client.post(
            "/api/v1/templates",
            headers=auth_header(sub_admin),
            json={"code": "RO2", "name": "越权模板", **PAYLOAD},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"

    def test_sub_admin_cannot_add_a_version(self, client, sub_admin: User, template):
        resp = client.patch(
            f"/api/v1/templates/{template.id}", headers=auth_header(sub_admin), json=PAYLOAD
        )
        assert resp.status_code == 403

    def test_sub_admin_cannot_replace_version_content(
        self, client, sub_admin: User, template
    ):
        resp = client.put(
            f"/api/v1/templates/{template.id}/versions/1",
            headers=auth_header(sub_admin),
            json=PAYLOAD,
        )
        assert resp.status_code == 403

    def test_sub_admin_cannot_disable_template(self, client, db: Session, sub_admin, template):
        resp = client.post(
            f"/api/v1/templates/{template.id}/disable", headers=auth_header(sub_admin)
        )
        assert resp.status_code == 403

        db.refresh(template)
        assert template.status == "active", "被拒的操作不得改变任何状态"

    def test_operator_cannot_write_either(self, client, operator: User, template):
        resp = client.patch(
            f"/api/v1/templates/{template.id}", headers=auth_header(operator), json=PAYLOAD
        )
        assert resp.status_code == 403

    def test_anonymous_is_rejected(self, client, template):
        assert client.get("/api/v1/templates").status_code == 401


class TestHqAdminIsAllowed:
    def test_hq_admin_can_create(self, client, hq_admin: User):
        resp = client.post(
            "/api/v1/templates",
            headers=auth_header(hq_admin),
            json={"code": "RO3", "name": "总部模板", **PAYLOAD},
        )
        assert resp.status_code == 201
        assert resp.json()["current_version_no"] == 1

    def test_hq_admin_adds_a_second_version(self, client, hq_admin: User, template):
        resp = client.patch(
            f"/api/v1/templates/{template.id}",
            headers=auth_header(hq_admin),
            json={**PAYLOAD, "paper_width_mm": 70},
        )
        assert resp.status_code == 200
        assert resp.json()["version_no"] == 2
