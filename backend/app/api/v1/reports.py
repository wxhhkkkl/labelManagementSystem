"""报表导出接口。

FR-031 的码量导出在本阶段实现；看板展示口径（FR-065）归 US7。
"""

import csv
import tempfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.db import get_db
from app.core.deps import CurrentUser, HqAdmin
from app.core.scope import Scope
from app.schemas.reprint import LedgerEntryOut
from app.services import reports

router = APIRouter(prefix="/reports", tags=["report"])
# 台账挂在 /api/v1/reprints（契约如此），与 /api/v1/reports/* 不同前缀
ledger_router = APIRouter(tags=["report"])

DbSession = Annotated[Session, Depends(get_db)]

STOCK_HEADERS = (
    "公司",
    "产品",
    "待分配",
    "已分配未打印",
    "已打印",
    "已作废",
    "合计",
)


@router.get("/code-stock/export")
def export_code_stock(user: HqAdmin, db: DbSession) -> Response:
    """导出各公司、各产品的码量。

    用 CSV（UTF-8 BOM）而不是 xlsx：结果集可能很大，CSV 可以边写边落盘，
    且 Excel 双击打开时中文不乱码。
    """
    rows = reports.code_stock(db)

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(STOCK_HEADERS)
    for row in rows:
        total = (
            row.unallocated + row.allocated + row.printing + row.printed + row.voided
        )
        writer.writerow(
            [
                row.company_name,
                row.product_name,
                row.unallocated,
                row.allocated_not_printed,
                row.printed,
                row.voided,
                total,
            ]
        )

    # BOM 让 Excel 正确识别 UTF-8
    content = "﻿" + buffer.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="code-stock.csv"'},
    )


@ledger_router.get("/reprints", response_model=list[LedgerEntryOut])
def reprint_and_void_ledger(
    user: CurrentUser, db: DbSession, limit: int = 200
) -> list[LedgerEntryOut]:
    """补打/作废台账（FR-067）。子公司只能看到本公司的记录（R7）。"""
    scope = Scope(user)
    rows = reports.reprint_ledger(
        db, scope_company_id=scope.scope_company_id, limit=min(limit, 500)
    )
    return [LedgerEntryOut(**row) for row in rows]


class PrintDetailItem(BaseModel):
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


@router.get("/prints", response_model=list[PrintDetailItem])
def print_details(
    user: CurrentUser,
    db: DbSession,
    company_id: int | None = None,
    workstation_id: int | None = None,
    operator_id: int | None = None,
    product_id: int | None = None,
    printed_from: datetime | None = None,
    printed_to: datetime | None = None,
    limit: int = 500,
) -> list[PrintDetailItem]:
    """打印明细（FR-066）。按公司/工位/操作员/产品/时间段筛选。

    子公司只能看本公司——显式传他公司 company_id 会被拒（R7）。
    """
    scope = Scope(user)
    if company_id is not None:
        scope.assert_can_access_company(company_id)

    rows = reports.print_details(
        db,
        scope_company_id=scope.scope_company_id,
        company_id=company_id,
        workstation_id=workstation_id,
        operator_id=operator_id,
        product_id=product_id,
        printed_from=printed_from,
        printed_to=printed_to,
        limit=limit,
    )
    return [PrintDetailItem(**vars(row)) for row in rows]


PRINT_EXPORT_HEADERS = (
    "码值",
    "产品",
    "公司",
    "工位",
    "操作员",
    "打印机",
    "打印类型",
    "结果",
    "失败原因",
    "打印时间",
)


@router.get("/prints/export")
def export_print_details(
    user: CurrentUser,
    db: DbSession,
    company_id: int | None = None,
    workstation_id: int | None = None,
    operator_id: int | None = None,
    product_id: int | None = None,
    printed_from: datetime | None = None,
    printed_to: datetime | None = None,
) -> FileResponse:
    """导出打印明细为 Excel（FR-066）。

    用 openpyxl 的 write_only 模式逐行落盘，再以 FileResponse 流式回传——
    直接把整份表在内存里拼完再返回，在明细量大时会直接吃掉服务端内存。
    临时文件由后台任务删除。
    """
    scope = Scope(user)
    if company_id is not None:
        scope.assert_can_access_company(company_id)

    rows = reports.print_details(
        db,
        scope_company_id=scope.scope_company_id,
        company_id=company_id,
        workstation_id=workstation_id,
        operator_id=operator_id,
        product_id=product_id,
        printed_from=printed_from,
        printed_to=printed_to,
        limit=100_000,
    )

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("打印明细")
    sheet.append(list(PRINT_EXPORT_HEADERS))
    for row in rows:
        sheet.append(
            [
                row.code_value,
                row.product_name or "",
                row.company_name or "",
                row.workstation_name or "",
                row.operator_name or "",
                row.printer_name,
                "首次" if row.print_type == "first" else "补打",
                row.result,
                row.failure_reason or "",
                row.printed_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    handle = tempfile.NamedTemporaryFile(
        suffix=".xlsx", prefix="print-details-", delete=False
    )
    workbook.save(handle.name)
    handle.close()

    return FileResponse(
        handle.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="print-details.xlsx",
        background=BackgroundTask(lambda: Path(handle.name).unlink(missing_ok=True)),
    )
