"""工位端打印接口的请求/响应模型（contracts/workstation-api.md）。"""

from pydantic import BaseModel, Field


class PrintableCodeOut(BaseModel):
    code_value: str
    product_id: int


class PrintableCodePage(BaseModel):
    total: int
    items: list[PrintableCodeOut]
    # 契约明确写出这条，避免下游误以为码是按工位分配的
    screen_scope_note: str = "本公司全部工位共享，码不限定工位"


class PrintRequest(BaseModel):
    workstation_id: int
    code_values: list[str] = Field(min_length=1)
    printer_name: str | None = Field(default=None, max_length=255)


class AcceptedPrintOut(BaseModel):
    code_value: str
    template_version_id: int
    elements_json: dict
    data: dict[str, str]


class RejectedPrintOut(BaseModel):
    code_value: str
    error_code: str
    message: str


class PrintResponse(BaseModel):
    accepted: list[AcceptedPrintOut]
    rejected: list[RejectedPrintOut]


class ConfirmItem(BaseModel):
    code_value: str
    outcome: str = Field(pattern="^(succeeded|failed)$")
    printer_name: str | None = Field(default=None, max_length=255)
    failure_reason: str | None = Field(default=None, max_length=255)


class ConfirmRequest(BaseModel):
    workstation_id: int
    results: list[ConfirmItem] = Field(min_length=1)


class ConfirmResponse(BaseModel):
    confirmed: list[str]
    rejected: list[RejectedPrintOut]
