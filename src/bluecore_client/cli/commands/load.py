"""Loading data in bulk.

Loading is asynchronous, the API hands the work to Airflow and returns a
workflow id, so a success here means "accepted", not "loaded".
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from bluecore_client.cli import ui
from bluecore_client.cli.context import client, die, settings
from bluecore_client.errors import BluecoreError

app = typer.Typer(name="load", help="Load BIBFRAME data in bulk.", no_args_is_help=True)


@app.command("url")
def load_url(
    url: Annotated[str, typer.Argument(help="URL of a JSON-LD document to load")],
) -> None:
    """Load a JSON-LD document from a URL."""
    try:
        target = client(require_auth=True)
        with ui.working(f"Submitting {url}"):
            result = target.batches.from_url(url)
    except BluecoreError as error:
        die(error)
        return

    _report(result, f"Queued {url}")


@app.command("file")
def load_file(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="RDF file, or a .zip / .tar.gz archive of them",
        ),
    ],
) -> None:
    """Upload a file to load.

    Accepts a single RDF file (JSON-LD or RDF/XML), or an archive of them which
    is bulk loaded by the archived_file_loader workflow.
    """
    try:
        target = client(require_auth=True)
        with ui.working(f"Uploading {file.name}"):
            result = target.batches.upload(file)
    except BluecoreError as error:
        die(error)
        return

    _report(result, f"Uploaded {file.name}")


@app.command("profiles")
def load_profiles(
    host: Annotated[
        str, typer.Argument(help="Blue Core host to copy profiles from")
    ] = "https://dev.bcld.info",
    page_size: Annotated[
        int, typer.Option("--page-size", help="How many to fetch at a time")
    ] = 50,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report what would be loaded")
    ] = False,
) -> None:
    """Copy resource profiles from another Blue Core instance.

    Each profile is created through the API, so the local instance mints its own
    URI and rewrites the profile's resource template to match. Note this
    creates profiles rather than updating existing ones, so running it twice
    will load two copies.
    """
    from bluecore_client import BluecoreClient

    target = client(require_auth=True)
    # The remote read hits a public endpoint, so don't try to log in there.
    source = BluecoreClient(bluecore_url=host, anonymous=True, load_dotenv=False)

    loaded = 0
    try:
        with ui.working(f"Reading profiles from {host}"):
            incoming = list(source.profiles.search(limit=page_size))
    except BluecoreError as error:
        die(f"Could not read profiles from {host}: {error}")
        return
    finally:
        source.close()

    if dry_run:
        for profile in incoming:
            ui.note(f"  would load {profile.get('uri', '')}")
        ui.warn(f"Dry run: {len(incoming)} profiles, nothing written")
        return

    for profile in incoming:
        data = profile.get("data")
        if data is None:
            ui.failure(f"{profile.get('uri', '')}: no profile data to copy")
            continue
        try:
            created = target.profiles.create(data)
        except BluecoreError as error:
            ui.failure(f"{profile.get('uri', '')}: {error}")
            continue
        loaded += 1
        if settings.verbose:
            ui.note(f"  {profile.get('uri', '')} {ui.ARROW} {created.get('uri', '')}")

    if loaded == len(incoming):
        ui.success(f"Loaded {ui.count(loaded, 'profile')}")
    else:
        ui.warn(f"Loaded {loaded} of {len(incoming)} profiles")


def _report(result: dict, message: str) -> None:
    """Report a queued batch, including the workflow that will run it."""
    if settings.wants_document:
        ui.emit_json(result)
        return

    ui.success(message)
    workflow_id = result.get("workflow_id")
    if workflow_id:
        ui.note(f"  workflow {workflow_id}")
