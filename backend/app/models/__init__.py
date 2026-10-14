"""集中导入全部模型，供 Alembic 与应用启动时构建 metadata 使用。

新增模型 MUST 在此登记，否则迁移会漏表。
"""

from app.models.allocation_order import AllocationOrder
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.company import Company
from app.models.import_batch import ImportBatch
from app.models.print_log import PrintLog
from app.models.print_task import PrintTask
from app.models.product import Product
from app.models.template import Template, TemplateVersion
from app.models.user import User
from app.models.workstation import Workstation, WorkstationOperator

__all__ = [
    "AllocationOrder",
    "AuditLog",
    "Base",
    "Code",
    "CodeEvent",
    "Company",
    "ImportBatch",
    "PrintLog",
    "PrintTask",
    "Product",
    "Template",
    "TemplateVersion",
    "User",
    "Workstation",
    "WorkstationOperator",
]
