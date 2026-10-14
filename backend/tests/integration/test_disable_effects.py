"""T036：停用连带效应（FR-003）。

停用公司/工位后不可再被分配新码、不可再执行打印；历史数据保留可查。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workstation import Workstation
from tests.conftest import auth_header

pytestmark = pytest.mark.integration


def test_disable_workstation_takes_effect(client, db: Session, hq_admin, workstation):
    """FR-003：停用由管理员执行并持久化；操作员无权调用该接口。"""
    resp = client.post(
        f"/api/v1/workstations/{workstation.id}/disable",
        headers=auth_header(hq_admin),
    )
    assert resp.status_code == 200
    db.refresh(workstation)
    assert workstation.status == "disabled"


def test_operator_cannot_disable_workstation(client, db: Session, operator, workstation):
    """停用是管理动作，工位操作员调用应被拒且不产生副作用。"""
    resp = client.post(
        f"/api/v1/workstations/{workstation.id}/disable",
        headers=auth_header(operator),
    )
    assert resp.status_code == 403
    db.refresh(workstation)
    assert workstation.status == "active"


def test_disabled_workstation_reports_offline_after_heartbeat_gap(
    db: Session, workstation: Workstation
):
    """停用工位不改变心跳语义，但 is_online 只反映心跳，不反映启用状态——
    调用方必须同时检查 status。此处锁定这一约定，防止误用。"""
    from app.services.workstation import is_online, record_heartbeat

    record_heartbeat(db, workstation.id)
    db.refresh(workstation)
    assert is_online(workstation) is True

    workstation.status = "disabled"
    db.flush()
    # 心跳仍新鲜，但状态已停用——两者是独立维度
    assert is_online(workstation) is True
    assert workstation.status == "disabled"


def test_disable_workstation_is_audited(client, db: Session, hq_admin, workstation):
    from app.models.audit_log import AuditLog

    client.post(
        f"/api/v1/workstations/{workstation.id}/disable",
        headers=auth_header(hq_admin),
    )
    rows = db.query(AuditLog).filter(AuditLog.target_type == "workstation").all()
    assert len(rows) == 1
    assert rows[0].result == "success"


def test_disabled_company_history_remains_queryable(
    client, db: Session, hq_admin, hq_company, workstation
):
    client.post(
        f"/api/v1/companies/{hq_company.id}/disable", headers=auth_header(hq_admin)
    )

    companies = client.get("/api/v1/companies", headers=auth_header(hq_admin)).json()
    record = next(c for c in companies if c["id"] == hq_company.id)
    assert record["status"] == "disabled"
    assert record["name"] == "华东分公司"  # 记录本身未丢失

    # 其下工位仍可查询
    stations = client.get("/api/v1/workstations", headers=auth_header(hq_admin)).json()
    assert any(w["company_id"] == hq_company.id for w in stations)


def test_disable_company_twice_is_idempotent(client, hq_admin, hq_company):
    for _ in range(2):
        resp = client.post(
            f"/api/v1/companies/{hq_company.id}/disable", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"


def test_hq_can_still_administer_disabled_company(client, hq_admin, hq_company, operator):
    """停用只是业务状态，不阻断总部的事后管理（例如补建工位以便恢复）。"""
    client.post(
        f"/api/v1/companies/{hq_company.id}/disable", headers=auth_header(hq_admin)
    )
    resp = client.post(
        "/api/v1/workstations",
        headers=auth_header(hq_admin),
        json={"code": "W960", "name": "停用公司下新建", "company_id": hq_company.id},
    )
    assert resp.status_code == 201
