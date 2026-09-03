"""The FHIR R4 push adapter (INT-161; ADR-002 makes R4 canonical for exchange).

**It re-encodes nothing, and that is the design.** The adapter is handed
already-rendered bytes and puts exactly those bytes on the wire. Invariant 22
says a clinical quantity must not cross a representation boundary unguarded;
INT-303 closed one seam where a ``Decimal`` became a float and INT-309 records
three more that are still open. A connector that parsed the bundle and
re-serialised it would be a fourth, so it does not parse the bundle. The
cheapest way to hold a boundary is not to have one.

**No FHIR library is added** (invariant 19). ``packages/clinical-schemas``
already emits the profiled R4 subset this product exchanges — ``Bundle``,
``Composition``, ``Observation``, ``RiskAssessment``, ``Condition`` and the
rest, as pydantic models with ``to_wire`` — built for exactly this under
INT-033. A second FHIR implementation would be a second answer to "what shape
do we send", and the licence-verification cost of a new dependency (raw
LICENSE blob, ``licence_verified_at`` in the model registry) would buy
something we already have.

**What it reads back, and what it refuses to.** The response body is never
read — a FHIR server answers a rejection with an ``OperationOutcome`` whose
``diagnostics`` routinely quotes the resource that was submitted, which is a
patient's name arriving back inside an error (invariant 6). So the adapter
asks the server not to send one at all (``Prefer: return=minimal``, FHIR R4
§3.1.0.1.7) and reads three headers:

- ``Location`` — the receiver's own reference, reduced to the **relative**
  FHIR reference. HAPI answers with an absolute URL naming its own base, and
  storing that verbatim would put a receiver-chosen host into our audit
  record. The base is dropped; ``Bundle/12/_history/1`` survives.
- ``WWW-Authenticate`` — an OAuth error code, and only if it is one of three
  we recognise. That single token separates "the token expired" from "the
  token was never granted this", two faults in the same status family with
  entirely different fixes.
- ``Content-Type`` — whether a FHIR server answered at all. ``text/html`` on
  a 4xx is a proxy or a login page, not the hospital, and that is worth
  knowing before anyone re-reads the bundle looking for the fault.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from intake_connectors.adapter import ClinicalPayload, OutboundCall
from intake_connectors.destinations import ConnectorDestination

__all__ = ["FHIR_JSON", "FhirR4PushAdapter", "PayloadNotFhir"]

#: The FHIR R4 JSON media type. ``application/json`` is deliberately not
#: accepted: a payload whose renderer did not think it was producing FHIR is a
#: payload whose shape we have not agreed with the receiver.
FHIR_JSON = "application/fhir+json"

#: ``ResourceType/id`` with an optional version, and nothing else. FHIR ids are
#: ``[A-Za-z0-9-.]{1,64}``; resource types are upper-camel. Anchored, so a
#: trailing path a receiver appended fails rather than being truncated into
#: something plausible.
_REFERENCE = re.compile(
    r"^[A-Z][A-Za-z]{1,63}/[A-Za-z0-9\-.]{1,64}(/_history/[A-Za-z0-9\-.]{1,64})?$"
)

#: OAuth 2.0 error codes we act on. Closed, because ``WWW-Authenticate`` is
#: receiver-controlled text and an unrecognised code is not a code.
_AUTH_ERRORS = frozenset({"invalid_token", "invalid_request", "insufficient_scope"})

_AUTH_ERROR = re.compile(r'error\s*=\s*"([A-Za-z_]{1,64})"')

#: What counts as "a FHIR server answered". ``application/json`` is included
#: because some servers negotiate down to it and that is not itself a fault.
_FHIR_MEDIA_PREFIXES = ("application/fhir+json", "application/json", "application/fhir+xml")


class PayloadNotFhir(ValueError):
    """The rendered payload does not declare itself as FHIR R4 JSON."""


class FhirR4PushAdapter:
    """Push one rendered FHIR document Bundle to a hospital FHIR endpoint."""

    adapter_id = "fhir-r4-push"

    def build(self, destination: ConnectorDestination, payload: ClinicalPayload) -> OutboundCall:
        """``POST [base]/Bundle`` — the R4 way to store a document Bundle.

        The path is the registry's ``base_path`` plus one fixed segment. It is
        not derived from the payload, because deriving it would mean parsing
        the payload, and it is not derived from anything the receiver said,
        because that is a destination the receiver chose.
        """
        if payload.media_type != FHIR_JSON:
            raise PayloadNotFhir(
                f"a FHIR push carries {FHIR_JSON!r}; this payload declares "
                f"{payload.media_type!r}, so its shape was never agreed with the receiver"
            )
        return OutboundCall(
            method="POST",
            path=f"{destination.base_path}/Bundle",
            media_type=FHIR_JSON,
            body=payload.body,
            headers={
                "Accept": FHIR_JSON,
                # Ask the server not to echo the resource back. Not reading the
                # body keeps PHI out of our logs; not being sent one keeps it
                # off our socket, which is strictly better and costs a header.
                "Prefer": "return=minimal",
            },
        )

    def receiver_ref(self, status: int, headers: Mapping[str, str]) -> str | None:
        """The stored resource's FHIR reference, with the server's base removed."""
        location = headers.get("location") or headers.get("content-location")
        if not location:
            return None
        candidate = location.split("?", 1)[0].split("#", 1)[0]
        if "://" in candidate:
            # Absolute: keep the tail that looks like a reference and discard
            # the base, so a host the receiver named cannot enter a receipt.
            candidate = candidate.split("://", 1)[1]
            _, _, candidate = candidate.partition("/")
        candidate = candidate.lstrip("/")
        for start in range(candidate.count("/") + 1):
            tail = "/".join(candidate.split("/")[start:])
            if _REFERENCE.match(tail):
                return tail
        return None

    def failure_hint(self, status: int, headers: Mapping[str, str]) -> str | None:
        """The diagnosis available without reading a word of the body."""
        if status >= 400:
            challenge = headers.get("www-authenticate")
            if challenge:
                match = _AUTH_ERROR.search(challenge)
                if match and match.group(1) in _AUTH_ERRORS:
                    return match.group(1)
            content_type = headers.get("content-type", "").strip().lower()
            if content_type and not content_type.startswith(_FHIR_MEDIA_PREFIXES):
                # Not a FHIR server's answer. A login page or a proxy notice,
                # which sends an operator to the network rather than to the
                # bundle they were about to re-read line by line.
                return "not_fhir"
        return None
