"""Resource profiles, e.g. Sinopia profiles."""

from __future__ import annotations

import json
from typing import Any

from bluecore_client.identifiers import extract_uuid
from bluecore_client.pagination import DEFAULT_LIMIT, Pages
from bluecore_client.resources.base import Collection


class Profiles(Collection):
    """Profiles describing how a resource should be edited."""

    path = "profiles"
    collection_key = "profiles"

    def list(self, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> Pages:
        """Page through every profile."""
        return self._paged(limit=limit, offset=offset)

    def search(self, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> Pages:
        """Page through profiles via the search index.

        Unlike :meth:`list`, this is the endpoint that carries each profile's
        full ``data``, which is what makes it the useful one for copying
        profiles between deployments.
        """
        return self._paged(limit=limit, offset=offset, path="/search/profile")

    def get(self, profile_uuid: str) -> dict[str, Any]:
        """Fetch one profile by UUID, or by its Blue Core URI."""
        return self._client.get_json(f"/{self.path}/{self._identify(profile_uuid)}")

    def _identify(self, value: str) -> str:
        """Accept either a UUID or a full Blue Core URI."""
        return extract_uuid(value, expected=self.path)

    def find(self, uri: str) -> dict[str, Any]:
        """Look a profile up by its URI."""
        return self._client.get_json(f"/{self.path}/", params={"uri": uri})

    def create(self, data: dict[str, Any] | str) -> dict[str, Any]:
        """Create a profile.

        The API mints a fresh URI and rewrites the profile's resource template
        to match, so the created profile's URI will not be the one you passed
        in.
        """
        return self._client.post_json(f"/{self.path}/", {"data": _as_text(data)})

    def update(self, profile_uuid: str, data: dict[str, Any] | str) -> dict[str, Any]:
        """Replace a profile's data."""
        return self._client.post_json(
            f"/{self.path}/{self._identify(profile_uuid)}",
            {"data": _as_text(data)},
            method="PUT",
        )

    def delete(self, profile_uuid: str) -> None:
        """Delete a profile, along with its versions and classes."""
        self._client.request("DELETE", f"/{self.path}/{self._identify(profile_uuid)}")


def _as_text(data: dict[str, Any] | str) -> str:
    """The profiles API takes ``data`` as a JSON string, not an object."""
    return data if isinstance(data, str) else json.dumps(data)
