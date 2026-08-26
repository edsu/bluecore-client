"""Commands shared by Works, Instances, and Hubs.

The three behave identically, so their command groups are built from one
factory rather than written out three times.


Annotations here are deliberately *not* postponed: Typer evaluates annotation
strings at module scope, and these reference the factory's ``noun`` argument.
"""

import json
from pathlib import Path
from typing import Annotated

import typer

from bluecore_client.cli import ui
from bluecore_client.cli.context import client, die, settings
from bluecore_client.errors import BluecoreError


def build(noun: str, attribute: str) -> typer.Typer:
    """Make a command group for one BIBFRAME resource type."""
    app = typer.Typer(
        name=noun,
        help=f"Work with {noun.capitalize()}s.",
        no_args_is_help=True,
    )

    def endpoint(*, require_auth: bool = False):
        return getattr(client(require_auth=require_auth), attribute)

    @app.command("view", help=f"Show one {noun}.")
    def view(
        uuid: Annotated[
            str, typer.Argument(help=f"{noun.capitalize()} UUID or Blue Core URI")
        ],
        expand: Annotated[
            bool, typer.Option("--expand", help="Include referenced resources")
        ] = False,
    ) -> None:
        # A single resource is serialized by the API itself, which is always
        # better than converting here -- it's the deployment's own output.
        try:
            with ui.working(f"Fetching {noun} {uuid}"):
                result = endpoint().get(
                    uuid, format=settings.output.format_key, expand=expand
                )
        except BluecoreError as error:
            die(error)
            return

        if isinstance(result, str):
            ui.emit_code(result, ui.LEXERS.get(str(settings.output), "text"))
        else:
            ui.emit(result, as_json=settings.wants_document)

    @app.command("create", help=f"Create a {noun} from a JSON-LD file.")
    def create(
        file: Annotated[
            Path,
            typer.Argument(
                exists=True,
                dir_okay=False,
                readable=True,
                help="JSON-LD file to create from",
            ),
        ],
    ) -> None:
        try:
            graph = json.loads(file.read_text())
        except json.JSONDecodeError as error:
            die(f"{file} is not valid JSON: {error}")
            return

        try:
            # Signing in happens before the spinner starts, so a prompt
            # never competes with it for the terminal.
            target = endpoint(require_auth=True)
            with ui.working(f"Creating {noun}"):
                result = target.create(graph)
        except BluecoreError as error:
            die(error)
            return

        if settings.wants_document:
            ui.emit_json(result)
        else:
            ui.success(f"Created {noun} {result.get('uuid', '')}".rstrip())
            if result.get("uri"):
                ui.note(f"  {ui.ARROW} {result['uri']}")

    @app.command("update", help=f"Replace a {noun}'s graph from a JSON-LD file.")
    def update(
        uuid: Annotated[
            str, typer.Argument(help=f"{noun.capitalize()} UUID or Blue Core URI")
        ],
        file: Annotated[
            Path,
            typer.Argument(exists=True, dir_okay=False, readable=True),
        ],
    ) -> None:
        try:
            graph = json.loads(file.read_text())
        except json.JSONDecodeError as error:
            die(f"{file} is not valid JSON: {error}")
            return

        try:
            target = endpoint(require_auth=True)
            with ui.working(f"Updating {noun} {uuid}"):
                result = target.update(uuid, graph)
        except BluecoreError as error:
            die(error)
            return

        if settings.wants_document:
            ui.emit_json(result)
        else:
            ui.success(f"Updated {noun} {uuid}")

    @app.command("delete", help=f"Delete a {noun}.")
    def delete(
        uuid: Annotated[
            str, typer.Argument(help=f"{noun.capitalize()} UUID or Blue Core URI")
        ],
        yes: Annotated[
            bool, typer.Option("--yes", "-y", help="Skip the confirmation")
        ] = False,
    ) -> None:
        if not yes:
            typer.confirm(f"Delete {noun} {uuid}?", abort=True)

        try:
            target = endpoint(require_auth=True)
            with ui.working(f"Deleting {noun} {uuid}"):
                target.delete(uuid)
        except BluecoreError as error:
            die(error)
            return

        ui.success(f"Deleted {noun} {uuid}")

    return app
