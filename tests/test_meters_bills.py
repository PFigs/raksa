import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from raksa.cli import app
from raksa.commands import meters as meters_cmd
from raksa.meters.bills import parse_bill

FIXTURES = Path(__file__).parent / "fixtures" / "bills"

runner = CliRunner()


def _reading(label: str, utility: str, meter_id: str, start: str, end: str, consumption: float, unit: str) -> dict:
    return {
        "label": label,
        "utility": utility,
        "meter_id": meter_id,
        "period_start": start,
        "period_end": end,
        "consumption": consumption,
        "unit": unit,
    }


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (
            "heat.html",
            [_reading("Kaukolämpö (55306988)", "heat", "55306988", "2026-03-01", "2026-03-31", 24.33, "MWh")],
        ),
        (
            "grid.html",
            [
                _reading(
                    "Sähkö yhteinen (643007572070390203)",
                    "electricity",
                    "643007572070390203",
                    "2026-08-01",
                    "2026-08-31",
                    1201.72,
                    "kWh",
                )
            ],
        ),
        (
            "water_estimate.html",
            [
                _reading("Vesi (06245559)", "water", "06245559", "2026-02-27", "2026-03-31", 150.0, "m3"),
                _reading("Jätevesi (06245559)", "water", "06245559", "2026-02-27", "2026-03-31", 150.0, "m3"),
            ],
        ),
        ("fortum.html", []),
        ("water_balancing.html", []),
    ],
)
def test_parse_bill(fixture, expected):
    readings = parse_bill((FIXTURES / fixture).read_text(encoding="utf-8"))

    assert [reading.model_dump() for reading in readings] == expected


class _FakeHuoneistotieto:
    """Serves the bill fixtures as this year's purchase invoices, and nothing for the year before."""

    attachments = {
        "1_1.html": ("text/html", (FIXTURES / "heat.html").read_bytes()),
        "2_1.html": ("text/html", (FIXTURES / "grid.html").read_bytes()),
        "3_1.html": ("text/html", (FIXTURES / "water_estimate.html").read_bytes()),
        # A second water estimate, so that the water meters get two new readings each.
        "4_1.html": ("text/html", (FIXTURES / "water_estimate.html").read_bytes().replace(b"2026", b"2025")),
        "5_1.pdf": ("application/pdf", b"%PDF"),
    }

    def list_purchase_invoices(self, year: int) -> list[dict]:
        if year != datetime.date.today().year:
            return []
        return [{"maksunsaaja": "Payee", "liitteet": [name]} for name in self.attachments]

    def download_invoice_file(self, file_name: str) -> tuple[str, bytes]:
        return self.attachments[file_name]


def test_plan_readings_never_replaces(monkeypatch):
    stored = [
        {"_id": "heat-1", "specification": "kaukolämpö_(55306988)", "readingDate": "2026-03-31", "value": 24.33},
        {"specification": "sähkö_yhteinen_(643007572070390203)", "readingDate": "2026-08-31", "value": 1190.5},
    ]
    submit_calls = []

    def _submit_readings(_client, _cid, readings):
        submit_calls.append(readings)
        stored.extend({"specification": r["specification"], "readingDate": r["readingDate"], "value": r["value"]}
                      for r in readings)
        return {"inserted": len(readings), "refused": 0}

    monkeypatch.setattr(meters_cmd, "_get_bills_client", _FakeHuoneistotieto)
    monkeypatch.setattr(meters_cmd, "_get_client", lambda: object())
    monkeypatch.setattr(meters_cmd, "get_consumptions", lambda *_args, **_kwargs: list(stored))
    monkeypatch.setattr(meters_cmd, "ensure_meters_exist", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(meters_cmd, "submit_readings", _submit_readings)

    result = runner.invoke(app, ["meters", "sync-bills", "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 0, result.output
    assert sorted([(r["specification"], r["readingDate"], r["value"]) for r in readings] for readings in submit_calls) == [
        [("jätevesi_(06245559)", "2025-03-31", 150.0), ("jätevesi_(06245559)", "2026-03-31", 150.0)],
        [("vesi_(06245559)", "2025-03-31", 150.0), ("vesi_(06245559)", "2026-03-31", 150.0)],
    ]
    assert "EstateApp has 1190.500, bill has 1201.720" in result.output
