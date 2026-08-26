"""Commands that don't warrant a group of their own."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from bluecore_client.cli import ui
from bluecore_client.cli.context import client, die, settings
from bluecore_client.errors import BluecoreError


def register(app: typer.Typer) -> None:
    """Attach the standalone commands to the top-level app."""

    @app.command("token")
    def token() -> None:
        """Print a Keycloak access token.

        Useful for handing to curl:

            curl -H "Authorization: Bearer $(bluecore token)" ...
        """
        try:
            access_token = client(require_auth=True).login()
        except BluecoreError as error:
            die(error)
            return

        # Deliberately unstyled and unterminated, so it can be captured
        # cleanly in a shell variable.
        print(access_token, end="")

    @app.command("export")
    def export(
        instance_uri: Annotated[str, typer.Argument(help="URI of the Instance")],
        local_id: Annotated[str, typer.Argument(help="Identifier in the target LSP")],
    ) -> None:
        """Export an Instance to a Library Services Platform."""
        try:
            with ui.working(f"Exporting {instance_uri}"):
                result = client(require_auth=True).export(instance_uri, local_id)
        except BluecoreError as error:
            die(error)
            return

        if settings.wants_document:
            ui.emit_json(result)
            return

        ui.success(f"Queued export of {instance_uri}")
        if result.get("workflow_id"):
            ui.note(f"  workflow {result['workflow_id']}")

    @app.command("whoami")
    def whoami() -> None:
        """Show which Blue Core this is pointed at, and as whom."""
        connection = client()

        if connection.auth is None:
            who = "anonymous (reads only)"
        elif connection.config.username:
            who = connection.config.username
        else:
            who = "supplied token"

        ui.fields(
            {
                "api": connection.config.api_url,
                "keycloak": connection.config.keycloak_url,
                "auth": who,
                "client": connection.config.client_id,
            },
            "api",
            "keycloak",
            "auth",
            "client",
        )


convert_app = typer.Typer(
    name="convert", help="Convert MARC records.", no_args_is_help=True
)


@convert_app.command("bibframe")
def to_bibframe(
    file: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Binary MARC"),
    ],
) -> None:
    """Convert binary MARC to BIBFRAME JSON-LD.

    Nothing is stored, so this is a safe way to see what a record becomes.
    """
    try:
        with ui.working(f"Converting {file.name}"):
            result = client(require_auth=True).convert.marc_to_bibframe(file)
    except BluecoreError as error:
        die(error)
        return

    ui.emit(result, as_json=settings.wants_document)


@convert_app.command("marcxml")
def to_marcxml(
    file: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Binary MARC"),
    ],
) -> None:
    """Convert binary MARC to MARCXML."""
    try:
        with ui.working(f"Converting {file.name}"):
            result = client(require_auth=True).convert.marc_to_xml(file)
    except BluecoreError as error:
        die(error)
        return

    print(result)
