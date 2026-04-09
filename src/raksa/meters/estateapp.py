"""EstateApp consumption meter operations."""
from raksa.client import EstateAppClient


def get_existing_meters(client: EstateAppClient, condo_id: str) -> list[dict]:
    """Get all consumption meters for a condominium."""
    data = client._gql("""
    query getLatestConsumptionPerMeter($condominiumId: ID!) {
        getLatestConsumptionPerMeter(condominiumId: $condominiumId) {
            _id category readingDate value specification type
        }
    }
    """, {"condominiumId": condo_id})
    return data.get("getLatestConsumptionPerMeter", [])


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
) -> None:
    """Create meters that don't already exist."""
    existing = get_existing_meters(client, condo_id)
    existing_specs = {m["specification"] for m in existing if m.get("specification")}

    new_meters = [
        {"label": label, "category": category, "multiplier": multiplier}
        for label in labels
        if label not in existing_specs
    ]

    if not new_meters:
        return

    client._gql("""
    mutation addConsumptionMeters($condominiumId: ID!, $consumptionMeters: [ConsumptionMeterInput!]!) {
        addConsumptionMeters(condominiumId: $condominiumId, consumptionMeters: $consumptionMeters)
    }
    """, {"condominiumId": condo_id, "consumptionMeters": new_meters})


def submit_readings(
    client: EstateAppClient,
    condo_id: str,
    readings: list[dict],
) -> dict:
    """Submit consumption readings.

    Each reading should have: category, specification, readingDate, value, type.
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
