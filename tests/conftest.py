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


#: Everything config.resolve() consults. Left set, these leak a developer's
#: own deployment into the tests -- so the suite would fail for exactly the
#: people who have configured the tool for real use.
CONFIG_VARIABLES = (
    "BLUECORE_URL",
    "API_URL",
    "KEYCLOAK_EXTERNAL_URL",
    "API_KEYCLOAK_USER",
    "API_KEYCLOAK_PASSWORD",
    "API_KEYCLOAK_CLIENT_ID",
    "BLUECORE_TOKEN",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Run every test against a bare environment.

    The CLI path reaches ``config.resolve()`` with dotenv loading enabled, so a
    ``.env`` in the repo root would be read too. Point it at a file that
    doesn't exist rather than trusting the working directory.
    """
    for name in CONFIG_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "dotenv.load_dotenv", lambda *args, **kwargs: False, raising=False
    )


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
