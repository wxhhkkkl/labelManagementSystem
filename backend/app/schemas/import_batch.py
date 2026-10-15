"""导入批次的响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_no: str
    code_list_filename: str
    mapping_filename: str
    product_id: int | None = None
    product_names: list[str] = Field(default_factory=list)
    status: str
    total_rows: int | None
    processed_rows: int
    success_count: int
    failure_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ImportCreatedOut(BaseModel):
    batch_id: int
    batch_no: str
    status: str
