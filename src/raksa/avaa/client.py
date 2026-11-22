"""Avaa (app.avaa.io) client. Avaa has no public API; this uses the endpoints of its web page."""
import base64
import re
from urllib.parse import unquote

import httpx

BASE_URL = "https://app.avaa.io"


class AvaaError(Exception):
    pass


class AvaaClient:
    def __init__(self, http_client: httpx.Client, condo_id: int) -> None:
        self._http = http_client
        self._condo_id = condo_id

    @classmethod
    def sign_in(cls, email: str, password: str, http_client: httpx.Client | None = None) -> "AvaaClient":
        """Sign in through the login form, and find the one housing company of the account."""
        http = http_client or httpx.Client(timeout=120.0)
        token = re.search(r'name="_token" value="([^"]+)"', http.get(f"{BASE_URL}/login").text)
        if not token:
            raise AvaaError("the Avaa login page has no form token")
        response = http.post(
            f"{BASE_URL}/login",
            data={"_token": token[1], "email": email, "password": password},
            follow_redirects=True,
        )
        response.raise_for_status()
        if response.url.path == "/login":
            raise AvaaError("Avaa refused the email or the password")

        condos = cls(http_client=http, condo_id=0)._get("getCustomerCondos")["condos"]
        if len(condos) != 1:
            raise AvaaError(f"expected one housing company in the Avaa account, found {len(condos)}")
        return cls(http_client=http, condo_id=condos[0]["condo_id"])

    def _get(self, path: str) -> dict:
        # The API answers 401 unless the request carries the XSRF cookie in a header, as the web page does.
        response = self._http.get(
            f"{BASE_URL}/api/{path}",
            headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": unquote(self._http.cookies.get("XSRF-TOKEN", "")),
            },
        )
        response.raise_for_status()
        return response.json()

    def list_purchase_invoices(self) -> list[dict]:
        """List the purchase invoices of the housing company, newest first."""
        invoices: list[dict] = []
        # The last part of the path is the number of invoices to skip.
        while page := self._get(f"fetchPurchaseInvoices/{self._condo_id}/{len(invoices)}")["returnData"]:
            invoices.extend(page)
        return invoices

    def download_attachments(self, invoice_id: int) -> list[tuple[str, bytes]]:
        """Download the attachments of a purchase invoice. Returns the content type and content of each."""
        attachments = self._get(f"getInvoiceAttachments/{invoice_id}")["returnData"]
        return [(attachment["mimetype"], base64.b64decode(attachment["data"])) for attachment in attachments]
