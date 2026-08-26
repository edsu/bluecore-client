"""Works."""

from __future__ import annotations

from bluecore_client.resources.base import ResourceEndpoint


class Works(ResourceEndpoint):
    """BIBFRAME Works -- the abstract creation, apart from any edition."""

    path = "works"
    label = "Work"
