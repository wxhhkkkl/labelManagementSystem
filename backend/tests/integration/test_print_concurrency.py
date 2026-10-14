"""T081：并发抢码（FR-044）。

两个工位同时打印同一个码时，MUST 只有一方成功、另一方被拒。
这是"一码一打"在并发路径上的保证——顺序执行测不出来。

与分配并发测试一样，本文件**必须提交事务**才有行锁竞争，
因此用独立会话并在首尾清理自己写入的数据。
"""

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.allocation_order import AllocationOrder
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.company import Company
from app.models.import_batch import ImportBatch
from app.models.print_log import PrintLog
from app.models.print_task import PrintTask
from app.models.product import Product
from app.models.template import Template, TemplateVersion
from app.models.user import User
from app.models.workstation import Workstation
from app.services import printing

pytestmark = pytest.mark.integration


def _wipe(engine) -> None:
    """顺序受外键约束驱动：product 引用 template，必须先删 product。"""
    with Session(engine) as session:
        for model in (PrintLog, PrintTask, CodeEvent, Code, AllocationOrder, ImportBatch):
            session.execute(delete(model))
        session.execute(delete(Workstation))
        session.execute(delete(Product))
        session.execute(delete(TemplateVersion))
        session.execute(delete(Template))
        session.execute(delete(User))
        session.execute(delete(Company))
        session.commit()


