"""T054：产品服务（FR-009 ~ FR-011）。

停用前置校验（FR-010）：产品仍有"已分配未打印"的码时拒绝停用。
该口径已由用户确认——把决定权显式交回总部，不做静默的批量状态变更。
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.code import Code
from app.models.product import Product
from app.models.template import Template, TemplateVersion

# 视为"在途"的码状态：已被公司持有，尚未终态
IN_FLIGHT_STATUSES = ("allocated", "printing")


@dataclass
class ProductStats:
    imported: int = 0
    allocated: int = 0
    printed: int = 0


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(ErrorCode.NOT_FOUND, "产品不存在")
    return product


def get_by_code(db: Session, code: str) -> Product | None:
    return db.execute(select(Product).where(Product.code == code)).scalar_one_or_none()


def stats_for(db: Session, product_ids: list[int]) -> dict[int, ProductStats]:
    """一次分组查询取回所有产品的三个计数，避免 N+1（SC-013）。"""
    if not product_ids:
        return {}

    rows = db.execute(
        select(
            Code.product_id,
            func.count().label("total"),
            func.sum(func.if_(Code.status.in_(IN_FLIGHT_STATUSES), 1, 0)).label("inflight"),
            func.sum(func.if_(Code.status == "printed", 1, 0)).label("printed"),
        )
        .where(Code.product_id.in_(product_ids))
        .group_by(Code.product_id)
    ).all()

    return {
        product_id: ProductStats(
            imported=int(total or 0),
            allocated=int(inflight or 0),
            printed=int(printed or 0),
        )
        for product_id, total, inflight, printed in rows
    }


def list_products(db: Session, *, keyword: str | None = None) -> list[tuple[Product, ProductStats]]:
    stmt = select(Product).order_by(Product.code)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Product.name.like(like) | Product.code.like(like))
    products = list(db.execute(stmt).scalars())
    stats = stats_for(db, [p.id for p in products])
    return [(p, stats.get(p.id, ProductStats())) for p in products]


def _assert_template_exists(db: Session, template_id: int | None) -> None:
    if template_id is None:
        return
    if db.get(Template, template_id) is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "指定的默认模板不存在")


def create_product(
    db: Session,
    *,
    code: str,
    name: str,
    spec: str | None = None,
    default_template_id: int | None = None,
) -> Product:
    if get_by_code(db, code) is not None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"产品编码已存在：{code}")
    _assert_template_exists(db, default_template_id)

    product = Product(
        code=code, name=name, spec=spec, default_template_id=default_template_id, status="active"
    )
    db.add(product)
    db.flush()
    return product


def update_product(db: Session, product_id: int, **fields) -> Product:
    product = get_product(db, product_id)
    if "default_template_id" in fields:
        _assert_template_exists(db, fields["default_template_id"])
    for key in ("name", "spec", "default_template_id"):
        if key in fields and fields[key] is not None:
            setattr(product, key, fields[key])
    db.flush()
    return product


def count_in_flight_codes(db: Session, product_id: int) -> int:
    return db.execute(
        select(func.count())
        .select_from(Code)
        .where(Code.product_id == product_id, Code.status.in_(IN_FLIGHT_STATUSES))
    ).scalar_one()


def disable_product(db: Session, product_id: int) -> Product:
    """FR-010：存在"已分配未打印"（含打印中）的码时拒绝停用。"""
    product = get_product(db, product_id)
    in_flight = count_in_flight_codes(db, product_id)
    if in_flight:
        raise ApiError(
            ErrorCode.PRODUCT_HAS_ALLOCATED_CODES,
            f"该产品仍有 {in_flight} 个已分配未打印的码，请先回收或作废后再停用",
            {"in_flight": in_flight},
        )
    product.status = "disabled"
    db.flush()
    return product


def resolve_default_template_version(db: Session, product: Product) -> TemplateVersion | None:
    """取产品默认模板的当前（最新）版本，供分配单携带（FR-035）。

    委托给模板服务，避免"当前版本"存在两份实现而日后走叉。
    """
    if product.default_template_id is None:
        return None
    from app.services.template import current_version

    return current_version(db, product.default_template_id)
