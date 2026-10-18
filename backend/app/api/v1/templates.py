"""模板接口（FR-032 ~ FR-038，契约：contracts/admin-api.md 打印模板小节）。

读、写操作均仅总部管理员可用（FR-036：子公司 MUST NOT 修改模板内容）。
工位端从打印载荷获取模板内容，不直接访问本接口。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, HqAdmin
from app.models.template import TemplateVersion
from app.schemas.template import (
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
    TemplateVersionOut,
)
from app.services import audit
from app.services import template as template_service

router = APIRouter(prefix="/templates", tags=["template"])

DbSession = Annotated[Session, Depends(get_db)]


def _version_out(version: TemplateVersion) -> TemplateVersionOut:
    return TemplateVersionOut(
        id=version.id,
        template_id=version.template_id,
        version_no=version.version_no,
        paper_width_mm=float(version.paper_width_mm),
        paper_height_mm=float(version.paper_height_mm),
        elements_json=version.elements_json,
        frozen=version.frozen,
    )


@router.get("", response_model=list[TemplateOut])
def list_templates(user: HqAdmin, db: DbSession) -> list[TemplateOut]:
    """模板列表。仅总部可查；子公司通过分配单获知所用模板版本。"""
    rows = template_service.list_templates(db)
    return [
        TemplateOut(
            id=template.id,
            code=template.code,
            name=template.name,
            status=template.status,
            current_version_no=latest,
            version_count=count,
        )
        for template, count, latest in rows
    ]


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateCreate, user: HqAdmin, db: DbSession, ip: ClientIp
) -> TemplateOut:
    template, version = template_service.create_template(db, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.TEMPLATE_CHANGE,
        result=audit.AuditResult.SUCCESS,
        target_type="template",
        target_id=template.id,
        ip=ip,
    )
    db.commit()
    return TemplateOut(
        id=template.id,
        code=template.code,
        name=template.name,
        status=template.status,
        current_version_no=version.version_no,
        version_count=1,
    )


@router.get("/{template_id}/versions", response_model=list[TemplateVersionOut])
def list_versions(template_id: int, user: HqAdmin, db: DbSession):
    return [_version_out(v) for v in template_service.list_versions(db, template_id)]


@router.put("/{template_id}", response_model=TemplateVersionOut)
@router.patch("/{template_id}", response_model=TemplateVersionOut)
def update_template(
    template_id: int, payload: TemplateUpdate, user: HqAdmin, db: DbSession, ip: ClientIp
) -> TemplateVersionOut:
    """修改模板 = 追加新版本（FR-033），历史版本内容保持原样。"""
    version = template_service.add_version(db, template_id, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.TEMPLATE_CHANGE,
        result=audit.AuditResult.SUCCESS,
        target_type="template_version",
        target_id=version.id,
        ip=ip,
    )
    db.commit()
    return _version_out(version)


@router.put("/{template_id}/versions/{version_no}", response_model=TemplateVersionOut)
def replace_version(
    template_id: int,
    version_no: int,
    payload: TemplateUpdate,
    user: HqAdmin,
    db: DbSession,
    ip: ClientIp,
) -> TemplateVersionOut:
    """就地修改某个版本的内容——仅在该版本尚未被引用时允许（FR-034）。"""
    versions = template_service.list_versions(db, template_id)
    target = next((v for v in versions if v.version_no == version_no), None)
    if target is None:
        from app.core.errors import ApiError, ErrorCode

        raise ApiError(ErrorCode.NOT_FOUND, f"模板 {template_id} 不存在版本 {version_no}")

    version = template_service.replace_version_content(db, target.id, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.TEMPLATE_CHANGE,
        result=audit.AuditResult.SUCCESS,
        target_type="template_version",
        target_id=version.id,
        ip=ip,
    )
    db.commit()
    return _version_out(version)


@router.post("/{template_id}/disable", response_model=TemplateOut)
def disable_template(template_id: int, user: HqAdmin, db: DbSession, ip: ClientIp) -> TemplateOut:
    """停用模板。只影响后续新分配；已冻结的历史版本继续可用于打印与补打。"""
    template = template_service.disable_template(db, template_id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.TEMPLATE_CHANGE,
        result=audit.AuditResult.SUCCESS,
        target_type="template",
        target_id=template.id,
        ip=ip,
    )
    db.commit()
    latest = template_service.current_version(db, template_id)
    count = len(template_service.list_versions(db, template_id))
    return TemplateOut(
        id=template.id,
        code=template.code,
        name=template.name,
        status=template.status,
        current_version_no=latest.version_no if latest else None,
        version_count=count,
    )
