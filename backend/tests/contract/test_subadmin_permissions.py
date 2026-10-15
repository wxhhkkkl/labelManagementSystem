import pytest

from app.models.base import utcnow
from app.models.code import Code
from app.models.print_log import PrintLog
from app.models.print_task import PrintTask
from app.models.workstation import Workstation
from tests.conftest import auth_header

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/v1/org/tree", None),
        ("GET", "/api/v1/products", None),
        ("GET", "/api/v1/templates", None),
        ("GET", "/api/v1/imports", None),
        ("GET", "/api/v1/allocations", None),
        ("GET", "/api/v1/audit-logs", None),
        ("GET", "/api/v1/codes/TEST123", None),
        ("POST", "/api/v1/codes/void", {"code_values": ["TEST123"], "reason": "test"}),
        ("POST", "/api/v1/products", {"code": "TEST", "name": "Test"}),
        ("POST", "/api/v1/templates", {"code": "TEST", "name": "Test"}),
        ("POST", "/api/v1/allocations", {"company_id": 1, "product_id": 1, "quantity": 1}),
    ],
)
def test_forbidden_admin_routes(client, sub_admin, method, path, payload):
    response = client.request(method, path, headers=auth_header(sub_admin), json=payload)
    assert response.status_code == 403


def test_subadmin_queries_and_details_are_company_scoped(
    client, db, sub_admin, product, import_batch, workstation, other_company, template_version
):
    sub_admin.company_id = workstation.company_id
    foreign_ws = Workstation(code="FOREIGN", name="Other station", company_id=other_company.id)
    db.add(foreign_ws)
    db.flush()
    own = Code(
        code_value="OWNCODE",
        status="printed",
        company_id=workstation.company_id,
        product_id=product.id,
        import_batch_id=import_batch.id,
    )
    foreign = Code(
        code_value="OTHERCODE",
        status="printed",
        company_id=other_company.id,
        product_id=product.id,
        import_batch_id=import_batch.id,
    )
    voided = Code(
        code_value="VOIDCODE",
        status="voided",
        company_id=workstation.company_id,
        product_id=product.id,
        import_batch_id=import_batch.id,
        void_reason="void",
        voided_at=utcnow(),
    )
    db.add_all([own, foreign, voided])
    db.flush()
    for code, ws in [(own, workstation), (foreign, foreign_ws)]:
        db.add(
            PrintLog(
                code_id=code.id,
                code_value=code.code_value,
                product_id=product.id,
                company_id=code.company_id,
                workstation_id=ws.id,
                operator_id=sub_admin.id,
                printer_name="Test",
                template_version_id=template_version.id,
                print_type="first",
                result="succeeded",
                printed_at=utcnow(),
            )
        )
        db.add(
            PrintTask(
                code_id=code.id,
                target_workstation_id=ws.id,
                template_version_id=template_version.id,
                reason="Reprint",
                created_by=sub_admin.id,
            )
        )
    db.flush()
    headers = auth_header(sub_admin)
    codes = client.get("/api/v1/codes", headers=headers).json()["items"]
    assert {row["code_value"] for row in codes} == {"OWNCODE", "VOIDCODE"}
    assert [
        row["code_value"] for row in client.get("/api/v1/reports/prints", headers=headers).json()
    ] == ["OWNCODE"]
    ledger = client.get("/api/v1/reprints", headers=headers).json()
    assert [row["code_value"] for row in ledger] == ["OWNCODE"]
    assert all(row["kind"] == "reprint" for row in ledger)
    assert (
        client.get(
            "/api/v1/reports/prints", params={"company_id": other_company.id}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/codes/OTHERCODE/reprint", headers=headers, json={"reason": "test"}
        ).status_code
        == 403
    )
    # Own reprint access passes authorization; this seed has no original station so it is rejected for business reasons.
    own_response = client.post(
        "/api/v1/codes/OWNCODE/reprint", headers=headers, json={"reason": "test"}
    )
    assert own_response.status_code != 403
    options = client.get("/api/v1/products/options", headers=headers).json()
    assert options and "stats" not in options[0]


def test_subadmin_can_only_manage_own_workstations(client, sub_admin, other_company):
    headers = auth_header(sub_admin)
    own = client.post(
        "/api/v1/workstations",
        headers=headers,
        json={"code": "OWNNEW", "name": "Own station", "company_id": sub_admin.company_id},
    )
    assert own.status_code == 201
    foreign = client.post(
        "/api/v1/workstations",
        headers=headers,
        json={"code": "FOREIGNNEW", "name": "Other station", "company_id": other_company.id},
    )
    assert foreign.status_code == 403


def test_subadmin_adds_and_manages_only_own_employees(
    client, db, sub_admin, other_company, hq_admin
):
    headers = auth_header(sub_admin)
    payload = {
        "username": "new-own-employee",
        "display_name": "Employee",
        "password": "password123",
        "role": "operator",
        "company_id": sub_admin.company_id,
    }
    response = client.post("/api/v1/users", headers=headers, json=payload)
    assert response.status_code == 201
    employee = response.json()
    assert employee["company_id"] == sub_admin.company_id and employee["role"] == "operator"
    users = client.get("/api/v1/users", headers=headers).json()
    assert users and all(
        user["company_id"] == sub_admin.company_id and user["role"] == "operator" for user in users
    )
    assert (
        client.post(
            "/api/v1/users",
            headers=headers,
            json={**payload, "username": "foreign-employee", "company_id": other_company.id},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/users",
            headers=headers,
            json={**payload, "username": "new-admin", "role": "sub_admin"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/users/{hq_admin.id}", headers=headers, json={"password": "password456"}
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/v1/users/{employee['id']}/disable", headers=headers).status_code == 200
    )
