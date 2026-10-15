import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.code import Code
from tests.conftest import auth_header
from tests.contract.test_machine_binding import MACHINE, OTHER, bind

pytestmark = pytest.mark.contract


@pytest.mark.parametrize("admin_fixture", ["hq_admin", "sub_admin"])
def test_admin_unbind_and_old_machine_rejected(
    client, db, request, admin_fixture, operator, workstation
):
    admin = request.getfixturevalue(admin_fixture)
    admin.company_id = workstation.company_id
    assert bind(client, operator, workstation).status_code == 200
    workstation.printer_name = "Old printer"
    response = client.post(
        f"/api/v1/workstations/{workstation.id}/unbind", headers=auth_header(admin)
    )
    assert response.status_code == 200 and response.json()["machine_bound"] is False
    db.refresh(workstation)
    assert (
        workstation.machine_id is None
        and workstation.last_heartbeat_at is None
        and workstation.printer_name is None
    )
    old = client.post(
        "/api/v1/workstation/heartbeat",
        headers={**auth_header(operator), "X-LMS-Machine-ID": MACHINE},
        json={"workstation_id": workstation.id},
    )
    assert old.status_code == 403 and old.json()["error_code"] == "WORKSTATION_NOT_BOUND"
    available = client.get("/api/v1/workstation/available", headers=auth_header(operator)).json()
    assert any(row["workstation_id"] == workstation.id for row in available)
    assert bind(client, operator, workstation, OTHER).status_code == 200
    assert db.scalar(select(AuditLog).where(AuditLog.action == "workstation_unbind")) is not None


def test_subadmin_cannot_unbind_other_company(
    client, db, sub_admin, other_company, workstation, operator
):
    assert bind(client, operator, workstation).status_code == 200
    sub_admin.company_id = other_company.id
    r = client.post(f"/api/v1/workstations/{workstation.id}/unbind", headers=auth_header(sub_admin))
    assert r.status_code == 403
    assert workstation.machine_id == MACHINE


def test_operator_cannot_unbind(client, operator, workstation):
    assert (
        client.post(
            f"/api/v1/workstations/{workstation.id}/unbind", headers=auth_header(operator)
        ).status_code
        == 403
    )


def test_unbind_blocked_while_printing(
    client, db, hq_admin, operator, workstation, product, import_batch
):
    assert bind(client, operator, workstation).status_code == 200
    db.add(
        Code(
            code_value="UNBINDTEST1",
            status="printing",
            product_id=product.id,
            import_batch_id=import_batch.id,
            company_id=workstation.company_id,
            locked_workstation_id=workstation.id,
        )
    )
    db.flush()
    r = client.post(f"/api/v1/workstations/{workstation.id}/unbind", headers=auth_header(hq_admin))
    assert r.status_code == 409 and r.json()["error_code"] == "WORKSTATION_BUSY"
    assert workstation.machine_id == MACHINE
