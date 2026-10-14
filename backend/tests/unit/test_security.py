"""T023：JWT 签发与校验、密码哈希。"""

import time

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_plaintext_and_verifies(self):
        h = hash_password("s3cret-密码")
        assert h != "s3cret-密码"
        assert verify_password("s3cret-密码", h) is True

    def test_wrong_password_rejected(self):
        h = hash_password("right")
        assert verify_password("wrong", h) is False

    def test_same_password_yields_different_hash(self):
        # bcrypt 每次加盐，同一明文必须产出不同哈希
        assert hash_password("same") != hash_password("same")

    def test_password_longer_than_72_bytes_is_handled(self):
        # bcrypt 只取前 72 字节，超长密码不得抛异常
        long_pw = "a" * 200
        h = hash_password(long_pw)
        assert verify_password(long_pw, h) is True

    def test_verify_against_garbage_hash_returns_false(self):
        assert verify_password("x", "not-a-hash") is False


class TestTokens:
    def test_access_token_payload_contains_required_claims(self):
        tok = create_access_token(
            user_id=42, role="operator", company_id=7, workstation_id=11
        )
        payload = decode_token(tok)
        assert payload["sub"] == "42"
        assert payload["role"] == "operator"
        assert payload["company_id"] == 7
        assert payload["workstation_id"] == 11
        assert payload["typ"] == "access"

    def test_hq_admin_has_null_company(self):
        payload = decode_token(create_access_token(user_id=1, role="hq_admin"))
        assert payload["company_id"] is None
        assert payload["workstation_id"] is None

    def test_refresh_token_has_refresh_type_and_longer_ttl(self):
        access = decode_token(create_access_token(user_id=1, role="hq_admin"))
        refresh = decode_token(
            create_refresh_token(user_id=1, role="hq_admin"), expected_type="refresh"
        )
        assert refresh["typ"] == "refresh"
        assert refresh["exp"] - refresh["iat"] > access["exp"] - access["iat"]

    def test_expired_token_is_rejected(self, monkeypatch):
        from app.core import config

        settings = config.get_settings()
        monkeypatch.setattr(settings, "access_token_seconds", -1)
        tok = create_access_token(user_id=1, role="hq_admin")
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(tok)

    def test_tampered_signature_is_rejected(self):
        tok = create_access_token(user_id=1, role="hq_admin")
        head, body, _ = tok.split(".")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(f"{head}.{body}.deadbeef")

    def test_wrong_token_type_is_rejected(self):
        # 刷新令牌不得当作访问令牌使用
        refresh = create_refresh_token(user_id=1, role="hq_admin")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(refresh, expected_type="access")

    def test_tokens_are_unique_within_same_second(self):
        a = create_access_token(user_id=1, role="hq_admin")
        time.sleep(0.001)
        b = create_access_token(user_id=1, role="hq_admin")
        assert a != b
