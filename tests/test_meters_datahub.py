import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from raksa.cli import app
from raksa.commands import meters as meters_cmd
from raksa.meters import estateapp
from raksa.meters.datahub import DatahubError, MonthlyConsumption, read_export, plan_readings

runner = CliRunner()

GSRN = "643000000000000000"
HEADER = "MeteringPointGSRN;Product Type;Resolution;Unit Type;Reading Type;Start Time;Quantity;Quality"


def _write_csv(path: Path, rows: list[tuple[str, str, str, str]], gsrn: str = GSRN, unit: str = "kWh"):
    """rows: (resolution, start_time, quantity, quality)"""
    lines = [HEADER]
    for resolution, start, quantity, quality in rows:
        lines.append(f"{gsrn};8716867000030;{resolution};{unit};BN01;{start};{quantity};{quality}")
    path.write_text("﻿" + "\n".join(lines) + "\n", encoding="utf-8")


def _steps(start_utc: str, count: int, resolution: str, quantity: str, quality: str = "OK"):
    step = {"PT1H": datetime.timedelta(hours=1), "PT15M": datetime.timedelta(minutes=15)}[resolution]
    first = datetime.datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    return [
        (resolution, (first + step * i).strftime("%Y-%m-%dT%H:%M:00Z"), quantity, quality)
        for i in range(count)
    ]


def test_complete_month_is_aggregated(tmp_path):
    csv_path = tmp_path / "export.csv"
    # February 2026 in Helsinki: 2026-01-31T22:00Z .. 2026-02-28T22:00Z = 672 hours
    _write_csv(csv_path, _steps("2026-01-31T22:00:00Z", 672, "PT1H", "1,000000"))

    summary = read_export(csv_path)

    assert summary.gsrn == GSRN
    assert summary.incomplete == []
    assert len(summary.months) == 1
    month = summary.months[0]
    assert (month.year, month.month) == (2026, 2)
    assert month.consumption_kwh == 672.0
    assert month.reading_date == "2026-02-28"
    assert month.estimated_intervals == 0


def test_spring_forward_month_has_one_hour_less(tmp_path):
    csv_path = tmp_path / "export.csv"
    # March 2026 in Helsinki: 2026-02-28T22:00Z .. 2026-03-31T21:00Z = 743 hours
    _write_csv(csv_path, _steps("2026-02-28T22:00:00Z", 743, "PT1H", "1,000000"))

    summary = read_export(csv_path)

    assert [(m.year, m.month) for m in summary.months] == [(2026, 3)]
    assert summary.months[0].consumption_kwh == 743.0
    assert summary.months[0].reading_date == "2026-03-31"


def test_incomplete_month_is_reported_not_aggregated(tmp_path):
    csv_path = tmp_path / "export.csv"
    _write_csv(csv_path, _steps("2026-01-31T22:00:00Z", 100, "PT1H", "1,000000"))

    summary = read_export(csv_path)

    assert summary.months == []
    assert summary.incomplete == ["2026-02"]


def test_mixed_resolutions_in_one_month(tmp_path):
    csv_path = tmp_path / "export.csv"
    rows = _steps("2026-01-31T22:00:00Z", 336, "PT1H", "1,000000")
    rows += _steps("2026-02-14T22:00:00Z", 1344, "PT15M", "0,250000")
    _write_csv(csv_path, rows)

    summary = read_export(csv_path)

    assert len(summary.months) == 1
    assert summary.months[0].consumption_kwh == 672.0


def test_non_ok_quality_is_summed_and_counted(tmp_path):
    csv_path = tmp_path / "export.csv"
    rows = _steps("2026-01-31T22:00:00Z", 671, "PT1H", "1,000000")
    rows += _steps("2026-02-28T21:00:00Z", 1, "PT1H", "2,000000", quality="QM")
    _write_csv(csv_path, rows)

    summary = read_export(csv_path)

    assert summary.months[0].consumption_kwh == 673.0
    assert summary.months[0].estimated_intervals == 1


