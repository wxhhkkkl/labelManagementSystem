"""产品接口（FR-009 ~ FR-011）。写操作仅总部管理员。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import ClientIp, CurrentUser, HqAdmin
from app.schemas.product import ProductCreate, ProductOut, ProductStatsOut, ProductUpdate
from app.services import audit
from app.services import product as product_service
from app.services.product import ProductStats

router = APIRouter(prefix="/products", tags=["product"])

DbSession = Annotated[Session, Depends(get_db)]

_EMPTY = ProductStats()


def _stats_for(db: Session, product_id: int) -> ProductStats:
    """取单个产品的计数。

    stats_for 是 GROUP BY 查询，零码的产品不会出现在结果里，
    因此必须给默认值，否则新建产品取计数会拿到 None。
    """
    return product_service.stats_for(db, [product_id]).get(product_id, _EMPTY)


def _serialize(product, stats: ProductStats) -> ProductOut:
    return ProductOut(
        id=product.id,
        code=product.code,
        name=product.name,
        spec=product.spec,
        default_template_id=product.default_template_id,
        status=product.status,
        stats=ProductStatsOut(
            imported=stats.imported, allocated=stats.allocated, printed=stats.printed
        ),
    )


@router.get("", response_model=list[ProductOut])
def list_products(user: CurrentUser, db: DbSession, keyword: str | None = None):
    # 产品是总部统一管理的全局数据，子公司只读可见（不按组织过滤）
    rows = product_service.list_products(db, keyword=keyword)
    return [_serialize(product, stats) for product, stats in rows]


@router.post("", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, user: HqAdmin, db: DbSession, ip: ClientIp):
    product = product_service.create_product(db, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action="product.change",
        result=audit.AuditResult.SUCCESS,
        target_type="product",
        target_id=product.id,
        ip=ip,
    )
    db.commit()
    return _serialize(product, _stats_for(db, product.id))


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int, payload: ProductUpdate, user: HqAdmin, db: DbSession, ip: ClientIp
):
    product = product_service.update_product(db, product_id, **payload.model_dump())
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action="product.change",
        result=audit.AuditResult.SUCCESS,
        target_type="product",
        target_id=product.id,
        ip=ip,
    )
    db.commit()
    return _serialize(product, _stats_for(db, product.id))


@router.post("/{product_id}/disable", response_model=ProductOut)
def disable_product(product_id: int, user: HqAdmin, db: DbSession, ip: ClientIp):
    """FR-010：有在途码时返回 409 PRODUCT_HAS_ALLOCATED_CODES。

    拒绝时不写任何东西，所以不需要在这里 rollback —— 请求结束时依赖会关闭会话，
    未提交的改动自然丢弃。
    """
    product = product_service.disable_product(db, product_id)
    audit.record(
        db,
        operator_id=user.id,
        role=user.role,
        action="product.change",
        result=audit.AuditResult.SUCCESS,
        target_type="product",
        target_id=product.id,
        ip=ip,
    )
    db.commit()
    return _serialize(product, _stats_for(db, product.id))
