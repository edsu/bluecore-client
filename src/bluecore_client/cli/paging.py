"""Walking paged collections for the CLI.

Streaming is the whole point here: with ``--all``, rows should appear as soon
as the first page lands rather than after every page has been fetched. A
collection of a thousand records otherwise looks exactly like a hang.

``--json`` is the one case that has to buffer, since a single JSON document
can't be emitted a piece at a time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import typer

from bluecore_client.cli import ui
from bluecore_client.cli.context import settings
from bluecore_client.pagination import Page, Pages

#: The largest page /search/ and /search/profile accept, per the API's own
#: OpenAPI schema (``maximum: 100``). Asking for more is rejected with a 422.
SEARCH_MAX_PAGE = 100

#: /profiles/ and /resources/ declare no maximum, so this is our own restraint
#: rather than the API's limit -- big enough that --all isn't hundreds of tiny
#: requests, small enough not to ask an unbounded endpoint for everything.
DEFAULT_MAX_PAGE = 100


def page_size(limit: int, *, all: bool, cap: int = DEFAULT_MAX_PAGE) -> int:
    """How much to ask for per request.

    With ``--all`` that's the biggest page allowed, since fewer round trips is
    strictly better when every record is wanted anyway.
    """
    return cap if all else max(1, min(limit, cap))


def stream(
    pages: Pages,
    *,
    all: bool,
    limit: int,
    emit: Callable[[dict[str, Any]], None],
    noun: str,
    json_key: str,
    spinner: str,
    plural: str | None = None,
) -> None:
    """Walk ``pages``, handing each item to ``emit`` as it arrives."""
    page_iter = pages.pages()

    # Only the first fetch gets a spinner. After that, rows appearing on screen
    # is the progress indicator.
    with ui.working(spinner):
        first = next(page_iter, None)

    if first is None or not first.items:
        _report_empty(noun, json_key, plural)
        return

    wanted = None if all else limit
    # Always chain. Page iteration is lazy, so reaching the limit inside the
    # first page costs no extra request -- but a --limit above the page cap
    # still gets everything it asked for instead of being silently truncated.
    sources: Iterator[Page] = _chain(first, page_iter)

    if settings.output.emits_graph:
        _emit_rdf(first, sources, wanted, noun, plural)
        return

    if settings.wants_document:
        _emit_json(first, sources, wanted, json_key)
        return

    shown = 0
    for page in sources:
        for item in page.items:
            emit(item)
            shown += 1
            if wanted is not None and shown >= wanted:
                _report(shown, first.total, noun, plural, truncated=True)
                return

    _report(shown, first.total, noun, plural, truncated=False)


def stream_items(
    items: Iterator[dict[str, Any]],
    *,
    all: bool,
    limit: int,
    emit: Callable[[dict[str, Any]], None],
    noun: str,
    json_key: str,
    spinner: str,
    plural: str | None = None,
) -> None:
    """Stream an already-flat iterator of items, e.g. a change feed.

    Change document feeds page by path rather than by limit and offset, so they
    don't fit :func:`stream`, but they should stream just the same.
    """
    if settings.output.is_rdf:
        ui.failure(
            f"{settings.output} output isn't available for "
            f"{plural or noun + 's'}; the change feeds are Activity Streams, "
            "not BIBFRAME."
        )
        raise typer.Exit(1)

    wanted = None if all else limit
    collected: list[dict[str, Any]] = []
    shown = 0

    with ui.working(spinner):
        first = next(items, None)

    if first is None:
        _report_empty(noun, json_key, plural)
        return

    for item in _chain(first, items):
        if settings.wants_document:
            collected.append(item)
        else:
            emit(item)
        shown += 1
        if wanted is not None and shown >= wanted:
            break

    if settings.wants_document:
        # The same envelope stream() uses, so a script doesn't need to know
        # which kind of collection it asked for.
        ui.emit_json({"total": len(collected), json_key: collected})
        return

    ui.note(ui.count(shown, noun, plural))


def _chain(first: Any, rest: Iterator[Any]) -> Iterator[Any]:
    """``first``, then everything left in ``rest``."""
    yield first
    yield from rest


def _emit_rdf(
    first: Page,
    sources: Iterator[Page],
    wanted: int | None,
    noun: str,
    plural: str | None,
) -> None:
    """Convert a whole result set to turtle, RDF/XML, or N-Triples.

    This has to buffer. Turtle and RDF/XML need the full graph before they can
    emit prefixes, and the point of merging is that a shared node appears once.
    """
    from bluecore_client import rdf

    items = _collect(sources, wanted)
    graphs = rdf.graphs_of(items)
    if not graphs:
        ui.warn(f"No RDF found in {len(items)} {plural or noun + 's'}.")
        return

    with ui.working(f"Converting {len(graphs)} {plural or noun + 's'}"):
        body = rdf.serialize(
            graphs, str(settings.output), context=settings.client().context()
        )

    ui.emit_code(body, ui.LEXERS.get(str(settings.output), "text"))
    ui.note(ui.count(len(graphs), noun, plural))


def _collect(sources: Iterator[Page], wanted: int | None) -> list[dict[str, Any]]:
    """Gather items across pages, up to ``wanted`` if there is a limit."""
    items: list[dict[str, Any]] = []
    for page in sources:
        items.extend(page.items)
        if wanted is not None and len(items) >= wanted:
            break
    return items[:wanted] if wanted is not None else items


def _emit_json(
    first: Page, sources: Iterator[Page], wanted: int | None, json_key: str
) -> None:
    ui.emit_json({"total": first.total, json_key: _collect(sources, wanted)})


def _report_empty(noun: str, json_key: str, plural: str | None) -> None:
    if settings.wants_document:
        ui.emit_json({"total": 0, json_key: []})
    else:
        ui.note(f"No {plural or noun + 's'}.")


def _report(
    shown: int, total: int | None, noun: str, plural: str | None, *, truncated: bool
) -> None:
    """Report what was actually printed, not what the API claimed.

    Offset paging over a collection that's being written to can hand back fewer
    records than ``total`` promised, so counting rows is the honest number.
    """
    if truncated and total is not None and shown < total:
        ui.note(f"Showing {shown} of {total}. Use --all to fetch them all.")
    elif total is not None and shown != total:
        ui.note(f"{ui.count(shown, noun, plural)} ({total} reported by the API)")
    else:
        ui.note(ui.count(shown, noun, plural))