def _seed(engine, *, code_values: list[str]) -> dict:
    """造出两个本公司工位 + 一批已分配的码（提交入库）。"""
    with Session(engine) as session:
        company = Company(code="PC", name="打印并发公司", status="active")
        operator = User(
            username="pc-op",
            display_name="打印并发操作员",
            password_hash="x",
            role="operator",
            company_id=None,
            status="active",
        )
        session.add_all([company, operator])
        session.flush()
        operator.company_id = company.id

        product = Product(code="PP", name="打印并发产品", status="active")
        session.add(product)
        session.flush()

        template = Template(code="PT", name="并发模板", status="active")
        session.add(template)
        session.flush()

        version = TemplateVersion(
            template_id=template.id,
            version_no=1,
            paper_width_mm=60,
            paper_height_mm=40,
            elements_json={"paper_width_mm": 60, "paper_height_mm": 40, "elements": []},
            frozen=True,
        )
        session.add(version)
        session.flush()
        product.default_template_id = template.id

        batch = ImportBatch(
            batch_no="IMPPC",
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

        ws_a = Workstation(
            code="PWA", name="并发工位A", company_id=company.id,
            printer_name="Printer-A", status="active",
        )
        ws_b = Workstation(
            code="PWB", name="并发工位B", company_id=company.id,
            printer_name="Printer-B", status="active",
        )
        session.add_all([ws_a, ws_b])
        session.flush()

        order = AllocationOrder(
            order_no="ALLPC",
            company_id=company.id,
            product_id=product.id,
            code_count=len(code_values),
            template_version_id=version.id,
            allocated_by=operator.id,
            allocated_at=datetime.now(UTC).replace(tzinfo=None),
            status="active",
        )
        session.add(order)
        session.flush()

        session.add_all(
            [
                Code(
                    code_value=value,
                    status="allocated",
                    product_id=product.id,
                    company_id=company.id,
                    import_batch_id=batch.id,
                    current_allocation_order_id=order.id,
                )
                for value in code_values
            ]
        )
        session.commit()

        return {
            "operator_id": operator.id,
            "ws_a": ws_a.id,
            "ws_b": ws_b.id,
        }


def _worker(engine, barrier, out: dict, idx: int, ws_id: int, operator_id: int, values: list[str]):
    with Session(engine) as session:
        barrier.wait(timeout=15)
        try:
            workstation = session.get(Workstation, ws_id)
            accepted, rejected = printing.preempt(
                session,
                workstation=workstation,
                operator_id=operator_id,
                code_values=values,
            )
            session.commit()
            out[idx] = {
                "ok": True,
                "accepted": [a.code_value for a in accepted],
                "rejected": [(r.code_value, r.error_code) for r in rejected],
            }
        except ApiError as exc:
            session.rollback()
            out[idx] = {"ok": False, "error_code": exc.error_code}
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            out[idx] = {"ok": False, "error_code": type(exc).__name__, "detail": str(exc)[:200]}


def _run(engine, ids: dict, values_a: list[str], values_b: list[str]) -> dict:
    barrier = threading.Barrier(2)
    out: dict = {}
    threads = [
        threading.Thread(
            target=_worker, args=(engine, barrier, out, 0, ids["ws_a"], ids["operator_id"], values_a)
        ),
        threading.Thread(
            target=_worker, args=(engine, barrier, out, 1, ids["ws_b"], ids["operator_id"], values_b)
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(out) == 2, f"有线程未完成：{out}"
    return out


class TestSameCodeConcurrently:
    def test_only_one_workstation_wins(self, engine):
        """核心断言：同一个码被两个工位同时抢，只有一方拿到。"""
        _wipe(engine)
        try:
            ids = _seed(engine, code_values=["CC001"])
            out = _run(engine, ids, ["CC001"], ["CC001"])

            for result in out.values():
                assert result.get("error_code") != "OperationalError", f"不应出现死锁：{out}"

            winners = [r for r in out.values() if r["accepted"]]
            losers = [r for r in out.values() if not r["accepted"]]
            assert len(winners) == 1, f"只能有一方成功：{out}"
            assert len(losers) == 1, f"另一方必须被拒：{out}"
            assert losers[0]["rejected"][0][1] in ("CODE_LOCKED", "CODE_ALREADY_PRINTED")

            with Session(engine) as session:
                code = session.execute(
                    select(Code).where(Code.code_value == "CC001")
                ).scalar_one()
            assert code.status == "printing"
        finally:
            _wipe(engine)

    def test_loser_leaves_no_trace(self, engine):
        """落败方不得改动码状态，也不得留下打印记录。"""
        _wipe(engine)
        try:
            ids = _seed(engine, code_values=["CC002"])
            _run(engine, ids, ["CC002"], ["CC002"])

            with Session(engine) as session:
                logs = list(session.execute(select(PrintLog)).scalars())
                events = list(
                    session.execute(
                        select(CodeEvent).where(CodeEvent.event_type == "print_started")
                    ).scalars()
                )
            assert logs == [], "预占还未确认，不该有打印记录"
            assert len(events) == 1, f"只应有一次预占事件：{len(events)}"
        finally:
            _wipe(engine)


class TestDifferentCodesConcurrently:
    def test_both_workstations_succeed_on_disjoint_codes(self, engine):
        """不是所有并发都该失败——不同码之间不应互相阻塞。"""
        _wipe(engine)
        try:
            ids = _seed(engine, code_values=["DC001", "DC002", "DC003", "DC004"])
            out = _run(engine, ids, ["DC001", "DC002"], ["DC003", "DC004"])

            for result in out.values():
                assert result["ok"], f"不同码不该冲突：{out}"
                assert len(result["accepted"]) == 2
                assert result["rejected"] == []

            with Session(engine) as session:
                statuses = {
                    c.code_value: c.status
                    for c in session.execute(select(Code)).scalars()
                }
            assert set(statuses.values()) == {"printing"}
        finally:
            _wipe(engine)

    def test_partial_overlap_conflicts_only_on_the_shared_code(self, engine):
        """部分重叠时，只有重叠的那个码冲突，其余照常成功。"""
        _wipe(engine)
        try:
            ids = _seed(engine, code_values=["PO001", "PO002", "PO003"])
            out = _run(engine, ids, ["PO001", "PO002"], ["PO002", "PO003"])

            accepted_total = sum(len(r["accepted"]) for r in out.values())
            rejected_total = sum(len(r["rejected"]) for r in out.values())
            # 三个码各被接受恰好一次，合计 3；重叠的那个码让另一方失败一次
            assert accepted_total == 3, f"每个码只能被一方拿到：{out}"
            assert rejected_total == 1, f"另一方应在 PO002 上失败：{out}"

            accepted_values = [v for r in out.values() for v in r["accepted"]]
            assert sorted(accepted_values) == ["PO001", "PO002", "PO003"], f"不得重复预占：{out}"
            assert {v for r in out.values() for v, _ in r["rejected"]} == {"PO002"}

            with Session(engine) as session:
                locked = set(
                    session.execute(
                        select(Code.code_value).where(Code.status == "printing")
                    ).scalars()
                )
            assert locked == {"PO001", "PO002", "PO003"}
        finally:
            _wipe(engine)
