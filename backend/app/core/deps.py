"""T027：认证依赖。

关键点：每次请求都实时查库校验 User.status（research.md R4）。JWT 无法即时吊销，
若只依赖令牌过期，停用账号后其令牌在有效期内仍然可用——这是不可接受的安全缺口。
"""

from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ApiError, ErrorCode
from app.core.security import decode_token
from app.models.user import User

HQ_ADMIN = "hq_admin"
SUB_ADMIN = "sub_admin"
OPERATOR = "operator"


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "缺少或格式错误的访问令牌")
    return token


def get_current_user(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> User:
    token = _extract_bearer(request)
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "访问令牌已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "访问令牌无效") from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS, "账号不存在")

    # 实时校验，不依赖令牌有效期
    if user.status != "active":
        raise ApiError(ErrorCode.ACCOUNT_DISABLED, "账号已停用")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    """生成一个只允许指定角色通过的依赖。"""

    def _dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "当前角色无权执行该操作")
        return user

    return _dependency


require_hq_admin = require_roles(HQ_ADMIN)
require_admin = require_roles(HQ_ADMIN, SUB_ADMIN)

HqAdmin = Annotated[User, Depends(require_hq_admin)]
AnyAdmin = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


ClientIp = Annotated[str | None, Depends(client_ip)]
