"""Instances."""

from __future__ import annotations

from typing import Any

from bluecore_client.resources.base import ResourceEndpoint


class Instances(ResourceEndpoint):
    """BIBFRAME Instances -- a particular published edition of a Work."""

    path = "instances"
    label = "Instance"

    def cbd(self, uuid: str, *, xml: bool = False) -> Any:
        """Fetch the Concise Bounded Description of an Instance.

        A CBD nests everything the Instance references into one document. The
        API only offers this for Instances, which is why it lives here and not
        on Works or Hubs.
        """
        return self.get(uuid, format="cbd.xml" if xml else "cbd.jsonld")
