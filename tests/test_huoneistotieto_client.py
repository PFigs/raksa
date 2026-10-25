import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from raksa.huoneistotieto.client import HuoneistotietoClient


@pytest.fixture
def mock_transport():
    return MagicMock(spec=httpx.BaseTransport)


@pytest.fixture
def client(mock_transport):
    return HuoneistotietoClient(
        token="test-jwt",
        user_id="123456",
        office_id="131",
        condominium_id="206",
        condominium_number="174",
        http_client=httpx.Client(transport=mock_transport),
    )


def _mock_response(transport, status_code=200, json_data=None):
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("POST", "https://example.com"),
    )
    transport.handle_request.return_value = resp
    return resp


def test_create_folder(client, mock_transport):
    _mock_response(mock_transport, json_data={
        "result": "69d893ef3d28bf7d88304557",
    })

    folder_id = client.create_folder(
        name="year=2024",
        parent_id="69cb705c3d28bf7d882e43ab",
    )

    assert folder_id == "69d893ef3d28bf7d88304557"
    request = mock_transport.handle_request.call_args[0][0]
    assert "/api/services/app/Asiakirja/AddCondominiumFolder" in str(request.url)
    assert "officeId=131" in str(request.url)
    assert "condominiumNumber=174" in str(request.url)
    assert "name=year%3D2024" in str(request.url)
    assert "parentId=69cb705c3d28bf7d882e43ab" in str(request.url)
    assert "level=3" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-jwt"


def test_upload_files(client, mock_transport, tmp_path):
    _mock_response(mock_transport, json_data={"result": True})

    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-fake")
    yaml_file = tmp_path / "invoice.yaml"
    yaml_file.write_text("seller: Test Oy")

    client.upload_files(
        folder_id="69d893ef3d28bf7d88304557",
        files=[pdf, yaml_file],
    )

    request = mock_transport.handle_request.call_args[0][0]
    assert "/uploadfiles" in str(request.url)
    assert "officeId=131" in str(request.url)
    assert "condominiumId=206" in str(request.url)
    assert "userId=123456" in str(request.url)
    assert "folderId=69d893ef3d28bf7d88304557" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-jwt"


def test_list_purchase_invoices(client, mock_transport):
    rows = [{"yhtio": 174, "erapaiva": "18.03.2026", "maksunsaaja": "Tampereen Energia Oy",
             "summa": 3836.5, "liitteet": ["101315_1.pdf"]}]
    documents = [
        {"_id": "a", "type": "OSTOLASKUT", "file": {"fileId": "a", "json": json.dumps(rows)}},
        {"_id": "b", "type": "TALOUSARVIOVERTAILU", "file": {"fileId": "b", "fileName": "taloussuun.html"}},
        {"_id": "c", "type": "TOSITEPAAKIRJA", "file": {"fileId": "c", "json": json.dumps([{"tili": 990}])}},
    ]
    _mock_response(mock_transport, json_data={"result": json.dumps(documents)})

    assert client.list_purchase_invoices(2026) == rows
    request = mock_transport.handle_request.call_args[0][0]
    assert request.url.path == "/api/services/app/Asiakirja/GetAccountingDocuments"
    assert dict(request.url.params) == {"officeId": "131", "condominiumId": "206", "year": "2026"}


def test_create_folder_error(client, mock_transport):
    _mock_response(mock_transport, status_code=500, json_data={"error": "server error"})

    with pytest.raises(httpx.HTTPStatusError):
        client.create_folder(name="year=2024", parent_id="parent123")
