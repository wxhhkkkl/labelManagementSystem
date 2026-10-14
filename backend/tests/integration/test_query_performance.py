"""T130：百万级下列表查询 3 秒内返回（SC-013）。

这条测试保护的是**聚合下推**这个设计决定：看板与码池查询都必须由数据库完成，
把行拉回应用层再计数在百万级下必然超时。

默认造 20 万行（够暴露数量级问题，又不至于让回归太慢）。
要验真实目标规模：
    IMPORT_SCALE_ROWS 无关；用 PERF_ROWS=1000000 单独跑本文件。
"""

import os
import time

import pytest
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.product import Product
from app.models.user import User
from tests.conftest import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.scale]

ROWS = int(os.environ.get("PERF_ROWS", "200000"))
CHUNK = 5000
# SC-013 的目标是 3 秒。测试环境与生产不同，给一倍余量只为发现数量级退化。
TIME_BUDGET_SECONDS = 6.0

STATUS_MIX = ["unallocated", "allocated", "printing", "printed", "voided"]


@pytest.fixture(scope="module")
def bulk_codes(engine):
    """灌入 ROWS 条码，产出本次使用的产品 id；用完清理干净。

    两个作用域上的考量：
      * module 作用域——灌一次、跑多个查询，否则光准备数据就把时间吃光了。
      * 必须显式清理——这些数据是**提交**入库的，而本文件之后的测试
        （作废、补打、模板等）里有对码表的全量断言，残留的 20 万行会把它们全部打挂。
    """
    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session as RawSession

    from app.models.code_event import CodeEvent
    from app.models.import_batch import ImportBatch

    with RawSession(engine) as db:
        product = Product(code="PERF-P", name="性能测试产品", status="active")
        db.add(product)
        db.flush()

        user = User(
            username="perf-user",
            display_name="perf",
            password_hash="x",
            role="hq_admin",
            status="active",
        )
        db.add(user)
        db.flush()

        batch = ImportBatch(
            batch_no="IMPPERF",
            code_list_filename="c.xlsx",
            mapping_filename="m.xlsx",
            status="succeeded",
            processed_rows=0,
            success_count=0,
            failure_count=0,
            created_by=user.id,
        )
        db.add(batch)
        db.flush()

        for start in range(0, ROWS, CHUNK):
            db.execute(
                insert(Code),
                [
                    {
                        "code_value": f"PERF{i:012d}",
                        "status": STATUS_MIX[i % len(STATUS_MIX)],
                        "product_id": product.id,
                        "import_batch_id": batch.id,
                    }
                    for i in range(start, min(start + CHUNK, ROWS))
                ],
            )
        db.commit()
        # 必须在会话内取走：commit 会让实例属性过期，出了 with 再读就是 detached
        product_id = product.id

    yield product_id

    with RawSession(engine) as db:
        ids = list(
            db.execute(select(Code.id).where(Code.code_value.like("PERF%"))).scalars()
        )
        if ids:
            db.execute(delete(CodeEvent).where(CodeEvent.code_id.in_(ids)))
            db.execute(delete(Code).where(Code.id.in_(ids)))
        db.execute(delete(ImportBatch).where(ImportBatch.batch_no == "IMPPERF"))
        db.execute(delete(Product).where(Product.code == "PERF-P"))
        db.execute(delete(User).where(User.username == "perf-user"))
        db.commit()


def _timed(fn):
    started = time.monotonic()
    result = fn()
    return result, time.monotonic() - started


class TestDashboardAtScale:
    def test_distribution_query_completes_within_budget(
        self, client, db: Session, hq_admin: User, bulk_codes
    ):
        def call():
            resp = client.get(
                "/api/v1/dashboard/code-distribution", headers=auth_header(hq_admin)
            )
            assert resp.status_code == 200
            return resp.json()

        body, elapsed = _timed(call)

        assert body["totals"]["total"] >= ROWS
        assert elapsed < TIME_BUDGET_SECONDS, (
            f"看板聚合耗时 {elapsed:.2f}s（{ROWS} 行），超出 {TIME_BUDGET_SECONDS}s 预算——"
            "聚合可能被拉回了应用层"
        )

    def test_group_by_company_is_no_slower(self, client, hq_admin, bulk_codes):
        def call():
            resp = client.get(
                "/api/v1/dashboard/code-distribution?group_by=company",
                headers=auth_header(hq_admin),
            )
            return resp.json()

        body, elapsed = _timed(call)
        assert body["totals"]["total"] >= ROWS
        assert elapsed < TIME_BUDGET_SECONDS, f"按公司聚合耗时 {elapsed:.2f}s"


class TestCodePoolAtScale:
    def test_paginated_query_is_fast(self, client, hq_admin, bulk_codes):
        """分页查询走索引，不该随总量线性变慢。"""

        def call():
            resp = client.get(
                f"/api/v1/codes?product_id={bulk_codes}&page=1&page_size=50",
                headers=auth_header(hq_admin),
            )
            assert resp.status_code == 200
            return resp.json()

        body, elapsed = _timed(call)

        assert len(body["items"]) == 50
        assert body["total"] >= ROWS
        assert elapsed < TIME_BUDGET_SECONDS, f"码池分页耗时 {elapsed:.2f}s"

    def test_filtered_by_status_is_fast(self, client, hq_admin, bulk_codes):
        def call():
            resp = client.get(
                f"/api/v1/codes?product_id={bulk_codes}&status=unallocated&page=1&page_size=50",
                headers=auth_header(hq_admin),
            )
            return resp.json()

        body, elapsed = _timed(call)
        assert body["items"]
        assert elapsed < TIME_BUDGET_SECONDS, f"按状态筛选耗时 {elapsed:.2f}s"


class TestPrintDetailAtScale:
    def test_limited_detail_query_is_fast(self, client, hq_admin: User, bulk_codes):
        """打印明细做了 limit，即使表很大也只取需要的那一段。"""

        def call():
            resp = client.get("/api/v1/reports/prints?limit=200", headers=auth_header(hq_admin))
            assert resp.status_code == 200
            return resp.json()

        _rows, elapsed = _timed(call)
        assert elapsed < TIME_BUDGET_SECONDS, f"打印明细查询耗时 {elapsed:.2f}s"
