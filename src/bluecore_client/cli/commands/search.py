"""Search commands."""

from __future__ import annotations

from typing import Annotated

import typer

from bluecore_client import SearchType
from bluecore_client.cli import paging, ui
from bluecore_client.cli.context import client, die
from bluecore_client.errors import BluecoreError

#: How many results to show before stopping, when no limit is given.
DEFAULT_SHOW = 20


def register(app: typer.Typer) -> None:
    """Attach ``bluecore search`` as a top-level command."""

    @app.command("search")
    def search(
        query: Annotated[str, typer.Argument(help="What to search for")] = "",
        type: Annotated[
            SearchType,
            typer.Option("--type", "-t", help="Restrict to hubs, works, or instances"),
        ] = SearchType.ALL,
        limit: Annotated[
            int, typer.Option("--limit", "-n", help="Maximum results to show")
        ] = DEFAULT_SHOW,
        all: Annotated[
            bool, typer.Option("--all", help="Fetch every page, ignoring --limit")
        ] = False,
    ) -> None:
        """Search Blue Core.

        Quote a phrase to match the words in order:

            bluecore search '"le mal joli"'

        Results stream in as each page arrives, so --all starts printing
        immediately rather than after everything has been fetched.
        """
        size = paging.page_size(limit, all=all, cap=paging.SEARCH_MAX_PAGE)
        records = ui.UriRecords()

        try:
            paging.stream(
                client().search(query, type=type, limit=size),
                all=all,
                limit=limit,
                emit=lambda item: records.add(_uri_of(item), _title_of(item)),
                noun="result",
                json_key="results",
                spinner=f"Searching for {query!r}" if query else "Listing",
            )
        except BluecoreError as error:
            die(error)


def _uri_of(item: dict) -> str:
    """The resource's URI, falling back to whatever identifier is present."""
    return str(item.get("uri") or item.get("@id") or item.get("uuid") or "")


def _title_of(item: dict) -> str:
    """Dig the human-readable title out of the BIBFRAME structure.

    In BIBFRAME the title is nested at ``title[0].mainTitle`` rather than being
    a plain string, and compaction means any level might be a bare value
    instead of a list. This is exactly the kind of thing people shouldn't have
    to write, and the reason a friendlier accessor is worth adding later.
    """
    # Collection endpoints wrap the graph under "data"; a bare graph is itself.
    embedded = item.get("data")
    data = embedded if isinstance(embedded, dict) else item
    titles = data.get("title") or data.get("mainTitle") or ""

    if isinstance(titles, str):
        return titles
    if isinstance(titles, dict):
        titles = [titles]
    if isinstance(titles, list):
        for entry in titles:
            if isinstance(entry, str):
                return entry
            if isinstance(entry, dict):
                main = entry.get("mainTitle")
                if isinstance(main, list):
                    main = main[0] if main else None
                if isinstance(main, dict):
                    main = main.get("@value")
                if main:
                    return str(main)
    return ""
