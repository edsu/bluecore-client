"""MARC conversion.

These endpoints convert without storing anything, so they're a safe way to see
what MARC turns into.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bluecore_client.resources.base import Endpoint


class Convert(Endpoint):
    """Turn binary MARC into MARCXML or BIBFRAME."""

    def marc_to_xml(self, path: str | Path) -> str:
        """Convert a binary MARC file to MARCXML."""
        return self._client.request(
            "POST",
            "/marc2xml",
            content=Path(path).read_bytes(),
            content_type="application/marc",
            accept="application/xml",
        ).text

    def marc_to_bibframe(self, path: str | Path) -> Any:
        """Convert a binary MARC file to BIBFRAME JSON-LD."""
        return self._client.request(
            "POST",
            "/marc2bibframe",
            content=Path(path).read_bytes(),
            content_type="application/marc",
            accept="application/ld+json",
        ).json()
