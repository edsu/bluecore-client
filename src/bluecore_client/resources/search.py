"""Full text search over Works and Instances."""

from __future__ import annotations

from enum import StrEnum, auto

from bluecore_client.pagination import Pages
from bluecore_client.resources.base import Collection

#: The API's own default search page size.
DEFAULT_SEARCH_LIMIT = 20

#: The API caps search pages at this size.
MAX_SEARCH_LIMIT = 100


class SearchType(StrEnum):
    """Which resource types a search should cover.

    Mirrors ``SearchType`` in ``bluecore_api``'s constants, which is a StrEnum
    of ``auto()`` members -- so the wire values are lowercase.
    """

    HUBS = auto()
    WORKS = auto()
    INSTANCES = auto()
    ALL = auto()


class Search(Collection):
    """Search Blue Core.

    A phrase in double quotes is matched in order, so ``'"le mal joli"'`` is a
    phrase search while ``'le mal joli'`` matches the words separately.
    """

    path = "search"
    collection_key = "results"

    def __call__(
        self,
        q: str = "",
        *,
        type: SearchType | str = SearchType.ALL,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
    ) -> Pages:
        """Run a search, returning a lazily-paged result set.

        An empty query matches everything, which -- since the API has no
        collection endpoints for Works and Instances -- is currently the only
        way to enumerate them short of reading the change document feeds.
        """
        if limit > MAX_SEARCH_LIMIT:
            raise ValueError(
                f"limit must be {MAX_SEARCH_LIMIT} or less; the API rejects more"
            )
        return self._paged(
            limit=limit,
            offset=offset,
            path="/search/",
            params={"q": q, "type": str(type)},
        )
