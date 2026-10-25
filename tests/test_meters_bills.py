import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from raksa.cli import app
from raksa.commands import meters as meters_cmd
from raksa.meters.bills import BillParseError, parse_bill

FIXTURES = Path(__file__).parent / "fixtures" / "bills"

runner = CliRunner()


def _reading(
    label: str, utility: str, meter_id: str, start: str, end: str, consumption: float, unit: str, balancing: bool = False
) -> dict:
    return {
        "label": label,
        "utility": utility,
        "meter_id": meter_id,
        "period_start": start,
        "period_end": end,
        "consumption": consumption,
        "unit": unit,
        "balancing": balancing,
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
        (
            "water_balancing.html",
            [
                _reading("Vesi (14667678)", "water", "14667678", "2024-01-01", "2026-02-26", 3630.0, "m3", True),
                _reading("Jätevesi (14667678)", "water", "14667678", "2024-01-01", "2026-02-26", 3630.0, "m3", True),
            ],
        ),
    ],
)
def test_parse_bill(fixture, expected):
    readings = parse_bill((FIXTURES / fixture).read_text(encoding="utf-8"))

    assert [reading.model_dump() for reading in readings] == expected


def test_parse_bill_rejects_a_split_bill():
    page = (FIXTURES / "heat.html").read_text(encoding="utf-8") + "<p>KULUTUSLASKU 16.3.2026 - 31.3.2026</p>"

    with pytest.raises(BillParseError):
        parse_bill(page)


class _FakeHuoneistotieto:
    """Serves the bill fixtures as this year's purchase invoices, and nothing for the year before."""

    attachments = {
        "1_1.html": ("text/html", (FIXTURES / "heat.html").read_bytes()),
        "2_1.html": ("text/html", (FIXTURES / "grid.html").read_bytes()),
        "3_1.html": ("text/html", (FIXTURES / "water_estimate.html").read_bytes()),
        # A year-old heat bill and water estimate, so that each meter gets a new reading next to a stored one.
        "6_1.html": ("text/html", (FIXTURES / "heat.html").read_bytes().replace(b"2026", b"2025")),
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
        {"_id": "heat-1", "specification": "kaukolämpö_(55306988)", "readingDate": "2026-03-31", "value": 24.30},
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
        [("kaukolämpö_(55306988)", "2025-03-31", 24.33)],
        [("vesi_(06245559)", "2025-03-31", 150.0), ("vesi_(06245559)", "2026-03-31", 150.0)],
    ]
    assert "EstateApp has 1190.500, bill has 1201.720" in result.output
    assert "EstateApp has 24.300, bill has 24.330" in result.output


def test_sync_bills_fails_when_estateapp_stores_another_value(monkeypatch):
    stored = []

    def _submit_readings(_client, _cid, readings):
        # EstateApp reports every reading as inserted, but keeps a different value.
        stored.extend({"specification": r["specification"], "readingDate": r["readingDate"], "value": r["value"] + 1}
                      for r in readings)
        return {"inserted": len(readings), "refused": 0}

    monkeypatch.setattr(meters_cmd, "_get_bills_client", _FakeHuoneistotieto)
    monkeypatch.setattr(meters_cmd, "_get_client", lambda: object())
    monkeypatch.setattr(meters_cmd, "get_consumptions", lambda *_args, **_kwargs: list(stored))
    monkeypatch.setattr(meters_cmd, "ensure_meters_exist", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(meters_cmd, "submit_readings", _submit_readings)

    result = runner.invoke(app, ["meters", "sync-bills", "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 1
    assert "not stored as expected" in result.output


class _FakeBalancingHuoneistotieto(_FakeHuoneistotieto):
    """Serves a balancing bill for meter 14667678, and an estimate inside its period that EstateApp does not hold yet."""

    attachments = {
        "1_1.html": ("text/html", (FIXTURES / "water_balancing.html").read_bytes()),
        "2_1.html": (
            "text/html",
            (FIXTURES / "water_estimate.html").read_bytes().replace(b"06245559", b"14667678").replace(b"2026", b"2025"),
        ),
    }


@pytest.mark.parametrize(
    ("stored_estimate", "expected_correction"),
    [
        # 3630 real, minus the stored 1000, minus the 150 estimate that the same run inserts.
        (1000.0, 2480.0),
        # The estimates add up to more than the real consumption.
        (4000.0, None),
    ],
)
def test_sync_bills_corrects_a_balancing_bill(monkeypatch, stored_estimate, expected_correction):
    stored = [
        {"_id": f"{key}-1", "specification": key, "readingDate": "2024-03-31", "value": stored_estimate}
        for key in ("vesi_(14667678)", "jätevesi_(14667678)")
    ]
    submit_calls = []

    def _submit_readings(_client, _cid, readings):
        submit_calls.append(readings)
        stored.extend({"specification": r["specification"], "readingDate": r["readingDate"], "value": r["value"]}
                      for r in readings)
        return {"inserted": len(readings), "refused": 0}

    def _get_consumptions(_client, _cid, start_date, end_date, category="electricity"):
        return [r for r in stored if start_date <= r["readingDate"] <= end_date]

    monkeypatch.setattr(meters_cmd, "_get_bills_client", _FakeBalancingHuoneistotieto)
    monkeypatch.setattr(meters_cmd, "_get_client", lambda: object())
    monkeypatch.setattr(meters_cmd, "get_consumptions", _get_consumptions)
    monkeypatch.setattr(meters_cmd, "ensure_meters_exist", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(meters_cmd, "submit_readings", _submit_readings)

    result = runner.invoke(app, ["meters", "sync-bills", "--condo-id", "condo-1", "--submit"])

    if expected_correction is None:
        assert result.exit_code == 1
        assert "(14667678) 2024-01-01 - 2026-02-26" in result.output
        assert submit_calls == []
        return
    assert result.exit_code == 0, result.output
    assert sorted([(r["specification"], r["readingDate"], r["value"]) for r in readings] for readings in submit_calls) == [
        [("jätevesi_(14667678)", "2025-03-31", 150.0), ("jätevesi_(14667678)", "2026-02-26", expected_correction)],
        [("vesi_(14667678)", "2025-03-31", 150.0), ("vesi_(14667678)", "2026-02-26", expected_correction)],
    ]

    # A second run finds the correction stored on the last day and leaves it alone.
    submit_calls.clear()
    rerun = runner.invoke(app, ["meters", "sync-bills", "--condo-id", "condo-1", "--submit"])
    assert rerun.exit_code == 0, rerun.output
    assert submit_calls == []
    assert "EstateApp has" not in rerun.output
