"""认证接口的请求/响应模型（契约：contracts/auth-api.md）。"""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class MeWorkstation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class MeCompany(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class MeUser(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    company_id: int | None
    company: MeCompany | None = None
    workstations: list[MeWorkstation] = Field(default_factory=list)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: MeUser
