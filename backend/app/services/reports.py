"""汇总查询（FR-031 的码量测算）。

聚合 MUST 在数据库完成（SC-013）：百万级码库下，把行拉到应用层再计数必然超时。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.company import Company
from app.models.product import Product

# 看板与导出关心的四态
CODE_STATUSES = ("unallocated", "allocated", "printing", "printed", "voided")


@dataclass
class CodeStockRow:
    company_id: int | None
    company_name: str
    product_id: int
    product_name: str
    unallocated: int = 0
    allocated: int = 0
    printing: int = 0
    printed: int = 0
    voided: int = 0

    @property
    def allocated_not_printed(self) -> int:
        """已分配未打印（含打印中）——FR-031 明确要求的口径。"""
        return self.allocated + self.printing


def code_stock(db: Session, *, scope_company_id: int | None = None) -> list[CodeStockRow]:
    """按"公司 + 产品"汇总五态码量。"""
    stmt = select(
        Code.company_id,
        Code.product_id,
        Code.status,
        func.count().label("count"),
    ).group_by(Code.company_id, Code.product_id, Code.status)
    if scope_company_id is not None:
        stmt = stmt.where(Code.company_id == scope_company_id)

    rows = db.execute(stmt).all()

    company_names = dict(db.execute(select(Company.id, Company.name)).all())
    product_names = dict(db.execute(select(Product.id, Product.name)).all())

    buckets: dict[tuple[int | None, int], CodeStockRow] = {}
    for company_id, product_id, status, count in rows:
        key = (company_id, product_id)
        if key not in buckets:
            buckets[key] = CodeStockRow(
                company_id=company_id,
                company_name=company_names.get(company_id, "总部码池"),
                product_id=product_id,
                product_name=product_names.get(product_id, f"#{product_id}"),
            )
        bucket = buckets[key]
        if status in CODE_STATUSES:
            setattr(bucket, status, int(count))

    return sorted(buckets.values(), key=lambda r: (r.company_name, r.product_name))


def reprint_ledger(
    db: Session, *, scope_company_id: int | None = None, limit: int = 200, include_void: bool = True
) -> list[dict]:
    """补打与作废台账（FR-067）。

    两个来源合并成一条时间线：
      * 补打来自 PrintTask（每条都带必填原因）
      * 作废来自码本身的终态字段

    按时间倒序，便于审计时从最近往前翻。
    """
    from app.models.print_task import PrintTask

    product_names = dict(db.execute(select(Product.id, Product.name)).all())
    company_names = dict(db.execute(select(Company.id, Company.name)).all())

    entries: list[dict] = []

    task_query = select(PrintTask).join(Code, Code.id == PrintTask.code_id)
    if scope_company_id is not None:
        task_query = task_query.where(Code.company_id == scope_company_id)
    tasks = db.execute(task_query.order_by(PrintTask.id.desc()).limit(limit)).scalars()
    for task in tasks:
        code = db.get(Code, task.code_id)
        if code is None:
            continue
        if scope_company_id is not None and code.company_id != scope_company_id:
            continue
        entries.append(
            {
                "kind": "reprint",
                "code_value": code.code_value,
                "product_name": product_names.get(code.product_id),
                "company_name": company_names.get(code.company_id),
                "reason": task.reason,
                "operator_id": task.created_by,
                "workstation_id": task.target_workstation_id,
                "result": task.status,
                "occurred_at": task.created_at,
            }
        )

    void_query = select(Code).where(Code.status == "voided")
    if scope_company_id is not None:
        void_query = void_query.where(Code.company_id == scope_company_id)
    voided = (
        db.execute(void_query.order_by(Code.voided_at.desc()).limit(limit)).scalars()
        if include_void
        else []
    )
    for code in voided:
        if scope_company_id is not None and code.company_id != scope_company_id:
            continue
        entries.append(
            {
                "kind": "void",
                "code_value": code.code_value,
                "product_name": product_names.get(code.product_id),
                "company_name": company_names.get(code.company_id),
                "reason": code.void_reason,
                "operator_id": code.voided_by,
                "workstation_id": code.last_printed_workstation_id,
                "result": "voided",
                "occurred_at": code.voided_at,
            }
        )

    entries.sort(key=lambda e: (e["occurred_at"] is not None, e["occurred_at"]), reverse=True)
    return entries[:limit]


# ---------------------------------------------------------------- 看板


@dataclass
class DashboardRow:
    """看板的一行：某公司 + 某产品的四态码量。"""

    company_id: int | None
    company_name: str
    product_id: int
    product_name: str
    unallocated: int = 0
    allocated: int = 0
    printing: int = 0
    printed: int = 0
    voided: int = 0

    @property
    def allocated_not_printed(self) -> int:
        """FR-031 的口径：已分配未打印 = 已分配 + 打印中。"""
        return self.allocated + self.printing

    @property
    def total(self) -> int:
        return self.unallocated + self.allocated + self.printing + self.printed + self.voided


def dashboard_distribution(
    db: Session,
    *,
    scope_company_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> list[DashboardRow]:
    """按公司 + 产品汇总四态码量（FR-065）。

    时间筛选的口径：按**码入库时间**（`code.created_at`）过滤。
    四态本身是当前快照，没有"历史某时刻的分布"可言——能筛的是
    "这批码是哪个时间段进来的"。这一点在接口文档里也写明了，
    避免调用方以为能查到历史分布。

    聚合 MUST 由数据库完成：百万级下单表扫描后回应用层计数必然超时（SC-013）。
    """
    stmt = select(
        Code.company_id,
        Code.product_id,
        Code.status,
        func.count().label("count"),
    )
    if scope_company_id is not None:
        stmt = stmt.where(Code.company_id == scope_company_id)
    if created_from is not None:
        stmt = stmt.where(Code.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Code.created_at <= created_to)
    stmt = stmt.group_by(Code.company_id, Code.product_id, Code.status)

    rows = db.execute(stmt).all()

    company_names = dict(db.execute(select(Company.id, Company.name)).all())
    product_names = dict(db.execute(select(Product.id, Product.name)).all())

    buckets: dict[tuple[int | None, int], DashboardRow] = {}
    for company_id, product_id, status, count in rows:
        key = (company_id, product_id)
        if key not in buckets:
            buckets[key] = DashboardRow(
                company_id=company_id,
                company_name=company_names.get(company_id, "总部码池"),
                product_id=product_id,
                product_name=product_names.get(product_id, f"#{product_id}"),
            )
        bucket = buckets[key]
        if status in CODE_STATUSES:
            setattr(bucket, status, int(count))

    return sorted(buckets.values(), key=lambda r: (r.company_name, r.product_name))


# ---------------------------------------------------------------- 打印明细


@dataclass
class PrintDetailRow:
    """打印明细的一行，字段与 FR-066 要求的筛选项对齐。"""

    code_value: str
    product_name: str | None
    company_name: str | None
    workstation_name: str | None
    operator_name: str | None
    printer_name: str
    print_type: str
    result: str
    failure_reason: str | None
    printed_at: datetime


def print_details(
    db: Session,
    *,
    scope_company_id: int | None = None,
    company_id: int | None = None,
    workstation_id: int | None = None,
    operator_id: int | None = None,
    product_id: int | None = None,
    printed_from: datetime | None = None,
    printed_to: datetime | None = None,
    limit: int = 500,
) -> list[PrintDetailRow]:
    """打印明细查询（FR-066）。

    按公司/工位/操作员/产品/时间段筛选。走 `(company_id, printed_at)` 等索引，
    不做全表扫描。
    """
    from app.models.print_log import PrintLog
    from app.models.user import User
    from app.models.workstation import Workstation

    stmt = (
        select(PrintLog, Product.name, Company.name, Workstation.name, User.display_name)
        .join(Product, Product.id == PrintLog.product_id, isouter=True)
        .join(Company, Company.id == PrintLog.company_id, isouter=True)
        .join(Workstation, Workstation.id == PrintLog.workstation_id, isouter=True)
        .join(User, User.id == PrintLog.operator_id, isouter=True)
    )

    if scope_company_id is not None:
        stmt = stmt.where(PrintLog.company_id == scope_company_id)
    elif company_id is not None:
        stmt = stmt.where(PrintLog.company_id == company_id)
    if workstation_id is not None:
        stmt = stmt.where(PrintLog.workstation_id == workstation_id)
    if operator_id is not None:
        stmt = stmt.where(PrintLog.operator_id == operator_id)
    if product_id is not None:
        stmt = stmt.where(PrintLog.product_id == product_id)
    if printed_from is not None:
        stmt = stmt.where(PrintLog.printed_at >= printed_from)
    if printed_to is not None:
        stmt = stmt.where(PrintLog.printed_at <= printed_to)

    stmt = stmt.order_by(PrintLog.printed_at.desc()).limit(min(limit, 5000))

    return [
        PrintDetailRow(
            code_value=log.code_value,
            product_name=product_name,
            company_name=company_name,
            workstation_name=workstation_name,
            operator_name=operator_name,
            printer_name=log.printer_name,
            print_type=log.print_type,
            result=log.result,
            failure_reason=log.failure_reason,
            printed_at=log.printed_at,
        )
        for log, product_name, company_name, workstation_name, operator_name in db.execute(
            stmt
        ).all()
    ]
