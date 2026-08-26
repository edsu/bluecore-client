"""Keycloak authentication.

The client owns the whole token lifecycle: it logs in on first use, caches the
access token, refreshes it before it expires, and retries once if the API
rejects it anyway. Callers never handle a token unless they want to.
"""

from __future__ import annotations

import time
from collections.abc import Generator

import httpx

from bluecore_client.config import Config
from bluecore_client.errors import AuthError

#: Refresh this many seconds before the token actually expires, so a token
#: never dies in flight on a slow request.
EXPIRY_LEEWAY = 30.0


class KeycloakAuth(httpx.Auth):
    """Attaches a bearer token, keeping it fresh.

    Not safe to share across threads; give each thread its own client.
    """

    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.BaseTransport | None = None,
        event_hooks: dict[str, list] | None = None,
    ):
        self._config = config
        self._transport = transport
        self._event_hooks = event_hooks or {}
        self._access_token: str | None = config.token
        self._refresh_token: str | None = None
        # A caller-supplied token has no known expiry, so treat it as valid
        # until the API says otherwise.
        self._expires_at: float | None = None

    def sync_auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token()}"
        response = yield request

        if response.status_code != 401:
            return

        # The token was rejected despite looking valid to us -- the server may
        # have restarted or revoked it. Throw it away and try once more.
        if not self._config.has_credentials:
            return

        response.read()
        self._forget()
        request.headers["Authorization"] = f"Bearer {self._token()}"
        yield request

    def _token(self) -> str:
        """Return a usable access token, fetching or refreshing as needed."""
        if self._access_token and not self._expired():
            return self._access_token

        if self._refresh_token:
            try:
                return self._grant(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    }
                )
            except AuthError:
                # Refresh tokens expire too; fall back to a full login.
                self._refresh_token = None

        if not self._config.has_credentials:
            raise AuthError(
                "Access token is expired and no credentials are configured to "
                "get a new one. Pass username and password, or set "
                "API_KEYCLOAK_USER and API_KEYCLOAK_PASSWORD."
            )

        return self._grant(
            {
                "grant_type": "password",
                "username": self._config.username,
                "password": self._config.password,
            }
        )

    def _expired(self) -> bool:
        if self._expires_at is None:
            return False
        return time.monotonic() >= self._expires_at

    def _forget(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._expires_at = None

    def _grant(self, data: dict[str, str | None]) -> str:
        """Run a Keycloak grant and cache what comes back."""
        payload = {"client_id": self._config.client_id, **data}

        # A dedicated client, so token requests don't recurse through this auth.
        with httpx.Client(
            transport=self._transport, timeout=30.0, event_hooks=self._event_hooks
        ) as client:
            try:
                response = client.post(self._config.token_url, data=payload)
            except httpx.HTTPError as error:
                raise AuthError(
                    f"Could not reach Keycloak at {self._config.token_url}: {error}"
                ) from error

        if response.is_error:
            raise AuthError(_describe(response, payload["grant_type"]))

        body = response.json()
        token = body.get("access_token")
        if not token:
            raise AuthError(
                f"Keycloak returned no access_token from {self._config.token_url}"
            )

        self._access_token = token
        self._refresh_token = body.get("refresh_token")
        # Compare against None, not falsiness: an expires_in of 0 means the
        # token is already dead, which is very different from absent.
        expires_in = body.get("expires_in")
        self._expires_at = (
            time.monotonic() + float(expires_in) - EXPIRY_LEEWAY
            if expires_in is not None
            else None
        )
        return token

    def login(self) -> str:
        """Authenticate now and return the access token.

        Useful on its own -- this is what ``bluecore auth token`` prints.
        """
        return self._token()


def _describe(response: httpx.Response, grant_type: str | None) -> str:
    """Turn a Keycloak error response into something worth reading."""
    try:
        body = response.json()
        detail = body.get("error_description") or body.get("error") or ""
    except ValueError:
        detail = response.text.strip()

    hint = ""
    if response.status_code == 401 and grant_type == "password":
        hint = " Check the username and password."
    elif response.status_code == 400 and "client" in detail.lower():
        hint = " Check the Keycloak client id."

    return f"Keycloak rejected the login ({response.status_code}): {detail}.{hint}"
