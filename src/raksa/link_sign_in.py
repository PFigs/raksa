"""Get an EstateApp login token through the EstateApp link on the Huoneistotieto board page."""
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from raksa.client import EstateAppClient
from raksa.config import HuoneistotietoLogin
from raksa.huoneistotieto.client import BASE_URL as HT_BASE_URL


class LinkSignInError(Exception):
    pass


def _huoneistotieto_token(login: HuoneistotietoLogin, http: httpx.Client) -> str:
    response = http.post(
        f"{HT_BASE_URL}/api/TokenAuth/Authenticate",
        json={
            "userNameOrEmailAddress": login.email,
            "password": login.password,
            "rememberClient": False,
        },
    )
    if not response.is_success:
        raise LinkSignInError(f"Huoneistotieto login failed with HTTP {response.status_code}")
    return response.json()["result"]["accessToken"]


def _estateapp_link(login: HuoneistotietoLogin, ht_token: str, http: httpx.Client) -> str:
    response = http.get(
        f"{HT_BASE_URL}/api/services/app/Yhtio/GetAlykasPTSUrl",
        params={
            "officeId": login.office_id,
            "condominiumId": login.condominium_id,
        },
        headers={"Authorization": f"Bearer {ht_token}"},
    )
    if not response.is_success:
        raise LinkSignInError(f"Huoneistotieto returned HTTP {response.status_code} for the EstateApp link")
    return response.json()["result"]


def sign_in_through_huoneistotieto(
    login: HuoneistotietoLogin,
    base_url: str,
    http_client: httpx.Client | None = None,
) -> str:
    """Log in to Huoneistotieto, ask it for an EstateApp sign-in link, and exchange the link for a login token."""
    http = http_client or httpx.Client(timeout=60.0)
    ht_token = _huoneistotieto_token(login=login, http=http)
    link = urlparse(_estateapp_link(login=login, ht_token=ht_token, http=http))
    prefix = "/link-sign-in/"
    if not link.path.startswith(prefix):
        raise LinkSignInError("Huoneistotieto returned a link that is not an EstateApp sign-in link")
    # The EstateApp page passes the rest of the path and the source query value to signInWithLink.
    data = EstateAppClient(token="", base_url=base_url, http_client=http)._gql(
        """
        query signInWithLink($encryptedData: String!, $source: String) {
            signInWithLink(encryptedData: $encryptedData, source: $source) { token userId }
        }
        """,
        {
            "encryptedData": unquote(link.path[len(prefix):]),
            "source": parse_qs(link.query).get("source", [None])[0],
        },
    )
    token = (data.get("signInWithLink") or {}).get("token")
    if not token:
        raise LinkSignInError("EstateApp returned no token for the sign-in link")
    return token
