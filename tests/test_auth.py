"""Keycloak login, caching, refresh, and retry."""

from typing import Any

import pytest

from bluecore_client import BluecoreClient
from bluecore_client.errors import AuthError
from tests.conftest import API_URL, KEYCLOAK_URL, TOKEN_URL


def make_client(**kwargs: Any) -> BluecoreClient:
    defaults: dict[str, Any] = {
        "api_url": API_URL,
        "keycloak_url": KEYCLOAK_URL,
        "username": "developer",
        "password": "123456",
        "load_dotenv": False,
    }
    return BluecoreClient(**{**defaults, **kwargs})


def test_logs_in_and_sends_a_bearer_token(httpx_mock, token_response):
    token_response(access_token="abc123")
    httpx_mock.add_response(url=f"{API_URL}/works/w1", json={"@id": "w1"})

    with make_client() as client:
        client.works.get("w1")

    login, work = httpx_mock.get_requests()
    assert login.url == TOKEN_URL
    assert b"grant_type=password" in login.read()
    assert b"client_id=bluecore_api" in login.read()
    assert work.headers["Authorization"] == "Bearer abc123"


def test_logs_in_once_for_many_requests(httpx_mock, token_response):
    token_response()
    httpx_mock.add_response(
        url=f"{API_URL}/works/w1", json={"@id": "w1"}, is_reusable=True
    )

    with make_client() as client:
        client.works.get("w1")
        client.works.get("w1")
        client.works.get("w1")

    logins = [r for r in httpx_mock.get_requests() if str(r.url) == TOKEN_URL]
    assert len(logins) == 1


def test_refreshes_with_the_refresh_token_when_expired(httpx_mock):
    # expires_in of 0 puts the token past the leeway window immediately.
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        json={"access_token": "first", "refresh_token": "r1", "expires_in": 0},
    )
    httpx_mock.add_response(
        url=f"{API_URL}/works/w1", json={"@id": "w1"}, is_reusable=True
    )
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        json={"access_token": "second", "refresh_token": "r2", "expires_in": 300},
    )

    with make_client() as client:
        client.works.get("w1")
        client.works.get("w1")

    logins = [r for r in httpx_mock.get_requests() if str(r.url) == TOKEN_URL]
    assert len(logins) == 2
    assert b"grant_type=refresh_token" in logins[1].read()
    assert b"refresh_token=r1" in logins[1].read()

    work_requests = [r for r in httpx_mock.get_requests() if "works" in str(r.url)]
    assert work_requests[-1].headers["Authorization"] == "Bearer second"


def test_falls_back_to_a_full_login_when_the_refresh_token_is_dead(httpx_mock):
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        json={"access_token": "first", "refresh_token": "r1", "expires_in": 0},
    )
    httpx_mock.add_response(
        url=f"{API_URL}/works/w1", json={"@id": "w1"}, is_reusable=True
    )
    # The refresh attempt is rejected...
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        status_code=400,
        json={"error": "invalid_grant", "error_description": "Token is not active"},
    )
    # ...so a password grant should follow.
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        json={"access_token": "third", "expires_in": 300},
    )

    with make_client() as client:
        client.works.get("w1")
        client.works.get("w1")

    logins = [r for r in httpx_mock.get_requests() if str(r.url) == TOKEN_URL]
    assert len(logins) == 3
    assert b"grant_type=password" in logins[2].read()


def test_retries_once_when_the_api_rejects_a_token_we_thought_was_good(httpx_mock):
    token_body = {"access_token": "stale", "refresh_token": "r1", "expires_in": 300}
    httpx_mock.add_response(url=TOKEN_URL, method="POST", json=token_body)
    httpx_mock.add_response(url=f"{API_URL}/works/w1", status_code=401, json={})
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        json={"access_token": "fresh", "expires_in": 300},
    )
    httpx_mock.add_response(url=f"{API_URL}/works/w1", json={"@id": "w1"})

    with make_client() as client:
        assert client.works.get("w1") == {"@id": "w1"}

    # httpx re-yields the same Request object on retry, so only the final
    # header state is observable here -- what matters is that it retried once
    # with a freshly fetched token.
    work_requests = [r for r in httpx_mock.get_requests() if "works" in str(r.url)]
    assert len(work_requests) == 2
    assert work_requests[-1].headers["Authorization"] == "Bearer fresh"


def test_a_supplied_token_is_used_as_is(httpx_mock):
    httpx_mock.add_response(url=f"{API_URL}/works/w1", json={"@id": "w1"})

    with make_client(token="handed-to-us", username=None, password=None) as client:
        client.works.get("w1")

    requests = httpx_mock.get_requests()
    assert len(requests) == 1, "should not have contacted Keycloak"
    assert requests[0].headers["Authorization"] == "Bearer handed-to-us"


def test_bad_credentials_explain_themselves(httpx_mock):
    httpx_mock.add_response(
        url=TOKEN_URL,
        method="POST",
        status_code=401,
        json={"error_description": "Invalid user credentials"},
    )

    with (
        make_client() as client,
        pytest.raises(AuthError, match="Check the username and password"),
    ):
        client.works.get("w1")


def test_unreachable_keycloak_says_where_it_looked(httpx_mock):
    import httpx

    httpx_mock.add_exception(httpx.ConnectError("nope"), url=TOKEN_URL)

    with (
        make_client() as client,
        pytest.raises(AuthError, match="Could not reach Keycloak"),
    ):
        client.works.get("w1")


def test_login_returns_the_token(httpx_mock, token_response):
    token_response(access_token="printable")

    with make_client() as client:
        assert client.login() == "printable"
