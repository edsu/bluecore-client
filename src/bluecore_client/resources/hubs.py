"""Hubs."""

from __future__ import annotations

from bluecore_client.resources.base import ResourceEndpoint


class Hubs(ResourceEndpoint):
    """BIBFRAME Hubs -- a work-like grouping across expressions."""

    path = "hubs"
    label = "Hub"
