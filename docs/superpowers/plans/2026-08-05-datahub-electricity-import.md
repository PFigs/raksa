# Datahub Electricity Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `raksa meters import-datahub <csv>`, which turns a Fingrid Datahub consumption export into monthly EstateApp electricity readings, inserting missing months and replacing values that disagree.

**Architecture:** A new pure module `src/raksa/meters/datahub.py` parses the CSV, sums intervals into Helsinki-time calendar months, drops months the export does not fully cover, and classifies each month against the readings EstateApp already holds. `commands/meters.py` gains one additive command that wires this to the existing `_get_client`, `_get_condo_id`, `ensure_meters_exist`, `get_consumptions` and `submit_readings` helpers. Replacement of a disagreeing reading needs one live probe (Task 3) before its code path is written.

**Tech Stack:** Python 3.14, typer, pydantic, stdlib `csv` and `zoneinfo`, pytest. No new dependencies.

## Global Constraints

- `requires-python = ">=3.14"`. Use stdlib `zoneinfo`, never `pytz`.
- Use `uv` for every Python invocation. Never `pip`.
- Run tests with `uv run python -m pytest tests/ -v`. Live write tests only with `uv run python -m pytest -m submit ...` (`addopts = "-m 'not submit'"` excludes them otherwise).
- Add no dependency to `pyproject.toml`.
- Dry-run is the default for the new command; `--submit` executes. This matches `import-zaptec`, `sync-zaptec` and `import-readings`.
- Change no existing command's arguments, return values or output. Every change is additive.
- Timezone for month boundaries is `Europe/Helsinki`; timestamps in the CSV are UTC.
- Monetary/consumption values are rounded to 2 decimals, matching stored readings.
- The meter is `Sähkö yhteinen (<GSRN>)` -> key `sähkö_yhteinen_(<GSRN>)`. Non-ASCII in the label is intentional; do not transliterate.
- Comments only where they state intent the code cannot. No comments narrating history or mechanics.
- Commit after each task with the repo's `feat:` / `test:` / `docs:` prefixes.

---

### Task 1: CSV parse and monthly aggregation

**Files:**
- Create: `src/raksa/meters/datahub.py`
- Test: `tests/test_meters_datahub.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `DatahubError(Exception)`
  - `MonthlyConsumption(BaseModel)` with fields `year: int`, `month: int`, `consumption_kwh: float`, `estimated_intervals: int`, and property `reading_date -> str` (`"YYYY-MM-DD"`, last day of month)
  - `ExportSummary(BaseModel)` with fields `gsrn: str`, `months: list[MonthlyConsumption]`, `incomplete: list[str]` (each `"YYYY-MM"`, sorted)
  - `read_export(file_path: Path) -> ExportSummary`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_meters_datahub.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_meters_datahub.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'raksa.meters.datahub'`

- [ ] **Step 3: Write the implementation**

Create `src/raksa/meters/datahub.py`:

