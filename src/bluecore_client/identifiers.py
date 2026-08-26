"""Accepting a Blue Core URI wherever a UUID is expected.

Data you find in Blue Core is full of URIs -- an Instance points at its Work by
URI, search results carry them, the HTML views link with them. Making every
lookup accept a URI as well as a bare UUID means you can paste what you just
found instead of picking it apart first.
"""

from __future__ import annotations

from urllib.parse import urlparse

from bluecore_client.errors import BluecoreError

#: Path segments that name a resource type in a Blue Core URI. Used to catch a
#: URI handed to the wrong command.
RESOURCE_SEGMENTS = frozenset({"works", "instances", "hubs", "resources", "profiles"})


def extract_uuid(value: str, *, expected: str | None = None) -> str:
    """Return the identifier from a UUID or a Blue Core URI.

    A bare identifier passes straight through, so this is always safe to call::

        >>> extract_uuid("4403fbce-ba01-5a4e-a8fc-03fc71caf56d")
        '4403fbce-ba01-5a4e-a8fc-03fc71caf56d'
        >>> extract_uuid("https://dev.bcld.info/works/4403fbce")
        '4403fbce'

    ``expected`` is the resource type the caller deals in. When the URI names a
    different one, that's almost always a mistake worth reporting rather than
    turning into a confusing 404.
    """
    text = value.strip()
    if "://" not in text:
        return text

    parsed = urlparse(text)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        raise BluecoreError(f"No identifier found in {value!r}")

    identifier = segments[-1]
    kind = segments[-2] if len(segments) > 1 else None

    # A collection URI names a type where an identifier should be, which would
    # otherwise be requested as /works/works and 404 confusingly.
    if identifier in RESOURCE_SEGMENTS:
        raise BluecoreError(
            f"{value} is a collection, not a single {_singular(identifier)}. "
            f"Add an identifier, or search instead."
        )

    if expected and kind in RESOURCE_SEGMENTS and kind != expected:
        raise BluecoreError(
            f"{value} points at {kind}, not {expected}. "
            f"Try the {_singular(kind)} command instead."
        )

    return identifier


def _singular(segment: str) -> str:
    """``works`` -> ``work``, for a readable message."""
    return segment.removesuffix("s")
