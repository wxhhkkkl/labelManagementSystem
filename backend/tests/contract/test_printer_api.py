"""T145：打印机绑定接口契约测试（FR-070）。

打印机清单由工位端从操作系统读取，服务端只记录选中的名字。
这条边界很重要：服务端不可能知道某台工位电脑上装了哪些打印机。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.workstation import Workstation
from tests.conftest import auth_header

pytestmark = pytest.mark.contract


def _set_printer(client, user, workstation_id: int, name: str):
    return client.put(
        "/api/v1/workstation/printer",
        headers=auth_header(user),
        json={"workstation_id": workstation_id, "printer_name": name},
    )


class TestSetPrinter:
    def test_saves_the_selected_printer(self, client, db: Session, operator: User, workstation):
        resp = _set_printer(client, operator, workstation.id, "Zebra ZD421")

        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"workstation_id", "printer_name"}
        assert body["workstation_id"] == workstation.id
        assert body["printer_name"] == "Zebra ZD421"

        db.refresh(workstation)
        assert workstation.printer_name == "Zebra ZD421"

    def test_trims_surrounding_whitespace(self, client, db: Session, operator, workstation):
        _set_printer(client, operator, workstation.id, "  Zebra ZD421  ")
        db.refresh(workstation)
        assert workstation.printer_name == "Zebra ZD421"

    def test_can_change_the_printer(self, client, db: Session, operator, workstation):
        _set_printer(client, operator, workstation.id, "Printer-A")
        _set_printer(client, operator, workstation.id, "Printer-B")

        db.refresh(workstation)
        assert workstation.printer_name == "Printer-B"

    def test_empty_name_is_422(self, client, operator: User, workstation):
        resp = _set_printer(client, operator, workstation.id, "")
        assert resp.status_code == 422

    def test_unknown_workstation_is_404(self, client, operator: User):
        assert _set_printer(client, operator, 999999, "Printer-X").status_code == 404

    def test_requires_authentication(self, client, workstation):
        resp = client.put(
            "/api/v1/workstation/printer",
            json={"workstation_id": workstation.id, "printer_name": "X"},
        )
        assert resp.status_code == 401


class TestScope:
    def test_other_company_workstation_is_forbidden(self, client, db: Session, operator, other_company):
        foreign = Workstation(
            code="W900", name="他公司工位", company_id=other_company.id, status="active"
        )
        db.add(foreign)
        db.flush()

        resp = _set_printer(client, operator, foreign.id, "Printer-X")
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"

        db.refresh(foreign)
        assert foreign.printer_name is None, "被拒的操作不得改变任何状态"

    def test_hq_admin_can_set_printer_for_any_workstation(
        self, client, db: Session, hq_admin, other_company
    ):
        foreign = Workstation(code="W901", name="他公司工位", company_id=other_company.id)
        db.add(foreign)
        db.flush()

        assert _set_printer(client, hq_admin, foreign.id, "Printer-Y").status_code == 200


class TestAudit:
    def test_printer_change_is_recorded(self, client, db: Session, operator, workstation):
        _set_printer(client, operator, workstation.id, "Zebra ZD421")

        rows = list(
            db.execute(
                AuditLog.__table__.select().where(AuditLog.workstation_id == workstation.id)
            ).all()
        )
        assert rows, "改绑定打印机属于关键操作，必须留痕"


class TestPrintedRecordsCarryThePrinter:
    def test_print_log_uses_the_bound_printer(
        self, client, db: Session, operator, workstation, product, hq_company, import_batch, template_version, hq_admin
    ):
        """绑定打印机不是摆设——打印记录必须带上它（SC-006）。"""
        from sqlalchemy import select

        from app.models.print_log import PrintLog
        from tests.helpers import make_printable

        make_printable(
            db,
            product=product,
            batch=import_batch,
            company=hq_company,
            operator_id=hq_admin.id,
            values=["PR01"],
        )
        _set_printer(client, operator, workstation.id, "Zebra ZD421")

        client.post(
            "/api/v1/workstation/print",
            headers=auth_header(operator),
            json={"workstation_id": workstation.id, "code_values": ["PR01"]},
        )
        client.post(
            "/api/v1/workstation/print/confirm",
            headers=auth_header(operator),
            json={
                "workstation_id": workstation.id,
                "results": [{"code_value": "PR01", "outcome": "succeeded"}],
            },
        )

        log = db.execute(select(PrintLog)).scalar_one()
        assert log.printer_name == "Zebra ZD421"