def test_interior_gap_makes_the_month_incomplete(tmp_path):
    csv_path = tmp_path / "export.csv"
    rows = _steps("2026-01-31T22:00:00Z", 1, "PT1H", "1,000000")
    rows += _steps("2026-02-28T21:00:00Z", 1, "PT1H", "1,000000")
    _write_csv(csv_path, rows)

    summary = read_export(csv_path)

    assert summary.months == []
    assert summary.incomplete == ["2026-02"]


def test_two_metering_points_is_an_error(tmp_path):
    csv_path = tmp_path / "export.csv"
    lines = [HEADER,
             f"{GSRN};8716867000030;PT1H;kWh;BN01;2026-01-31T22:00:00Z;1,000000;OK",
             "643007572070390357;8716867000030;PT1H;kWh;BN01;2026-01-31T22:00:00Z;1,000000;OK"]
    csv_path.write_text("﻿" + "\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(DatahubError, match="one accounting point"):
        read_export(csv_path)


def test_unexpected_unit_is_an_error(tmp_path):
    csv_path = tmp_path / "export.csv"
    _write_csv(csv_path, _steps("2026-01-31T22:00:00Z", 1, "PT1H", "1,000000"), unit="MWh")

    with pytest.raises(DatahubError, match="MWh"):
        read_export(csv_path)


def test_unknown_resolution_is_an_error(tmp_path):
    csv_path = tmp_path / "export.csv"
    _write_csv(csv_path, [("PT5M", "2026-01-31T22:00:00Z", "1,000000", "OK")])

    with pytest.raises(DatahubError, match="PT5M"):
        read_export(csv_path)


def test_export_without_rows_is_an_error(tmp_path):
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("﻿" + HEADER + "\n", encoding="utf-8")

    with pytest.raises(DatahubError, match="no rows"):
        read_export(csv_path)


def _month(year: int, month: int, kwh: float) -> MonthlyConsumption:
    return MonthlyConsumption(year=year, month=month, consumption_kwh=kwh, estimated_intervals=0)


def _reading(reading_date: str, value: float, _id: str | None = "r1") -> dict:
    reading = {"specification": "sähkö_yhteinen_(643000000000000000)",
               "readingDate": reading_date, "value": value}
    if _id is not None:
        reading["_id"] = _id
    return reading


def test_month_absent_from_estateapp_is_an_insert():
    planned = plan_readings([_month(2026, 2, 1179.2)], [])

    assert [(p.reading_date, p.action, p.value) for p in planned] == [("2026-02-28", "insert", 1179.2)]
    assert planned[0].existing_id is None


def test_matching_value_is_skipped():
    planned = plan_readings([_month(2026, 1, 1227.44)], [_reading("2026-01-31", 1227.44)])

    assert planned[0].action == "skip"
    assert planned[0].existing_value == 1227.44


def test_differing_value_is_replaced_and_carries_the_id():
    planned = plan_readings([_month(2022, 3, 778.03)], [_reading("2022-03-31", 822.92, _id="abc123")])

    assert planned[0].action == "replace"
    assert planned[0].value == 778.03
    assert planned[0].existing_value == 822.92
    assert planned[0].existing_id == "abc123"


def test_difference_below_half_a_cent_is_a_skip():
    planned = plan_readings([_month(2026, 1, 1227.44)], [_reading("2026-01-31", 1227.441)])

    assert planned[0].action == "skip"


def test_epoch_millis_reading_dates_are_matched():
    epoch_ms = "1769817600000"  # 2026-01-31 00:00 UTC
    planned = plan_readings([_month(2026, 1, 1227.44)], [_reading(epoch_ms, 1227.44)])

    assert planned[0].action == "skip"


def test_unmatched_existing_reading_does_not_block_an_insert():
    planned = plan_readings([_month(2026, 2, 100.0)], [_reading("2019-01-31", 5.0)])

    assert [p.action for p in planned] == ["insert"]


def test_one_cent_difference_is_a_replace():
    planned = plan_readings([_month(2026, 1, 100.01)], [_reading("2026-01-31", 100.0)])

    assert planned[0].action == "replace"


def test_difference_at_the_tolerance_is_a_replace():
    planned = plan_readings([_month(2026, 1, 100.0051)], [_reading("2026-01-31", 100.0)])

    assert planned[0].action == "replace"


def test_difference_just_inside_the_tolerance_is_a_skip():
    planned = plan_readings([_month(2026, 1, 100.0049)], [_reading("2026-01-31", 100.0)])

    assert planned[0].action == "skip"


def test_unusable_reading_date_is_an_error():
    with pytest.raises(DatahubError, match="unusable readingDate"):
        plan_readings([_month(2026, 1, 100.0)], [_reading("not-a-date", 100.0)])


def test_duplicate_existing_readings_for_same_date_is_an_error():
    with pytest.raises(DatahubError, match="more than one existing reading for 2026-01-31"):
        plan_readings(
            [_month(2026, 1, 100.0)],
            [_reading("2026-01-31", 100.0, _id="r1"), _reading("2026-01-31", 150.0, _id="r2")]
        )


def test_replace_without_reading_id_is_an_error():
    with pytest.raises(DatahubError, match="has no id to replace"):
        plan_readings([_month(2026, 1, 100.0)], [_reading("2026-01-31", 150.0, _id=None)])


def test_replace_reading_updates_in_place(monkeypatch):
    sent = {}

    def fake_submit_readings(_client, _condo_id, readings):
        sent["readings"] = readings
        return {"inserted": 1, "refused": 0}

    monkeypatch.setattr(estateapp, "submit_readings", fake_submit_readings)

    reading = {"category": "electricity", "specification": "k", "readingDate": "2022-03-31",
               "value": 778.03, "type": "usual"}
    result = estateapp.replace_reading(object(), "condo-1", "abc123", reading)

    assert result == {"inserted": 1, "refused": 0}
    assert sent["readings"] == [dict(reading, _id="abc123")]


def _six_hundred_hours(path: Path):
    """A complete February 2026 at 1 kWh/hour."""
    _write_csv(path, _steps("2026-01-31T22:00:00Z", 672, "PT1H", "1,000000"))


def _stub_estateapp(monkeypatch, existing: list[dict]):
    """Stub EstateApp reads/writes for the import command.

    `stored` models what EstateApp actually holds, so the post-submit
    verification re-read sees submitted/replaced readings as settled.
    """
    stored = list(existing)
    calls = {"submitted": [], "replaced": [], "window": None, "labels": None}

    def _get_consumptions(_client, _condo_id, start_date, end_date, **_kwargs):
        calls["window"] = (start_date, end_date)
        return list(stored)

    def _ensure(_client, _cid, labels, **_kwargs):
        calls["labels"] = list(labels)
        return {label: meters_cmd.label_to_key(label) for label in labels}

    def _submit_readings(_client, _cid, readings):
        calls["submitted"].extend(readings)
        stored.extend(
            {"specification": r["specification"], "readingDate": r["readingDate"], "value": r["value"]}
            for r in readings
        )
        return {"inserted": len(readings), "refused": 0}

    def _replace_reading(_client, _cid, consumption_id, reading):
        calls["replaced"].append((consumption_id, reading))
        for record in stored:
            if str(record.get("_id")) == consumption_id:
                record["value"] = reading["value"]
                break
        return {"inserted": 1, "refused": 0}

    monkeypatch.setattr(meters_cmd, "_get_client", lambda: object())
    monkeypatch.setattr(meters_cmd, "get_consumptions", _get_consumptions)
    monkeypatch.setattr(meters_cmd, "ensure_meters_exist", _ensure)
    monkeypatch.setattr(meters_cmd, "submit_readings", _submit_readings)
    monkeypatch.setattr(meters_cmd, "replace_reading", _replace_reading)
    return calls


def test_import_datahub_dry_run_submits_nothing(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    calls = _stub_estateapp(monkeypatch, [])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path), "--condo-id", "condo-1"])

    assert result.exit_code == 0
    assert "2026-02-28" in result.output
    assert "insert" in result.output
    assert "Dry-run mode" in result.output
    assert calls["submitted"] == []
    assert calls["replaced"] == []


