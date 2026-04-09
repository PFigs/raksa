"""EstateApp consumption meter operations."""
import re

from raksa.client import EstateAppClient


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
