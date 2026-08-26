"""Batch loading.

Both operations hand work to Airflow and return a ``workflow_id`` rather than
waiting, so a successful call means "accepted", not "loaded".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bluecore_client.resources.base import Endpoint


class Batches(Endpoint):
    """Load BIBFRAME data in bulk."""

    def from_url(self, uri: str) -> dict[str, Any]:
        """Load a JSON-LD document from a URL the API can reach."""
        return self._client.post_json("/batches/", {"uri": uri})

    def upload(self, path: str | Path) -> dict[str, Any]:
        """Upload a file to load.

        Accepts a single RDF file (JSON-LD or RDF/XML), or a ``.zip`` or
        ``.tar.gz`` archive of them, which is bulk loaded by the
        ``archived_file_loader`` workflow.
        """
        file_path = Path(path)
        with file_path.open("rb") as handle:
            return self._client.request(
                "POST",
                "/batches/upload/",
                files={"file": (file_path.name, handle)},
            ).json()

    def from_rdfxml(self, name: str, rdfxml: str) -> dict[str, Any]:
        """Load RDF/XML given as a string, converting it to JSON-LD first."""
        return self._client.post_json(
            "/batches/upload/", {"name": name, "rdfxml": rdfxml}
        )
