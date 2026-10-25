"""EstateApp consumption meter operations."""
import datetime
import re

from pydantic import BaseModel

from raksa.client import EstateAppClient

VALUE_TOLERANCE = 0.005


class ReadingPlanError(Exception):
    pass


class PlannedReading(BaseModel):
    reading_date: str
    value: float
    action: str
    existing_value: float | None = None
    existing_id: str | None = None


def label_to_key(label: str) -> str:
    """Convert a meter label to its EstateApp key format.

    EstateApp generates keys by lowercasing and replacing spaces with underscores.
    e.g. "AP 01" -> "ap_01"
    """
    return re.sub(r"\s+", "_", label.strip().lower())


def get_meter_definitions(client: EstateAppClient, condo_id: str) -> list[dict]:
    """Get meter definitions from the condominium's property details."""
    data = client._gql("""
    query condominiumById($condominiumId: ID!) {
        condominiumById(condominiumId: $condominiumId) {
            propertyDetails {
                consumptionMeters {
                    key label category multiplier
                }
            }
        }
    }
    """, {"condominiumId": condo_id})
    details = data.get("condominiumById", {}).get("propertyDetails") or {}
    return details.get("consumptionMeters") or []


def get_consumption_summary(client: EstateAppClient, condo_id: str) -> list[dict]:
    """Get yearly consumption summaries per category."""
    data = client._gql("""
    query consumptionMonitoringOfCodominiums($condominiumId: ID!) {
        consumptionMonitoringOfCodominiums(condominiumId: $condominiumId) {
            category
            years { year value }
        }
    }
    """, {"condominiumId": condo_id})
    return data.get("consumptionMonitoringOfCodominiums", [])


def get_consumptions(
    client: EstateAppClient,
    condo_id: str,
    start_date: str,
    end_date: str,
    category: str = "electricity",
) -> list[dict]:
    """Get consumption readings in a date window. Dates are `YYYY-MM-DD`, both inclusive."""
    data = client._gql("""
    query getCondoConsumptions($condominiumId: ID!, $category: String, $startDate: String!, $endDate: String!) {
        getCondoConsumptions(condominiumId: $condominiumId, category: $category, startDate: $startDate, endDate: $endDate) {
            _id specification readingDate value
        }
    }
    """, {
        "condominiumId": condo_id,
        "category": category,
        "startDate": start_date,
        "endDate": end_date,
    })
    return data.get("getCondoConsumptions") or []


def reading_date_to_iso(value) -> str | None:
    """Normalize a `readingDate` (epoch ms or ISO string) to `YYYY-MM-DD`."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if isinstance(value, (int, float)) or text.isdigit():
        moment = datetime.datetime.fromtimestamp(int(float(text)) / 1000, tz=datetime.timezone.utc)
        return moment.date().isoformat()
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def ensure_meters_exist(
    client: EstateAppClient,
    condo_id: str,
    labels: list[str],
    category: str = "electricity",
    multiplier: float = 1.0,
) -> dict[str, str]:
    """Create meters that don't already exist. Returns label -> key mapping."""
    existing = get_meter_definitions(client, condo_id)
    existing_keys = {m["key"] for m in existing}

    new_meters = []
    for label in labels:
        key = label_to_key(label)
        if key not in existing_keys:
            new_meters.append({"label": label, "category": category, "multiplier": multiplier})

    if new_meters:
        client._gql("""
        mutation addConsumptionMeters($condominiumId: ID!, $consumptionMeters: [ConsumptionMeterInput!]!) {
            addConsumptionMeters(condominiumId: $condominiumId, consumptionMeters: $consumptionMeters)
        }
        """, {"condominiumId": condo_id, "consumptionMeters": new_meters})

    return {label: label_to_key(label) for label in labels}


def submit_readings(
    client: EstateAppClient,
    condo_id: str,
    readings: list[dict],
) -> dict:
    """Submit consumption readings.

    Each reading should have: category, specification (meter key), readingDate, value, type.
    Returns {'inserted': int, 'refused': int}.
    """
    data = client._gql("""
    mutation editConsumptionMonitoring($condominiumId: ID!, $consumptionInput: [ConsumptionMonitoringInput!]!) {
        editConsumptionMonitoring(condominiumId: $condominiumId, consumptionInput: $consumptionInput) {
            inserted refused
        }
    }
    """, {"condominiumId": condo_id, "consumptionInput": readings})
    return data["editConsumptionMonitoring"]


def replace_reading(
    client: EstateAppClient,
    condo_id: str,
    consumption_id: str,
    reading: dict,
) -> dict:
    """Overwrite an existing consumption reading with a new value."""
    return submit_readings(client, condo_id, [dict(reading, _id=consumption_id)])


def plan_readings(
    readings: list[tuple[str, float]],
    existing: list[dict],
    replace_needs_id: bool = True,
) -> list[PlannedReading]:
    """Decide per (reading_date, value) pair whether to insert, skip or replace an EstateApp reading."""
    by_date: dict[str, dict] = {}
    for reading in existing:
        iso = reading_date_to_iso(reading.get("readingDate"))
        if iso is None:
            raise ReadingPlanError(f"existing reading has an unusable readingDate: {reading.get('readingDate')!r}")
        if iso in by_date:
            raise ReadingPlanError(f"more than one existing reading for {iso}")
        by_date[iso] = reading

    planned = []
    for reading_date, value in readings:
        current = by_date.get(reading_date)
        if current is None:
            planned.append(PlannedReading(reading_date=reading_date, value=value, action="insert"))
            continue

        existing_value = float(current["value"])
        same = abs(existing_value - value) < VALUE_TOLERANCE
        existing_id = str(current.get("_id")) if current.get("_id") else None
        if not same and existing_id is None and replace_needs_id:
            raise ReadingPlanError(f"existing reading for {reading_date} has no id to replace")
        planned.append(
            PlannedReading(
                reading_date=reading_date,
                value=value,
                action="skip" if same else "replace",
                existing_value=existing_value,
                existing_id=None if same else existing_id,
            )
        )
    return planned
