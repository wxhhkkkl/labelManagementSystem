"""补打、作废与任务轮询的请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReprintRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class ReprintTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: int
    code_value: str
    target_workstation_id: int
    target_workstation_name: str | None = None
    status: str


class VoidRequest(BaseModel):
    code_values: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=255)


class VoidResponse(BaseModel):
    voided: list[str]
    skipped: list[str]


class TaskItemOut(BaseModel):
    task_id: int
    task_type: str
    code_value: str
    template_version_id: int
    # 补打必须能直接渲染出纸，所以模板内容与动态字段随任务一起下发——
    # 只有 version_id 的话工位端还得再取一次模板，多一次往返且多一个失败点。
    elements_json: dict
    data: dict[str, str]
    product_name: str
    company_name: str
    reason: str


class TaskListOut(BaseModel):
    tasks: list[TaskItemOut]


class TaskResultRequest(BaseModel):
    result: str = Field(pattern="^(succeeded|failed)$")
    failure_reason: str | None = Field(default=None, max_length=255)


class TaskResultOut(BaseModel):
    task_id: int
    status: str
    reprint_count: int


class LedgerEntryOut(BaseModel):
    """补打/作废台账的一行（FR-067）。"""

    kind: str  # reprint | void
    code_value: str
    product_name: str | None = None
    company_name: str | None = None
    reason: str | None = None
    operator_id: int | None = None
    workstation_id: int | None = None
    result: str | None = None
    occurred_at: datetime
