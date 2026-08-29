"""Standards bindings for the protocol compiler (INT-041).

Two bindings, both of which exist so that a stored answer keeps its identity
across a protocol edit: the FHIR ``linkId`` (derived, never a counter) and
the openEHR archetype path (checked against a sha-pinned operational
template). files/12 §8 keeps them in one table for exactly that reason.
"""

from __future__ import annotations

from protocols.bindings.fhir_link import fhir_link_id
from protocols.bindings.openehr import (
    OPT_PATH,
    OPT_SHA256,
    OPT_TEMPLATE_ID,
    OperationalTemplate,
    OptError,
    load_opt,
)

__all__ = [
    "OPT_PATH",
    "OPT_SHA256",
    "OPT_TEMPLATE_ID",
    "OperationalTemplate",
    "OptError",
    "fhir_link_id",
    "load_opt",
]
