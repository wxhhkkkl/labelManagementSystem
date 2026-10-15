from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.print_identity import PrintDailyCounter, PrintIdentity
from app.models.template import TemplateVersion
from app.services import printing, template_resolver
from app.services.print_identity import ensure_identity, fields_for
from tests.helpers import make_printable
from tests.integration.test_print_concurrency import _run, _seed, _wipe

pytestmark = pytest.mark.integration


def test_reset_each_day_and_reuse_original_identity(
    db, product, import_batch, hq_company, hq_admin, template_version
):
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["SER01", "SER02", "SER03"],
    )
    codes = db.scalars(select(Code).order_by(Code.id)).all()
    first = ensure_identity(db, codes[0].id, date(2026, 10, 14))
    second = ensure_identity(db, codes[1].id, date(2026, 10, 14))
    third = ensure_identity(db, codes[2].id, date(2026, 10, 15))
    assert [first.serial_no, second.serial_no, third.serial_no] == [1, 2, 1]
    assert ensure_identity(db, codes[0].id, date(2026, 10, 15)).print_date == date(2026, 10, 14)
    assert fields_for(db, codes[0].id) == {"print_date": "2026-10-14", "serial_no": "1"}


def test_print_payload_and_reprint_keep_date_and_serial(
    db, product, import_batch, hq_company, hq_admin, template_version, workstation, operator
):
    template_version.elements_json = {
        "paper_width_mm": 60,
        "paper_height_mm": 40,
        "elements": [
            {"type": "date", "x": 2, "y": 2, "font_size": 3},
            {"type": "serial", "x": 2, "y": 8, "font_size": 3},
        ],
    }
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["SER04"],
    )
    codes = db.scalars(select(Code).where(Code.code_value == "SER04")).all()
    accepted, rejected = printing.preempt(
        db, workstation=workstation, operator_id=operator.id, code_values=["SER04"]
    )
    assert not rejected
    initial = accepted[0].data
    assert initial["serial_no"] == "1"
    assert initial["print_date"]
    printing.confirm(
        db,
        workstation=workstation,
        operator_id=operator.id,
        results=[{"code_value": "SER04", "outcome": "succeeded"}],
    )
    assert template_resolver.dynamic_fields_for(db, codes[0]) == initial


def test_explicit_failure_discards_identity_but_does_not_recycle_number(
    db, product, import_batch, hq_company, hq_admin, template_version, workstation, operator
):
    template_version.elements_json = {
        "paper_width_mm": 60,
        "paper_height_mm": 40,
        "elements": [{"type": "serial", "x": 2, "y": 2, "font_size": 3}],
    }
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["SER05"],
    )
    accepted, _ = printing.preempt(
        db, workstation=workstation, operator_id=operator.id, code_values=["SER05"]
    )
    assert accepted[0].data["serial_no"] == "1"
    printing.confirm(
        db,
        workstation=workstation,
        operator_id=operator.id,
        results=[{"code_value": "SER05", "outcome": "failed"}],
    )
    code = db.scalar(select(Code).where(Code.code_value == "SER05"))
    assert db.get(PrintIdentity, code.id) is None
    accepted, _ = printing.preempt(
        db, workstation=workstation, operator_id=operator.id, code_values=["SER05"]
    )
    assert accepted[0].data["serial_no"] == "2"


@pytest.mark.parametrize("overlap", [False, True])
def test_two_workstations_receive_distinct_daily_numbers(engine, overlap):
    _wipe(engine)
    try:
        ids = _seed(engine, code_values=["SERCON1", "SERCON2"])
        with Session(engine) as session:
            version = session.scalar(select(TemplateVersion))
            version.elements_json = {
                "paper_width_mm": 60,
                "paper_height_mm": 40,
                "elements": [{"type": "serial", "x": 2, "y": 2, "font_size": 3}],
            }
            session.commit()
        results = _run(engine, ids, ["SERCON1", "SERCON2"] if overlap else ["SERCON1"], ["SERCON2"])
        assert all(result["ok"] for result in results.values()), results
        with Session(engine) as session:
            identities = session.scalars(select(PrintIdentity)).all()
            assert sorted(identity.serial_no for identity in identities) == [1, 2]
    finally:
        with Session(engine) as session:
            session.execute(delete(PrintIdentity))
            session.execute(delete(PrintDailyCounter))
            session.commit()
        _wipe(engine)