```python
"""Read Fingrid Datahub consumption exports (CSV from the customer portal)."""
import calendar
import csv
import datetime
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

HELSINKI = ZoneInfo("Europe/Helsinki")
UTC = datetime.timezone.utc

RESOLUTIONS = {
    "PT15M": datetime.timedelta(minutes=15),
    "PT1H": datetime.timedelta(hours=1),
    "P1D": datetime.timedelta(days=1),
}


class DatahubError(Exception):
    pass


class MonthlyConsumption(BaseModel):
    year: int
    month: int
    consumption_kwh: float
    estimated_intervals: int

    @property
    def reading_date(self) -> str:
        last_day = calendar.monthrange(self.year, self.month)[1]
        return f"{self.year}-{self.month:02d}-{last_day:02d}"


class ExportSummary(BaseModel):
    gsrn: str
    months: list[MonthlyConsumption]
    incomplete: list[str]


def _month_bounds_utc(year: int, month: int) -> tuple[datetime.datetime, datetime.datetime]:
    start = datetime.datetime(year, month, 1, tzinfo=HELSINKI)
    end = datetime.datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=HELSINKI)
    return start.astimezone(UTC), end.astimezone(UTC)


def read_export(file_path: Path) -> ExportSummary:
    """Aggregate a Datahub export into complete Helsinki-time calendar months."""
    totals: dict[tuple[int, int], float] = defaultdict(float)
    estimated: dict[tuple[int, int], int] = defaultdict(int)
    covered: dict[tuple[int, int], datetime.timedelta] = defaultdict(datetime.timedelta)
    points: set[str] = set()

    with file_path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            points.add(row["MeteringPointGSRN"])
            if len(points) > 1:
                raise DatahubError(
                    "export covers more than one accounting point; export one at a time"
                )
            unit = row["Unit Type"]
            if unit != "kWh":
                raise DatahubError(f"unexpected unit type: {unit}")
            step = RESOLUTIONS.get(row["Resolution"])
            if step is None:
                raise DatahubError(f"unknown resolution: {row['Resolution']}")

            start = datetime.datetime.fromisoformat(row["Start Time"].replace("Z", "+00:00"))
            local = start.astimezone(HELSINKI)
            key = (local.year, local.month)

            totals[key] += float(row["Quantity"].replace(",", "."))
            if row["Quality"] != "OK":
                estimated[key] += 1
            covered[key] += step

    if not points:
        raise DatahubError(f"no rows in export: {file_path}")

    months = []
    incomplete = []
    for key in sorted(totals):
        month_start, month_end = _month_bounds_utc(*key)
        if covered[key] == month_end - month_start:
            months.append(
                MonthlyConsumption(
                    year=key[0],
                    month=key[1],
                    consumption_kwh=round(totals[key], 2),
                    estimated_intervals=estimated[key],
                )
            )
        else:
            incomplete.append(f"{key[0]}-{key[1]:02d}")

    return ExportSummary(gsrn=points.pop(), months=months, incomplete=incomplete)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_meters_datahub.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/raksa/meters/datahub.py tests/test_meters_datahub.py
git commit -m "feat: parse Datahub consumption exports into monthly totals"
```

---

### Task 2: Classify months against existing EstateApp readings

**Files:**
- Modify: `src/raksa/meters/datahub.py` (append)
- Test: `tests/test_meters_datahub.py` (append)

**Interfaces:**
- Consumes: `MonthlyConsumption` from Task 1; `reading_date_to_iso` from `raksa.meters.estateapp`.
- Produces:
  - `PlannedReading(BaseModel)` with fields `reading_date: str`, `value: float`, `action: str` (one of `"insert"`, `"skip"`, `"replace"`), `existing_value: float | None = None`, `existing_id: str | None = None`
  - `plan_readings(months: list[MonthlyConsumption], existing: list[dict]) -> list[PlannedReading]` where `existing` are raw EstateApp readings (`specification`, `readingDate`, `value`, `_id`) already filtered to the target meter

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_meters_datahub.py`:

```python
from raksa.meters.datahub import MonthlyConsumption, plan_readings


def _month(year: int, month: int, kwh: float) -> MonthlyConsumption:
    return MonthlyConsumption(year=year, month=month, consumption_kwh=kwh, estimated_intervals=0)


def _reading(reading_date: str, value: float, _id: str = "r1") -> dict:
    return {"specification": "sähkö_yhteinen_(643000000000000000)",
            "readingDate": reading_date, "value": value, "_id": _id}


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