def test_import_datahub_submits_inserts(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    calls = _stub_estateapp(monkeypatch, [])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path),
                                 "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 0
    assert calls["labels"] == ["Sähkö yhteinen (643000000000000000)"]
    assert calls["submitted"] == [{
        "category": "electricity",
        "specification": "sähkö_yhteinen_(643000000000000000)",
        "readingDate": "2026-02-28",
        "value": 672.0,
        "type": "usual",
    }]
    assert calls["window"] == ("2026-02-01", "2026-02-28")


def test_import_datahub_replaces_a_differing_value(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    calls = _stub_estateapp(monkeypatch, [
        {"specification": "sähkö_yhteinen_(643000000000000000)",
         "readingDate": "2026-02-28", "value": 999.0, "_id": "abc123"},
    ])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path),
                                 "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 0
    assert "999.00 -> 672.00" in result.output
    assert calls["submitted"] == []
    assert len(calls["replaced"]) == 1
    consumption_id, reading = calls["replaced"][0]
    assert consumption_id == "abc123"
    assert reading["value"] == 672.0


def test_import_datahub_skips_matching_value(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    calls = _stub_estateapp(monkeypatch, [
        {"specification": "sähkö_yhteinen_(643000000000000000)",
         "readingDate": "2026-02-28", "value": 672.0, "_id": "abc123"},
    ])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path),
                                 "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 0
    assert calls["submitted"] == []
    assert calls["replaced"] == []
    assert calls["labels"] is None


