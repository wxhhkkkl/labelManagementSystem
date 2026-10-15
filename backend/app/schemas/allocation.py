"""分配与回收的请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AllocationCreate(BaseModel):
    production_batch_no: str | None = Field(default=None, max_length=64)
    company_id: int
    product_id: int
    quantity: int = Field(gt=0)
    # 留空则取产品绑定的默认模板的当前版本（FR-035）
    template_version_id: int | None = None
    # 定向分配（FR-026）
    batch_id: int | None = None
    code_range_from: str | None = Field(default=None, max_length=100)
    code_range_to: str | None = Field(default=None, max_length=100)


class AllocationOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    production_batch_no: str | None = None
    company_id: int
    company_name: str | None = None
    product_id: int
    product_name: str | None = None
    code_count: int
    code_range_from: str | None
    code_range_to: str | None
    template_version_id: int
    template_name: str | None = None
    allocated_by: int
    allocated_at: datetime
    status: str


class AllocationCreatedOut(BaseModel):
    order: AllocationOrderOut
    allocated: int


class CodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code_value: str
    production_batch_no: str | None = None
    status: str
    product_id: int
    company_id: int | None
    import_batch_id: int
    print_count: int
    reprint_count: int
