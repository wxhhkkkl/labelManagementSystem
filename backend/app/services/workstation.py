"""工位服务（FR-002、FR-003、FR-069）。"""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, ErrorCode
from app.core.scope import Scope
from app.models.base import utcnow
from app.models.company import Company
from app.models.user import User
from app.models.workstation import Workstation, WorkstationOperator


def is_online(workstation: Workstation) -> bool:
    """心跳超时判定（research.md R1）。

    由服务端按 last_heartbeat_at 计算，MUST NOT 信任客户端自报的在线状态。
    """
    if workstation.last_heartbeat_at is None:
        return False
    threshold = timedelta(seconds=get_settings().offline_threshold_seconds)
    return utcnow() - workstation.last_heartbeat_at <= threshold


def get_workstation(db: Session, workstation_id: int) -> Workstation:
    ws = db.get(Workstation, workstation_id)
    if ws is None:
        raise ApiError(ErrorCode.NOT_FOUND, "工位不存在")
    return ws


def get_operator_ids(db: Session, workstation_id: int) -> list[int]:
    stmt = select(WorkstationOperator.user_id).where(
        WorkstationOperator.workstation_id == workstation_id
    )
    return list(db.execute(stmt).scalars())


def list_workstations(
    db: Session, scope: Scope, *, company_id: int | None = None
) -> list[Workstation]:
    stmt = select(Workstation).order_by(Workstation.company_id, Workstation.code)
    stmt = scope.apply_company_filter(stmt, Workstation.company_id)
    if company_id is not None:
        scope.assert_can_access_company(company_id)
        stmt = stmt.where(Workstation.company_id == company_id)
    return list(db.execute(stmt).scalars())


def _set_operators(db: Session, ws: Workstation, operator_ids: list[int]) -> None:
    """重建工位—操作员绑定；操作员必须属于同一公司。"""
    db.execute(
        delete(WorkstationOperator).where(WorkstationOperator.workstation_id == ws.id)
    )
    if not operator_ids:
        return
    users = list(db.execute(select(User).where(User.id.in_(operator_ids))).scalars())
    if len(users) != len(set(operator_ids)):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "存在不存在的操作员账号")
    for user in users:
        if user.company_id != ws.company_id:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "操作员必须与工位属于同一公司")
        if user.role != "operator":
            raise ApiError(ErrorCode.VALIDATION_ERROR, "只有工位操作员可绑定到工位")
        db.add(WorkstationOperator(workstation_id=ws.id, user_id=user.id))
    db.flush()


def create_workstation(
    db: Session,
    scope: Scope,
    *,
    code: str,
    name: str,
    company_id: int | None,
    printer_name: str | None = None,
    operator_ids: list[int] | None = None,
) -> Workstation:
    target_company = scope.resolve_target_company(company_id)
    if target_company is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "必须指定所属公司")
    scope.assert_can_administer_company(target_company)

    company = db.get(Company, target_company)
    if company is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "所属公司不存在")

    exists = db.execute(
        select(Workstation).where(
            Workstation.company_id == target_company, Workstation.code == code
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"该公司下工位编码已存在：{code}")

    ws = Workstation(
        code=code,
        name=name,
        company_id=target_company,
        printer_name=printer_name,
        status="active",
    )
    db.add(ws)
    db.flush()
    if operator_ids is not None:
        _set_operators(db, ws, operator_ids)
    return ws


def _assert_can_administer(scope: Scope, ws: Workstation) -> None:
    scope.assert_can_administer_company(ws.company_id)


def update_workstation(
    db: Session,
    scope: Scope,
    workstation_id: int,
    *,
    name=None,
    printer_name=None,
    operator_ids=None,
) -> Workstation:
    ws = get_workstation(db, workstation_id)
    _assert_can_administer(scope, ws)
    if name is not None:
        ws.name = name
    if printer_name is not None:
        ws.printer_name = printer_name
    if operator_ids is not None:
        _set_operators(db, ws, operator_ids)
    db.flush()
    return ws


def disable_workstation(db: Session, scope: Scope, workstation_id: int) -> Workstation:
    """停用工位（FR-003）。停用后不可再被分配新码、不可再执行打印。"""
    ws = get_workstation(db, workstation_id)
    _assert_can_administer(scope, ws)
    ws.status = "disabled"
    db.flush()
    return ws


def record_heartbeat(db: Session, workstation_id: int) -> Workstation:
    ws = get_workstation(db, workstation_id)
    ws.last_heartbeat_at = utcnow()
    db.flush()
    return ws


def bind_workstation(db: Session, user: User, workstation_id: int) -> Workstation:
    """工位软件首次配置时声明本机代表的工位（FR-069）。

    服务端职责：校验归属、校验停用、记录绑定时间。绑定关系本身持久化在工位端本机。
    """
    ws = get_workstation(db, workstation_id)

    # 非总部用户只能绑定本公司工位
    if user.role != "hq_admin" and ws.company_id != user.company_id:
        raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "无权绑定其他公司的工位")

    company = db.get(Company, ws.company_id)
    if ws.status != "active" or (company is not None and company.status != "active"):
        raise ApiError(ErrorCode.WORKSTATION_DISABLED, "工位或其所属公司已停用")

    if ws.bound_at is None:
        ws.bound_at = utcnow()

    # 绑定后立即刷新心跳，避免刚绑定就被判定离线
    ws.last_heartbeat_at = utcnow()
    db.flush()
    return ws
