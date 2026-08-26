"""Change document feed commands.

The feeds are an append-only history, which makes them the dependable way to
enumerate or harvest everything in a deployment.
"""

from __future__ import annotations

from typing import Annotated

import typer

from bluecore_client.cli import paging, ui
from bluecore_client.cli.context import client, die, settings
from bluecore_client.errors import BluecoreError

app = typer.Typer(
    name="changes", help="Read the change document feeds.", no_args_is_help=True
)


@app.command("feed")
def feed(
    kind: Annotated[
        str, typer.Argument(help="Which feed: works or instances")
    ] = "works",
) -> None:
    """Show a feed's collection document."""
    try:
        with ui.working(f"Fetching the {kind} feed"):
            document = client().changes.feed(kind)
    except ValueError as error:
        die(str(error))
        return
    except BluecoreError as error:
        die(error)
        return

    ui.emit(document, as_json=settings.wants_document)


@app.command("page")
def page(
    page_id: Annotated[int, typer.Argument(help="Page number")],
    kind: Annotated[
        str, typer.Argument(help="Which feed: works or instances")
    ] = "works",
) -> None:
    """Show one page of a feed."""
    try:
        with ui.working(f"Fetching {kind} page {page_id}"):
            document = client().changes.page(page_id, kind)
    except ValueError as error:
        die(str(error))
        return
    except BluecoreError as error:
        die(error)
        return

    ui.emit(document, as_json=settings.wants_document)


@app.command("list")
def list_activities(
    kind: Annotated[
        str, typer.Argument(help="Which feed: works or instances")
    ] = "works",
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Maximum activities to show")
    ] = 20,
    all: Annotated[
        bool, typer.Option("--all", help="Walk every page, ignoring --limit")
    ] = False,
) -> None:
    """List change activities, oldest first.

    Activities stream in as each page of the feed arrives, so --all starts
    printing straight away rather than walking the whole feed first.
    """
    records = ui.UriRecords("WHEN")

    def emit(activity: dict) -> None:
        resource = str((activity.get("object") or {}).get("id", ""))
        when = str(activity.get("published", ""))
        what = str(activity.get("type", ""))
        records.add(resource, f"{what} {when}".strip())

    try:
        paging.stream_items(
            client().changes.activities(kind),
            all=all,
            limit=limit,
            emit=emit,
            noun="activity",
            plural="activities",
            spinner=f"Walking the {kind} feed",
        )
    except ValueError as error:
        die(str(error))
    except BluecoreError as error:
        die(error)
