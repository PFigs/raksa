import json

import httpx

from raksa.client import EstateAppClient
from raksa.meters.estateapp import submit_readings


def test_submit_readings_sends_the_meter_id_of_each_reading():
    submitted = []

    def handler(request):
        body = json.loads(request.content)
        if "condominiumById" in body["query"]:
            meters = [
                {"_id": "id-ap-01", "key": "ap_01", "label": "AP 01", "category": "electricity", "multiplier": 1},
                {"_id": "id-ap-10", "key": "ap_10", "label": "AP 10", "category": "electricity", "multiplier": 1},
            ]
            return httpx.Response(200, json={"data": {"condominiumById": {"propertyDetails": {"consumptionMeters": meters}}}})
        submitted.extend(body["variables"]["consumptionInput"])
        return httpx.Response(200, json={"data": {"editConsumptionMonitoring": {"inserted": 2, "refused": 0}}})

    client = EstateAppClient(
        token="test_token",
        base_url="https://test.example.com",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    readings = [
        {"category": "electricity", "specification": "ap_10", "readingDate": "2026-11-06", "value": 26.811, "type": "usual"},
        {"category": "electricity", "specification": "ap_01", "readingDate": "2026-11-06", "value": 15.927, "type": "usual"},
    ]

    submit_readings(client, "condo-1", readings)

    assert [(r["specification"], r["meterId"]) for r in submitted] == [("ap_10", "id-ap-10"), ("ap_01", "id-ap-01")]
