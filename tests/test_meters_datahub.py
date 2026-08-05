import datetime
from pathlib import Path

import pytest

from raksa.meters.datahub import DatahubError, read_export

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
