"""Shared test fixtures.

Tests run against a mocked transport, so nothing here touches a real server.
The Keycloak token endpoint is stubbed alongside the API, since the client
authenticates itself.
"""

import pytest

from bluecore_client import BluecoreClient

API_URL = "http://testserver/api"
KEYCLOAK_URL = "http://testserver/keycloak"
TOKEN_URL = f"{KEYCLOAK_URL}/realms/bluecore/protocol/openid-connect/token"


@pytest.fixture
def token_response(httpx_mock):
    """Stub a successful Keycloak login, reusable across requests."""

    def register(access_token="test-token", expires_in=300, refresh_token="refresh-1"):
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "token_type": "Bearer",
            },
            is_reusable=True,
            # Optional because some tests fail validation client-side and so
            # never authenticate at all.
            is_optional=True,
        )

    return register


@pytest.fixture
def client(token_response):
    """A client wired to the fake host, with credentials configured."""
    token_response()
    with BluecoreClient(
        api_url=API_URL,
        keycloak_url=KEYCLOAK_URL,
        username="developer",
        password="123456",
        load_dotenv=False,
    ) as client:
        yield client
