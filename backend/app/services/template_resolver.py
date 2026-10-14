"""T091：模板版本解析与动态字段填充（FR-037 / FR-041）。

按分配单携带的模板版本取 elements_json，并填充四个动态字段：
产品名、公司名、码值、批次号。

批次号取**该码所在分配单的单号**——这是用户明确确认的口径，
不是导入批次号（见 spec 的澄清记录）。
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.allocation_order import AllocationOrder
from app.models.code import Code
from app.models.company import Company
from app.models.product import Product
from app.models.template import TemplateVersion


@dataclass
class RenderPayload:
    template_version_id: int
    elements_json: dict
    data: dict[str, str]


def dynamic_fields_for(db: Session, code: Code) -> dict[str, str]:
    """对外暴露的动态字段取值。补打任务下发时也要用同一套口径。"""
    return _dynamic_fields(db, code)


def _dynamic_fields(db: Session, code: Code) -> dict[str, str]:
    """填充动态字段。

    取值缺失（例如码尚未分配、没有分配单号）时回退为空字符串——
    契约要求渲染空串而不是 "null" 或占位符（contracts/template-rendering.md）。
    """
    product = db.get(Product, code.product_id) if code.product_id else None
    company = db.get(Company, code.company_id) if code.company_id else None
    order = (
        db.get(AllocationOrder, code.current_allocation_order_id)
        if code.current_allocation_order_id
        else None
    )

    return {
        "product_name": product.name if product else "",
        "company_name": company.name if company else "",
        "code_value": code.code_value,
        "batch_no": order.order_no if order else "",
    }


def resolve_for_code(db: Session, code: Code) -> RenderPayload:
    """取该码应使用的模板版本与渲染数据。

    版本来源是分配单携带的版本（FR-036：工位打印强制使用分配单携带的版本，
    工位端 MUST NOT 自行选择模板）。
    """
    order = (
        db.get(AllocationOrder, code.current_allocation_order_id)
        if code.current_allocation_order_id
        else None
    )
    if order is None:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR, "该码没有关联分配单，无法确定打印模板版本"
        )

    version = db.get(TemplateVersion, order.template_version_id)
    if version is None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "分配单携带的模板版本不存在")

    return RenderPayload(
        template_version_id=version.id,
        elements_json=version.elements_json,
        data=_dynamic_fields(db, code),
    )
