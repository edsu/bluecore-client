"""Everything the CLI puts on screen.

All presentation lives here so it can be restyled without touching a single
command. The house style, borrowed from tools like ``gh``: colour carries
meaning rather than decoration, glyphs mark outcomes, and anything a machine
might read goes to stdout while status chatter goes to stderr.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.theme import Theme

THEME = Theme(
    {
        "ok": "green",
        "warn": "yellow",
        "err": "red",
        "muted": "dim",
        "key": "cyan",
        "heading": "bold",
    }
)

TICK = "✓"
CROSS = "✗"
ARROW = "→"


def _colour_wanted() -> bool:
    """Honour NO_COLOR and pipes, the way well-behaved CLI tools do."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


#: Data goes here, so it can be piped.
out = Console(theme=THEME, no_color=not _colour_wanted(), soft_wrap=True)

#: Status, progress, and errors go here, so they don't pollute a pipe.
err = Console(theme=THEME, stderr=True, no_color=not _colour_wanted())


def success(message: str) -> None:
    err.print(f"[ok]{TICK}[/ok] {message}")


def failure(message: str) -> None:
    err.print(f"[err]{CROSS}[/err] {message}")


def warn(message: str) -> None:
    err.print(f"[warn]![/warn] {message}")


def note(message: str) -> None:
    err.print(f"[muted]{message}[/muted]")


@contextmanager
def working(message: str) -> Iterator[None]:
    """Show a spinner while something slow happens.

    Silent when stderr isn't a terminal, so logs stay readable.
    """
    if not err.is_terminal:
        yield
        return
    with err.status(f"[muted]{message}[/muted]", spinner="dots"):
        yield


def emit_json(data: Any) -> None:
    """Print machine-readable JSON, unstyled and unwrapped."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def emit(data: Any, *, as_json: bool) -> None:
    """Print a payload, pretty by default and plain with --json."""
    if as_json:
        emit_json(data)
        return
    if isinstance(data, (dict, list)):
        out.print_json(json.dumps(data, ensure_ascii=False))
    else:
        out.print(data)


def trace_hooks() -> dict[str, list]:
    """httpx event hooks that narrate each request to stderr.

    Used by ``--verbose``, so a slow or hanging request shows what it's waiting
    on instead of looking like a hang.
    """

    def on_request(request: Any) -> None:
        err.print(f"[muted]{ARROW} {request.method} {request.url}[/muted]")

    def on_response(response: Any) -> None:
        status = response.status_code
        style = "ok" if status < 400 else "err"
        elapsed = ""
        try:
            elapsed = f" in {response.elapsed.total_seconds():.2f}s"
        except RuntimeError:
            # elapsed isn't available until the response has been read.
            pass
        err.print(f"[{style}]{status}[/{style}][muted]{elapsed}[/muted]")

    return {"request": [on_request], "response": [on_response]}


#: How much room a text column needs alongside a URI to be worth having.
MIN_TEXT_WIDTH = 24


class UriRecords:
    """Prints ``(uri, text)`` pairs one at a time, as they arrive.

    Streaming matters for ``--all``: results should appear as each page lands
    rather than after every page has been fetched. That rules out a rich Table,
    which needs every row up front to size its columns -- so the layout is
    decided from the first record and then held. URIs from one deployment are a
    constant length, so in practice that stays aligned.

    A URI is the thing you came to copy, so it is never truncated. Given a wide
    enough terminal the pair goes on one line; on a narrow one it is stacked,
    which stays readable where a single line would have to cut something.
    """

    def __init__(self, header: str | None = "TITLE"):
        #: ``None`` means URIs only. A UUID is already inside its URI, so
        #: printing both just makes the line harder to read.
        self._header = header
        self._width: int | None = None
        self._tabular = False
        self.count = 0

    def add(self, uri: str, text: str = "") -> None:
        if self._width is None:
            self._start(uri)
        self.count += 1

        if self._header is None or not text:
            out.print(escape(uri))
            return

        # Titles are arbitrary data and routinely contain square brackets, so
        # they must never be read as rich markup.
        if self._tabular:
            assert self._width is not None
            room = max(out.width - self._width - 2, MIN_TEXT_WIDTH)
            body = text if len(text) <= room else text[: room - 1] + "\u2026"
            out.print(f"{uri.ljust(self._width)}  {escape(body)}")
        else:
            out.print(escape(text) if text else "[muted](untitled)[/muted]")
            out.print(f"  [muted]{escape(uri)}[/muted]")

    def _start(self, uri: str) -> None:
        """Decide the layout from the first record and print any header."""
        self._width = max(len(uri), len("URI"))
        if self._header is None:
            return
        self._tabular = out.width >= self._width + MIN_TEXT_WIDTH + 2
        if self._tabular:
            out.print(f"[muted]{'URI'.ljust(self._width)}  {self._header}[/muted]")


def fields(data: dict[str, Any], *names: str) -> None:
    """Print selected fields as an aligned key/value block."""
    width = max((len(name) for name in names), default=0)
    for name in names:
        value = data.get(name, "")
        # Escaped for the same reason UriRecords escapes: bracketed values are
        # routine in this domain, and rich would silently swallow them as markup.
        out.print(f"[key]{name.rjust(width)}[/key]  {escape(str(value))}")


def count(total: int | None, noun: str, plural: str | None = None) -> str:
    """Describe a result count without lying when the total is unknown."""
    many = plural or f"{noun}s"
    if total is None:
        return many
    return f"{total} {noun if total == 1 else many}"
