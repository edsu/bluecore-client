"""Commands for resources that aren't Works, Instances, or Hubs."""

from __future__ import annotations

from typing import Annotated

import typer

from bluecore_client.cli import paging, ui
from bluecore_client.cli.context import client, die, settings
from bluecore_client.errors import BluecoreError

app = typer.Typer(
    name="resource",
    help="Work with other resources, such as agents and subjects.",
    no_args_is_help=True,
)


@app.command("list")
def list_resources(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Maximum resources to show")
    ] = 20,
    all: Annotated[bool, typer.Option("--all", help="Fetch every page")] = False,
) -> None:
    """List other resources.

    Results stream in as each page arrives, so --all starts printing straight
    away rather than after every page has been fetched.
    """
    size = paging.page_size(limit, all=all)
    records = ui.UriRecords(None)

    try:
        paging.stream(
            client().resources.list(limit=size),
            all=all,
            limit=limit,
            emit=lambda item: records.add(str(item.get("uri", ""))),
            noun="resource",
            json_key="resources",
            spinner="Fetching resources",
        )
    except BluecoreError as error:
        die(error)


@app.command("view")
def view(
    resource_id: Annotated[str, typer.Argument(help="Resource id or Blue Core URI")],
) -> None:
    """Show one resource."""
    try:
        with ui.working(f"Fetching resource {resource_id}"):
            resource = client().resources.get(resource_id)
    except BluecoreError as error:
        die(error)
        return

    ui.emit(resource, as_json=settings.wants_document)
