"""看板接口（FR-065）。

四态码量按公司 / 按产品 / 按公司+产品 三种口径汇总。
聚合**全部由数据库完成**（SC-013）：百万级码库下，把行拉到应用层再计数必然超时。
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser
from app.core.scope import Scope
from app.services import reports

router = APIRouter(prefix="/dashboard", tags=["report"])

DbSession = Annotated[Session, Depends(get_db)]

GroupBy = Literal["company", "product", "company_product"]


class DistributionRow(BaseModel):
    key: str
    company_name: str | None = None
    product_name: str | None = None
    unallocated: int
    allocated: int
    printing: int
    printed: int
    voided: int
    allocated_not_printed: int
    total: int


class DistributionOut(BaseModel):
    group_by: str
    rows: list[DistributionRow]
    totals: DistributionRow


def _row_key(row: reports.DashboardRow, group_by: str) -> tuple[str, str | None, str | None]:
    if group_by == "company":
        return row.company_name, row.company_name, None
    if group_by == "product":
        return row.product_name, None, row.product_name
    return f"{row.company_name}/{row.product_name}", row.company_name, row.product_name


def _aggregate(rows: list[reports.DashboardRow], group_by: str) -> list[DistributionRow]:
    buckets: dict[str, DistributionRow] = {}
    for row in rows:
        key, company_name, product_name = _row_key(row, group_by)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = DistributionRow(
                key=key,
                company_name=company_name,
                product_name=product_name,
                unallocated=0,
                allocated=0,
                printing=0,
                printed=0,
                voided=0,
                allocated_not_printed=0,
                total=0,
            )
            buckets[key] = bucket
        bucket.unallocated += row.unallocated
        bucket.allocated += row.allocated
        bucket.printing += row.printing
        bucket.printed += row.printed
        bucket.voided += row.voided

    for bucket in buckets.values():
        bucket.allocated_not_printed = bucket.allocated + bucket.printing
        bucket.total = (
            bucket.unallocated + bucket.allocated + bucket.printing + bucket.printed + bucket.voided
        )

    return sorted(buckets.values(), key=lambda r: r.key)


@router.get("/code-distribution", response_model=DistributionOut)
def code_distribution(
    user: CurrentUser,
    db: DbSession,
    group_by: GroupBy = "company_product",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> DistributionOut:
    """四态码量分布（FR-065）。

    时间筛选的口径是**码入库时间**，不是"历史某时刻的分布"——
    四态本身是当前快照，不存在历史版本。这一点在参数说明里也写明。
    """
    scope = Scope(user)
    rows = reports.dashboard_distribution(
        db,
        scope_company_id=scope.scope_company_id,
        created_from=created_from,
        created_to=created_to,
    )

    aggregated = _aggregate(rows, group_by)
    totals = DistributionRow(
        key="ALL",
        unallocated=sum(r.unallocated for r in aggregated),
        allocated=sum(r.allocated for r in aggregated),
        printing=sum(r.printing for r in aggregated),
        printed=sum(r.printed for r in aggregated),
        voided=sum(r.voided for r in aggregated),
        allocated_not_printed=sum(r.allocated_not_printed for r in aggregated),
        total=sum(r.total for r in aggregated),
    )

    return DistributionOut(group_by=group_by, rows=aggregated, totals=totals)
