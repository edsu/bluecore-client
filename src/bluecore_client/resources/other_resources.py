"""Other resources: everything that isn't a Work, Instance, or Hub."""

from __future__ import annotations

from typing import Any

from bluecore_client.identifiers import extract_uuid
from bluecore_client.pagination import DEFAULT_LIMIT, Pages
from bluecore_client.resources.base import Collection


class OtherResources(Collection):
    """Agents, subjects, and other referenced resources."""

    path = "resources"
    collection_key = "resources"

    def list(self, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> Pages:
        """Page through every other resource.

        Iterate the result for items, or call ``.pages()`` to work a page at a
        time.
        """
        return self._paged(limit=limit, offset=offset)

    def get(self, resource_id: str) -> dict[str, Any]:
        """Fetch one resource by id, or by its Blue Core URI."""
        return self._client.get_json(f"/{self.path}/{self._identify(resource_id)}")

    def _identify(self, value: str) -> str:
        """Accept either an id or a full Blue Core URI."""
        return extract_uuid(value, expected=self.path)

    def find(self, uri: str) -> dict[str, Any]:
        """Look a resource up by its URI."""
        return self._client.get_json(f"/{self.path}/", params={"uri": uri})

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a resource from a JSON-LD graph."""
        return self._client.post_jsonld(f"/{self.path}/", data)

    def update(self, resource_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Replace a resource's graph."""
        return self._client.post_jsonld(
            f"/{self.path}/{self._identify(resource_id)}", data, method="PUT"
        )

    def delete(self, resource_id: str) -> None:
        """Delete a resource."""
        self._client.request("DELETE", f"/{self.path}/{self._identify(resource_id)}")
