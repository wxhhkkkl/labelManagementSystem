import pytest
from sqlalchemy import select

from app.models.code import Code
from app.models.import_batch import ImportBatch
from app.services.allocation import allocate
from app.services.template_resolver import dynamic_fields_for
from app.tasks.import_worker import process_batch
from tests.conftest import auth_header
from tests.contract.test_import_api import _xlsx_bytes

pytestmark = pytest.mark.integration


def upload(client, admin, product, rows, header=None):
    return client.post(
        "/api/v1/imports",
        headers=auth_header(admin),
        data={"product_id": product.id},
        files={
            "code_list_file": (
                "product-batch.xlsx",
                _xlsx_bytes(header or ["防伪码", "产品批号", "状态"], rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def test_one_file_keeps_each_batch_and_leading_zero_through_allocation(
    client, db, hq_admin, product, hq_company, template_version, import_storage
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
    response = upload(
        client,
        hq_admin,
        product,
        [
            ["0612286397031613", "22PT510020DL99S78", "未查"],
            ["5375762743854650", "22PT510020DPHXQ1V", "已查"],
        ],
    )
    assert response.status_code == 202
    process_batch(db, response.json()["batch_id"])
    batch = db.get(ImportBatch, response.json()["batch_id"])
    assert batch.status == "succeeded" and batch.success_count == 2
    codes = db.scalars(select(Code).order_by(Code.id)).all()
    assert [c.code_value for c in codes] == ["0612286397031613", "5375762743854650"]
    assert all(c.status == "unallocated" for c in codes)
    allocate(
        db,
        company_id=hq_company.id,
        product_id=product.id,
        quantity=2,
        operator_id=hq_admin.id,
        production_batch_no="FALLBACK",
    )
    assert [dynamic_fields_for(db, c)["production_batch_no"] for c in codes] == [
        "22PT510020DL99S78",
        "22PT510020DPHXQ1V",
    ]


@pytest.mark.parametrize(
    "rows,header",
    [
        ([["A001", "B1"], ["A001", "B2"]], None),
        ([["A001", "B1"]], ["防伪码", "错误批号"]),
    ],
)
def test_duplicate_or_wrong_header_does_not_insert(
    client, db, hq_admin, product, import_storage, rows, header
):
    response = upload(client, hq_admin, product, rows, header)
    process_batch(db, response.json()["batch_id"])
    batch = db.get(ImportBatch, response.json()["batch_id"])
    assert batch.status == "failed"
    assert batch.error_detail_path
    assert not db.scalars(select(Code)).all()


def test_bad_cells_are_reported_without_importing_corrupt_identifiers(
    client, db, hq_admin, product, import_storage
):
    response = upload(
        client,
        hq_admin,
        product,
        [
            ["GOOD1", "B1"],
            [5375762743854650, "B2"],
            ["FORMULA1", "=1+1"],
            ["NOBATCH", ""],
            ["BAD!", "B3"],
        ],
    )
    process_batch(db, response.json()["batch_id"])
    batch = db.get(ImportBatch, response.json()["batch_id"])
    assert batch.success_count == 1 and batch.failure_count == 4
    assert [c.code_value for c in db.scalars(select(Code)).all()] == ["GOOD1"]


def test_product_must_exist_and_be_active(client, hq_admin, product, import_storage):
    product.status = "disabled"
    response = upload(client, hq_admin, product, [["A001", "B1"]])
    assert response.status_code == 422
