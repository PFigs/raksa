"""Read Fingrid Datahub consumption exports (CSV from the customer portal)."""
import calendar
import csv
import datetime
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from raksa.meters.estateapp import reading_date_to_iso

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
