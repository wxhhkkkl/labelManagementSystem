"""T025：认证四接口契约测试（contracts/auth-api.md）。

覆盖正常返回结构与 INVALID_CREDENTIALS / ACCOUNT_DISABLED。
需要真实 MySQL：无库时由 engine 夹具整体跳过。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import auth_header, make_user

pytestmark = pytest.mark.contract


def test_login_returns_tokens_and_user(client, hq_admin: User):
    resp = client.post(
        "/api/v1/auth/login", json={"username": "hq", "password": "pw123456"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"access_token", "refresh_token", "expires_in", "user"}
    assert body["expires_in"] == 7200
    assert body["user"]["username"] == "hq"
    assert body["user"]["role"] == "hq_admin"
    assert body["user"]["company_id"] is None


def test_login_wrong_password_is_401(client, hq_admin: User):
    resp = client.post(
        "/api/v1/auth/login", json={"username": "hq", "password": "nope"}
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "INVALID_CREDENTIALS"


def test_login_unknown_user_is_same_error(client, db: Session):
    """账号不存在与密码错误返回同一错误码，避免账号枚举。"""
    resp = client.post(
        "/api/v1/auth/login", json={"username": "ghost", "password": "whatever"}
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "INVALID_CREDENTIALS"


def test_login_disabled_account_is_403(client, db: Session, hq_company):
    user = make_user(db, username="gone", role="operator", company=hq_company)
    user.status = "disabled"
    db.flush()

    resp = client.post(
        "/api/v1/auth/login", json={"username": "gone", "password": "pw123456"}
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "ACCOUNT_DISABLED"


def test_me_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "INVALID_CREDENTIALS"


def test_me_returns_company_and_bound_workstations(
    client, db: Session, operator: User, workstation
):
    from app.models.workstation import WorkstationOperator

    db.add(WorkstationOperator(workstation_id=workstation.id, user_id=operator.id))
    db.flush()

    resp = client.get("/api/v1/auth/me", headers=auth_header(operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "operator"
    assert body["company"]["id"] == operator.company_id
    assert [w["name"] for w in body["workstations"]] == ["一号包装工位"]


def test_refresh_issues_new_access_token(client, hq_admin: User):
    login = client.post(
        "/api/v1/auth/login", json={"username": "hq", "password": "pw123456"}
    ).json()

    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()

    # 新令牌可用
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
    )
    assert me.status_code == 200


def test_refresh_rejects_access_token(client, hq_admin: User):
    """刷新令牌不得接受访问令牌，反之亦然。"""
    login = client.post(
        "/api/v1/auth/login", json={"username": "hq", "password": "pw123456"}
    ).json()

    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["access_token"]}
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "INVALID_CREDENTIALS"


def test_disabling_account_invalidates_existing_token(client, db: Session, operator: User):
    """research.md R4：账号停用必须每次请求实时校验，不能只靠令牌过期。"""
    headers = auth_header(operator)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    operator.status = "disabled"
    db.flush()

    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "ACCOUNT_DISABLED"


def test_logout_writes_audit_and_returns_204(client, db: Session, hq_admin: User):
    from app.models.audit_log import AuditLog

    resp = client.post("/api/v1/auth/logout", headers=auth_header(hq_admin))
    assert resp.status_code == 204

    actions = [row.action for row in db.query(AuditLog).all()]
    assert "logout" in actions


def test_login_failure_is_audited_for_known_account(client, db: Session, hq_admin: User):
    from app.models.audit_log import AuditLog

    client.post("/api/v1/auth/login", json={"username": "hq", "password": "nope"})

    rows = [r for r in db.query(AuditLog).all() if r.action == "login"]
    assert [r.result for r in rows] == ["failed"]
