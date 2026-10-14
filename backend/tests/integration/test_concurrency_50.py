"""T154：50 工位并发压测（SC-008）。

"支持不少于 50 个工位同时在线操作，无需人工干预"——这条只有真并发跑一遍才算数。

与其他并发测试一样，本文件**必须提交事务**才有锁竞争，因此用独立会话，
并在首尾清理自己写入的数据。
"""

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.allocation_order import AllocationOrder
from app.models.base import utcnow
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

pytestmark = [pytest.mark.integration, pytest.mark.scale]

WORKSTATIONS = 50
CODES_PER_WORKSTATION = 5
POOL_SIZE = WORKSTATIONS * CODES_PER_WORKSTATION


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


def _seed(engine) -> dict:
    """造 50 个工位、50 个操作员、以及足够每个工位打 5 张的码。"""
    with Session(engine) as session:
        company = Company(code="C50", name="压测公司", status="active")
        session.add(company)
        session.flush()

        product = Product(code="P50", name="压测产品", status="active")
        session.add(product)
        session.flush()

        template = Template(code="T50", name="压测模板", status="active")
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

        operator = User(
            username="op50",
            display_name="压测操作员",
            password_hash="x",
            role="operator",
            company_id=company.id,
            status="active",
        )
        session.add(operator)
        session.flush()

        # import_batch.created_by 非空，所以批次必须排在操作员之后建
        batch = ImportBatch(
            batch_no="IMPC50",
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

        order = AllocationOrder(
            order_no="ALL50",
            company_id=company.id,
            product_id=product.id,
            code_count=POOL_SIZE,
            template_version_id=version.id,
            allocated_by=operator.id,
            allocated_at=datetime.now(UTC).replace(tzinfo=None),
            status="active",
        )
        session.add(order)
        session.flush()

        workstations = [
            Workstation(
                code=f"W{i:03d}",
                name=f"压测工位{i}",
                company_id=company.id,
                printer_name=f"Printer-{i:03d}",
                status="active",
            )
            for i in range(WORKSTATIONS)
        ]
        session.add_all(workstations)
        session.flush()

        session.add_all(
            [
                Code(
                    code_value=f"C50{i:05d}",
                    status="allocated",
                    product_id=product.id,
                    company_id=company.id,
                    import_batch_id=batch.id,
                    current_allocation_order_id=order.id,
                )
                for i in range(POOL_SIZE)
            ]
        )
        session.commit()

        return {
            "operator_id": operator.id,
            "workstation_ids": [ws.id for ws in workstations],
        }


def _worker(engine, barrier, out: dict, index: int, workstation_id: int, operator_id: int, offset: int):
    """模拟一个工位：心跳 → 预占 → 确认，走完整的打印链路。"""
    values = [f"C50{i:05d}" for i in range(offset, offset + CODES_PER_WORKSTATION)]
    try:
        with Session(engine) as session:
            barrier.wait(timeout=30)

            # 心跳：50 个工位同时写 last_heartbeat_at
            workstation = session.get(Workstation, workstation_id)
            workstation.last_heartbeat_at = utcnow()
            session.flush()

            accepted, rejected = printing.preempt(
                session,
                workstation=workstation,
                operator_id=operator_id,
                code_values=values,
            )
            if rejected:
                out[index] = {"ok": False, "stage": "preempt", "rejected": [r.error_code for r in rejected]}
                session.rollback()
                return

            printing.confirm(
                session,
                workstation=workstation,
                operator_id=operator_id,
                results=[
                    {"code_value": item.code_value, "outcome": "succeeded", "printer_name": workstation.printer_name}
                    for item in accepted
                ],
            )
            session.commit()
            out[index] = {"ok": True, "printed": len(accepted)}
    except Exception as exc:  # noqa: BLE001
        out[index] = {"ok": False, "stage": "exception", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}


class TestFiftyWorkstations:
    def test_all_workstations_print_concurrently(self, engine):
        _wipe(engine)
        try:
            ids = _seed(engine)
            barrier = threading.Barrier(WORKSTATIONS)
            out: dict = {}

            threads = [
                threading.Thread(
                    target=_worker,
                    args=(
                        engine,
                        barrier,
                        out,
                        i,
                        ids["workstation_ids"][i],
                        ids["operator_id"],
                        i * CODES_PER_WORKSTATION,
                    ),
                )
                for i in range(WORKSTATIONS)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=120)

            assert len(out) == WORKSTATIONS, f"有工位未完成：已完成 {len(out)} 个"

            failures = {i: r for i, r in out.items() if not r["ok"]}
            assert not failures, f"并发下出现失败：{list(failures.items())[:3]}"

            with Session(engine) as session:
                printed = session.execute(
                    select(func.count()).select_from(Code).where(Code.status == "printed")
                ).scalar_one()
                logs = session.execute(select(func.count()).select_from(PrintLog)).scalar_one()

            assert printed == POOL_SIZE, f"应有 {POOL_SIZE} 个码打印完成，实际 {printed}"
            assert logs == POOL_SIZE, f"每条打印都该有记录，实际 {logs}"
        finally:
            _wipe(engine)

    def test_no_code_is_printed_twice(self, engine):
        """50 工位并发下，"一码一打"依然成立。"""
        _wipe(engine)
        try:
            ids = _seed(engine)
            barrier = threading.Barrier(WORKSTATIONS)
            out: dict = {}

            threads = [
                threading.Thread(
                    target=_worker,
                    args=(
                        engine, barrier, out, i,
                        ids["workstation_ids"][i], ids["operator_id"],
                        i * CODES_PER_WORKSTATION,
                    ),
                )
                for i in range(WORKSTATIONS)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=120)

            with Session(engine) as session:
                duplicates = session.execute(
                    select(PrintLog.code_value, func.count().label("n"))
                    .group_by(PrintLog.code_value)
                    .having(func.count() > 1)
                ).all()

            assert duplicates == [], f"出现重复打印：{duplicates[:5]}"
        finally:
            _wipe(engine)

    def test_heartbeats_all_land(self, engine):
        """50 个工位同时上报心跳，不得有写冲突或丢失。"""
        _wipe(engine)
        try:
            ids = _seed(engine)
            barrier = threading.Barrier(WORKSTATIONS)

            def beat(index: int) -> None:
                with Session(engine) as session:
                    barrier.wait(timeout=30)
                    ws = session.get(Workstation, ids["workstation_ids"][index])
                    ws.last_heartbeat_at = utcnow()
                    session.commit()

            threads = [threading.Thread(target=beat, args=(i,)) for i in range(WORKSTATIONS)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)

            with Session(engine) as session:
                reported = session.execute(
                    select(func.count())
                    .select_from(Workstation)
                    .where(Workstation.last_heartbeat_at.is_not(None))
                ).scalar_one()

            assert reported == WORKSTATIONS
        finally:
            _wipe(engine)
