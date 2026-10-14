"""T128：看板聚合正确性（FR-065）。

四态码量必须与逐条统计一致——看板是"账实一致"这项目标的直接体现，
数字对不上比没有看板更糟。
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.code import Code
from app.models.product import Product
from app.models.user import User
from tests.conftest import auth_header

pytestmark = pytest.mark.integration


def _code(db: Session, value: str, product_id: int, batch_id: int, status: str, company_id=None):
    code = Code(
        code_value=value,
        status=status,
        product_id=product_id,
        company_id=company_id,
        import_batch_id=batch_id,
    )
    db.add(code)
    db.flush()
    return code


@pytest.fixture
def distribution(db: Session, product, hq_company, other_company, import_batch):
    """造一份四种状态齐全、跨两家公司的码。"""
    _code(db, "D-P1", product.id, import_batch.id, "unallocated")
    _code(db, "D-P2", product.id, import_batch.id, "unallocated")
    _code(db, "D-A1", product.id, import_batch.id, "allocated", hq_company.id)
    _code(db, "D-R1", product.id, import_batch.id, "printing", hq_company.id)
    _code(db, "D-T1", product.id, import_batch.id, "printed", hq_company.id)
    _code(db, "D-V1", product.id, import_batch.id, "voided", hq_company.id)
    _code(db, "D-T2", product.id, import_batch.id, "printed", other_company.id)
    db.flush()


def _fetch(client, user, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/v1/dashboard/code-distribution{('?' + query) if query else ''}"
    resp = client.get(url, headers=auth_header(user))
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestAggregation:
    def test_four_states_match_row_counts(self, client, db: Session, hq_admin: User, distribution):
        body = _fetch(client, hq_admin)
        totals = body["totals"]

        assert totals["unallocated"] == 2
        assert totals["allocated"] == 1
        assert totals["printing"] == 1
        assert totals["printed"] == 2
        assert totals["voided"] == 1
        assert totals["total"] == 7

    def test_allocated_not_printed_includes_printing(self, client, hq_admin, distribution):
        """FR-031 的口径：打印中也算"已分配未打印"。"""
        totals = _fetch(client, hq_admin)["totals"]
        assert totals["allocated_not_printed"] == 2  # 1 allocated + 1 printing

    def test_totals_equal_the_sum_of_rows(self, client, hq_admin, distribution):
        body = _fetch(client, hq_admin)
        for field in ("unallocated", "allocated", "printing", "printed", "voided", "total"):
            assert body["totals"][field] == sum(r[field] for r in body["rows"]), field

    def test_rows_are_split_by_company_and_product(self, client, hq_admin, distribution):
        body = _fetch(client, hq_admin)
        keys = {r["key"] for r in body["rows"]}
        assert "华东分公司/500ml 矿泉水" in keys
        assert "华南分公司/500ml 矿泉水" in keys

    def test_empty_database_returns_zeroed_totals(self, client, hq_admin: User):
        body = _fetch(client, hq_admin)
        assert body["rows"] == []
        assert body["totals"]["total"] == 0


class TestGroupBy:
    def test_group_by_company_collapses_products(self, client, db: Session, hq_admin, product, hq_company, import_batch):
        other = Product(code="P-2", name="330ml 汽水", status="active")
        db.add(other)
        db.flush()
        _code(db, "G-C1", product.id, import_batch.id, "printed", hq_company.id)
        _code(db, "G-C2", other.id, import_batch.id, "printed", hq_company.id)
        db.flush()

        body = _fetch(client, hq_admin, group_by="company")
        row = next(r for r in body["rows"] if r["company_name"] == "华东分公司")
        assert row["printed"] == 2
        assert row["product_name"] is None

    def test_group_by_product_collapses_companies(
        self, client, db: Session, hq_admin, product, hq_company, other_company, import_batch
    ):
        _code(db, "G-P1", product.id, import_batch.id, "printed", hq_company.id)
        _code(db, "G-P2", product.id, import_batch.id, "printed", other_company.id)
        db.flush()

        body = _fetch(client, hq_admin, group_by="product")
        row = next(r for r in body["rows"] if r["product_name"] == product.name)
        assert row["printed"] == 2
        assert row["company_name"] is None

    def test_group_by_company_product_is_the_default(self, client, hq_admin, distribution):
        assert _fetch(client, hq_admin)["group_by"] == "company_product"

    def test_invalid_group_by_is_422(self, client, hq_admin):
        resp = client.get(
            "/api/v1/dashboard/code-distribution?group_by=nonsense",
            headers=auth_header(hq_admin),
        )
        assert resp.status_code == 422


class TestTimeFilter:
    def test_created_from_excludes_older_codes(self, client, db: Session, hq_admin, product, import_batch):
        old = _code(db, "T-OLD", product.id, import_batch.id, "printed")
        old.created_at = utcnow() - timedelta(days=10)
        _code(db, "T-NEW", product.id, import_batch.id, "printed")
        db.flush()

        cutoff = (utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        body = _fetch(client, hq_admin, created_from=cutoff)
        assert body["totals"]["printed"] == 1

    def test_created_to_excludes_newer_codes(self, client, db: Session, hq_admin, product, import_batch):
        _code(db, "T-NEW2", product.id, import_batch.id, "printed")
        db.flush()

        cutoff = (utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        body = _fetch(client, hq_admin, created_to=cutoff)
        assert body["totals"]["printed"] == 0
