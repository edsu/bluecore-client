"""Paging over Blue Core collections.

Collection endpoints return an envelope holding the items, a ``total``, and
``links``. Iterating a :class:`Pages` walks the whole collection, fetching each
page as you reach it, so ``for work in client.search("emma")`` just works.

Paging is done with ``limit``/``offset`` arithmetic rather than by following
``links.next``. Those links are absolute URLs built from the server's own
``BLUECORE_URL``, which in development often isn't the host you're talking to.
Counting ourselves also sidesteps the API's ``next`` link appearing on an exact
final page.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

#: Matches the API's own default for collection endpoints.
DEFAULT_LIMIT = 10


@dataclass
class Page:
    """One page of a collection."""

    items: list[Any]
    total: int | None
    limit: int
    offset: int
    links: dict[str, str] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    @property
    def has_more(self) -> bool:
        """Whether another page is worth asking for."""
        if not self.items:
            return False
        if self.total is not None:
            return self.offset + len(self.items) < self.total
        # No total to go on, so a full page means there might be more.
        return len(self.items) >= self.limit


def read_page(
    payload: dict[str, Any],
    *,
    key: str,
    limit: int,
    offset: int,
) -> Page:
    """Pull a :class:`Page` out of a collection response.

    ``key`` is the field holding the items, which varies by endpoint -- the API
    uses ``results`` for search but ``profiles`` and ``resources`` elsewhere.
    """
    items = payload.get(key)
    if items is None:
        # Be forgiving: take the first list-valued field that isn't metadata.
        items = next(
            (
                value
                for name, value in payload.items()
                if isinstance(value, list) and name not in ("links",)
            ),
            [],
        )

    return Page(
        items=list(items),
        total=payload.get("total"),
        limit=limit,
        offset=offset,
        links=payload.get("links") or {},
    )


class Pages:
    """A lazily-paged collection.

    Iterate it for items, or call :meth:`pages` to work a page at a time.
    """

    def __init__(
        self,
        fetch: Callable[[int, int], Page],
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ):
        self._fetch = fetch
        self._limit = limit
        self._offset = offset

    def __iter__(self) -> Iterator[Any]:
        for page in self.pages():
            yield from page.items

    def pages(self) -> Iterator[Page]:
        """Yield each page in turn, fetching as it goes."""
        offset = self._offset
        while True:
            page = self._fetch(self._limit, offset)
            if not page.items:
                return
            yield page
            if not page.has_more:
                return
            offset += len(page.items)

    def first(self) -> Page:
        """Fetch just the first page."""
        return self._fetch(self._limit, self._offset)

    @property
    def total(self) -> int | None:
        """How many items there are, if the API says."""
        return self.first().total

    def __repr__(self) -> str:
        return f"Pages(limit={self._limit}, offset={self._offset})"
