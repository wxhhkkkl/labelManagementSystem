"""导入批次的响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_no: str
    code_list_filename: str
    mapping_filename: str
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
