import asyncio
import json
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import billing_gateway as gateway
from app.config import settings
from app.services import store_billing as billing


@pytest.fixture
def relay(monkeypatch, tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    credentials = tmp_path / "service.json"
    credentials.write_text(json.dumps({"client_email": "verifier@example.iam.gserviceaccount.com",
        "private_key": key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()).decode()}))
    monkeypatch.setattr(settings, "google_service_account_path", str(credentials))
    monkeypatch.setattr(settings, "google_gateway_token", "test-relay-secret-" * 3)
    calls = []

    def upstream(request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            assertion = parse_qs(request.content.decode())["assertion"][0]
            claims = jwt.decode(assertion, key.public_key(), algorithms=["RS256"], audience="https://oauth2.googleapis.com/token")
            assert claims["scope"] == "https://www.googleapis.com/auth/androidpublisher"
            return httpx.Response(200, json={"access_token": "short-lived-token", "expires_in": 3600})
        if request.url.host == "www.googleapis.com":
            return httpx.Response(200, json={"keys": [{"kid": "test-key"}]})
        assert request.url.host == "androidpublisher.googleapis.com"
        assert request.headers["authorization"] == "Bearer short-lived-token"
        return httpx.Response(200, json={"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE"})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(upstream), **kwargs))
    with TestClient(gateway.app) as client:
        yield client, {"Authorization": "Bearer " + settings.google_gateway_token}, calls


def path(token="opaque%2Ftoken"):
    return f"applications/{settings.google_package_name}/purchases/subscriptionsv2/tokens/{token}"


def test_relay_requires_auth_and_rejects_arbitrary_operations(relay):
    client, headers, calls = relay
    assert client.get("/health").status_code == 200
    assert client.get("/google/certs").status_code == 401
    assert client.post("/google/request", json={"method": "GET", "path": path()}).status_code == 401
    assert client.get("/google/certs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    for value in ["https://attacker.example/", path().replace(settings.google_package_name, "other.app"),
                  path(".."), path("%2E%2E%2Felsewhere"), path() + "?redirect=elsewhere",
                  path().replace("subscriptionsv2", "orders")]:
        assert client.post("/google/request", headers=headers, json={"method": "GET", "path": value}).status_code == 403
    assert client.post("/google/request", headers=headers, json={"method": "GET", "path": path(), "body": {"extra": True}}).status_code == 403
    assert calls == []


def test_relay_limits_authority_calls_caches_oauth_and_serves_google_keys(relay):
    client, headers, calls = relay
    for _ in range(2):
        response = client.post("/google/request", headers=headers, json={"method": "GET", "path": path()})
        assert response.json()["subscriptionState"] == "SUBSCRIPTION_STATE_ACTIVE"
    assert sum(r.url.host == "oauth2.googleapis.com" for r in calls) == 1
    acknowledge = f"applications/{settings.google_package_name}/purchases/subscriptions/monthly/tokens/opaque:acknowledge"
    assert client.post("/google/request", headers=headers, json={"method": "POST", "path": acknowledge, "body": {}}).status_code == 200
    assert calls[-1].method == "POST" and calls[-1].content == b"{}"
    assert client.get("/google/certs", headers=headers).json() == {"keys": [{"kid": "test-key"}]}


def test_relay_upstream_failure_is_generic_and_expired_token_is_refreshed(relay, monkeypatch):
    client, headers, calls = relay
    assert client.post("/google/request", headers=headers, json={"method": "GET", "path": path()}).status_code == 200
    original = gateway.app.state.client.request

    async def denied(*args, **kwargs):
        return httpx.Response(401, json={"error": "expired"})
    monkeypatch.setattr(gateway.app.state.client, "request", denied)
    assert client.post("/google/request", headers=headers, json={"method": "GET", "path": path()}).status_code == 401
    assert gateway.app.state.expires == 0
    monkeypatch.setattr(gateway.app.state.client, "request", original)
    assert client.post("/google/request", headers=headers, json={"method": "GET", "path": path()}).status_code == 200
    assert sum(r.url.host == "oauth2.googleapis.com" for r in calls) == 2

    async def unavailable(*args, **kwargs):
        raise httpx.ConnectError("secret diagnostic that must not be exposed")
    monkeypatch.setattr(gateway.app.state.client, "request", unavailable)
    response = client.post("/google/request", headers=headers, json={"method": "GET", "path": path()})
    assert response.status_code == 502 and response.json() == {"detail": "Google Play unavailable"}


def test_api_uses_https_relay_without_local_google_key(monkeypatch):
    monkeypatch.setattr(settings, "google_gateway_url", "https://relay.example")
    monkeypatch.setattr(settings, "google_gateway_token", "test-relay-secret-" * 3)
    monkeypatch.setattr(settings, "google_service_account_path", "/does/not/exist")
    monkeypatch.setattr(settings, "google_pubsub_audience", "https://relay.example/payments/googleplay/notify")
    monkeypatch.setattr(settings, "google_pubsub_email", "push@example.iam.gserviceaccount.com")
    monkeypatch.setattr(settings, "store_token_secret", Fernet.generate_key().decode())
    billing.configured("googleplay")

    def relay(request):
        assert str(request.url) == "https://relay.example/google/request"
        assert request.headers["authorization"] == "Bearer " + settings.google_gateway_token
        assert json.loads(request.content) == {"method": "GET", "path": path(), "body": None}
        return httpx.Response(200, json={"verified": True})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(relay), **kwargs))
    assert asyncio.run(billing.google_request("GET", path())) == {"verified": True}
    for origin in ["http://relay.example", "https://user:password@relay.example", "https://relay.example/path", "https://relay.example?query=1"]:
        monkeypatch.setattr(settings, "google_gateway_url", origin)
        with pytest.raises(billing.StoreError):
            asyncio.run(billing.google_request("GET", path()))
