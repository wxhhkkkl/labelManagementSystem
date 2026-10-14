"""T155：批量打印下发性能（SC-005）。

"单次 500 码的批量打印任务在 60 秒内完成下发"。

这里的"下发"指服务端把 500 个码预占为 `printing` 并把模板与数据交给工位端——
实际出纸由工位端逐张完成，不计入这 60 秒。

用真实 HTTP 接口测而不是直接调服务层：接口层还包含鉴权、审计、序列化开销，
只测服务层会低估真实耗时。
"""

import time

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import auth_header
from tests.helpers import make_printable

pytestmark = pytest.mark.integration

BATCH_SIZE = 500
TIME_BUDGET_SECONDS = 60


@pytest.fixture
def batch_codes(
    db: Session, product, hq_company, import_batch, template_version, hq_admin
):
    values = [f"BATCH{i:05d}" for i in range(BATCH_SIZE)]
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=values,
    )
    return values


class TestBatchPreempt:
    def test_500_codes_dispatch_within_budget(
        self, client, operator: User, workstation, batch_codes
    ):
        started = time.monotonic()
        resp = client.post(
            "/api/v1/workstation/print",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "code_values": batch_codes,
                "printer_name": "Zebra ZD421",
            },
        )
        elapsed = time.monotonic() - started

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["accepted"]) == BATCH_SIZE
        assert body["rejected"] == []

        assert elapsed < TIME_BUDGET_SECONDS, (
            f"500 码下发耗时 {elapsed:.1f}s，超出 {TIME_BUDGET_SECONDS}s 预算（SC-005）"
        )

    def test_each_accepted_item_carries_the_render_payload(
        self, client, operator: User, workstation, batch_codes, template_version
    ):
        """下发的不只是"可以打了"，而是工位端能直接渲染的完整数据。"""
        body = client.post(
            "/api/v1/workstation/print",
            headers=auth_header(operator),
            json={"workstation_id": workstation.id, "code_values": batch_codes[:10]},
        ).json()

        for item in body["accepted"]:
            assert item["template_version_id"] == template_version.id
            assert item["elements_json"]["paper_width_mm"] == 60
            assert item["data"]["code_value"] == item["code_value"]
            assert item["data"]["product_name"]
            assert item["data"]["batch_no"].startswith("ALL")

    def test_all_codes_are_locked_as_printing(
        self, client, db: Session, operator, workstation, batch_codes
    ):
        from sqlalchemy import func, select

        from app.models.code import Code

        client.post(
            "/api/v1/workstation/print",
            headers=auth_header(operator),
            json={"workstation_id": workstation.id, "code_values": batch_codes},
        )

        printing_count = db.execute(
            select(func.count())
            .select_from(Code)
            .where(Code.status == "printing", Code.locked_workstation_id == workstation.id)
        ).scalar_one()
        assert printing_count == BATCH_SIZE


class TestBatchConfirm:
    def test_500_codes_confirm_within_budget(
        self, client, db: Session, operator, workstation, batch_codes
    ):
        """确认 500 个码同样要快——它写在打印动作的关键路径上。"""
        client.post(
            "/api/v1/workstation/print",
            headers=auth_header(operator),
            json={"workstation_id": workstation.id, "code_values": batch_codes},
        )

        started = time.monotonic()
        resp = client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [
                    {"code_value": value, "outcome": "succeeded", "printer_name": "Zebra ZD421"}
                    for value in batch_codes
                ],
            },
        )
        elapsed = time.monotonic() - started

        assert resp.status_code == 200
        assert len(resp.json()["confirmed"]) == BATCH_SIZE
        assert elapsed < TIME_BUDGET_SECONDS, f"500 码确认耗时 {elapsed:.1f}s"

    def test_every_code_gets_a_print_log(
        self, client, db: Session, operator, workstation, batch_codes
    ):
        """SC-006：一条打印都不能漏记。"""
        from sqlalchemy import func, select

        from app.models.print_log import PrintLog

        client.post(
            "/api/v1/workstation/print",
            headers=auth_header(operator),
            json={"workstation_id": workstation.id, "code_values": batch_codes},
        )
        client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [{"code_value": v, "outcome": "succeeded"} for v in batch_codes],
            },
        )

        logs = db.execute(select(func.count()).select_from(PrintLog)).scalar_one()
        assert logs == BATCH_SIZE
