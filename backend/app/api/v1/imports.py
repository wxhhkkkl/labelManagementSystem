"""码导入接口（FR-012 ~ FR-021，契约：contracts/admin-api.md 码导入小节）。

异步模型（research.md R3）：上传接口只落盘与登记批次，立刻返回 batch_id；
解析与校验交给后台 worker，前端轮询批次详情直到终态。
"""

import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import FileResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, HqAdmin
from app.core.errors import ApiError, ErrorCode
from app.models.code import Code
from app.models.import_batch import ImportBatch
from app.models.product import Product
from app.schemas.import_batch import ImportBatchOut, ImportCreatedOut
from app.services import audit
from app.tasks import import_worker

router = APIRouter(prefix="/imports", tags=["import"])

DbSession = Annotated[Session, Depends(get_db)]

FINAL_STATUSES = ("succeeded", "failed", "interrupted")
# 上传体积上限的兜底（nginx 侧也会限制）；10 万行 xlsx 通常几十 MB
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def _new_batch_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"IMP{stamp}{uuid.uuid4().hex[:6].upper()}"


def _get_batch(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ApiError(ErrorCode.NOT_FOUND, "导入批次不存在")
    return batch


# 注意：/template 必须声明在 /{batch_id} 之前，否则会被当作 batch_id 解析
@router.get("/template")
def download_template(user: HqAdmin) -> Response:
    """Download the single-file anti-counterfeit-code / production-batch template."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "产品批号表"
    sheet.append(["防伪码", "产品批号", "状态"])
    sheet.append(["0612286397031613", "22PT510020DL99S78", "未查"])
    for cell in sheet[2][:2]:
        cell.number_format = "@"
    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 26
    sheet.column_dimensions["C"].width = 12
    sheet.freeze_panes = "A2"

    bio = BytesIO()
    workbook.save(bio)
    return Response(
        content=bio.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="import-template.xlsx"'},
    )


@router.post("", response_model=ImportCreatedOut, status_code=status.HTTP_202_ACCEPTED)
def create_import(
    user: HqAdmin,
    db: DbSession,
    ip: ClientIp,
    code_list_file: Annotated[UploadFile, File()],
    mapping_file: Annotated[UploadFile | None, File()] = None,
    product_id: Annotated[int | None, Form()] = None,
) -> ImportCreatedOut:
    """Register one workbook with a selected product, or a legacy file pair."""
    if mapping_file is None:
        product = db.get(Product, product_id) if product_id is not None else None
        if product is None or product.status != "active":
            raise ApiError(ErrorCode.VALIDATION_ERROR, "请选择有效的所属产品")
    elif product_id is not None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请使用单文件加产品，或旧版双文件方式，不能混用")
    batch_no = _new_batch_no()
    target = import_worker.batch_dir(batch_no)
    target.mkdir(parents=True, exist_ok=True)

    saved = {
        import_worker.code_list_path(batch_no): code_list_file,
    }
    if mapping_file is not None:
        saved[import_worker.mapping_path(batch_no)] = mapping_file
    for path, upload in saved.items():
        _save_upload(upload, path)

    batch = ImportBatch(
        batch_no=batch_no,
        code_list_filename=code_list_file.filename or "code_list.xlsx",
        mapping_filename=(mapping_file.filename or "mapping.xlsx") if mapping_file else "",
        product_id=product_id,
        status="pending",
        processed_rows=0,
        success_count=0,
        failure_count=0,
        created_by=user.id,
    )
    db.add(batch)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.IMPORT_CREATE,
        result=audit.AuditResult.SUCCESS,
        target_type="import_batch",
        ip=ip,
    )
    db.commit()

    import_worker.enqueue(batch.id)
    return ImportCreatedOut(batch_id=batch.id, batch_no=batch.batch_no, status=batch.status)


def _save_upload(upload: UploadFile, path) -> None:
    if not upload.filename:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "上传文件缺少文件名")
    size = 0
    with path.open("wb") as fh:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                fh.close()
                path.unlink(missing_ok=True)
                raise ApiError(
                    ErrorCode.VALIDATION_ERROR,
                    f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 上限：{upload.filename}",
                )
            fh.write(chunk)


@router.get("", response_model=list[ImportBatchOut])
def list_imports(user: HqAdmin, db: DbSession, limit: int = 50):
    stmt = select(ImportBatch).order_by(ImportBatch.id.desc()).limit(min(limit, 200))
    return _batch_outputs(db, list(db.execute(stmt).scalars()))


def _batch_outputs(db: Session, batches: list[ImportBatch]) -> list[ImportBatchOut]:
    product_ids = {batch.product_id for batch in batches if batch.product_id is not None}
    names = (
        dict(db.execute(select(Product.id, Product.name).where(Product.id.in_(product_ids))).all())
        if product_ids
        else {}
    )
    legacy_ids = [batch.id for batch in batches if batch.product_id is None]
    legacy_names: dict[int, list[str]] = {}
    if legacy_ids:
        rows = db.execute(
            select(Code.import_batch_id, Product.id, Product.name)
            .join(Product, Product.id == Code.product_id)
            .where(Code.import_batch_id.in_(legacy_ids))
            .distinct()
            .order_by(Product.id)
        ).all()
        for batch_id, _, name in rows:
            legacy_names.setdefault(batch_id, []).append(name)
    output = []
    for batch in batches:
        item = ImportBatchOut.model_validate(batch)
        item.product_names = (
            [names[batch.product_id]]
            if batch.product_id in names
            else legacy_names.get(batch.id, [])
        )
        output.append(item)
    return output


@router.get("/{batch_id}", response_model=ImportBatchOut)
def get_import(batch_id: int, user: HqAdmin, db: DbSession) -> ImportBatchOut:
    return _batch_outputs(db, [_get_batch(db, batch_id)])[0]


@router.get("/{batch_id}/errors")
def download_errors(batch_id: int, user: HqAdmin, db: DbSession) -> FileResponse:
    """FR-018：下载失败明细。批次尚未产出明细时返回 404。"""
    batch = _get_batch(db, batch_id)
    if not batch.error_detail_path:
        raise ApiError(ErrorCode.NOT_FOUND, "该批次没有失败明细")
    path = Path(batch.error_detail_path)
    if not path.exists():
        raise ApiError(ErrorCode.NOT_FOUND, "失败明细文件已不存在")
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=f"{batch.batch_no}-errors.csv",
    )
