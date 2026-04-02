import json

import httpx
import pytest

from raksa.client import EstateAppClient, EstateAppError


def make_client(handler):
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return EstateAppClient(token="test_token", base_url="https://test.example.com", http_client=http_client)


def gql_response(data):
    def handler(request):
        return httpx.Response(200, json={"data": data})
    return handler


def gql_error_response(message):
    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": message}]})
    return handler


def test_list_renovations():
    data = {
        "getCondominiumShareholderRenovationGigs": [
            {
                "_id": "gig1",
                "title": "ILP",
                "status": "UPCOMING",
                "startDate": "1000",
                "endDate": None,
                "description": None,
                "createdAt": None,
                "condominiumId": "c1",
                "shareholderRenovationWork": {
                    "apartmentAddress": "Raitti 1 H20",
                    "premiseName": None,
                    "workDescription": None,
                    "informant": {"_id": "i1", "name": "Test", "email": None, "phone": None},
                    "shareholder": None,
                    "informantIsApartmentOwner": True,
                    "hazardousSubstanceSurveysDone": None,
                    "renovationRequiresFireWork": False,
                    "formSize": None,
                    "workPerfromer": None,
                    "contractors": [],
                    "chosenJobs": {"heatPumpInstallation": True},
                    "collateral": None,
                },
            }
        ]
    }
    client = make_client(gql_response(data))
    results = client.list_renovations("c1")
    assert len(results) == 1
    assert results[0].id == "gig1"
    assert results[0].shareholder_renovation_work.informant.name == "Test"


def test_list_faults():
    data = {
        "faultNotificationsOfCodominiums": [
            {
                "_id": "fn1",
                "condominiumId": "c1",
                "createdAt": "2024-01-01",
                "informantInfo": None,
                "apartment": "A6",
                "faultDescription": "Light broken",
                "streetAddress": "Raitti 1",
                "space": "A6",
                "contactPhone": None,
                "contactName": "Test",
                "additionalInformation": None,
                "completedAt": None,
            }
        ]
    }
    client = make_client(gql_response(data))
    results = client.list_faults("c1")
    assert len(results) == 1
    assert results[0].fault_description == "Light broken"


def test_graphql_error_raises():
    client = make_client(gql_error_response("Not authorized"))
    with pytest.raises(EstateAppError, match="Not authorized"):
        client.list_renovations("c1")


def test_create_renovation_sends_mutation():
    captured = {}
    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"createShareholderRenovationGig": "new_id"}})

    client = make_client(handler)
    gig_input = {"condominiumId": "c1", "type": "shareholderRenovationWork"}
    result = client.create_renovation(gig_input)
    assert result == "new_id"
    assert "createShareholderRenovationGig" in captured["body"]["query"]


def test_create_fault_sends_mutation():
    captured = {}
    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"editFaultNotification": "new_fn_id"}})

    client = make_client(handler)
    fault_input = {"faultDescription": "Broken pipe"}
    result = client.create_fault("c1", fault_input)
    assert result == "new_fn_id"
    assert "editFaultNotification" in captured["body"]["query"]
