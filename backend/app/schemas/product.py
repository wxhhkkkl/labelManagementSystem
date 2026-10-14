"""产品相关的请求/响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    spec: str | None = Field(default=None, max_length=255)
    default_template_id: int | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    spec: str | None = Field(default=None, max_length=255)
    default_template_id: int | None = None


class ProductStatsOut(BaseModel):
    imported: int
    allocated: int
    printed: int


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    spec: str | None
    default_template_id: int | None
    status: str
    stats: ProductStatsOut
