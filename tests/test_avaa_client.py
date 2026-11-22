import base64

import httpx
import pytest

from raksa.avaa.client import AvaaClient, AvaaError

PASSWORD = "right-password"
INVOICES = [{"invoice_id": n, "supplier": f"Supplier {n}"} for n in range(5)]
PAGE_SIZE = 2


def _avaa(request: httpx.Request) -> httpx.Response:
    """Answer like Avaa: a form sign-in that sets the XSRF cookie, and an API that needs the cookie in a header."""
    path = request.url.path
    if path == "/login" and request.method == "GET":
        return httpx.Response(200, text='<form><input type="hidden" name="_token" value="form-token"></form>')
    if path == "/login":
        form = dict(pair.split("=") for pair in request.content.decode().split("&"))
        target = "/dashboard" if form["_token"] == "form-token" and form["password"] == PASSWORD else "/login"
        return httpx.Response(302, headers={"Location": target, "Set-Cookie": "XSRF-TOKEN=xsrf%3D; path=/"})
    if path == "/dashboard":
        return httpx.Response(200, text="dashboard")
    if request.headers.get("X-XSRF-TOKEN") != "xsrf=":
        return httpx.Response(401, json={"message": "Unauthenticated."})
    if path == "/api/getCustomerCondos":
        return httpx.Response(200, json={"condos": [{"condo_id": 11841}]})
    if path.startswith("/api/fetchPurchaseInvoices/11841/"):
        offset = int(path.rsplit("/", 1)[1])
        return httpx.Response(200, json={"returnData": INVOICES[offset:offset + PAGE_SIZE]})
    if path == "/api/getInvoiceAttachments/3":
        attachment = {"mimetype": "application/pdf", "data": base64.b64encode(b"%PDF-1.7").decode()}
        return httpx.Response(200, json={"returnData": [attachment]})
    return httpx.Response(404)


def _sign_in(password: str) -> AvaaClient:
    return AvaaClient.sign_in(
        email="board@example.com",
        password=password,
        http_client=httpx.Client(transport=httpx.MockTransport(_avaa)),
    )


def test_avaa_client_reads_every_page():
    client = _sign_in(PASSWORD)

    assert client.list_purchase_invoices() == INVOICES
    assert client.download_attachments(3) == [("application/pdf", b"%PDF-1.7")]


def test_avaa_client_fails_on_a_wrong_password():
    with pytest.raises(AvaaError, match="email or the password"):
        _sign_in("wrong-password")
