"""INT-230 — the shape of what leaves: subject rows and the served extract.

Three types and a canonicaliser, kept apart from the gate for one reason: the
name of the artefact is a legal claim, and it should be readable without
wading through the permission logic. :class:`PseudonymisedExtract` is
pseudonymised — the subject key is a keyed HMAC derivation, re-derivable by
whoever holds the tokenization key, and therefore personal data under KVKK.
KSVY m.16(1)'s route is anonymisation and this is not it. Nothing in this
module is named otherwise.

:class:`SubjectRow` is the caller's projection and is the only place a
``patient_id`` appears; it is the one field that does not survive into
:class:`PseudonymisedRow`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from intake_platform.analytics import Measurement
from intake_platform.research.values import RESEARCH_SCOPE

__all__ = ["PseudonymisedExtract", "PseudonymisedRow", "SubjectRow", "canonical_bytes"]


@dataclass(frozen=True)
class SubjectRow:
    """One candidate subject as the caller projected it. ``patient_id`` is the
    join key the consent filter needs and is the ONE field that does not
    survive into the extract."""

    patient_id: uuid.UUID
    dimensions: Mapping[str, str]
    measures: Mapping[str, int]


@dataclass(frozen=True)
class PseudonymisedRow:
    """One row of the served extract. Named for what it is: a study-scoped
    pseudonym, which is personal data under KVKK, not an anonymous record."""

    pseudonym: str
    dimensions: Mapping[str, str]
    measures: Mapping[str, int]


@dataclass(frozen=True)
class PseudonymisedExtract:
    """A served extract, inseparable from the study that authorised it and
    the cohort and window that produced it (invariant 20)."""

    study_id: str
    ethics_approval_id: str
    protocol_version: str
    recipient: str
    spec_name: str
    measurement: Measurement
    rows: tuple[PseudonymisedRow, ...]
    content_sha256: str
    built_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def subjects(self) -> int:
        return len(self.rows)

    @property
    def provenance(self) -> str:
        """The sentence a paper's methods section needs, and the one this
        repo will stand behind: pseudonymised, consented, ethics-bound."""
        return (
            f"Pseudonymised extract {self.content_sha256[:16]} for study {self.study_id} "
            f"under ethics approval {self.ethics_approval_id} (protocol "
            f"{self.protocol_version}); {self.subjects} subjects, each holding the "
            f"`{RESEARCH_SCOPE}` consent scope; quasi-identifier combinations suppressed "
            f"below k={self.measurement.k}. Pseudonymised, NOT anonymised: the subject key "
            "is a keyed derivation and remains personal data under KVKK."
        )


def canonical_bytes(spec_name: str, study_id: str, rows: Sequence[PseudonymisedRow]) -> bytes:
    payload = {
        "spec": spec_name,
        "study_id": study_id,
        "rows": sorted(
            (
                {
                    "pseudonym": row.pseudonym,
                    "dimensions": dict(sorted(row.dimensions.items())),
                    "measures": dict(sorted(row.measures.items())),
                }
                for row in rows
            ),
            key=lambda row: str(row["pseudonym"]),
        ),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
