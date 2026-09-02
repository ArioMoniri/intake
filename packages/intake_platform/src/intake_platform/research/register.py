"""INT-230 — the register of research extracts (files/06 §75; KSVY m.16).

files/06 §75 asks for one thing in particular: *"ethics IDs recorded on every
export"*. That is a register, and this is it — one row per extract that was
actually served, carrying who asked, under which study and ethics decision,
for which window, how many subjects, at what threshold, and the SHA-256 of
the bytes that left. The hash is the row's identity: an extract handed to an
investigator can be matched back to its authorisation without keeping a copy.

**What the register does not hold.** No patient id, no pseudonym, no
dimension value, and no copy of the extract. Two reasons, and both are
binding rather than stylistic. Keeping the extract would create a second
persisted store of personal data, which is a stop-and-ask under CLAUDE.md
rather than a design an agent may choose. And keeping pseudonyms would make
the register itself a linkage table — the exact artefact the study-scoped
pseudonym exists to avoid.

**Refusals are not registered here.** This is a register of *extracts*, and a
refused request produced none. The attempt is recorded in the hash-chained
audit log instead (``research.extract.refused.<reason>``), which is where the
trail of what was asked belongs. The split is deliberate: the register
answers "what left, under what authority", the chain answers "what was
asked".

The store is INSERT-shaped on purpose, mirroring the audit chain's
:class:`~intake_platform.audit.AuditStore`: no update, no delete. A
SQLAlchemy implementation maps :meth:`append` to an INSERT and belongs to the
integration slice, not this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

__all__ = [
    "ExtractRecord",
    "ExtractRegister",
    "ExtractRegisterStore",
    "InMemoryExtractRegisterStore",
]


@dataclass(frozen=True)
class ExtractRecord:
    """One served extract. The field set is closed (invariant 6): a register
    that accepts arbitrary keys accumulates PHI the first time someone records
    a cohort "for context"."""

    content_sha256: str
    study_id: str
    ethics_approval_id: str
    protocol_version: str
    recipient: str
    requested_by: str
    spec_name: str
    window_start: str
    window_end: str
    subjects: int
    k: int
    recorded_at: str

    def __post_init__(self) -> None:
        if self.subjects < self.k:
            raise ValueError(
                "a register row cannot record a cohort below its own threshold: "
                "the k gate refuses before anything reaches the register"
            )


class ExtractRegisterStore(Protocol):
    """Storage seam, INSERT-shaped. There is no update and no delete, because
    a register an operator can edit is not a register."""

    def append(self, record: ExtractRecord) -> None: ...
    def records(self) -> Sequence[ExtractRecord]: ...


class InMemoryExtractRegisterStore:
    """Unit-lane store: a list behind the :class:`ExtractRegisterStore`
    shape."""

    def __init__(self) -> None:
        self._records: list[ExtractRecord] = []

    def append(self, record: ExtractRecord) -> None:
        self._records.append(record)

    def records(self) -> Sequence[ExtractRecord]:
        return tuple(self._records)


class ExtractRegister:
    """Append-only writer over a store. Deliberately offers no way to remove
    or amend a row — retention over the register is the destruction engine's
    job under a policy a human states, never an ad-hoc delete here."""

    def __init__(self, store: ExtractRegisterStore) -> None:
        self._store = store

    def append(self, record: ExtractRecord) -> ExtractRecord:
        self._store.append(record)
        return record

    def records(self) -> tuple[ExtractRecord, ...]:
        return tuple(self._store.records())

    def for_study(self, study_id: str) -> tuple[ExtractRecord, ...]:
        """Every extract taken under one study — what an ethics committee or a
        KVKK inspection asks for."""
        return tuple(record for record in self.records() if record.study_id == study_id)

    @staticmethod
    def recorded_at(instant: datetime) -> str:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("a register timestamp must carry a timezone")
        return instant.isoformat()
