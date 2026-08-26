"""Serialization formats the API can return.

The API negotiates on either an ``Accept`` header or a ``format`` query
parameter; this client uses ``Accept``. Keys here match the ones in
``bluecore_api``'s ``serializer_format_registry`` so they'll look familiar.
"""

from __future__ import annotations

from enum import StrEnum

from bluecore_client.errors import BluecoreError


class Format:
    """An available serialization: its Accept header and whether it's JSON."""

    def __init__(self, key: str, media_type: str, *, is_json: bool):
        self.key = key
        self.media_type = media_type
        self.is_json = is_json

    def __repr__(self) -> str:
        return f"Format({self.key!r})"


FORMATS: dict[str, Format] = {
    "jsonld": Format("jsonld", "application/ld+json", is_json=True),
    "json": Format("json", "application/json", is_json=True),
    "ttl": Format("ttl", "text/turtle", is_json=False),
    "turtle": Format("turtle", "text/turtle", is_json=False),
    "rdf": Format("rdf", "application/rdf+xml", is_json=False),
    "xml": Format("xml", "application/rdf+xml", is_json=False),
    "nt": Format("nt", "application/n-triples", is_json=False),
    "cbd.jsonld": Format("cbd.jsonld", "application/cbd+jsonld", is_json=True),
    "cbd.xml": Format("cbd.xml", "application/cbd+xml", is_json=False),
    "vnd.sinopia.json": Format(
        "vnd.sinopia.json", "application/vnd.sinopia+json", is_json=True
    ),
    "html": Format("html", "text/html", is_json=False),
}

#: What you get when you don't ask for anything in particular.
DEFAULT = FORMATS["jsonld"]


class Output(StrEnum):
    """The output serializations the CLI offers.

    Deliberately smaller and friendlier than :data:`FORMATS`, which mirrors
    every media type the API registers. These are spelled the way someone would
    say them rather than as file extensions.
    """

    #: Human-readable, and the default. For a single resource that means
    #: pretty-printed JSON-LD; for a list it means one record per line.
    TEXT = "text"

    JSON = "json"
    JSONLD = "jsonld"
    TURTLE = "turtle"
    RDFXML = "rdfxml"
    NTRIPLES = "ntriples"
    SINOPIA = "sinopia"

    @property
    def is_json(self) -> bool:
        """Whether this is a JSON shape, printed rather than serialized."""
        return self in (Output.TEXT, Output.JSON, Output.JSONLD, Output.SINOPIA)

    @property
    def is_rdf(self) -> bool:
        """Whether this needs converting to another RDF serialization."""
        return self in (Output.TURTLE, Output.RDFXML, Output.NTRIPLES)

    @property
    def is_document(self) -> bool:
        """Whether the whole result should be emitted as one document.

        True for everything except :attr:`TEXT`, which streams instead.
        """
        return self is not Output.TEXT

    @property
    def format_key(self) -> str:
        """The :data:`FORMATS` key the API knows this by."""
        return {
            Output.TEXT: "jsonld",
            Output.JSON: "json",
            Output.JSONLD: "jsonld",
            Output.TURTLE: "ttl",
            Output.RDFXML: "rdf",
            Output.NTRIPLES: "nt",
            Output.SINOPIA: "vnd.sinopia.json",
        }[self]


def lookup(key: str | None) -> Format:
    """Find a format by key, or explain what the options are."""
    if key is None:
        return DEFAULT
    try:
        return FORMATS[key]
    except KeyError:
        options = ", ".join(sorted(FORMATS))
        raise BluecoreError(
            f"Unknown format {key!r}. Available formats: {options}"
        ) from None
