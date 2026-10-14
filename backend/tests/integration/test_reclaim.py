"""T068：回收规则（FR-029 / FR-030）。

未打印的码可回收回码池；分配单下只要有一个码已打印或打印中，整单拒绝回收——
避免出现"部分回收"的半截状态。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.services import allocation as allocation_service

pytestmark = pytest.mark.integration


def _allocated_pool(db: Session, product, batch, values: list[str]) -> list[Code]:
    codes = [
        Code(code_value=v, status="unallocated", product_id=product.id, import_batch_id=batch.id)
        for v in values
    ]
    db.add_all(codes)
    db.flush()
    return codes


def _allocate(db, hq_admin, product, company, quantity):
    return allocation_service.allocate(
        db,
        company_id=company.id,
        product_id=product.id,
        quantity=quantity,
        operator_id=hq_admin.id,
    )


class TestReclaimSucceeds:
    def test_codes_return_to_pool(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _allocated_pool(db, product, import_batch, ["K001", "K002"])
        result = _allocate(db, hq_admin, product, hq_company, 2)

        allocation_service.reclaim(db, order_id=result.order.id, operator_id=hq_admin.id)

        codes = list(db.execute(select(Code)).scalars())
        assert {c.status for c in codes} == {"unallocated"}
        assert {c.company_id for c in codes} == {None}
        assert {c.current_allocation_order_id for c in codes} == {None}

    def test_order_is_marked_reclaimed(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _allocated_pool(db, product, import_batch, ["K010"])
        result = _allocate(db, hq_admin, product, hq_company, 1)

        allocation_service.reclaim(db, order_id=result.order.id, operator_id=hq_admin.id)
        assert result.order.status == "reclaimed"

    def test_reclaim_writes_events(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _allocated_pool(db, product, import_batch, ["K020", "K021"])
        result = _allocate(db, hq_admin, product, hq_company, 2)

        allocation_service.reclaim(db, order_id=result.order.id, operator_id=hq_admin.id)

        events = list(
            db.execute(select(CodeEvent).where(CodeEvent.event_type == "reclaimed")).scalars()
        )
        assert len(events) == 2

    def test_reclaimed_codes_can_be_allocated_again(
        self, db: Session, hq_admin, product, hq_company, other_company, import_batch, template_version
    ):
        _allocated_pool(db, product, import_batch, ["K030", "K031"])
        first = _allocate(db, hq_admin, product, hq_company, 2)
        allocation_service.reclaim(db, order_id=first.order.id, operator_id=hq_admin.id)

        second = _allocate(db, hq_admin, product, other_company, 2)
        codes = list(db.execute(select(Code)).scalars())
        assert {c.company_id for c in codes} == {other_company.id}
        assert {c.current_allocation_order_id for c in codes} == {second.order.id}


class TestReclaimBlockedByPrinted:
    """FR-030：已打印的码不可回收。"""

    @pytest.mark.parametrize("status", ["printed", "printing"])
    def test_whole_order_rejected_when_any_code_is_not_reclaimable(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version, status
    ):
        codes = _allocated_pool(db, product, import_batch, ["K100", "K101", "K102"])
        result = _allocate(db, hq_admin, product, hq_company, 3)

        codes[1].status = status
        db.flush()

        with pytest.raises(ApiError) as exc:
            allocation_service.reclaim(db, order_id=result.order.id, operator_id=hq_admin.id)
        assert exc.value.details["blocked"] == 1

        # 整单拒绝：一个码都不该被改动
        db.refresh(codes[0])
        db.refresh(codes[2])
        assert codes[0].status == "allocated"
        assert codes[2].status == "allocated"
        db.refresh(result.order)
        assert result.order.status == "active"

    def test_cannot_reclaim_twice(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _allocated_pool(db, product, import_batch, ["K200"])
        result = _allocate(db, hq_admin, product, hq_company, 1)
        allocation_service.reclaim(db, order_id=result.order.id, operator_id=hq_admin.id)

        with pytest.raises(ApiError) as exc:
            allocation_service.reclaim(db, order_id=result.order.id, operator_id=hq_admin.id)
        assert "已被回收" in exc.value.message

    def test_unknown_order_is_404(self, db: Session, hq_admin):
        with pytest.raises(ApiError) as exc:
            allocation_service.reclaim(db, order_id=999999, operator_id=hq_admin.id)
        assert exc.value.error_code == "NOT_FOUND"
