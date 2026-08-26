"""Shared pieces for the endpoint groups hanging off a client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bluecore_client import formats
from bluecore_client.identifiers import extract_uuid
from bluecore_client.pagination import DEFAULT_LIMIT, Page, Pages, read_page

if TYPE_CHECKING:
    from bluecore_client.client import BluecoreClient


class Endpoint:
    """A group of related API operations, reached as ``client.<name>``."""

    def __init__(self, client: BluecoreClient):
        self._client = client

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._client.api_url}>"


class Collection(Endpoint):
    """An endpoint whose collection is paged with ``limit`` and ``offset``."""

    #: URL path segment, e.g. ``profiles``.
    path: str = ""

    #: Field in the response envelope holding the items. The API isn't
    #: consistent about this -- search says ``results`` while profiles and
    #: resources name themselves.
    collection_key: str = "results"

    def _paged(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        path: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Pages:
        """Build a lazily-paged view of a collection."""
        base = dict(params or {})
        target = path or f"/{self.path}/"

        def fetch(page_limit: int, page_offset: int) -> Page:
            payload = self._client.get_json(
                target,
                params={**base, "limit": page_limit, "offset": page_offset},
            )
            return read_page(
                payload,
                key=self.collection_key,
                limit=page_limit,
                offset=page_offset,
            )

        return Pages(fetch, limit=limit, offset=offset)


class ResourceEndpoint(Endpoint):
    """A BIBFRAME resource type: Works, Instances, or Hubs.

    These three share an identical operation set. Note the API has no
    collection endpoint for them yet -- there is no ``GET /works/`` -- so there
    is no ``list()`` here. Use :meth:`BluecoreClient.search` to find resources,
    or the change document feeds to enumerate them.
    """

    path: str = ""
    label: str = "Resource"

    def get(
        self,
        uuid: str,
        *,
        format: str | None = None,
        expand: bool = False,
    ) -> Any:
        """Fetch one resource by UUID, or by its Blue Core URI.

        Returns a JSON-LD dictionary by default. Pass ``format`` for another
        serialization -- ``"ttl"``, ``"rdf"``, ``"nt"``, ``"vnd.sinopia.json"``
        -- and non-JSON formats come back as text.

        ``expand`` asks the API to include referenced resources in the graph.
        """
        return self._client.fetch(
            f"/{self.path}/{self._identify(uuid)}",
            format=format,
            params={"expand": "true"} if expand else None,
        )

    def _identify(self, value: str) -> str:
        """Accept either a UUID or a full Blue Core URI."""
        return extract_uuid(value, expected=self.path)

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a resource from a JSON-LD graph.

        ``data`` is sent as raw JSON-LD, so pass the graph itself rather than
        wrapping it.
        """
        return self._client.post_jsonld(f"/{self.path}/", data)

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Replace a resource's graph, by UUID or Blue Core URI."""
        return self._client.post_jsonld(
            f"/{self.path}/{self._identify(uuid)}", data, method="PUT"
        )

    def delete(self, uuid: str) -> None:
        """Delete a resource, by UUID or Blue Core URI."""
        self._client.request("DELETE", f"/{self.path}/{self._identify(uuid)}")

    def embedding(self, uuid: str) -> Any:
        """Fetch the stored vector embedding for a resource."""
        return self._client.get_json(f"/{self.path}/{self._identify(uuid)}/embeddings")

    def create_embedding(self, uuid: str) -> Any:
        """Generate and store a vector embedding for a resource."""
        return self._client.request(
            "POST", f"/{self.path}/{self._identify(uuid)}/embeddings"
        ).json()


def json_format(format: str | None) -> formats.Format:
    """Resolve a format key, defaulting to JSON-LD."""
    return formats.lookup(format)
