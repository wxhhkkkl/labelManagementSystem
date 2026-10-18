"""T119：模板接口契约测试（contracts/admin-api.md 打印模板小节）。

其中元素结构校验部分直接对应 contracts/template-rendering.md——
把渲染契约变成入库前的硬校验，避免"打印时才发现模板不合法"。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import auth_header

pytestmark = pytest.mark.contract

QR = {"type": "qrcode", "x": 2, "y": 2, "size": 15}
TEXT = {"type": "text", "x": 20, "y": 2, "content": "产品：", "font_size": 3}
FIELD = {"type": "field", "x": 20, "y": 6, "field_name": "product_name", "font_size": 3}
DOC = {"paper_width_mm": 60, "paper_height_mm": 40, "elements": [QR, TEXT, FIELD]}


def _create(client, user, code="TC1", doc=None):
    return client.post(
        "/api/v1/templates",
        headers=auth_header(user),
        json={"code": code, "name": "契约模板", **(doc or DOC)},
    )


class TestCreateAndList:
    def test_create_returns_first_version(self, client, hq_admin: User):
        resp = _create(client, hq_admin)
        assert resp.status_code == 201
        body = resp.json()
        assert set(body) == {"id", "code", "name", "status", "current_version_no", "version_count"}
        assert body["current_version_no"] == 1
        assert body["status"] == "active"

    def test_duplicate_code_rejected(self, client, hq_admin: User):
        _create(client, hq_admin, code="TC2")
        resp = _create(client, hq_admin, code="TC2")
        assert resp.status_code == 422

    def test_list_shows_version_stats(self, client, hq_admin: User):
        _create(client, hq_admin, code="TC3")
        body = client.get("/api/v1/templates", headers=auth_header(hq_admin)).json()
        item = next(t for t in body if t["code"] == "TC3")
        assert item["version_count"] == 1
        assert item["current_version_no"] == 1


class TestVersions:
    def test_put_appends_a_version(self, client, hq_admin: User):
        template_id = _create(client, hq_admin, code="TC4").json()["id"]

        resp = client.put(
            f"/api/v1/templates/{template_id}",
            headers=auth_header(hq_admin),
            json={**DOC, "paper_width_mm": 70, "paper_height_mm": 50},
        )
        assert resp.status_code == 200
        assert resp.json()["version_no"] == 2

        versions = client.get(
            f"/api/v1/templates/{template_id}/versions", headers=auth_header(hq_admin)
        ).json()
        assert [v["version_no"] for v in versions] == [2, 1]
        assert all(v["frozen"] is False for v in versions)

    def test_version_payload_contains_the_document(self, client, hq_admin: User):
        template_id = _create(client, hq_admin, code="TC5").json()["id"]
        version = client.get(
            f"/api/v1/templates/{template_id}/versions", headers=auth_header(hq_admin)
        ).json()[0]

        assert set(version) == {
            "id",
            "template_id",
            "version_no",
            "paper_width_mm",
            "paper_height_mm",
            "elements_json",
            "frozen",
        }
        doc = version["elements_json"]
        assert doc["paper_width_mm"] == 60
        assert len(doc["elements"]) == 3

    def test_replace_content_of_unfrozen_version(self, client, hq_admin: User):
        template_id = _create(client, hq_admin, code="TC6").json()["id"]
        resp = client.put(
            f"/api/v1/templates/{template_id}/versions/1",
            headers=auth_header(hq_admin),
            json={**DOC, "paper_width_mm": 80},
        )
        assert resp.status_code == 200
        assert resp.json()["paper_width_mm"] == 80

    def test_unknown_version_no_is_404(self, client, hq_admin: User):
        template_id = _create(client, hq_admin, code="TC7").json()["id"]
        resp = client.put(
            f"/api/v1/templates/{template_id}/versions/99",
            headers=auth_header(hq_admin),
            json=DOC,
        )
        assert resp.status_code == 404

    def test_disable_template(self, client, hq_admin: User):
        template_id = _create(client, hq_admin, code="TC8").json()["id"]
        resp = client.post(
            f"/api/v1/templates/{template_id}/disable", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"


class TestElementValidation:
    """实现 contracts/template-rendering.md 第 3 节：未识别类型显式报错。"""

    def test_unknown_element_type_is_rejected(self, client, hq_admin: User):
        doc = {**DOC, "elements": [{"type": "hologram", "x": 1, "y": 1}]}
        resp = _create(client, hq_admin, code="TV1", doc=doc)
        assert resp.status_code == 422

    def test_qrcode_without_size_is_rejected(self, client, hq_admin: User):
        doc = {**DOC, "elements": [{"type": "qrcode", "x": 1, "y": 1}]}
        assert _create(client, hq_admin, code="TV2", doc=doc).status_code == 422

    def test_barcode_without_dimensions_is_rejected(self, client, hq_admin: User):
        doc = {**DOC, "elements": [{"type": "barcode", "x": 1, "y": 1, "width": 20}]}
        assert _create(client, hq_admin, code="TV3", doc=doc).status_code == 422

    def test_text_without_content_is_rejected(self, client, hq_admin: User):
        doc = {**DOC, "elements": [{"type": "text", "x": 1, "y": 1, "font_size": 3}]}
        assert _create(client, hq_admin, code="TV4", doc=doc).status_code == 422

    def test_text_without_font_size_is_rejected(self, client, hq_admin: User):
        doc = {**DOC, "elements": [{"type": "text", "x": 1, "y": 1, "content": "x"}]}
        assert _create(client, hq_admin, code="TV5", doc=doc).status_code == 422

    def test_unknown_dynamic_field_is_rejected(self, client, hq_admin: User):
        doc = {
            **DOC,
            "elements": [{"type": "field", "x": 1, "y": 1, "field_name": "secret", "font_size": 3}],
        }
        assert _create(client, hq_admin, code="TV6", doc=doc).status_code == 422

    @pytest.mark.parametrize(
        "field_name", ["product_name", "company_name", "code_value", "batch_no"]
    )
    def test_all_four_dynamic_fields_accepted(self, client, hq_admin: User, field_name):
        doc = {
            **DOC,
            "elements": [
                {"type": "field", "x": 1, "y": 1, "field_name": field_name, "font_size": 3}
            ],
        }
        resp = _create(client, hq_admin, code=f"TV-{field_name}", doc=doc)
        assert resp.status_code == 201

    def test_element_entirely_outside_the_paper_is_rejected(self, client, hq_admin: User):
        doc = {**DOC, "elements": [{"type": "qrcode", "x": 200, "y": 200, "size": 10}]}
        assert _create(client, hq_admin, code="TV7", doc=doc).status_code == 422

    def test_zero_or_negative_sizes_are_rejected(self, client, hq_admin: User):
        doc = {**DOC, "elements": [{"type": "qrcode", "x": 1, "y": 1, "size": 0}]}
        assert _create(client, hq_admin, code="TV8", doc=doc).status_code == 422

    def test_absurd_paper_size_is_rejected(self, client, hq_admin: User):
        """拦住"把 60 看成 6000"这类手误。"""
        doc = {**DOC, "paper_width_mm": 6000}
        assert _create(client, hq_admin, code="TV9", doc=doc).status_code == 422

    def test_empty_elements_is_allowed(self, client, hq_admin: User):
        """空白模板是合法起点——管理员先建模板再往里加元素。"""
        doc = {"paper_width_mm": 60, "paper_height_mm": 40, "elements": []}
        assert _create(client, hq_admin, code="TV10", doc=doc).status_code == 201


def test_request_validation_error_uses_unified_error_body(client, hq_admin: User):
    """422 也要走统一错误体，前端才能把具体字段展示给管理员。"""
    resp = client.put(
        "/api/v1/templates/999999",
        headers=auth_header(hq_admin),
        json={"paper_width_mm": 60},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "paper_height_mm" in body["message"]
    assert body["details"]["errors"][0]["loc"][0] == "body"
