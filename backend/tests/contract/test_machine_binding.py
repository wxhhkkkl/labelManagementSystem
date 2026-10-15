import pytest
from sqlalchemy import delete

from app.models.workstation import Workstation, WorkstationOperator
from tests.conftest import auth_header

pytestmark = pytest.mark.contract
MACHINE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def bind(client, user, ws, machine=MACHINE):
    return client.post(
        "/api/v1/workstation/bind",
        headers=auth_header(user),
        json={"workstation_id": ws.id, "machine_id": machine},
    )


def test_company_available_without_operator_assignment(
    client, db, operator, workstation, other_company
):
    db.execute(delete(WorkstationOperator))
    foreign = Workstation(code="FOREIGN", name="Other", company_id=other_company.id)
    occupied = Workstation(
        code="OCC", name="Occupied", company_id=operator.company_id, machine_id=OTHER
    )
    db.add_all([foreign, occupied])
    db.flush()
    r = client.get("/api/v1/workstation/available", headers=auth_header(operator))
    assert r.status_code == 200
    assert [row["workstation_id"] for row in r.json()] == [workstation.id]
    assert bind(client, operator, workstation).status_code == 200
    assert client.get("/api/v1/workstation/available", headers=auth_header(operator)).json() == []


def test_exclusive_binding_and_same_machine_resume(client, db, operator, workstation):
    assert bind(client, operator, workstation).status_code == 200
    assert bind(client, operator, workstation).status_code == 200
    assert bind(client, operator, workstation, OTHER).status_code == 409
    another = Workstation(code="SECOND", name="Second", company_id=operator.company_id)
    db.add(another)
    db.flush()
    assert bind(client, operator, another).status_code == 409
    r = client.get(
        "/api/v1/workstation/binding", params={"machine_id": MACHINE}, headers=auth_header(operator)
    )
    assert r.status_code == 200 and r.json()["workstation_id"] == workstation.id


def test_machine_header_required_for_bound_workstation(client, operator, workstation):
    assert bind(client, operator, workstation).status_code == 200
    payload = {"workstation_id": workstation.id}
    assert (
        client.post(
            "/api/v1/workstation/heartbeat", headers=auth_header(operator), json=payload
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/workstation/heartbeat",
            headers={**auth_header(operator), "X-LMS-Machine-ID": MACHINE},
            json=payload,
        ).status_code
        == 204
    )


def test_company_boundary_even_for_headquarters_login(client, db, hq_admin, other_company):
    ws = Workstation(code="F", name="Foreign", company_id=other_company.id)
    db.add(ws)
    db.flush()
    assert bind(client, hq_admin, ws).status_code == 403


def test_another_account_same_company_can_resume(client, operator, sub_admin, workstation):
    assert bind(client, operator, workstation).status_code == 200
    sub_admin.company_id = operator.company_id
    r = client.get(
        "/api/v1/workstation/binding",
        params={"machine_id": MACHINE},
        headers=auth_header(sub_admin),
    )
    assert r.status_code == 200 and r.json()["workstation_id"] == workstation.id
