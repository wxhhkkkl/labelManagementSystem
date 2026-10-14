"""T024：JWT 签发/校验与密码哈希（research.md R4：两端统一 JWT）。

访问令牌 2 小时、刷新令牌 7 天。账号停用不在这里校验——那必须每次请求实时查库
（见 app/core/deps.py），不能只依赖令牌过期。
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]

# bcrypt 只处理前 72 字节，超长明文需截断否则会抛异常
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # 哈希串损坏时不抛异常，一律视为校验失败
        return False


def _create_token(
    user_id: int,
    role: str,
    token_type: TokenType,
    company_id: int | None,
    workstation_id: int | None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = (
        settings.access_token_seconds
        if token_type == "access"
        else settings.refresh_token_seconds
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "company_id": company_id,
        "workstation_id": workstation_id,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        # 同一秒内签发的令牌必须互不相同
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    user_id: int,
    role: str,
    company_id: int | None = None,
    workstation_id: int | None = None,
) -> str:
    return _create_token(user_id, role, "access", company_id, workstation_id)


def create_refresh_token(user_id: int, role: str, company_id: int | None = None) -> str:
    return _create_token(user_id, role, "refresh", company_id, None)


def decode_token(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    """解码并校验令牌。类型不符时抛 jwt.InvalidTokenError。"""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(
            f"令牌类型不符：期望 {expected_type}，实际 {payload.get('typ')}"
        )
    return payload
