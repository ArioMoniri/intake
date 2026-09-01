"""INT-206 — identifier detection for CI surfaces, with the value withheld.

The detectors are :mod:`intake_platform.deid`'s pattern tier, reached through
its public ``analyze`` API rather than re-declared here. One definition of
"identifier-shaped" in this repository is the point: a second set of regexes
would drift from the first, and the half that drifts is always the one nobody
runs against real data.

Two deliberate narrowings against the de-identification tier:

* **Dates are not identifiers here.** ``deid`` shifts them because clinical
  intervals matter downstream. A CI fixture tree is full of ISO timestamps and
  changelog dates; treating those as findings would make the gate noise, and a
  noisy gate acquires an allow-list, which is how it stops being a gate.
* **Names and addresses are out of scope.** They are the NER tier, which needs
  a 5.7 GB model artefact; a gate that cannot run without one does not run on a
  developer's laptop. The classes kept here are the deterministic ones, and
  they are the ones a leak into CI actually looks like.

:class:`IdentifierHit` carries a digest and never the matched text. The scan
runs in a job whose stdout is a retained log (files/10 §6: 30 d hot, 1 y cold),
so its own report is a disclosure surface. The digest is enough to tell two
findings apart, to recognise the same value in two places, and to confirm a
fix — and it is not enough to reconstruct an 11-digit number, which is why it
is truncated rather than because truncation is cheaper.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from intake_platform.deid import Deidentifier

__all__ = [
    "IdentifierHit",
    "IdentifierKind",
    "find_identifiers",
    "identifier_digest",
]

#: How many hex characters of the sha256 a finding shows.
_DIGEST_CHARS = 16


class IdentifierKind(StrEnum):
    """The deterministic identifier classes this gate refuses in a CI context."""

    TCKN = "TCKN"
    PHONE = "PHONE"
    IBAN = "IBAN"
    EMAIL = "EMAIL"


@dataclass(frozen=True, slots=True)
class IdentifierHit:
    """Where an identifier is, and which one it is — never what it says."""

    kind: IdentifierKind
    start: int
    end: int
    digest: str


#: The subject key only seeds deid's date shifter, which this module never
#: reaches: `analyze` is read-only and no date class survives the filter below.
_PATTERN_TIER = Deidentifier(ner_model_dir=None, subject_key="intake-ci-policy")

_KINDS = {kind.value for kind in IdentifierKind}


def identifier_digest(value: str) -> str:
    """A stable, truncated fingerprint of an identifier, safe to print."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]


def find_identifiers(text: str) -> tuple[IdentifierHit, ...]:
    """Every deterministic identifier in ``text``, as positions and digests."""
    hits: list[IdentifierHit] = []
    for entity in _PATTERN_TIER.analyze(text).entities:
        if entity.type not in _KINDS:
            continue
        hits.append(
            IdentifierHit(
                kind=IdentifierKind(entity.type),
                start=entity.start,
                end=entity.end,
                digest=identifier_digest(entity.value),
            )
        )
    return tuple(hits)
