"""T032：操作日志写入服务。

append-only（FR-060）：本模块只提供写入与查询，**刻意不提供更新与删除方法**。
任何删除审计日志的能力都必须以新增公开 API 的方式引入，那会有明确的评审痕迹。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.base import utcnow


class AuditAction:
    LOGIN = "login"
    LOGOUT = "logout"
    IMPORT_CREATE = "import.create"
    ALLOCATION_CREATE = "allocation.create"
    ALLOCATION_RECLAIM = "allocation.reclaim"
    PRINT = "print"
    REPRINT = "reprint"
    VOID = "void"
    TEMPLATE_CHANGE = "template.change"
    ACCOUNT_CHANGE = "account.change"
    COMPANY_CHANGE = "company.change"
    WORKSTATION_CHANGE = "workstation.change"


class AuditResult:
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"


def record(
    db: Session,
    *,
    operator_id: int,
    role: str,
    action: str,
    result: str,
    company_id: int | None = None,
    workstation_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    ip: str | None = None,
    occurred_at: datetime | None = None,
) -> AuditLog:
    """写一条审计记录。调用方负责提交事务。"""
    entry = AuditLog(
        operator_id=operator_id,
        role=role,
        company_id=company_id,
        workstation_id=workstation_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
        result=result,
        occurred_at=occurred_at or utcnow(),
    )
    db.add(entry)
    return entry


def record_denied(
    db: Session,
    *,
    operator_id: int,
    role: str,
    action: str,
    company_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    ip: str | None = None,
) -> AuditLog:
    """越权请求专用入口（FR-007）。"""
    return record(
        db,
        operator_id=operator_id,
        role=role,
        action=action,
        result=AuditResult.DENIED,
        company_id=company_id,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
    )


def list_logs(db: Session, *, limit: int = 100, offset: int = 0) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def query_logs(
    db: Session,
    *,
    role: str | None = None,
    company_id: int | None = None,
    action: str | None = None,
    result: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[AuditLog]:
    """按条件查询操作日志（FR-061）。

    只读入口，仍然**不提供**任何修改或删除方法（FR-060）。
    """
    stmt = select(AuditLog)
    if role:
        stmt = stmt.where(AuditLog.role == role)
    if company_id is not None:
        stmt = stmt.where(AuditLog.company_id == company_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"%{action}%"))
    if result:
        stmt = stmt.where(AuditLog.result == result)
    if occurred_from is not None:
        stmt = stmt.where(AuditLog.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditLog.occurred_at <= occurred_to)

    stmt = (
        stmt.order_by(AuditLog.occurred_at.desc())
        .offset(offset)
        .limit(min(limit, 1000))
    )
    return list(db.execute(stmt).scalars())
