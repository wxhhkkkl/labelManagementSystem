"""T072 / T073：分配取码与分配单生成（FR-025 ~ FR-030）。

并发要点（research.md R2）：取码 MUST 在单个事务内用
`SELECT ... FOR UPDATE SKIP LOCKED` 完成。SKIP LOCKED 让并发分配各取各的码，
而不是排队等待同一批行——没有它，两个并发分配会互相阻塞甚至重复取到同一批码。
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.allocation_order import AllocationOrder
from app.models.base import utcnow
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.company import Company
from app.models.product import Product
from app.models.template import TemplateVersion
from app.services import product as product_service
from app.services import template as template_service

# 只有池中未分配的码可被分配
POOL_STATUS = "unallocated"


@dataclass
class AllocationResult:
    order: AllocationOrder
    allocated: int


def _new_order_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"ALL{stamp}{uuid.uuid4().hex[:6].upper()}"


def available_count(
    db: Session,
    *,
    product_id: int,
    batch_id: int | None = None,
    code_range_from: str | None = None,
    code_range_to: str | None = None,
) -> int:
    """池中该产品可分配的码量，用于分配前的可用量校验。"""
    stmt = select(func.count()).select_from(Code).where(
        Code.status == POOL_STATUS, Code.product_id == product_id
    )
    if batch_id is not None:
        stmt = stmt.where(Code.import_batch_id == batch_id)
    if code_range_from:
        stmt = stmt.where(Code.code_value >= code_range_from)
    if code_range_to:
        stmt = stmt.where(Code.code_value <= code_range_to)
    return db.execute(stmt).scalar_one()


def _assert_company_can_receive(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "目标公司不存在")
    if company.status != "active":
        # FR-003：停用公司不可再被分配新码
        raise ApiError(ErrorCode.VALIDATION_ERROR, "目标公司已停用，不可再分配")
    return company


def _assert_product_allocatable(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "产品不存在")
    if product.status != "active":
        # FR-010：停用产品不可再被分配
        raise ApiError(ErrorCode.VALIDATION_ERROR, "产品已停用，不可再分配")
    return product


def _resolve_template_version(
    db: Session, product: Product, template_version_id: int | None
) -> TemplateVersion:
    """确定分配单携带的模板版本（FR-035）。

    未显式指定时取产品默认模板的当前（最新）版本。
    """
    if template_version_id is not None:
        # FR-035 只要求"指定一个版本"，未限定必须来自产品的默认模板——
        # 管理员针对特定批次改用其他模板版本是允许的。
        version = db.get(TemplateVersion, template_version_id)
        if version is None:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "指定的模板版本不存在")
        return version

    version = product_service.resolve_default_template_version(db, product)
    if version is None:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "该产品未绑定默认打印模板，无法确定分配单携带的模板版本",
        )
    return version


def allocate(
    db: Session,
    *,
    company_id: int,
    product_id: int,
    quantity: int,
    operator_id: int,
    template_version_id: int | None = None,
    batch_id: int | None = None,
    code_range_from: str | None = None,
    code_range_to: str | None = None,
) -> AllocationResult:
    if quantity <= 0:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "分配数量必须大于 0")

    _assert_company_can_receive(db, company_id)
    product = _assert_product_allocatable(db, product_id)
    version = _resolve_template_version(db, product, template_version_id)

    # 先把模板版本行锁住并置冻结（FR-034），**必须在取码之前**。
    # 否则两个并发事务会各自先拿住一批码行、再回头更新同一个版本行，
    # 形成交叉等待而死锁（实测报 1213 Deadlock）。
    db.execute(
        select(TemplateVersion).where(TemplateVersion.id == version.id).with_for_update()
    )
    # 冻结逻辑集中在模板服务，新增引用点时不会漏（FR-034）
    template_service.freeze_version(db, version.id)

    # 可用量校验先做，给出明确的可用数（契约要求 details.available）
    available = available_count(
        db,
        product_id=product_id,
        batch_id=batch_id,
        code_range_from=code_range_from,
        code_range_to=code_range_to,
    )
    if available < quantity:
        raise ApiError(
            ErrorCode.INSUFFICIENT_STOCK,
            f"可分配数量不足：需要 {quantity}，可用 {available}",
            {"available": available, "requested": quantity},
        )

    # 取码：按导入批次先进先出（FR-025），并发时跳过已被他人锁定的行（research R2）。
    #
    # 这里 MUST 强制走 ix_code_pool_fifo。优化器在只看到 "status + product_id"
    # 的选择性时可能改走 product_id 索引，那样就需要 filesort——而 FOR UPDATE
    # 会在应用 LIMIT **之前**锁住全部匹配行，SKIP LOCKED 于是把整池都跳过，
    # 并发分配互相饿死并误报库存不足。走了有序索引后扫描按序推进、取够即停，
    # 锁定范围才真正等于 LIMIT。
    stmt = (
        select(Code)
        .where(Code.status == POOL_STATUS, Code.product_id == product_id)
        .order_by(Code.import_batch_id, Code.id)
        .limit(quantity)
        .with_for_update(skip_locked=True)
        .with_hint(Code, "FORCE INDEX (ix_code_pool_fifo)", "mysql")
    )
    if batch_id is not None:
        stmt = stmt.where(Code.import_batch_id == batch_id)
    if code_range_from:
        stmt = stmt.where(Code.code_value >= code_range_from)
    if code_range_to:
        stmt = stmt.where(Code.code_value <= code_range_to)

    codes = list(db.execute(stmt).scalars())
    if len(codes) < quantity:
        # SKIP LOCKED 会跳过被并发事务锁住的行，此时拿不满就是真的不够
        raise ApiError(
            ErrorCode.INSUFFICIENT_STOCK,
            f"可分配数量不足：需要 {quantity}，实际锁定 {len(codes)}",
            {"available": len(codes), "requested": quantity},
        )

    order = AllocationOrder(
        order_no=_new_order_no(),
        company_id=company_id,
        product_id=product_id,
        code_count=len(codes),
        code_range_from=codes[0].code_value,
        code_range_to=codes[-1].code_value,
        template_version_id=version.id,
        allocated_by=operator_id,
        allocated_at=utcnow(),
        status="active",
    )
    db.add(order)
    db.flush()

    now = utcnow()
    for code in codes:
        code.status = "allocated"
        code.company_id = company_id
        code.current_allocation_order_id = order.id
        db.add(
            CodeEvent(
                code_id=code.id,
                event_type="allocated",
                from_status=POOL_STATUS,
                to_status="allocated",
                operator_id=operator_id,
                occurred_at=now,
            )
        )
    db.flush()

    return AllocationResult(order=order, allocated=len(codes))


def reclaim(db: Session, *, order_id: int, operator_id: int) -> AllocationResult:
    """回收未打印的码（FR-029 / FR-030）。

    分配单下只要有一个码已打印或打印中，整单拒绝——否则会出现"部分回收"的
    半截状态，后续对账无从下手。
    """
    order = db.get(AllocationOrder, order_id)
    if order is None:
        raise ApiError(ErrorCode.NOT_FOUND, "分配单不存在")
    if order.status != "active":
        raise ApiError(ErrorCode.VALIDATION_ERROR, "该分配单已被回收")

    codes = list(
        db.execute(
            select(Code)
            .where(Code.current_allocation_order_id == order.id)
            .with_for_update(skip_locked=True)
        ).scalars()
    )

    blocked = [c for c in codes if c.status in ("printed", "printing")]
    if blocked:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"该分配单下有 {len(blocked)} 个码已打印或正在打印，不可回收",
            {"blocked": len(blocked)},
        )

    now = utcnow()
    for code in codes:
        if code.status != "allocated":
            continue
        code.status = "unallocated"
        code.company_id = None
        code.current_allocation_order_id = None
        db.add(
            CodeEvent(
                code_id=code.id,
                event_type="reclaimed",
                from_status="allocated",
                to_status="unallocated",
                operator_id=operator_id,
                occurred_at=now,
            )
        )

    order.status = "reclaimed"
    db.flush()
    return AllocationResult(order=order, allocated=len(codes))


def list_orders(
    db: Session, *, company_id: int | None = None, limit: int = 100
) -> list[AllocationOrder]:
    stmt = select(AllocationOrder).order_by(AllocationOrder.id.desc()).limit(min(limit, 500))
    if company_id is not None:
        stmt = stmt.where(AllocationOrder.company_id == company_id)
    return list(db.execute(stmt).scalars())
