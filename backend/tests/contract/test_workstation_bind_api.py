"""T038：工位软件绑定工位（FR-069）。

对应用户故事 1 验收场景 3、4 中"工位软件首次配置绑定本机工位"的服务端契约。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workstation import Workstation
from tests.conftest import auth_header

pytestmark = pytest.mark.contract


def test_bind_sets_bound_at_and_heartbeat(
    client, db: Session, operator: User, workstation: Workstation
):
    assert workstation.bound_at is None

    resp = client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": workstation.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workstation_id"] == workstation.id
    assert body["company_id"] == workstation.company_id

    db.refresh(workstation)
    assert workstation.bound_at is not None
    # 绑定后立即刷新心跳，否则刚绑定就会被判离线
    assert workstation.last_heartbeat_at is not None


def test_bind_is_idempotent_on_bound_at(
    client, db: Session, operator: User, workstation: Workstation
):
    client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": workstation.id},
    )
    first = workstation.bound_at

    client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": workstation.id},
    )
    db.refresh(workstation)
    assert workstation.bound_at == first  # 首次绑定时间不被覆盖


def test_bind_other_company_workstation_is_forbidden(
    client, db: Session, operator: User, other_company
):
    foreign = Workstation(code="W800", name="他公司工位", company_id=other_company.id)
    db.add(foreign)
    db.flush()

    resp = client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": foreign.id},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"


def test_bind_disabled_workstation_rejected(
    client, db: Session, operator: User, workstation: Workstation
):
    workstation.status = "disabled"
    db.flush()

    resp = client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": workstation.id},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "WORKSTATION_DISABLED"


def test_bind_workstation_of_disabled_company_rejected(
    client, db: Session, operator: User, workstation, hq_company
):
    """公司停用时，其下工位也不得绑定（FR-003）。"""
    hq_company.status = "disabled"
    db.flush()

    resp = client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": workstation.id},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "WORKSTATION_DISABLED"


def test_bind_unknown_workstation_is_404(client, operator: User):
    resp = client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": 999999},
    )
    assert resp.status_code == 404


def test_bind_requires_authentication(client, workstation: Workstation):
    resp = client.post(
        "/api/v1/workstation/bind", json={"workstation_id": workstation.id}
    )
    assert resp.status_code == 401


def test_bind_writes_audit_record(client, db: Session, operator: User, workstation):
    from app.models.audit_log import AuditLog

    client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(operator),
        json={"workstation_id": workstation.id},
    )
    rows = db.query(AuditLog).filter(AuditLog.action == "workstation.change").all()
    assert len(rows) == 1
    assert rows[0].result == "success"
    assert rows[0].target_id == workstation.id
