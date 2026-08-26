"""Activity Streams change document feeds.

These are the reliable way to enumerate or harvest everything in a Blue Core
instance, since they page over an append-only history rather than a shifting
offset window.

The paging here is unlike the rest of the API: instead of ``limit``/``offset``,
a feed points at numbered pages which are walked by path.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from bluecore_client.errors import NotFound
from bluecore_client.resources.base import Endpoint


class ChangeDocuments(Endpoint):
    """Change feeds for Works and Instances."""

    def feed(self, kind: str = "works") -> dict[str, Any]:
        """Fetch the feed's collection document.

        This is the entry point: it reports how many pages exist and links to
        the first and last of them.
        """
        return self._client.get_json(f"/change_documents/{_kind(kind)}/feed")

    def page(self, page_id: int | str, kind: str = "works") -> dict[str, Any]:
        """Fetch one numbered page of a feed."""
        return self._client.get_json(f"/change_documents/{_kind(kind)}/page/{page_id}")

    def pages(self, kind: str = "works", *, start: int = 1) -> Iterator[dict[str, Any]]:
        """Walk a feed's pages, oldest first, stopping when they run out."""
        kind = _kind(kind)
        page_id = start
        while True:
            try:
                page = self.page(page_id, kind)
            except NotFound:
                # Running off the end of the feed is how we learn it ended.
                return
            if not page.get("orderedItems"):
                return
            yield page
            page_id += 1

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate every change activity for Works."""
        return self.activities()

    def activities(
        self, kind: str = "works", *, start: int = 1
    ) -> Iterator[dict[str, Any]]:
        """Yield individual change activities across every page."""
        for page in self.pages(kind, start=start):
            yield from page.get("orderedItems", [])


def _kind(kind: str) -> str:
    """Normalize and check the feed name."""
    normalized = kind.lower().rstrip("s") + "s"
    if normalized not in ("works", "instances"):
        raise ValueError(
            f"Unknown change document feed {kind!r}. Choose 'works' or 'instances'."
        )
    return normalized
