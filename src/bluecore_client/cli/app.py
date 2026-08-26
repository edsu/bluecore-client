"""The ``bluecore`` command line interface.

Commands are noun-then-verb -- ``bluecore work view <uuid>`` -- which keeps the
shape of the API visible and makes new commands land in an obvious place.

The flat command names from the CLI in bluecore_api (``load-url``,
``load-file``, ``load-profiles``) are kept as hidden aliases so existing scripts
and documentation don't break.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from bluecore_client.cli import ui
from bluecore_client.cli.commands import changes, load, misc, other_resource, profile
from bluecore_client.cli.commands import resource as resource_commands
from bluecore_client.cli.commands import search as search_commands
from bluecore_client.cli.context import settings
from bluecore_client.formats import Output

app = typer.Typer(
    name="bluecore",
    help="Work with Blue Core BIBFRAME data.",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
)

app.add_typer(resource_commands.build("work", "works"))
app.add_typer(resource_commands.build("instance", "instances"))
app.add_typer(resource_commands.build("hub", "hubs"))
app.add_typer(other_resource.app)
app.add_typer(profile.app)
app.add_typer(changes.app)
app.add_typer(load.app)
app.add_typer(misc.convert_app)

search_commands.register(app)
misc.register(app)


@app.callback()
def main(
    api_url: Annotated[
        str | None,
        typer.Option("--api-url", help="Blue Core API URL", envvar="API_URL"),
    ] = None,
    bluecore_url: Annotated[
        str | None,
        typer.Option("--bluecore-url", help="Blue Core URL", envvar="BLUECORE_URL"),
    ] = None,
    keycloak_url: Annotated[
        str | None,
        typer.Option(
            "--keycloak-url", help="Keycloak URL", envvar="KEYCLOAK_EXTERNAL_URL"
        ),
    ] = None,
    username: Annotated[
        str | None,
        typer.Option("--username", "-u", help="Username", envvar="API_KEYCLOAK_USER"),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", help="Password", envvar="API_KEYCLOAK_PASSWORD"),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", help="Use this access token", envvar="BLUECORE_TOKEN"),
    ] = None,
    output: Annotated[
        Output,
        typer.Option(
            "--output",
            "-o",
            help="Output serialization",
        ),
    ] = Output.TEXT,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show each request as it happens"),
    ] = False,
    timeout: Annotated[
        float, typer.Option("--timeout", help="Seconds to wait for the API")
    ] = 30.0,
) -> None:
    """Configure the connection before running a command."""
    settings.api_url = api_url
    settings.bluecore_url = bluecore_url
    settings.keycloak_url = keycloak_url
    settings.username = username
    settings.password = password
    settings.token = token
    settings.output = output
    settings.verbose = verbose
    settings.timeout = timeout


# --- Aliases for the CLI this replaces -------------------------------------


@app.command("load-url", hidden=True)
def load_url_alias(url: Annotated[str, typer.Argument()]) -> None:
    """Deprecated: use `bluecore load url`."""
    ui.note("load-url is now `bluecore load url`")
    load.load_url(url)


@app.command("load-file", hidden=True)
def load_file_alias(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Deprecated: use `bluecore load file`."""
    ui.note("load-file is now `bluecore load file`")
    load.load_file(file)


@app.command("load-profiles", hidden=True)
def load_profiles_alias(
    host: Annotated[str, typer.Argument()] = "https://dev.bcld.info",
    page_size: Annotated[int, typer.Option("--page-size")] = 50,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Deprecated: use `bluecore load profiles`."""
    ui.note("load-profiles is now `bluecore load profiles`")
    load.load_profiles(host=host, page_size=page_size, dry_run=dry_run)


if __name__ == "__main__":
    app()
