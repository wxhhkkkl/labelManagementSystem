"""T049：产品停用前置校验（FR-010）。

用户确认的口径：停用前必须先处理干净——仍有"已分配未打印"的码时**拒绝停用**，
不做静默的批量状态变更，也不允许带码停用。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.user import User
from tests.conftest import auth_header

pytestmark = pytest.mark.integration


def _add_code(db: Session, value: str, product_id: int, batch_id: int, *, status: str, company_id=None):
    """Code.import_batch_id 是外键，必须指向真实批次。"""
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


class TestInFlightBlocksDisable:
    @pytest.mark.parametrize("status", ["allocated", "printing"])
    def test_disable_rejected_when_codes_in_flight(
        self, client, db: Session, hq_admin: User, product, hq_company, import_batch, status
    ):
        _add_code(
            db, "C001", product.id, import_batch.id,
            status=status, company_id=hq_company.id,
        )

        resp = client.post(
            f"/api/v1/products/{product.id}/disable", headers=auth_header(hq_admin)
        )

        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "PRODUCT_HAS_ALLOCATED_CODES"
        assert body["details"]["in_flight"] == 1

        db.refresh(product)
        assert product.status == "active", "被拒后产品状态不得改变"

    def test_error_message_tells_user_what_to_do(
        self, client, db: Session, hq_admin, product, hq_company, import_batch
    ):
        _add_code(
            db, "C002", product.id, import_batch.id,
            status="allocated", company_id=hq_company.id,
        )
        resp = client.post(
            f"/api/v1/products/{product.id}/disable", headers=auth_header(hq_admin)
        )
        message = resp.json()["message"]
        assert "回收" in message or "作废" in message


class TestDisableSucceedsWhenClear:
    def test_disable_succeeds_with_no_codes(
        self, client, db: Session, hq_admin: User, product
    ):
        resp = client.post(
            f"/api/v1/products/{product.id}/disable", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    @pytest.mark.parametrize("status", ["unallocated", "printed", "voided"])
    def test_terminal_or_pool_codes_do_not_block(
        self, client, db: Session, hq_admin, product, hq_company, import_batch, status
    ):
        """未分配、已打印、已作废都不算在途——只有"已分配未打印"（含打印中）才拦。"""
        company = hq_company.id if status == "printed" else None
        _add_code(
            db, f"C-{status}", product.id, import_batch.id,
            status=status, company_id=company,
        )

        resp = client.post(
            f"/api/v1/products/{product.id}/disable", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 200

    def test_disable_after_reclaim_succeeds(
        self, client, db: Session, hq_admin, product, hq_company, import_batch
    ):
        code = _add_code(
            db, "C-RECLAIM", product.id, import_batch.id,
            status="allocated", company_id=hq_company.id,
        )

        blocked = client.post(
            f"/api/v1/products/{product.id}/disable", headers=auth_header(hq_admin)
        )
        assert blocked.status_code == 409

        # 回收（FR-029 的效果）后再停用
        code.status = "unallocated"
        code.company_id = None
        db.flush()

        ok = client.post(
            f"/api/v1/products/{product.id}/disable", headers=auth_header(hq_admin)
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "disabled"


class TestDisabledProductRules:
    def test_disabled_product_rejected_as_binding_target(
        self, client, db: Session, hq_admin, product, import_batch
    ):
        from app.core.errors import ApiError
        from app.services.code_binding import bind_batch

        client.post(f"/api/v1/products/{product.id}/disable", headers=auth_header(hq_admin))

        with pytest.raises(ApiError) as exc:
            bind_batch(db, batch_id=import_batch.id, product_id=product.id, operator_id=hq_admin.id)
        assert exc.value.error_code == "VALIDATION_ERROR"

    def test_stats_reflect_code_states(
        self, client, db: Session, hq_admin, product, hq_company, import_batch
    ):
        _add_code(db, "S-1", product.id, import_batch.id, status="unallocated")
        _add_code(db, "S-2", product.id, import_batch.id, status="allocated", company_id=hq_company.id)
        _add_code(db, "S-3", product.id, import_batch.id, status="printed", company_id=hq_company.id)

        body = client.get("/api/v1/products", headers=auth_header(hq_admin)).json()
        item = next(p for p in body if p["id"] == product.id)

        assert item["stats"]["imported"] == 3
        assert item["stats"]["allocated"] == 1   # 仅 allocated + printing
        assert item["stats"]["printed"] == 1
