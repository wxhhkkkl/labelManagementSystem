"""审计日志与码详情的响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operator_id: int
    role: str
    company_id: int | None
    workstation_id: int | None
    action: str
    target_type: str | None
    target_id: int | None
    ip: str | None
    result: str
    occurred_at: datetime


class TimelineEntryOut(BaseModel):
    event_type: str
    label: str
    from_status: str | None
    from_status_label: str | None
    to_status: str | None
    to_status_label: str | None
    operator_name: str | None
    workstation_name: str | None
    reason: str | None
    occurred_at: datetime


class CodeDetailOut(BaseModel):
    code_value: str
    status: str
    status_label: str
    product_name: str | None
    company_name: str | None
    allocation_order_no: str | None
    template_version_id: int | None
    print_count: int
    reprint_count: int
    void_reason: str | None
    timeline: list[TimelineEntryOut]
