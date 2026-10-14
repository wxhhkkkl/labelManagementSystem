"""码导入接口（FR-012 ~ FR-021，契约：contracts/admin-api.md 码导入小节）。

异步模型（research.md R3）：上传接口只落盘与登记批次，立刻返回 batch_id；
解析与校验交给后台 worker，前端轮询批次详情直到终态。
"""

import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.responses import FileResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, HqAdmin
from app.core.errors import ApiError, ErrorCode
from app.models.import_batch import ImportBatch
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
    """FR-012：标准 Excel 导入模板。

    一个工作簿两个 sheet——码清单与对照关系需分别另存为两个文件后上传。
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "码清单"
    sheet.append(["码值"])
    sheet.append(["A001B002C003"])

    mapping = workbook.create_sheet("码-产品对照关系")
    mapping.append(["码值", "产品编码"])
    mapping.append(["A001B002C003", "P001"])

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
    mapping_file: Annotated[UploadFile, File()],
) -> ImportCreatedOut:
    """上传两个文件并登记批次。**不做任何解析**——那是 worker 的事。"""
    batch_no = _new_batch_no()
    target = import_worker.batch_dir(batch_no)
    target.mkdir(parents=True, exist_ok=True)

    saved = {
        import_worker.code_list_path(batch_no): code_list_file,
        import_worker.mapping_path(batch_no): mapping_file,
    }
    for path, upload in saved.items():
        _save_upload(upload, path)

    batch = ImportBatch(
        batch_no=batch_no,
        code_list_filename=code_list_file.filename or "code_list.xlsx",
        mapping_filename=mapping_file.filename or "mapping.xlsx",
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
    return list(db.execute(stmt).scalars())


@router.get("/{batch_id}", response_model=ImportBatchOut)
def get_import(batch_id: int, user: HqAdmin, db: DbSession) -> ImportBatch:
    return _get_batch(db, batch_id)


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
