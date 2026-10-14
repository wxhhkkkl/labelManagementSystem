"""分配与回收接口（FR-025 ~ FR-030）。仅总部管理员可写。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, CurrentUser, HqAdmin
from app.core.scope import Scope
from app.models.allocation_order import AllocationOrder
from app.models.company import Company
from app.models.product import Product
from app.schemas.allocation import AllocationCreate, AllocationCreatedOut, AllocationOrderOut
from app.services import allocation as allocation_service
from app.services import audit

router = APIRouter(prefix="/allocations", tags=["allocation"])

DbSession = Annotated[Session, Depends(get_db)]


def serialize(db: Session, order: AllocationOrder) -> AllocationOrderOut:
    company = db.get(Company, order.company_id)
    product = db.get(Product, order.product_id)
    return AllocationOrderOut(
        id=order.id,
        order_no=order.order_no,
        company_id=order.company_id,
        company_name=company.name if company else None,
        product_id=order.product_id,
        product_name=product.name if product else None,
        code_count=order.code_count,
        code_range_from=order.code_range_from,
        code_range_to=order.code_range_to,
        template_version_id=order.template_version_id,
        allocated_by=order.allocated_by,
        allocated_at=order.allocated_at,
        status=order.status,
    )


@router.get("", response_model=list[AllocationOrderOut])
def list_allocations(
    user: CurrentUser,
    db: DbSession,
    company_id: int | None = None,
    limit: int = 100,
):
    """分配单列表。子公司只能看到本公司的（R7 组织隔离）。"""
    scope = Scope(user)
    # 显式传了 company_id 就校验一次：非总部传他公司一律 403，
    # 而不是静默忽略参数返回自己的数据——那样调用方会以为查询生效了。
    if company_id is not None:
        scope.assert_can_access_company(company_id)
    if scope.scope_company_id is not None:
        company_id = scope.scope_company_id

    orders = allocation_service.list_orders(db, company_id=company_id, limit=limit)
    return [serialize(db, order) for order in orders]


@router.post("", response_model=AllocationCreatedOut, status_code=201)
def create_allocation(
    payload: AllocationCreate, user: HqAdmin, db: DbSession, ip: ClientIp
):
    """按"公司 + 产品 + 数量"分配码。可用量不足返回 409 并带 details.available。"""
    result = allocation_service.allocate(
        db,
        company_id=payload.company_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        operator_id=user.id,
        template_version_id=payload.template_version_id,
        batch_id=payload.batch_id,
        code_range_from=payload.code_range_from,
        code_range_to=payload.code_range_to,
    )
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.ALLOCATION_CREATE,
        result=audit.AuditResult.SUCCESS,
        company_id=result.order.company_id,
        target_type="allocation_order",
        target_id=result.order.id,
        ip=ip,
    )
    db.commit()
    return AllocationCreatedOut(
        order=serialize(db, result.order), allocated=result.allocated
    )


@router.post("/{order_id}/reclaim", response_model=AllocationOrderOut)
def reclaim_allocation(order_id: int, user: HqAdmin, db: DbSession, ip: ClientIp):
    """回收未打印的码。分配单下有已打印/打印中的码时整单拒绝（FR-030）。"""
    result = allocation_service.reclaim(db, order_id=order_id, operator_id=user.id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action=audit.AuditAction.ALLOCATION_RECLAIM,
        result=audit.AuditResult.SUCCESS,
        company_id=result.order.company_id,
        target_type="allocation_order",
        target_id=result.order.id,
        ip=ip,
    )
    db.commit()
    return serialize(db, result.order)
