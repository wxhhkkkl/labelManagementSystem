"""T066：分配单生成与模板携带（FR-027 / FR-028 / FR-035）。

分配单必须记录单号、公司、产品、码数量、码段范围、模板版本、分配人、时间；
未显式指定模板版本时取产品默认模板的当前版本。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.allocation_order import AllocationOrder
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.template import TemplateVersion
from app.services import allocation as allocation_service

pytestmark = pytest.mark.integration


def pool(db: Session, product, batch, values: list[str]) -> list[Code]:
    codes = [
        Code(code_value=v, status="unallocated", product_id=product.id, import_batch_id=batch.id)
        for v in values
    ]
    db.add_all(codes)
    db.flush()
    return codes


class TestOrderCreation:
    def test_creates_order_with_all_required_fields(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        pool(db, product, import_batch, ["A001", "A002", "A003"])

        result = allocation_service.allocate(
            db,
            company_id=hq_company.id,
            product_id=product.id,
            quantity=3,
            operator_id=hq_admin.id,
        )

        order = result.order
        assert order.order_no.startswith("ALL")
        assert order.company_id == hq_company.id
        assert order.product_id == product.id
        assert order.code_count == 3
        assert order.allocated_by == hq_admin.id
        assert order.allocated_at is not None
        assert order.status == "active"
        # 码段范围按实际取到的码记录
        assert order.code_range_from == "A001"
        assert order.code_range_to == "A003"

    def test_defaults_to_product_template_version(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        pool(db, product, import_batch, ["A010"])
        result = allocation_service.allocate(
            db, company_id=hq_company.id, product_id=product.id, quantity=1, operator_id=hq_admin.id
        )
        assert result.order.template_version_id == template_version.id

    def test_explicit_template_version_is_honoured(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        # 同模板的第二个版本
        v2 = TemplateVersion(
            template_id=template_version.template_id,
            version_no=2,
            paper_width_mm=70,
            paper_height_mm=50,
            elements_json={"paper_width_mm": 70, "paper_height_mm": 50, "elements": []},
            frozen=False,
        )
        db.add(v2)
        db.flush()
        pool(db, product, import_batch, ["A020"])

        result = allocation_service.allocate(
            db,
            company_id=hq_company.id,
            product_id=product.id,
            quantity=1,
            operator_id=hq_admin.id,
            template_version_id=v2.id,
        )
        assert result.order.template_version_id == v2.id

    def test_missing_version_is_rejected_when_product_has_no_default_template(
        self, db: Session, hq_admin, product, hq_company, import_batch
    ):
        # 未绑定默认模板的产品无法确定版本，必须拒绝而不是落一个空值
        pool(db, product, import_batch, ["A030"])
        with pytest.raises(ApiError) as exc:
            allocation_service.allocate(
                db,
                company_id=hq_company.id,
                product_id=product.id,
                quantity=1,
                operator_id=hq_admin.id,
            )
        assert "默认打印模板" in exc.value.message


class TestCodeStateAfterAllocation:
    def test_codes_become_allocated_and_belong_to_company(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        pool(db, product, import_batch, ["A100", "A101"])
        result = allocation_service.allocate(
            db, company_id=hq_company.id, product_id=product.id, quantity=2, operator_id=hq_admin.id
        )

        codes = list(db.execute(select(Code)).scalars())
        assert {c.status for c in codes} == {"allocated"}
        assert {c.company_id for c in codes} == {hq_company.id}
        assert {c.current_allocation_order_id for c in codes} == {result.order.id}

    def test_writes_allocation_event_per_code(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        pool(db, product, import_batch, ["A110", "A111", "A112"])
        allocation_service.allocate(
            db, company_id=hq_company.id, product_id=product.id, quantity=3, operator_id=hq_admin.id
        )

        events = list(
            db.execute(select(CodeEvent).where(CodeEvent.event_type == "allocated")).scalars()
        )
        assert len(events) == 3
        assert {e.from_status for e in events} == {"unallocated"}
        assert {e.to_status for e in events} == {"allocated"}


class TestGuards:
    def test_disabled_company_cannot_receive(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        hq_company.status = "disabled"
        db.flush()
        pool(db, product, import_batch, ["A200"])

        with pytest.raises(ApiError) as exc:
            allocation_service.allocate(
                db, company_id=hq_company.id, product_id=product.id, quantity=1, operator_id=hq_admin.id
            )
        assert "停用" in exc.value.message

    def test_disabled_product_cannot_be_allocated(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        product.status = "disabled"
        db.flush()
        pool(db, product, import_batch, ["A210"])

        with pytest.raises(ApiError) as exc:
            allocation_service.allocate(
                db, company_id=hq_company.id, product_id=product.id, quantity=1, operator_id=hq_admin.id
            )
        assert "停用" in exc.value.message

    def test_insufficient_available_reports_the_number(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        pool(db, product, import_batch, ["A300", "A301"])

        with pytest.raises(ApiError) as exc:
            allocation_service.allocate(
                db, company_id=hq_company.id, product_id=product.id, quantity=5, operator_id=hq_admin.id
            )
        assert exc.value.details["available"] == 2
        assert exc.value.details["requested"] == 5

    def test_zero_or_negative_quantity_rejected(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        for qty in (0, -1):
            with pytest.raises(ApiError):
                allocation_service.allocate(
                    db,
                    company_id=hq_company.id,
                    product_id=product.id,
                    quantity=qty,
                    operator_id=hq_admin.id,
                )


class TestTemplateVersionFreeze:
    """FR-034：被分配单引用的模板版本内容冻结。"""

    def test_version_is_frozen_on_allocation(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        assert template_version.frozen is False
        pool(db, product, import_batch, ["A400"])
        allocation_service.allocate(
            db, company_id=hq_company.id, product_id=product.id, quantity=1, operator_id=hq_admin.id
        )
        db.refresh(template_version)
        assert template_version.frozen is True
