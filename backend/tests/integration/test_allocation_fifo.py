"""T069：取码顺序与定向分配（FR-025 / FR-026）。

默认按导入批次先进先出——早导入的码先被分配出去，
否则先导入的码会长期滞留在池底。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.import_batch import ImportBatch
from app.models.user import User
from app.services import allocation as allocation_service

pytestmark = pytest.mark.integration


@pytest.fixture
def second_batch(db: Session, hq_admin: User) -> ImportBatch:
    batch = ImportBatch(
        batch_no="IMPB2",
        code_list_filename="c2.xlsx",
        mapping_filename="m2.xlsx",
        status="succeeded",
        processed_rows=0,
        success_count=0,
        failure_count=0,
        created_by=hq_admin.id,
    )
    db.add(batch)
    db.flush()
    return batch


def _pool(db: Session, product, batch, values: list[str]) -> None:
    db.add_all(
        [
            Code(code_value=v, status="unallocated", product_id=product.id, import_batch_id=batch.id)
            for v in values
        ]
    )
    db.flush()


def _allocated_values(db: Session) -> set[str]:
    return set(db.execute(select(Code.code_value).where(Code.status == "allocated")).scalars())


class TestFifo:
    def test_earlier_batch_is_taken_first(
        self, db: Session, hq_admin, product, hq_company, import_batch, second_batch, template_version
    ):
        # 第一批早于第二批创建，应优先被取走
        _pool(db, product, import_batch, ["B1-001", "B1-002"])
        _pool(db, product, second_batch, ["B2-001", "B2-002"])

        allocation_service.allocate(
            db, company_id=hq_company.id, product_id=product.id, quantity=2, operator_id=hq_admin.id
        )

        assert _allocated_values(db) == {"B1-001", "B1-002"}

    def test_spills_into_next_batch_when_first_is_exhausted(
        self, db: Session, hq_admin, product, hq_company, import_batch, second_batch, template_version
    ):
        _pool(db, product, import_batch, ["B1-001"])
        _pool(db, product, second_batch, ["B2-001", "B2-002"])

        allocation_service.allocate(
            db, company_id=hq_company.id, product_id=product.id, quantity=3, operator_id=hq_admin.id
        )

        assert _allocated_values(db) == {"B1-001", "B2-001", "B2-002"}


class TestTargetedAllocation:
    """FR-026：支持选择特定批次进行定向分配。"""

    def test_batch_filter_ignores_earlier_batches(
        self, db: Session, hq_admin, product, hq_company, import_batch, second_batch, template_version
    ):
        _pool(db, product, import_batch, ["B1-001", "B1-002"])
        _pool(db, product, second_batch, ["B2-001", "B2-002"])

        allocation_service.allocate(
            db,
            company_id=hq_company.id,
            product_id=product.id,
            quantity=2,
            operator_id=hq_admin.id,
            batch_id=second_batch.id,
        )

        assert _allocated_values(db) == {"B2-001", "B2-002"}

    def test_code_range_filter_narrows_the_selection(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        _pool(db, product, import_batch, ["R001", "R002", "R003", "R004"])

        allocation_service.allocate(
            db,
            company_id=hq_company.id,
            product_id=product.id,
            quantity=2,
            operator_id=hq_admin.id,
            code_range_from="R002",
            code_range_to="R003",
        )

        assert _allocated_values(db) == {"R002", "R003"}

    def test_available_count_honours_filters(
        self, db: Session, hq_admin, product, hq_company, import_batch, second_batch, template_version
    ):
        _pool(db, product, import_batch, ["B1-001", "B1-002"])
        _pool(db, product, second_batch, ["B2-001"])

        assert allocation_service.available_count(db, product_id=product.id) == 3
        assert (
            allocation_service.available_count(db, product_id=product.id, batch_id=second_batch.id)
            == 1
        )
        assert (
            allocation_service.available_count(
                db, product_id=product.id, code_range_from="B1-002"
            )
            == 2
        )

    def test_other_products_codes_are_not_touched(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        from app.models.product import Product

        other = Product(code="P-OTHER", name="别的产品", status="active")
        db.add(other)
        db.flush()
        _pool(db, product, import_batch, ["M001"])
        _pool(db, other, import_batch, ["N001", "N002"])

        allocation_service.allocate(
            db, company_id=hq_company.id, product_id=product.id, quantity=1, operator_id=hq_admin.id
        )

        assert _allocated_values(db) == {"M001"}
