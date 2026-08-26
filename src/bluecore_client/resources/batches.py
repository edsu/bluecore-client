"""Batch loading.

Both operations hand work to Airflow and return a ``workflow_id`` rather than
waiting, so a successful call means "accepted", not "loaded".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rdflib import Graph
from rdflib.util import guess_format

from bluecore_client.errors import BluecoreError
from bluecore_client.resources.base import Endpoint

#: Passed through untouched, since the API routes these to a different workflow
#: that unpacks them. Matches ARCHIVE_SUFFIXES in bluecore_api's batches route.
ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".gz")

#: What the loader can read. The resource_loader workflow parses uploads with
#: format="json-ld" and nothing else, so everything else has to be converted
#: before it is sent -- otherwise the upload is accepted and then fails inside
#: Airflow, long after the call returned.
LOADABLE_FORMAT = "json-ld"


class Batches(Endpoint):
    """Load BIBFRAME data in bulk."""

    def from_url(self, uri: str) -> dict[str, Any]:
        """Load a JSON-LD document from a URL the API can reach."""
        return self._client.post_json("/batches/", {"uri": uri})

    def upload(self, path: str | Path, *, convert: bool = True) -> dict[str, Any]:
        """Upload a file to load.

        Accepts any RDF serialization rdflib can read -- JSON-LD, turtle,
        RDF/XML, N-Triples -- or a ``.zip`` or ``.tar.gz`` archive of them,
        which is bulk loaded by the ``archived_file_loader`` workflow.

        Anything that isn't already JSON-LD is converted before being sent,
        because the loading workflow only reads JSON-LD. Pass
        ``convert=False`` to send the bytes exactly as they are on disk.
        """
        file_path = Path(path)
        name, payload = self._payload(file_path, convert=convert)

        return self._client.request(
            "POST",
            "/batches/upload/",
            files={"file": (name, payload)},
        ).json()

    def _payload(self, file_path: Path, *, convert: bool) -> tuple[str, bytes]:
        """The filename and bytes to send for ``file_path``."""
        raw = file_path.read_bytes()
        lower = file_path.name.lower()

        # Archives are unpacked by the workflow, so don't touch them.
        if any(lower.endswith(suffix) for suffix in ARCHIVE_SUFFIXES):
            return file_path.name, raw

        if not convert:
            return file_path.name, raw

        serialization = guess_format(file_path.name)
        if serialization == LOADABLE_FORMAT:
            return file_path.name, raw

        if serialization is None:
            raise BluecoreError(
                f"Cannot tell what {file_path.name} is. Give it a recognized "
                "extension (.jsonld, .ttl, .rdf, .nt), or pass convert=False "
                "to upload it unchanged."
            )

        graph = Graph()
        try:
            graph.parse(data=raw, format=serialization)
        except Exception as error:
            raise BluecoreError(
                f"Could not read {file_path.name} as {serialization}: {error}"
            ) from error

        # A .jsonld name so the workflow, which picks by extension, is in no
        # doubt about what it has been handed.
        return (
            f"{file_path.stem}.jsonld",
            graph.serialize(format="json-ld").encode(),
        )

    def from_rdfxml(self, name: str, rdfxml: str) -> dict[str, Any]:
        """Load RDF/XML given as a string, converting it to JSON-LD first."""
        return self._client.post_json(
            "/batches/upload/", {"name": name, "rdfxml": rdfxml}
        )
