"""T067：并发分配抢码（FR-044 同族的并发语义 / research.md R2）。

这是唯一验证 `SELECT ... FOR UPDATE SKIP LOCKED` 真的生效的测试。

注意本文件与其他测试的差异：它**必须提交事务**（否则行锁不产生竞争），
因此用独立会话而非共享夹具会话，并在首尾清理自己写入的数据，
避免污染同一测试库里的其他用例。
"""

import threading

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.allocation_order import AllocationOrder
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.company import Company
from app.models.import_batch import ImportBatch
from app.models.product import Product
from app.models.template import Template, TemplateVersion
from app.models.user import User
from app.services import allocation as allocation_service

pytestmark = pytest.mark.integration

POOL_SIZE = 10


def _wipe(engine) -> None:
    """清掉本文件会写入的表。

    顺序受外键约束驱动：product.default_template_id 指向 template，
    所以 Product 必须排在 Template 之前删除。
    """
    with Session(engine) as session:
        for model in (CodeEvent, Code, AllocationOrder, ImportBatch):
            session.execute(delete(model))
        session.execute(delete(Product))
        session.execute(delete(TemplateVersion))
        session.execute(delete(Template))
        session.execute(delete(User))
        session.execute(delete(Company))
        session.commit()


def _seed(engine) -> dict:
    """提交一批可分配的码，返回并发线程需要的 id。"""
    with Session(engine) as session:
        company = Company(code="CC1", name="并发测试公司", status="active")
        operator = User(
            username="cc-op",
            display_name="并发操作员",
            password_hash="x",
            role="hq_admin",
            company_id=None,
            status="active",
        )
        session.add_all([company, operator])
        session.flush()

        product = Product(code="PC1", name="并发测试产品", status="active")
        session.add(product)
        session.flush()

        template = Template(code="TC1", name="并发模板", status="active")
        session.add(template)
        session.flush()

        version = TemplateVersion(
            template_id=template.id,
            version_no=1,
            paper_width_mm=60,
            paper_height_mm=40,
            elements_json={"paper_width_mm": 60, "paper_height_mm": 40, "elements": []},
            frozen=False,
        )
        session.add(version)
        session.flush()
        product.default_template_id = template.id

        batch = ImportBatch(
            batch_no="IMPCONC",
            code_list_filename="c.xlsx",
            mapping_filename="m.xlsx",
            status="succeeded",
            processed_rows=0,
            success_count=0,
            failure_count=0,
            created_by=operator.id,
        )
        session.add(batch)
        session.flush()

        session.add_all(
            [
                Code(
                    code_value=f"CONC{i:04d}",
                    status="unallocated",
                    product_id=product.id,
                    import_batch_id=batch.id,
                )
                for i in range(POOL_SIZE)
            ]
        )
        session.commit()

        return {
            "company_id": company.id,
            "product_id": product.id,
            "operator_id": operator.id,
        }


def _worker(engine, barrier, out: dict, idx: int, ids: dict, quantity: int) -> None:
    with Session(engine) as session:
        barrier.wait(timeout=15)
        try:
            result = allocation_service.allocate(
                session,
                company_id=ids["company_id"],
                product_id=ids["product_id"],
                quantity=quantity,
                operator_id=ids["operator_id"],
            )
            session.commit()
            out[idx] = {"ok": True, "allocated": result.allocated, "order_id": result.order.id}
        except ApiError as exc:
            session.rollback()
            out[idx] = {"ok": False, "error_code": exc.error_code}
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            out[idx] = {"ok": False, "error_code": type(exc).__name__, "detail": str(exc)[:200]}


def _run_concurrently(engine, ids: dict, quantities: tuple[int, int]) -> dict:
    barrier = threading.Barrier(2)
    out: dict = {}
    threads = [
        threading.Thread(target=_worker, args=(engine, barrier, out, i, ids, qty))
        for i, qty in enumerate(quantities)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(out) == 2, f"有线程未完成：{out}"
    return out


class TestConcurrentAllocation:
    def test_two_allocations_of_half_the_pool_both_succeed_with_disjoint_codes(self, engine):
        """各取一半：两边都应成功，且取到的码互不重叠。"""
        _wipe(engine)
        try:
            ids = _seed(engine)
            out = _run_concurrently(engine, ids, (5, 5))

            assert out[0].get("boom") is None and out[1].get("boom") is None
            assert all(r["ok"] for r in out.values()), f"两边都该成功：{out}"
            assert {r["allocated"] for r in out.values()} == {5}
            # 两个分配单不同 —— 没有串到同一个单上
            assert out[0]["order_id"] != out[1]["order_id"]

            with Session(engine) as session:
                values = list(
                    session.execute(select(Code.code_value).where(Code.status == "allocated")).scalars()
                )
            assert len(values) == 10, "两个线程合计应恰好取走 10 个码"
            assert len(set(values)) == 10, f"出现重复分配：{values}"
        finally:
            _wipe(engine)

    def test_second_allocation_sees_reduced_stock_and_fails(self, engine):
        """总量不够时，后到的一方必须拿不到码并明确报错，而不是重复取走同一批。"""
        _wipe(engine)
        try:
            ids = _seed(engine)
            out = _run_concurrently(engine, ids, (8, 8))

            successes = [r for r in out.values() if r["ok"]]
            failures = [r for r in out.values() if not r["ok"]]
            assert len(successes) == 1, f"只应有一方拿满：{out}"
            assert successes[0]["allocated"] == 8
            assert len(failures) == 1

            with Session(engine) as session:
                allocated = session.execute(
                    select(Code).where(Code.status == "allocated")
                ).scalars().all()
            assert len(allocated) == 8, "失败的分配不得留下任何痕迹"
        finally:
            _wipe(engine)

    def test_skip_locked_does_not_deadlock(self, engine):
        """SKIP LOCKED 的意义：并发取码不互相等待，因此不应出现死锁。"""
        _wipe(engine)
        try:
            ids = _seed(engine)
            out = _run_concurrently(engine, ids, (3, 3))
            for result in out.values():
                assert result.get("error_code") != "OperationalError", f"出现死锁/锁等待超时：{out}"
                assert result["ok"], f"各取 3 个不该失败：{out}"
        finally:
            _wipe(engine)
