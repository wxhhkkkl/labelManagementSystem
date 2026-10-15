from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.template import TemplateElement, to_document
from app.services.print_identity import business_date, requires_identity


def test_date_and_serial_configuration_is_preserved():
    doc = to_document(
        60,
        40,
        [
            {
                "type": "date",
                "x": 2,
                "y": 2,
                "width": 25,
                "height": 4.2,
                "font_size": 3,
                "date_format": "YYYY/MM/DD",
            },
            {
                "type": "serial",
                "x": 2,
                "y": 8,
                "width": 25,
                "font_size": 3,
                "prefix": "SN-",
                "serial_digits": 8,
            },
        ],
    )
    assert doc["elements"][1]["prefix"] == "SN-"
    assert requires_identity(doc)


@pytest.mark.parametrize(
    "patch", [{"serial_digits": 0}, {"serial_digits": 13}, {"font_size": None}]
)
def test_invalid_serial_configuration_is_rejected(patch):
    with pytest.raises(ValidationError):
        TemplateElement.model_validate({"type": "serial", "x": 0, "y": 0, "font_size": 3, **patch})


def test_invalid_fixed_date_is_rejected():
    with pytest.raises(ValidationError):
        TemplateElement(
            type="date", x=0, y=0, font_size=3, date_source="fixed", content="2026-02-30"
        )


def test_fixed_date_does_not_allocate_a_serial():
    assert not requires_identity({"elements": [{"type": "date", "date_source": "fixed"}]})


def test_daily_counter_uses_china_midnight():
    assert business_date(datetime(2026, 10, 14, 15, 59, tzinfo=UTC)).isoformat() == "2026-10-14"
    assert business_date(datetime(2026, 10, 14, 16, 0, tzinfo=UTC)).isoformat() == "2026-10-15"