def test_import_datahub_fails_when_an_insert_is_refused(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    _stub_estateapp(monkeypatch, [])
    monkeypatch.setattr(meters_cmd, "submit_readings",
                        lambda _c, _cid, readings: {"inserted": 0, "refused": len(readings)})

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path),
                                 "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 1
    assert "refused" in result.output


def test_import_datahub_fails_when_a_replace_is_refused(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    _stub_estateapp(monkeypatch, [
        {"specification": "sähkö_yhteinen_(643000000000000000)",
         "readingDate": "2026-02-28", "value": 999.0, "_id": "abc123"},
    ])
    monkeypatch.setattr(meters_cmd, "replace_reading",
                        lambda _c, _cid, _id, _reading: {"inserted": 0, "refused": 1})

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path),
                                 "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 1
    assert "refused" in result.output


def test_import_datahub_fails_verification_when_nothing_was_actually_stored(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    _stub_estateapp(monkeypatch, [])
    monkeypatch.setattr(meters_cmd, "submit_readings",
                        lambda _c, _cid, readings: {"inserted": len(readings), "refused": 0})

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path),
                                 "--condo-id", "condo-1", "--submit"])

    assert result.exit_code == 1
    assert "not stored as expected" in result.output


def test_import_datahub_reports_incomplete_months(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _write_csv(csv_path, _steps("2026-01-31T22:00:00Z", 100, "PT1H", "1,000000"))
    _stub_estateapp(monkeypatch, [])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path), "--condo-id", "condo-1"])

    assert result.exit_code == 0
    assert "2026-02" in result.output
    assert "incomplete" in result.output
    assert "No complete months" in result.output


def test_import_datahub_reports_parse_errors(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("﻿" + HEADER + "\n", encoding="utf-8")
    _stub_estateapp(monkeypatch, [])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path), "--condo-id", "condo-1"])

    assert result.exit_code == 1
    assert "no rows" in result.output


def test_import_datahub_reports_estimated_intervals(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    rows = _steps("2026-01-31T22:00:00Z", 671, "PT1H", "1,000000")
    rows += _steps("2026-02-28T21:00:00Z", 1, "PT1H", "1,000000", quality="QM")
    _write_csv(csv_path, rows)
    _stub_estateapp(monkeypatch, [])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path), "--condo-id", "condo-1"])

    assert result.exit_code == 0
    assert "1 interval(s) not marked OK" in result.output


def test_import_datahub_reports_classification_errors(tmp_path, monkeypatch):
    csv_path = tmp_path / "export.csv"
    _six_hundred_hours(csv_path)
    _stub_estateapp(monkeypatch, [
        {"specification": "sähkö_yhteinen_(643000000000000000)",
         "readingDate": "not-a-date", "value": 1.0, "_id": "abc123"},
    ])

    result = runner.invoke(app, ["meters", "import-datahub", str(csv_path), "--condo-id", "condo-1"])

    assert result.exit_code == 1
    assert "unusable readingDate" in result.output
