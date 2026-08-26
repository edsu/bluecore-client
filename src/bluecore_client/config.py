"""Working out where Blue Core is and who we are.

Settings resolve in the order: explicit argument, then environment variable,
then a value derived from ``BLUECORE_URL``. The environment variable names
match the ones ``bluecore_api`` already documents in its README, so an existing
``.env`` works unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import dotenv

#: Keycloak realm the API authenticates against.
REALM = "bluecore"

#: Default Keycloak client id. ``bluecore_api``'s CLI hardcodes this value.
DEFAULT_CLIENT_ID = "bluecore_api"

#: Where to look when nothing is configured. This deployment serves the API at
#: ``/api`` and Keycloak at ``/keycloak``, which is what gets derived below.
#: It's also the host ``bluecore_api``'s own load-profiles command defaults to.
DEFAULT_BLUECORE_URL = "https://dev.bcld.info"


def _join(base: str, path: str) -> str:
    """Join a base URL and path with exactly one slash between them."""
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


@dataclass
class Config:
    """Resolved connection settings."""

    api_url: str
    keycloak_url: str
    username: str | None = None
    password: str | None = None
    client_id: str = DEFAULT_CLIENT_ID
    token: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def token_url(self) -> str:
        """The Keycloak endpoint that issues access tokens."""
        return _join(self.keycloak_url, f"realms/{REALM}/protocol/openid-connect/token")

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)

    def can_authenticate(self) -> bool:
        return bool(self.token) or self.has_credentials


def resolve(
    *,
    api_url: str | None = None,
    bluecore_url: str | None = None,
    keycloak_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    client_id: str | None = None,
    token: str | None = None,
    load_dotenv: bool = True,
) -> Config:
    """Build a :class:`Config`, filling gaps from the environment.

    ``bluecore_url`` is the root of a Blue Core deployment. In production the
    API hangs off it at ``/api``, so that is the default we derive; pass
    ``api_url`` explicitly for a local dev server, which serves the API at the
    bare root of ``localhost:3000``.

    With nothing configured at all, this points at
    :data:`DEFAULT_BLUECORE_URL`, so ``BluecoreClient()`` does something useful
    out of the box.
    """
    if load_dotenv:
        dotenv.load_dotenv()

    env = os.environ.get

    bluecore_url = bluecore_url or env("BLUECORE_URL") or DEFAULT_BLUECORE_URL

    resolved_api = api_url or env("API_URL") or _join(bluecore_url, "api")
    resolved_keycloak = (
        keycloak_url or env("KEYCLOAK_EXTERNAL_URL") or _join(bluecore_url, "keycloak")
    )

    return Config(
        api_url=resolved_api.rstrip("/"),
        keycloak_url=resolved_keycloak.rstrip("/"),
        username=username or env("API_KEYCLOAK_USER"),
        password=password or env("API_KEYCLOAK_PASSWORD"),
        client_id=client_id or env("API_KEYCLOAK_CLIENT_ID") or DEFAULT_CLIENT_ID,
        token=token or env("BLUECORE_TOKEN"),
    )
