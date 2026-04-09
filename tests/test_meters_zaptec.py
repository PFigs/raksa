from pathlib import Path

import openpyxl
import pytest

from raksa.meters.zaptec import read_usage_report, read_all_reports


def _write_zaptec_xlsx(path: Path, from_date: str, end_date: str, rows: list[tuple]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "UsageReport"
    ws.append(["Installation charge history report", None, None, None, "Generated: 2026-01-01T00:00:00Z"])
    ws.append([None])
    ws.append(["Test Oy", None, None, None, None])
    ws.append(["Street 1", None, None, None, None])
    ws.append(["00100", "Helsinki", None, None, None])
    ws.append([None])
    ws.append(["From Date", from_date, "End Date", end_date, "EET"])
    ws.append([None])
    ws.append(["Charger", "No. Sessions", "Total Duration (hh:mm)", "Total Energy (kWh)", None])
    for row in rows:
        ws.append(list(row) + [None])
    wb.save(path)


def test_read_single_report(tmp_path):
    xlsx = tmp_path / "report.xlsx"
    _write_zaptec_xlsx(xlsx, "2024-01-01", "2024-12-31", [
        ("AP 01", 10, "73:39", 125.57),
        ("AP 10", 6, "48:49", 139.83),
    ])

    readings = read_usage_report(xlsx)
    assert len(readings) == 2
    assert readings[0].charger == "AP 01"
    assert readings[0].energy_kwh == 125.57
    assert readings[0].sessions == 10
    assert readings[0].period_start == "2024-01-01"
    assert readings[0].period_end == "2024-12-31"
    assert readings[1].charger == "AP 10"
    assert readings[1].energy_kwh == 139.83


def test_read_all_reports(tmp_path):
    _write_zaptec_xlsx(tmp_path / "2024.xlsx", "2024-01-01", "2024-12-31", [
        ("AP 01", 10, "73:39", 125.57),
    ])
    _write_zaptec_xlsx(tmp_path / "2025.xlsx", "2025-01-01", "2025-12-31", [
        ("AP 01", 145, "1542:30", 2740.82),
        ("AP 02", 1, "0:01", 0.55),
    ])

    readings = read_all_reports(tmp_path)
    assert len(readings) == 3
    chargers = [r.charger for r in readings]
    assert "AP 01" in chargers
    assert "AP 02" in chargers


def test_read_empty_report(tmp_path):
    xlsx = tmp_path / "empty.xlsx"
    _write_zaptec_xlsx(xlsx, "2024-01-01", "2024-12-31", [])

    readings = read_usage_report(xlsx)
    assert len(readings) == 0
