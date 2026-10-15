"""组织与账号相关的请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

Role = str  # hq_admin | sub_admin | operator


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 公司 ----------


class CompanyCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    contact: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=64)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    contact: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=64)


class CompanyOut(_Base):
    id: int
    code: str
    name: str
    contact: str | None
    region: str | None
    status: str


# ---------- 工位 ----------


class WorkstationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    company_id: int | None = None
    printer_name: str | None = Field(default=None, max_length=255)
    operator_ids: list[int] = Field(default_factory=list)


class WorkstationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    printer_name: str | None = Field(default=None, max_length=255)
    operator_ids: list[int] | None = None


class WorkstationOut(_Base):
    id: int
    code: str
    name: str
    company_id: int
    company_name: str | None = None
    printer_name: str | None
    status: str
    last_heartbeat_at: datetime | None = None
    online: bool = False
    machine_bound: bool = False
    operator_ids: list[int] = Field(default_factory=list)


class OrgTreeNode(_Base):
    id: int
    code: str
    name: str
    status: str
    workstations: list[WorkstationOut] = Field(default_factory=list)


# ---------- 账号 ----------


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: str
    company_id: int | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UserOut(_Base):
    id: int
    username: str
    display_name: str
    role: str
    company_id: int | None
    status: str
