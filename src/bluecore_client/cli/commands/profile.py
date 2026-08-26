"""Profile commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from bluecore_client.cli import paging, ui
from bluecore_client.cli.context import client, die, settings
from bluecore_client.errors import BluecoreError

app = typer.Typer(
    name="profile", help="Work with resource profiles.", no_args_is_help=True
)


@app.command("list")
def list_profiles(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Maximum profiles to show")
    ] = 20,
    all: Annotated[bool, typer.Option("--all", help="Fetch every page")] = False,
) -> None:
    """List profiles.

    Results stream in as each page arrives, so --all starts printing straight
    away rather than after every page has been fetched.
    """
    size = paging.page_size(limit, all=all)
    records = ui.UriRecords(None)

    try:
        paging.stream(
            client().profiles.list(limit=size),
            all=all,
            limit=limit,
            emit=lambda item: records.add(str(item.get("uri", ""))),
            noun="profile",
            json_key="profiles",
            spinner="Fetching profiles",
        )
    except BluecoreError as error:
        die(error)


@app.command("view")
def view(
    uuid: Annotated[str, typer.Argument(help="Profile UUID or Blue Core URI")],
) -> None:
    """Show one profile."""
    try:
        with ui.working(f"Fetching profile {uuid}"):
            profile = client().profiles.get(uuid)
    except BluecoreError as error:
        die(error)
        return

    ui.emit(profile, as_json=settings.wants_document)


@app.command("create")
def create(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Create a profile from a JSON file."""
    try:
        data = json.loads(file.read_text())
    except json.JSONDecodeError as error:
        die(f"{file} is not valid JSON: {error}")
        return

    try:
        target = client(require_auth=True)
        with ui.working("Creating profile"):
            created = target.profiles.create(data)
    except BluecoreError as error:
        die(error)
        return

    if settings.wants_document:
        ui.emit_json(created)
    else:
        ui.success(f"Created profile {created.get('uuid', '')}".rstrip())
        if created.get("uri"):
            ui.note(f"  {ui.ARROW} {created['uri']}")


@app.command("delete")
def delete(
    uuid: Annotated[str, typer.Argument(help="Profile UUID or Blue Core URI")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete a profile, along with its versions and classes."""
    if not yes:
        typer.confirm(f"Delete profile {uuid}?", abort=True)

    try:
        target = client(require_auth=True)
        with ui.working(f"Deleting profile {uuid}"):
            target.profiles.delete(uuid)
    except BluecoreError as error:
        die(error)
        return

    ui.success(f"Deleted profile {uuid}")
