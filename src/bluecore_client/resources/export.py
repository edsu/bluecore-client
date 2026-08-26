"""Export to a Library Services Platform."""

from __future__ import annotations

from typing import Any

from bluecore_client.resources.base import Endpoint


class Export(Endpoint):
    """Send an Instance out to an LSP such as FOLIO or Alma."""

    def __call__(self, instance_uri: str, local_id: str) -> dict[str, Any]:
        """Trigger an export, returning the workflow that will run it."""
        return self._client.post_json(
            "/export/", {"instance_uri": instance_uri, "local_id": local_id}
        )
