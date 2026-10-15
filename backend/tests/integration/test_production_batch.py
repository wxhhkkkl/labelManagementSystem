import pytest
from sqlalchemy import select

from app.core.errors import ApiError
from app.models.code import Code
from app.services.allocation import allocate
from app.services.template_resolver import dynamic_fields_for
from tests.integration.test_allocation_order import pool

pytestmark = pytest.mark.integration


def test_production_batch_is_required_and_stored_separately(
    db, product, import_batch, hq_company, hq_admin, template_version
):
    template_version.elements_json = {
        "paper_width_mm": 40,
        "paper_height_mm": 55,
        "elements": [
            {
                "type": "field",
                "field_name": "production_batch_no",
                "x": 3,
                "y": 42,
                "font_size": 2.8,
            }
        ],
    }
    pool(db, product, import_batch, ["PRODBATCH01"])
    args = dict(
        company_id=hq_company.id, product_id=product.id, quantity=1, operator_id=hq_admin.id
    )
    with pytest.raises(ApiError, match="生产批号"):
        allocate(db, **args, production_batch_no="  ")
    result = allocate(db, **args, production_batch_no=" 22PT510020DPHXQ1V ")
    code = db.scalar(select(Code).where(Code.code_value == "PRODBATCH01"))
    fields = dynamic_fields_for(db, code)
    assert fields["production_batch_no"] == "22PT510020DPHXQ1V"
    assert fields["batch_no"] == result.order.order_no
    assert result.order.production_batch_no == "22PT510020DPHXQ1V"
