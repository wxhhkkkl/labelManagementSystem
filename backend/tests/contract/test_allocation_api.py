"""T070：分配与回收接口契约测试（contracts/admin-api.md）。"""

import pytest
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.user import User
from tests.conftest import auth_header

pytestmark = pytest.mark.contract


def _pool(db: Session, product, batch, values: list[str]) -> None:
    db.add_all(
        [
            Code(code_value=v, status="unallocated", product_id=product.id, import_batch_id=batch.id)
            for v in values
        ]
    )
    db.flush()


def _alloc(client, user, **payload):
    return client.post("/api/v1/allocations", headers=auth_header(user), json=payload)


class TestCreateAllocation:
    def test_creates_order_and_marks_codes(
        self, client, db: Session, hq_admin: User, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["X001", "X002"])

        resp = _alloc(
            client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=2
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["allocated"] == 2
        order = body["order"]
        assert order["order_no"].startswith("ALL")
        assert order["company_name"] == hq_company.name
        assert order["product_name"] == product.name
        assert order["template_version_id"] == template_version.id
        assert order["status"] == "active"

    def test_insufficient_stock_is_409_with_available(
        self, client, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["Y001"])

        resp = _alloc(
            client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=10
        )

        assert resp.status_code == 409
        details = resp.json()["details"]
        assert details["available"] == 1
        assert details["requested"] == 10

    def test_quantity_must_be_positive(
        self, client, hq_admin, product, hq_company, template_version
    ):
        resp = _alloc(
            client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=0
        )
        assert resp.status_code == 422

    def test_sub_admin_cannot_allocate(
        self, client, sub_admin, product, hq_company, template_version
    ):
        resp = _alloc(
            client, sub_admin, company_id=hq_company.id, product_id=product.id, quantity=1
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"

    def test_unknown_product_rejected(self, client, hq_admin, hq_company, template_version):
        resp = _alloc(
            client, hq_admin, company_id=hq_company.id, product_id=999999, quantity=1
        )
        assert resp.status_code == 422

    def test_targeted_allocation_by_batch(
        self, client, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["Z001", "Z002"])

        resp = _alloc(
            client,
            hq_admin,
            company_id=hq_company.id,
            product_id=product.id,
            quantity=2,
            batch_id=import_batch.id,
        )
        assert resp.status_code == 201
        assert resp.json()["allocated"] == 2


class TestReclaimEndpoint:
    def test_reclaims_and_returns_order(
        self, client, db: Session, hq_admin: User, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["W001", "W002"])
        order_id = _alloc(
            client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=2
        ).json()["order"]["id"]

        resp = client.post(
            f"/api/v1/allocations/{order_id}/reclaim", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reclaimed"

        codes = db.query(Code).all()
        assert {c.status for c in codes} == {"unallocated"}

    def test_printed_codes_block_reclaim(
        self, client, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["W100", "W101"])
        order_id = _alloc(
            client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=2
        ).json()["order"]["id"]

        first = db.query(Code).filter(Code.status == "allocated").first()
        first.status = "printed"
        db.flush()

        resp = client.post(
            f"/api/v1/allocations/{order_id}/reclaim", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 422
        assert "不可回收" in resp.json()["message"]

    def test_unknown_order_is_404(self, client, hq_admin: User):
        resp = client.post("/api/v1/allocations/999999/reclaim", headers=auth_header(hq_admin))
        assert resp.status_code == 404


class TestListAllocations:
    def test_hq_sees_all(
        self, client, db: Session, hq_admin: User, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["L001"])
        _alloc(client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=1)

        body = client.get("/api/v1/allocations", headers=auth_header(hq_admin)).json()
        assert len(body) >= 1
        assert body[0]["company_id"] == hq_company.id

    def test_sub_admin_sees_only_own_company(
        self,
        client,
        db: Session,
        hq_admin,
        sub_admin: User,
        product,
        hq_company,
        other_company,
        import_batch,
        template_version,
    ):
        """R7 组织隔离：子公司只能看到发给本公司的分配单。"""
        _pool(db, product, import_batch, ["L010", "L011"])
        _alloc(client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=1)
        _alloc(client, hq_admin, company_id=other_company.id, product_id=product.id, quantity=1)

        body = client.get("/api/v1/allocations", headers=auth_header(sub_admin)).json()
        assert body, "本公司应至少有一条"
        assert all(o["company_id"] == hq_company.id for o in body)

    def test_sub_admin_cannot_query_other_company(
        self, client, sub_admin, other_company
    ):
        resp = client.get(
            f"/api/v1/allocations?company_id={other_company.id}", headers=auth_header(sub_admin)
        )
        assert resp.status_code == 403


class TestCodePoolQuery:
    def test_filters_by_status_and_product(
        self, client, db: Session, hq_admin: User, product, import_batch
    ):
        _pool(db, product, import_batch, ["Q001", "Q002"])

        body = client.get(
            f"/api/v1/codes?product_id={product.id}&status=unallocated",
            headers=auth_header(hq_admin),
        ).json()

        assert body["total"] == 2
        assert {item["code_value"] for item in body["items"]} == {"Q001", "Q002"}
        assert body["page"] == 1

    def test_pagination_limits_page_size(self, client, db: Session, hq_admin, product, import_batch):
        _pool(db, product, import_batch, [f"P{i:03d}" for i in range(5)])

        body = client.get(
            f"/api/v1/codes?product_id={product.id}&page=1&page_size=2",
            headers=auth_header(hq_admin),
        ).json()
        assert body["total"] == 5
        assert len(body["items"]) == 2

    def test_page_size_upper_bound_enforced(self, client, hq_admin):
        resp = client.get("/api/v1/codes?page_size=5000", headers=auth_header(hq_admin))
        assert resp.status_code == 422


class TestCodeStockExport:
    def test_export_returns_csv_with_headers(
        self, client, db: Session, hq_admin: User, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["E001"])
        _alloc(client, hq_admin, company_id=hq_company.id, product_id=product.id, quantity=1)

        resp = client.get(
            "/api/v1/reports/code-stock/export", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 200
        text = resp.content.decode("utf-8-sig")
        assert "公司" in text and "已分配未打印" in text
        assert hq_company.name in text

    def test_export_requires_hq(self, client, sub_admin):
        resp = client.get(
            "/api/v1/reports/code-stock/export", headers=auth_header(sub_admin)
        )
        assert resp.status_code == 403
