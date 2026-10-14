"""T053：换绑限制与一码一产品（FR-022 / FR-023 / FR-024）。

FR-023 是硬约束：已分配的码不允许换绑，已打印的码不允许任何绑定变更。
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.product import Product
from app.services import code_binding

pytestmark = pytest.mark.integration


@pytest.fixture
def other_product(db: Session) -> Product:
    item = Product(code="P002", name="330ml 汽水", status="active")
    db.add(item)
    db.flush()
    return item


def _seed(db: Session, product: Product, batch) -> list[Code]:
    """在指定批次下放三个未分配的码。"""
    codes = [
        Code(
            code_value=value,
            status="unallocated",
            product_id=product.id,
            import_batch_id=batch.id,
        )
        for value in ("B001", "B002", "B003")
    ]
    db.add_all(codes)
    db.flush()
    return codes


def _codes_of(db: Session, batch_id: int) -> list[Code]:
    return list(
        db.execute(select(Code).where(Code.import_batch_id == batch_id).order_by(Code.code_value))
        .scalars()
    )


class TestBatchBinding:
    def test_rebinds_unallocated_codes(
        self, db: Session, hq_admin, product, other_product, import_batch
    ):
        _seed(db, product, import_batch)

        result = code_binding.bind_batch(
            db, batch_id=import_batch.id, product_id=other_product.id, operator_id=hq_admin.id
        )

        assert result.rebound == 3
        assert result.skipped == 0
        assert {c.product_id for c in _codes_of(db, import_batch.id)} == {other_product.id}

    def test_skips_codes_already_allocated(
        self, db: Session, hq_admin, product, other_product, hq_company, import_batch
    ):
        codes = _seed(db, product, import_batch)
        codes[0].status = "allocated"
        codes[0].company_id = hq_company.id
        db.flush()

        result = code_binding.bind_batch(
            db, batch_id=import_batch.id, product_id=other_product.id, operator_id=hq_admin.id
        )

        assert result.rebound == 2
        assert result.skipped == 1
        db.refresh(codes[0])
        assert codes[0].product_id == product.id, "已分配的码不得换绑（FR-023）"

    def test_skips_printed_codes(
        self, db: Session, hq_admin, product, other_product, hq_company, import_batch
    ):
        codes = _seed(db, product, import_batch)
        codes[0].status = "printed"
        codes[0].company_id = hq_company.id
        db.flush()

        result = code_binding.bind_batch(
            db, batch_id=import_batch.id, product_id=other_product.id, operator_id=hq_admin.id
        )

        assert result.skipped == 1
        assert result.skipped_reasons, "跳过原因应可回溯"
        db.refresh(codes[0])
        assert codes[0].product_id == product.id, "已打印的码不得任何绑定变更（FR-023）"

    def test_writes_binding_event(
        self, db: Session, hq_admin, product, other_product, import_batch
    ):
        _seed(db, product, import_batch)
        code_binding.bind_batch(
            db, batch_id=import_batch.id, product_id=other_product.id, operator_id=hq_admin.id
        )

        events = list(
            db.execute(select(CodeEvent).where(CodeEvent.event_type == "bound")).scalars()
        )
        assert len(events) == 3

    def test_disabled_product_rejected(
        self, db: Session, hq_admin, product, other_product, import_batch
    ):
        _seed(db, product, import_batch)
        other_product.status = "disabled"
        db.flush()

        with pytest.raises(ApiError) as exc:
            code_binding.bind_batch(
                db, batch_id=import_batch.id, product_id=other_product.id, operator_id=hq_admin.id
            )
        assert exc.value.error_code == "VALIDATION_ERROR"


class TestSingleBinding:
    def test_unallocated_code_can_be_rebound(
        self, db: Session, hq_admin, product, other_product, import_batch
    ):
        _seed(db, product, import_batch)
        code = code_binding.bind_single(
            db, code_value="B001", product_id=other_product.id, operator_id=hq_admin.id
        )
        assert code.product_id == other_product.id

    @pytest.mark.parametrize("status", ["allocated", "printing", "printed", "voided"])
    def test_non_pool_codes_rejected(
        self, db: Session, hq_admin, product, other_product, import_batch, status
    ):
        codes = _seed(db, product, import_batch)
        target = codes[0]
        target.status = status
        db.flush()

        with pytest.raises(ApiError) as exc:
            code_binding.bind_single(
                db,
                code_value=target.code_value,
                product_id=other_product.id,
                operator_id=hq_admin.id,
            )
        assert exc.value.error_code == "VALIDATION_ERROR"
        db.refresh(target)
        assert target.product_id == product.id

    def test_disabled_product_rejected(
        self, db: Session, hq_admin, product, other_product, import_batch
    ):
        _seed(db, product, import_batch)
        other_product.status = "disabled"
        db.flush()

        with pytest.raises(ApiError) as exc:
            code_binding.bind_single(db, code_value="B001", product_id=other_product.id)
        assert exc.value.error_code == "VALIDATION_ERROR"


class TestOneProductPerCode:
    """FR-024：一个码同一时间只能属于一个产品。

    由 Code.product_id 单值外键在结构上保证；这里锁定换绑后旧关联确实被替换。
    """

    def test_rebinding_replaces_rather_than_adds(
        self, db: Session, hq_admin, product, other_product, import_batch
    ):
        _seed(db, product, import_batch)
        code_binding.bind_batch(
            db, batch_id=import_batch.id, product_id=other_product.id, operator_id=hq_admin.id
        )

        remaining = db.execute(
            select(func.count()).select_from(Code).where(Code.product_id == product.id)
        ).scalar_one()
        assert remaining == 0
        assert len(_codes_of(db, import_batch.id)) == 3

    def test_rebind_to_same_product_is_noop(
        self, db: Session, hq_admin, product, import_batch
    ):
        _seed(db, product, import_batch)
        result = code_binding.bind_batch(
            db, batch_id=import_batch.id, product_id=product.id, operator_id=hq_admin.id
        )
        assert result.rebound == 0
        assert result.skipped == 0


class TestBatchSummary:
    def test_count_by_batch_groups_by_status(
        self, db: Session, product, import_batch, hq_company
    ):
        codes = _seed(db, product, import_batch)
        codes[0].status = "allocated"
        codes[0].company_id = hq_company.id
        db.flush()

        summary = code_binding.count_by_batch(db, import_batch.id)
        assert summary == {"unallocated": 2, "allocated": 1}
