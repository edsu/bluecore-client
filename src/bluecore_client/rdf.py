"""Turning Blue Core JSON-LD into other RDF serializations.

The API serializes a *single* resource into turtle, RDF/XML or N-Triples for
us, and that path is always preferred -- it is the deployment's own output. But
search and list endpoints only ever return JSON-LD, so converting a whole
result set has to happen here.

Note the context problem this solves. Blue Core sets ``@context`` to a URL
rather than an inline object, and rdflib resolves a remote context over HTTP --
once per document. Converting a thousand search results would mean a thousand
extra requests. So the context is fetched once and inlined before parsing.
"""

from __future__ import annotations

import json
from typing import Any

from rdflib import Graph

from bluecore_client.errors import BluecoreError

#: Output name -> the serializer name rdflib knows it by.
SERIALIZERS = {
    "turtle": "turtle",
    # "xml" rather than "pretty-xml": it is what the API's own as_rdfxml uses,
    # so a single resource and a result set come out in the same flavour, and
    # it doesn't emit rdflib's "assertions ... are ignored" warnings. Both are
    # lossless here, so the choice is about consistency and quiet.
    "rdfxml": "xml",
    "ntriples": "nt",
    "jsonld": "json-ld",
}

#: Prefixes bound so turtle and RDF/XML come out readable, matching the ones
#: the API itself binds.
PREFIXES = {
    "bf": "http://id.loc.gov/ontologies/bibframe/",
    "bflc": "http://id.loc.gov/ontologies/bflc/",
    "mads": "http://www.loc.gov/mads/rdf/v1#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}


def to_graph(
    documents: list[dict[str, Any]] | dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> Graph:
    """Parse one or more JSON-LD documents into a single merged graph.

    ``context`` replaces a document's ``@context`` when that is a bare URL,
    saving rdflib an HTTP round trip per document.
    """
    if isinstance(documents, dict):
        documents = [documents]

    graph = Graph()
    for prefix, namespace in PREFIXES.items():
        graph.namespace_manager.bind(prefix, namespace)

    for document in documents:
        prepared = json.dumps(_with_context(document, context))
        try:
            graph.parse(data=prepared, format="json-ld")
        except Exception as error:  # rdflib raises a variety of parse errors
            raise BluecoreError(
                f"Could not parse JSON-LD for {document.get('@id', '<unknown>')}: "
                f"{error}"
            ) from error

    return graph


def serialize(
    documents: list[dict[str, Any]] | dict[str, Any],
    output: str,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """Serialize JSON-LD documents as turtle, RDF/XML, or N-Triples."""
    try:
        serializer = SERIALIZERS[output]
    except KeyError:
        raise BluecoreError(
            f"{output} is not an RDF serialization. "
            f"Choose from: {', '.join(sorted(SERIALIZERS))}"
        ) from None

    graph = to_graph(documents, context=context)

    if serializer == "json-ld" and context:
        # Compacted against the deployment's own context, so the output looks
        # like what the API serves rather than fully expanded JSON-LD.
        return graph.serialize(format="json-ld", context=context, auto_compact=True)

    return graph.serialize(format=serializer)


def _with_context(
    document: dict[str, Any], context: dict[str, Any] | None
) -> dict[str, Any]:
    """Swap a remote ``@context`` URL for the context object, if we have it."""
    if context is None or not isinstance(document.get("@context"), str):
        return document
    return {**document, "@context": context}


def graphs_of(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull the JSON-LD graph out of each search or list result.

    Collection endpoints wrap the graph in a record alongside ``uri``, ``uuid``
    and timestamps; the graph itself is under ``data``.
    """
    graphs = []
    for item in items:
        data = item.get("data")
        if isinstance(data, dict):
            graphs.append(data)
        elif isinstance(data, list):
            graphs.extend(entry for entry in data if isinstance(entry, dict))
        elif "@id" in item or "@type" in item:
            # Already a bare graph rather than a wrapped record.
            graphs.append(item)
    return graphs