def test_existing_readings_outside_the_export_are_ignored():
    planned = plan_readings([_month(2026, 2, 100.0)], [_reading("2019-01-31", 5.0)])

    assert [p.action for p in planned] == ["insert"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_meters_datahub.py -v`
Expected: collection error, `ImportError: cannot import name 'plan_readings' from 'raksa.meters.datahub'`

- [ ] **Step 3: Write the implementation**

Add to the import block at the top of `src/raksa/meters/datahub.py`:

```python
from raksa.meters.estateapp import reading_date_to_iso
```

Then append the rest to the end of the module:

```python
VALUE_TOLERANCE = 0.005


class PlannedReading(BaseModel):
    reading_date: str
    value: float
    action: str
    existing_value: float | None = None
    existing_id: str | None = None


def plan_readings(
    months: list[MonthlyConsumption],
    existing: list[dict],
) -> list[PlannedReading]:
    """Decide per month whether to insert, skip or replace an EstateApp reading."""
    by_date: dict[str, dict] = {}
    for reading in existing:
        iso = reading_date_to_iso(reading.get("readingDate"))
        if iso is not None:
            by_date[iso] = reading

    planned = []
    for month in months:
        current = by_date.get(month.reading_date)
        if current is None:
            planned.append(
                PlannedReading(
                    reading_date=month.reading_date,
                    value=month.consumption_kwh,
                    action="insert",
                )
            )
            continue

        existing_value = float(current["value"])
        same = abs(existing_value - month.consumption_kwh) < VALUE_TOLERANCE
        planned.append(
            PlannedReading(
                reading_date=month.reading_date,
                value=month.consumption_kwh,
                action="skip" if same else "replace",
                existing_value=existing_value,
                existing_id=None if same else str(current.get("_id")),
            )
        )
    return planned
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_meters_datahub.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/raksa/meters/datahub.py tests/test_meters_datahub.py
git commit -m "feat: classify Datahub months against existing EstateApp readings"
```

---

### Task 3: Settle and implement reading replacement

The spec flags this as unverified: `editConsumptionMonitoring` may update in place when the input carries an existing reading's `_id`, or replacement may need `removeConsumptionMonitoring` followed by an insert. This task probes the live API on a throwaway meter, then implements the branch that works.

**Files:**
- Modify: `src/raksa/meters/estateapp.py` (append two functions)
- Test: `tests/test_meters_datahub.py` (append)

**Interfaces:**
- Consumes: `get_consumptions`, `submit_readings`, `ensure_meters_exist`, `label_to_key` from `raksa.meters.estateapp`.
- Produces:
  - `remove_reading(client: EstateAppClient, consumption_id: str) -> bool`
  - `replace_reading(client: EstateAppClient, condo_id: str, consumption_id: str, reading: dict) -> dict` returning `{"inserted": int, "refused": int}`

- [ ] **Step 1: Add the removal helper**

Append to `src/raksa/meters/estateapp.py`:

```python
def remove_reading(client: EstateAppClient, consumption_id: str) -> bool:
    """Delete a single consumption reading."""
    data = client._gql("""
    mutation removeConsumptionMonitoring($consumptionId: ID!) {
        removeConsumptionMonitoring(consumptionId: $consumptionId)
    }
    """, {"consumptionId": consumption_id})
    return bool(data.get("removeConsumptionMonitoring"))
```

- [ ] **Step 2: Probe the live API on a throwaway meter**

Run this exactly. It creates a scratch meter, inserts a reading, attempts an in-place update with the reading's `_id`, reports what happened, then deletes the reading and the meter.

```bash
cd /home/silva/home\ projects/estate_app && uv run python - <<'EOF'
from raksa.commands.meters import _get_client
from raksa.config import resolve_condo_id
from raksa.meters.estateapp import (
    ensure_meters_exist, get_consumptions, label_to_key, remove_reading, submit_readings,
)

LABEL = "Datahub replace probe"
KEY = label_to_key(LABEL)
client, cid = _get_client(), resolve_condo_id()

ensure_meters_exist(client, cid, [LABEL], category="electricity")
base = {"category": "electricity", "specification": KEY,
        "readingDate": "2019-01-31", "value": 111.11, "type": "usual"}
print("insert:", submit_readings(client, cid, [base]))

rows = [r for r in get_consumptions(client, cid, "2019-01-01", "2019-02-01")
        if r["specification"] == KEY]
print("after insert:", [(r["_id"], r["value"]) for r in rows])
probe_id = rows[0]["_id"]

updated = dict(base, value=222.22, _id=probe_id)
print("edit-with-id:", submit_readings(client, cid, [updated]))

rows = [r for r in get_consumptions(client, cid, "2019-01-01", "2019-02-01")
        if r["specification"] == KEY]
print("after edit:", [(r["_id"], r["value"]) for r in rows])
print("VERDICT: update-in-place" if len(rows) == 1 and rows[0]["value"] == 222.22
      else "VERDICT: remove-then-insert")

for r in rows:
    remove_reading(client, r["_id"])
client._gql("""
mutation removeConsumptionMeter($key: String!, $condominiumId: ID!) {
    removeConsumptionMeter(key: $key, condominiumId: $condominiumId)
}
""", {"key": KEY, "condominiumId": cid})
print("cleaned up")
EOF
```

Record the printed VERDICT. If `submit_readings` raises because `ConsumptionMonitoringInput` rejects `_id`, that is also a `remove-then-insert` verdict.

- [ ] **Step 3: Implement `replace_reading` for the verdict**

If VERDICT was **update-in-place**, append to `src/raksa/meters/estateapp.py`:

```python
def replace_reading(
    client: EstateAppClient,
    condo_id: str,
    consumption_id: str,
    reading: dict,
) -> dict:
    """Overwrite an existing consumption reading with a new value."""
    return submit_readings(client, condo_id, [dict(reading, _id=consumption_id)])
```

If VERDICT was **remove-then-insert**, append this instead:

```python
def replace_reading(
    client: EstateAppClient,
    condo_id: str,
    consumption_id: str,
    reading: dict,
) -> dict:
    """Overwrite an existing consumption reading with a new value."""
    remove_reading(client, consumption_id)
    return submit_readings(client, condo_id, [reading])
```

- [ ] **Step 4: Write a test for the chosen path**

Append to `tests/test_meters_datahub.py`. Use the variant matching the verdict; delete the other.

For **update-in-place**:

```python
from raksa.meters import estateapp


def test_replace_reading_updates_in_place(monkeypatch):
    sent = {}
    monkeypatch.setattr(estateapp, "submit_readings",
                        lambda _c, _cid, readings: sent.setdefault("readings", readings)
                        or {"inserted": 1, "refused": 0})

    reading = {"category": "electricity", "specification": "k", "readingDate": "2022-03-31",
               "value": 778.03, "type": "usual"}
    result = estateapp.replace_reading(object(), "condo-1", "abc123", reading)

    assert result == {"inserted": 1, "refused": 0}
    assert sent["readings"] == [dict(reading, _id="abc123")]
```

For **remove-then-insert**:

```python
from raksa.meters import estateapp


def test_replace_reading_removes_then_inserts(monkeypatch):
    calls = []
    monkeypatch.setattr(estateapp, "remove_reading",
                        lambda _c, cid: calls.append(("remove", cid)) or True)
    monkeypatch.setattr(estateapp, "submit_readings",
                        lambda _c, _cid, readings: calls.append(("insert", readings))
                        or {"inserted": 1, "refused": 0})

    reading = {"category": "electricity", "specification": "k", "readingDate": "2022-03-31",
               "value": 778.03, "type": "usual"}
    result = estateapp.replace_reading(object(), "condo-1", "abc123", reading)

    assert result == {"inserted": 1, "refused": 0}
    assert calls == [("remove", "abc123"), ("insert", [reading])]
```

- [ ] **Step 5: Run the tests**

Run: `uv run python -m pytest tests/test_meters_datahub.py -v`
Expected: 16 passed

- [ ] **Step 6: Commit**

```bash
git add src/raksa/meters/estateapp.py tests/test_meters_datahub.py
git commit -m "feat: add consumption reading removal and replacement"
```

---

### Task 4: The `import-datahub` command

**Files:**
- Modify: `src/raksa/commands/meters.py` (imports at lines 1-19; new command after `sync_zaptec`, before `import_zaptec` at line ~249)
- Test: `tests/test_meters_datahub.py` (append)

**Interfaces:**
- Consumes: `read_export`, `plan_readings`, `ExportSummary`, `DatahubError` from Task 1 and 2; `replace_reading` from Task 3; existing `_get_client`, `_get_condo_id`, `ensure_meters_exist`, `get_consumptions`, `submit_readings`, `label_to_key`.
- Produces: `raksa meters import-datahub` CLI command; module-level `DATAHUB_METER_LABEL = "Sähkö yhteinen ({gsrn})"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_meters_datahub.py`:

```python
from typer.testing import CliRunner

from raksa.cli import app
from raksa.commands import meters as meters_cmd

runner = CliRunner()


def _six_hundred_hours(path: Path):
    """A complete February 2026 at 1 kWh/hour."""
    _write_csv(path, _steps("2026-01-31T22:00:00Z", 672, "PT1H", "1,000000"))


def _stub_estateapp(monkeypatch, existing: list[dict]):
    calls = {"submitted": [], "replaced": [], "window": None, "labels": None}

    def _get_consumptions(_client, _condo_id, start_date, end_date, **_kwargs):
        calls["window"] = (start_date, end_date)
        return list(existing)

    def _ensure(_client, _cid, labels, **_kwargs):
        calls["labels"] = list(labels)
        return {label: meters_cmd.label_to_key(label) for label in labels}

    monkeypatch.setattr(meters_cmd, "_get_client", lambda: object())
    monkeypatch.setattr(meters_cmd, "get_consumptions", _get_consumptions)
    monkeypatch.setattr(meters_cmd, "ensure_meters_exist", _ensure)
    monkeypatch.setattr(meters_cmd, "submit_readings",
                        lambda _c, _cid, readings: calls["submitted"].extend(readings)
                        or {"inserted": len(readings), "refused": 0})
    monkeypatch.setattr(meters_cmd, "replace_reading",
                        lambda _c, _cid, cid, reading: calls["replaced"].append((cid, reading))
                        or {"inserted": 1, "refused": 0})
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_meters_datahub.py -v -k import_datahub`
Expected: all 7 fail — typer exits 2 with "No such command 'import-datahub'"

- [ ] **Step 3: Extend the imports in `src/raksa/commands/meters.py`**

The import block currently reads:

```python
from raksa.meters.estateapp import (
    ensure_meters_exist,
    get_consumption_summary,
    get_consumptions,
    label_to_key,
    reading_date_to_iso,
    submit_readings,
)
```

Add `replace_reading` to it (keep alphabetical order), and add below the other meter imports:

```python
from raksa.meters.datahub import DatahubError, plan_readings, read_export
```

Add next to the other module constants:

```python
DATAHUB_METER_LABEL = "Sähkö yhteinen ({gsrn})"
```

- [ ] **Step 4: Write the command**

Insert into `src/raksa/commands/meters.py` after `sync_zaptec` and before the `@app.command("import-zaptec")` decorator:

```python
@app.command("import-datahub")
def import_datahub(
    csv_path: Annotated[Path, typer.Argument(help="Fingrid Datahub consumption export (CSV)")],
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import monthly electricity consumption from a Fingrid Datahub export."""
    cid = _get_condo_id(condo_id)

    try:
        export = read_export(csv_path)
    except DatahubError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if export.incomplete:
        typer.echo(f"Skipping {len(export.incomplete)} incomplete month(s): {', '.join(export.incomplete)}")

    if not export.months:
        typer.echo("No complete months in export.")
        return

    label = DATAHUB_METER_LABEL.format(gsrn=export.gsrn)
    key = label_to_key(label)
    client = _get_client()

    existing = [
        reading
        for reading in get_consumptions(
            client,
            cid,
            start_date=f"{export.months[0].year}-{export.months[0].month:02d}-01",
            end_date=export.months[-1].reading_date,
        )
        if reading.get("specification") == key
    ]
    planned = plan_readings(export.months, existing)

    typer.echo(f"\n{label} -> {key}\n")
    for entry, month in zip(planned, export.months):
        detail = ""
        if entry.action == "replace":
            detail = f"  (was {entry.existing_value:.2f} -> {entry.value:.2f})"
        if month.estimated_intervals:
            detail += f"  [{month.estimated_intervals} interval(s) not marked OK]"
        typer.echo(f"  {entry.reading_date}  {entry.value:>10.2f} kWh  {entry.action}{detail}")

    inserts = [entry for entry in planned if entry.action == "insert"]
    replacements = [entry for entry in planned if entry.action == "replace"]
    skips = [entry for entry in planned if entry.action == "skip"]
    typer.echo(f"\n{len(inserts)} insert, {len(skips)} skip, {len(replacements)} replace")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    if not inserts and not replacements:
        typer.echo("Nothing to submit.")
        return

    typer.echo("\nEnsuring meter exists...")
    ensure_meters_exist(client, cid, [label], category="electricity")

    def _reading(entry) -> dict:
        return {
            "category": "electricity",
            "specification": key,
            "readingDate": entry.reading_date,
            "value": entry.value,
            "type": "usual",
        }

    refused = 0
    for entry in replacements:
        typer.echo(f"Replacing {entry.reading_date}: {entry.existing_value:.2f} -> {entry.value:.2f}")
        result = replace_reading(client, cid, entry.existing_id, _reading(entry))
        refused += int(result.get("refused", 0))

    if inserts:
        typer.echo(f"Submitting {len(inserts)} reading(s)...")
        result = submit_readings(client, cid, [_reading(entry) for entry in inserts])
        refused += int(result.get("refused", 0))
        typer.echo(f"  inserted={result.get('inserted', 0)}, refused={result.get('refused', 0)}")

    if refused:
        typer.echo("Error: some readings were refused by EstateApp.", err=True)
        raise typer.Exit(1)
```

The `zip(planned, export.months)` pairing is safe because `plan_readings` returns one entry per month in order.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_meters_datahub.py -v`
Expected: 23 passed

- [ ] **Step 6: Run the whole suite for regressions**

Run: `uv run python -m pytest tests/ -v`
Expected: all pass, 3 deselected (the `submit`-marked live tests)

- [ ] **Step 7: Commit**

```bash
git add src/raksa/commands/meters.py tests/test_meters_datahub.py
git commit -m "feat: add raksa meters import-datahub"
```

---

### Task 5: Verify against the real export and document the command

**Files:**
- Modify: `CLAUDE.md` (the `## CLI commands` block, and the `meters/` entry under `## Project structure`)

**Interfaces:**
- Consumes: the finished command from Task 4.
- Produces: nothing further.

- [ ] **Step 1: Dry-run the real six-year export**

Run: `uv run raksa meters import-datahub ~/Downloads/consumption_sale.csv`

Expected, from the analysis recorded in the spec:
- `Skipping 2 incomplete month(s): 2020-08, 2026-08`
- `8 insert, 61 skip, 2 replace`
- the two replaces are `2022-03-31  (was 822.92 -> 778.03)` and `2022-04-30  (was 703.81 -> 611.05)`
- inserts are 2020-09, 2020-10 and 2026-02 through 2026-07

If the counts differ from this, stop and report rather than submitting — it means the aggregation or classification disagrees with the verified analysis.

- [ ] **Step 2: Submit**

Run: `uv run raksa meters import-datahub ~/Downloads/consumption_sale.csv --submit`
Expected: two replacements logged, `inserted=8, refused=0`, exit 0.

- [ ] **Step 3: Verify the result through the API**

```bash
cd /home/silva/home\ projects/estate_app && uv run python - <<'EOF'
from raksa.commands.meters import _get_client
from raksa.config import resolve_condo_id
from raksa.meters.estateapp import get_consumptions, reading_date_to_iso

KEY = "sähkö_yhteinen_(643000000000000000)"
rows = [r for r in get_consumptions(_get_client(), resolve_condo_id(), "2020-01-01", "2026-12-31")
        if r["specification"] == KEY]
by_month = {}
for r in rows:
    by_month.setdefault(reading_date_to_iso(r["readingDate"])[:7], []).append(r["value"])
print("months:", len(by_month))
print("duplicated months:", {m: v for m, v in by_month.items() if len(v) > 1})
for m in ["2020-09", "2020-10", "2022-03", "2022-04", "2026-07"]:
    print(m, by_month.get(m))
EOF
```

Expected: 71 months, no duplicated months, `2020-09 [541.16]`, `2020-10 [617.77]`, `2022-03 [778.03]`, `2022-04 [611.05]`, `2026-07 [898.37]`.

A duplicated month means replacement inserted alongside the old reading instead of overwriting it — fix `replace_reading` before continuing.

- [ ] **Step 4: Re-run the dry-run to confirm idempotency**

Run: `uv run raksa meters import-datahub ~/Downloads/consumption_sale.csv`
Expected: `0 insert, 71 skip, 0 replace`

- [ ] **Step 5: Update `CLAUDE.md`**

In `## Project structure`, under `meters/`, add:

```
    datahub.py      - Read Fingrid Datahub consumption exports (CSV)
```

In `## CLI commands`, add after the `import-zaptec` line:

```
raksa meters import-datahub <csv> [--submit]   # import monthly electricity from a Datahub export
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document import-datahub command"
```

---

## Notes for the implementer

- Datahub exports for the same accounting point's sales and grid agreements are byte-identical; either file is the same input. Nothing in the code needs to distinguish them.
- The meter key contains non-ASCII characters (`sähkö_yhteinen_(...)`) because EstateApp derives keys by lowercasing the label and replacing whitespace. That is the real key in the live condominium; do not "fix" it.
- `get_consumptions` was added for the Zaptec sync in the same release. It takes `start_date` and `end_date` as `YYYY-MM-DD` strings, both inclusive, and returns `readingDate` as epoch-millisecond strings — hence `reading_date_to_iso`. Its original selection set was `specification readingDate value` with no `_id`, which the replace path needs; `_id` was added to the query during Task 2's fix round.
- Getting the export is manual by design: log in to `oma.datahub.fi` as a company user, open the accounting point's Energy Reporting, pick a range, click Download information. The portal's internal API is deliberately not used; the spec explains why.
- Timezone trap: subtracting two `zoneinfo`-aware datetimes in the same zone gives the wall-clock difference, not elapsed time. `datetime(2026,4,1,tz=HELSINKI) - datetime(2026,3,1,tz=HELSINKI)` is 744 hours, while the month really spans 743. `_month_bounds_utc` sidesteps this by converting both bounds to UTC and comparing against UTC row timestamps; keep it that way, and never compute month length by subtracting local datetimes.
- Test fixtures are written into `tmp_path` by a helper rather than committed, following `tests/test_meters_zaptec.py`. The spec says "committed CSV fixture"; the repo convention wins.
