"""T035：组织与账号接口契约测试（contracts/admin-api.md 组织与账号小节）。

重点覆盖 FR-004 的角色边界：子公司管理员只能管本公司工位与本公司在职操作员账号。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from tests.conftest import auth_header, make_user

pytestmark = pytest.mark.contract


# ---------- 公司 ----------


def test_hq_creates_company(client, hq_admin: User):
    resp = client.post(
        "/api/v1/companies",
        headers=auth_header(hq_admin),
        json={
            "code": "C900",
            "name": "西北分公司",
            "contact": "李四",
            "region": "西安",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "C900"
    assert body["status"] == "active"


def test_duplicate_company_code_rejected(client, hq_admin: User, hq_company):
    resp = client.post(
        "/api/v1/companies",
        headers=auth_header(hq_admin),
        json={"code": "C001", "name": "重复编码"},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


def test_sub_admin_cannot_create_company(client, sub_admin: User):
    resp = client.post(
        "/api/v1/companies",
        headers=auth_header(sub_admin),
        json={"code": "C901", "name": "越权公司"},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"


def test_disable_company_keeps_record_queryable(client, db: Session, hq_admin, hq_company):
    resp = client.post(
        f"/api/v1/companies/{hq_company.id}/disable", headers=auth_header(hq_admin)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    # FR-003：历史数据保留可查
    listing = client.get("/api/v1/companies", headers=auth_header(hq_admin)).json()
    assert any(c["id"] == hq_company.id for c in listing)


# ---------- 工位 ----------


def test_hq_creates_workstation_in_any_company(client, hq_admin: User, other_company):
    resp = client.post(
        "/api/v1/workstations",
        headers=auth_header(hq_admin),
        json={"code": "W900", "name": "华南一号位", "company_id": other_company.id},
    )
    assert resp.status_code == 201
    assert resp.json()["company_id"] == other_company.id


def test_sub_admin_creates_workstation_in_own_company(client, sub_admin: User, hq_company):
    resp = client.post(
        "/api/v1/workstations",
        headers=auth_header(sub_admin),
        json={"code": "W901", "name": "本公司新工位", "company_id": hq_company.id},
    )
    assert resp.status_code == 201


def test_sub_admin_cannot_create_workstation_in_other_company(
    client, sub_admin: User, other_company
):
    resp = client.post(
        "/api/v1/workstations",
        headers=auth_header(sub_admin),
        json={"code": "W902", "name": "越权工位", "company_id": other_company.id},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"


def test_sub_admin_cannot_edit_other_company_workstation(
    client, db: Session, sub_admin: User, other_company
):
    from app.models.workstation import Workstation

    foreign = Workstation(code="W950", name="他公司工位", company_id=other_company.id)
    db.add(foreign)
    db.flush()

    resp = client.patch(
        f"/api/v1/workstations/{foreign.id}",
        headers=auth_header(sub_admin),
        json={"name": "改名"},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"


def test_workstation_carries_printer_and_operators(client, hq_admin, hq_company, operator):
    resp = client.post(
        "/api/v1/workstations",
        headers=auth_header(hq_admin),
        json={
            "code": "W903",
            "name": "带打印机工位",
            "company_id": hq_company.id,
            "printer_name": "Zebra ZD421",
            "operator_ids": [operator.id],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["printer_name"] == "Zebra ZD421"
    assert body["operator_ids"] == [operator.id]
    assert body["online"] is False  # 尚无心跳


def test_operator_from_other_company_cannot_be_bound(
    client, db: Session, hq_admin, hq_company, other_company
):
    foreign_op = make_user(db, username="op2", role="operator", company=other_company)
    resp = client.post(
        "/api/v1/workstations",
        headers=auth_header(hq_admin),
        json={
            "code": "W904",
            "name": "跨公司绑定",
            "company_id": hq_company.id,
            "operator_ids": [foreign_op.id],
        },
    )
    assert resp.status_code == 422
    assert "同一公司" in resp.json()["message"]


def test_workstation_list_filters_by_scope(client, sub_admin: User, hq_company, other_company):
    body = client.get("/api/v1/workstations", headers=auth_header(sub_admin)).json()
    assert all(w["company_id"] == hq_company.id for w in body)


# ---------- 账号 ----------


def test_sub_admin_creates_operator_in_own_company(client, sub_admin, hq_company):
    resp = client.post(
        "/api/v1/users",
        headers=auth_header(sub_admin),
        json={
            "username": "op-new",
            "display_name": "新操作员",
            "password": "pw123456",
            "role": "operator",
            "company_id": hq_company.id,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "operator"


def test_sub_admin_cannot_create_admin_role(client, sub_admin, hq_company):
    """FR-004：子公司管理员不得创建 sub_admin 及以上角色。"""
    resp = client.post(
        "/api/v1/users",
        headers=auth_header(sub_admin),
        json={
            "username": "sneaky",
            "display_name": "越权管理员",
            "password": "pw123456",
            "role": "sub_admin",
            "company_id": hq_company.id,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"


def test_sub_admin_cannot_create_user_in_other_company(client, sub_admin, other_company):
    resp = client.post(
        "/api/v1/users",
        headers=auth_header(sub_admin),
        json={
            "username": "op-x",
            "display_name": "他公司操作员",
            "password": "pw123456",
            "role": "operator",
            "company_id": other_company.id,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"


def test_hq_admin_must_not_belong_to_a_company(client, hq_admin):
    resp = client.post(
        "/api/v1/users",
        headers=auth_header(hq_admin),
        json={
            "username": "hq2",
            "display_name": "第二个总部管理员",
            "password": "pw123456",
            "role": "hq_admin",
            "company_id": 1,
        },
    )
    assert resp.status_code == 422


def test_non_hq_role_requires_company(client, hq_admin):
    resp = client.post(
        "/api/v1/users",
        headers=auth_header(hq_admin),
        json={
            "username": "lonely",
            "display_name": "无公司操作员",
            "password": "pw123456",
            "role": "operator",
        },
    )
    assert resp.status_code == 422


def test_duplicate_username_rejected(client, hq_admin, hq_company, sub_admin):
    """sub_admin 夹具已创建用户 sub1，这里用同名再建应被拒。"""
    resp = client.post(
        "/api/v1/users",
        headers=auth_header(hq_admin),
        json={
            "username": "sub1",
            "display_name": "重名",
            "password": "pw123456",
            "role": "operator",
            "company_id": hq_company.id,
        },
    )
    assert resp.status_code == 422


def test_disable_self_rejected(client, hq_admin: User):
    resp = client.post(
        f"/api/v1/users/{hq_admin.id}/disable", headers=auth_header(hq_admin)
    )
    assert resp.status_code == 422


def test_user_list_filters_by_scope(client, sub_admin, hq_company):
    body = client.get("/api/v1/users", headers=auth_header(sub_admin)).json()
    assert all(u["company_id"] == hq_company.id for u in body)


# ---------- 组织树 ----------


def test_org_tree_groups_workstations_by_company(
    client, hq_admin, hq_company, other_company, workstation
):
    body = client.get("/api/v1/org/tree", headers=auth_header(hq_admin)).json()
    by_id = {node["id"]: node for node in body}
    assert by_id[hq_company.id]["workstations"][0]["name"] == "一号包装工位"
    assert by_id[other_company.id]["workstations"] == []


def test_org_tree_is_hq_only(client, sub_admin: User):
    resp = client.get("/api/v1/org/tree", headers=auth_header(sub_admin))
    assert resp.status_code == 403
