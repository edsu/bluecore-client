"""A Python client for the Blue Core API.

Blue Core describes library resources using BIBFRAME, which is RDF. You don't
need to know that: this client hands back plain JSON dictionaries.

    >>> from bluecore_client import BluecoreClient
    >>> client = BluecoreClient()
    >>> work = client.works.get("4403fbce-ba01-5a4e-a8fc-03fc71caf56d")
"""

from bluecore_client.client import BluecoreClient
from bluecore_client.config import Config
from bluecore_client.errors import (
    APIError,
    AuthError,
    BluecoreError,
    ConfigError,
    ConnectionFailed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from bluecore_client.pagination import Page, Pages
from bluecore_client.resources.search import SearchType

__all__ = [
    "APIError",
    "AuthError",
    "BluecoreClient",
    "BluecoreError",
    "Config",
    "ConfigError",
    "ConnectionFailed",
    "NotFound",
    "Page",
    "Pages",
    "PermissionDenied",
    "SearchType",
    "ValidationError",
]
