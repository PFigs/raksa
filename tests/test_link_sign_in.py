import json

import httpx

from raksa.config import HuoneistotietoLogin
from raksa.link_sign_in import sign_in_through_huoneistotieto


def test_sign_in_through_huoneistotieto_returns_the_estateapp_token():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/TokenAuth/Authenticate":
            seen["login"] = json.loads(request.content)
            return httpx.Response(200, json={"result": {"accessToken": "ht-token"}, "success": True})
        if request.url.path == "/api/services/app/Yhtio/GetAlykasPTSUrl":
            seen["link_auth"] = request.headers["authorization"]
            seen["link_params"] = dict(request.url.params)
            return httpx.Response(
                200,
                json={"result": "https://app.estateapp.com/link-sign-in/abc/def%2Bg?source=htf", "success": True},
            )
        if request.url.path == "/graphql":
            seen["sign_in"] = json.loads(request.content)["variables"]
            return httpx.Response(200, json={"data": {"signInWithLink": {"token": "ea-token", "userId": "u1"}}})
        return httpx.Response(404)

    token = sign_in_through_huoneistotieto(
        login=HuoneistotietoLogin(email="user@example.com", password="secret", office_id="131", condominium_id="206"),
        base_url="https://app.estateapp.com",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert token == "ea-token"
    assert seen["login"]["userNameOrEmailAddress"] == "user@example.com"
    assert seen["login"]["password"] == "secret"
    assert seen["login"]["application"] == "app"
    assert seen["link_auth"] == "Bearer ht-token"
    assert seen["link_params"] == {"officeId": "131", "condominiumId": "206"}
    assert seen["sign_in"] == {"encryptedData": "abc/def+g", "source": "htf"}
