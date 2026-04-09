"""Read Zaptec EV charger usage reports (Excel exports)."""
import datetime
import re
from pathlib import Path

import openpyxl
from pydantic import BaseModel


class ZaptecReading(BaseModel):
    charger: str
    sessions: int
    duration: str
    energy_kwh: float
    period_start: str
    period_end: str


def read_usage_report(file_path: Path) -> list[ZaptecReading]:
    """Parse a Zaptec UsageReport Excel file into readings."""
    wb = openpyxl.load_workbook(file_path, read_only=True)
    ws = wb["UsageReport"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    period_start = None
    period_end = None
    header_row = None
    readings = []

    for i, row in enumerate(rows):
        first = row[0]
        if first == "From Date":
            period_start = str(row[1])
            period_end = str(row[3])
        elif first == "Charger":
            header_row = i
        elif header_row is not None and i > header_row and first is not None:
            readings.append(ZaptecReading(
                charger=str(first).strip(),
                sessions=int(row[1]),
                duration=str(row[2]),
                energy_kwh=float(row[3]),
                period_start=period_start or "",
                period_end=period_end or "",
            ))

    return readings


def read_all_reports(directory: Path) -> list[ZaptecReading]:
    """Read all Zaptec Excel files in a directory."""
    readings = []
    for path in sorted(directory.glob("*.xlsx")):
        readings.extend(read_usage_report(path))
    return readings
