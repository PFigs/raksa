"""Read consumption reading YAML files (common format)."""
from pathlib import Path

import yaml
from pydantic import BaseModel


class CostEntry(BaseModel):
    provider: str
    amount_eur: float
    type: str
    invoice_number: str
    source_file: str


class ConsumptionReading(BaseModel):
    meter_id: str
    meter_label: str
    utility: str
    unit: str
    period_start: str
    period_end: str
    reading_date: str
    consumption: float
    costs: list[CostEntry] = []


def load_readings(readings_dir: Path) -> list[ConsumptionReading]:
    """Load all consumption reading YAML files from a directory."""
    readings = []
    for path in sorted(readings_dir.rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw is None:
            continue
        readings.append(ConsumptionReading.model_validate(raw))
    return readings


def load_readings_by_utility(readings_dir: Path) -> dict[str, list[ConsumptionReading]]:
    """Group readings by utility type."""
    by_utility: dict[str, list[ConsumptionReading]] = {}
    for reading in load_readings(readings_dir):
        by_utility.setdefault(reading.utility, []).append(reading)
    return by_utility
