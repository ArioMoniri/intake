"""INT-170 — the ``PatientOverlay`` store: what a confirmed fact is worth, and
for how long.

files/09 §3 (Loop 1) describes a per-patient learning object that is
*versioned, patient-owned, exported and deletable*, whose every fact *shows
"where from"*, and in which *a fact older than 12 months is re-confirmed before
use*. CLAUDE.md invariant 12 adds the load-bearing clause: **PatientOverlay
facts require patient or clinician confirmation (type-level)**.

Three decisions carry this module, and each is the answer to a question the
acceptance leaves open.

**1 · Confirmation is a type, and this store accepts only that type.**
:meth:`PatientOverlayStore.commit` takes a
:class:`~clinical_schemas.overlay.ConfirmedFact` — a frozen dataclass that
cannot be constructed without a
:class:`~clinical_schemas.overlay.Confirmation` naming a
:class:`~clinical_schemas.overlay.Confirmer`, of which there are two members
and no third. What extraction produces is an
:class:`~clinical_schemas.overlay.UnconfirmedObservation`, a *different type*,
and handing one to this method is an error the checker reports at the call site
rather than a validator rejects three layers later. There is no boolean on
either type, because a boolean is a value any caller can set and the acceptance
says *(type-level)*.

**2 · Twelve months is an expiry semantics, not a timer.** At twelve months and
a day a fact **stops being asserted and stays visible**:

- it is never rendered as current — :class:`FactStatus` marks it ``STALE`` and
  the ledger says so on its face, beside the date it fell due;
- it is still handed to the engine, because INT-081's
  ``clinical_agent.delta.decide_delta`` is the component that applies the
  twelve-month rule to a session, and it *records* the withholding in
  ``DeltaDecision.withheld_fact_keys``. Filtering here as well would delete
  that record and give the repository two implementations of "in date" that can
  drift — and a drift between the ledger's answer and the engine's answer is
  invisible from either side. So this module calls
  :func:`~clinical_schemas.overlay.fact_needs_reconfirmation`, the same
  predicate, rather than comparing timestamps of its own;
- it is **never deleted**. A silently dropped allergy is not the same artefact
  as one marked stale. Dropping it destroys the record of what the system was
  told, and takes the patient's KVKK m.11 correction right with it: you cannot
  correct a fact you can no longer see. Re-confirmation therefore *appends* —
  the older record becomes ``SUPERSEDED`` and stays in the ledger.

**No wall clock.** :class:`PatientOverlayStore` takes a ``clock`` with no
default, so "now" is a decision made at the wiring site and a test can advance
it (docs/TDD.md rule 6). A wall-clock expiry test for a twelve-month rule is a
test that takes a year to go red.

**3 · The store is a writer, so it lives here and not in ``services/learning``.**
Invariant 12 makes the learning loop proposal-only, and
``tests/learning/test_proposal_scope.py`` already names ``intake_api`` among
the import roots that package may not reach. Putting the overlay writer in
``services/api`` therefore makes "the learning loop cannot write a patient fact"
a property of the existing gate rather than a new rule to remember.

**Persistence is a seam.** :class:`OverlayFactRepository` is the only thing
this module knows about storage, and it handles :class:`SealedFactRow` — the
fact is envelope-encrypted *before* the repository sees it (invariant 14 names
learned facts among the field-level encrypted columns), bound by AAD to its own
tenant, patient and fact id, so a ciphertext moved between rows fails
authentication instead of re-attributing a fact to somebody else. The
SQLAlchemy repository behind that seam needs a ``learned_facts`` table that
does not exist yet; :data:`OVERLAY_INVENTORY` declares the invariant-18
annotation for every column of it so the gate binds now rather than then.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol

from clinical_schemas.common import JsonValue
from clinical_schemas.overlay import (
    RECONFIRM_AFTER,
    Confirmation,
    ConfirmedFact,
    Confirmer,
    LearnedFact,
    LearnedFactSource,
    PatientOverlay,
    fact_needs_reconfirmation,
)
from intake_platform.db.inventory import (
    CAT_HEALTH,
    CAT_OPERATIONAL,
    CAT_PSEUDONYM,
    REC_INTERNAL,
    REC_PATIENT_CLINICIAN,
    RET_RECORD,
    InventoryAnnotation,
    inv,
)
from intake_platform.envelope import EncryptedField

__all__ = [
    "COMMIT_ACTION",
    "LEARNING_SCOPE",
    "LEARNING_SCOPE_REF",
    "MATERIALISE_ACTION",
    "OVERLAY_INVENTORY",
    "READ_ACTION",
    "WITHDRAW_ACTION",
    "WITHDRAW_BASIS_REF",
    "Clock",
    "FactSealer",
    "FactStatus",
    "LedgerEntry",
    "OverlayAuditSink",
    "OverlayFactNotFound",
    "OverlayFactRepository",
    "PatientOverlayStore",
    "SealedFactRow",
]

#: The files/06 §2 purpose a learned fact is held under — "``learning:personal``
#: (on by default, inspectable — legal basis: performance of the very service
#: the patient configured)". Quoted from the closed registry, never invented.
LEARNING_SCOPE: Final = "learning:personal"

#: Audit consent references (INT-016 shape: ``scope:<id>`` or ``basis:<code>``).
LEARNING_SCOPE_REF: Final = f"scope:{LEARNING_SCOPE}"
#: A withdrawal rides KVKK m.11, not the purpose it acts against — a right that
#: the withdrawal of a purpose could lock is not a right.
WITHDRAW_BASIS_REF: Final = "basis:KVKK-11"

COMMIT_ACTION: Final = "overlay.fact.commit"
READ_ACTION: Final = "overlay.learned.read"
MATERIALISE_ACTION: Final = "overlay.learned.materialise"
WITHDRAW_ACTION: Final = "overlay.fact.withdraw"

#: files/06 §2's basis for this purpose, quoted rather than chosen. The purpose
#: itself is in the closed registry; nothing here invents a new one.
_BASIS_LEARNING_PERSONAL: Final = (
    "KVKK m.5/2-c via files/06 §2 learning:personal — 'performance of the very "
    "service the patient configured'; on by default, inspectable, withdrawable, "
    "and its withdrawal stops every fact held under it from being asserted"
)


class OverlayFactNotFound(LookupError):
    """The subject has no such fact. Raised rather than answered quietly: a
    withdrawal that silently succeeded against nothing would tell a patient
    their correction landed when it did not."""


class FactStatus(StrEnum):
    """What the store says about one recorded confirmation, right now.

    The four are exhaustive and ordered by how much weight they carry:

    - ``ASSERTED`` — confirmed inside the twelve-month window and not
      superseded. The only status that reaches a session.
    - ``STALE`` — past the window (files/09 §3). It stops being *asserted* and
      stays *visible*: the ledger shows it with its provenance and its
      ``reconfirm_due_at``, and INT-081's ``decide_delta`` withholds it from
      the session and records that it did. Deleting it instead would destroy
      the record of what the system was told, and a patient cannot correct a
      fact they can no longer see (KVKK m.11).
    - ``SUPERSEDED`` — a later confirmation of the same key exists.
      Re-confirmation appends; it never edits.
    - ``WITHDRAWN`` — the patient or a clinician said this is not so. A
      tombstone, never a delete: files/06 §2.2 makes the same choice for lane
      signals, because deleting one breaks the audit hash chain.
    """

    ASSERTED = "asserted"
    STALE = "stale"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class SealedFactRow:
    """One learned fact as it sits at rest.

    ``sealed`` is a packed :class:`~intake_platform.envelope.EncryptedField`
    holding the whole fact — key, value, confirmation and confidence. Nothing
    clinical is outside it: the other columns are ids and timestamps, which is
    what lets a repository index and expire rows without holding health data
    (invariants 6 and 14).
    """

    fact_id: str
    tenant_ref: str
    patient_ref: str
    sealed: str
    committed_at: datetime
    withdrawn_at: datetime | None = None


#: Invariant 18 — {category, purpose, basis, retention, recipients} for every
#: persisted field, declared beside the type so the gate binds before the table
#: exists. The SQLAlchemy ``learned_facts`` model copies these onto its columns
#: verbatim (see docs/evidence/INT-170.md for the wire that is still needed).
OVERLAY_INVENTORY: Final[Mapping[str, InventoryAnnotation]] = {
    name: annotation[  # ``inv`` returns the Column.info payload; take the row
        "inventory"
    ]
    for name, annotation in {
        "fact_id": inv(
            CAT_OPERATIONAL,
            "content-addressed key of one confirmation event, derived from its "
            f"own provenance so a replayed confirmation is idempotent ({LEARNING_SCOPE})",
            _BASIS_LEARNING_PERSONAL,
            RET_RECORD,
            REC_INTERNAL,
        ),
        "tenant_ref": inv(
            CAT_OPERATIONAL,
            "the tenant whose KEK opens the envelope; the isolation boundary",
            _BASIS_LEARNING_PERSONAL,
            RET_RECORD,
            REC_INTERNAL,
        ),
        "patient_ref": inv(
            CAT_PSEUDONYM,
            "the pseudonymised patient the fact belongs to; the overlay is "
            "patient-owned (files/09 §3)",
            _BASIS_LEARNING_PERSONAL,
            RET_RECORD,
            REC_INTERNAL,
        ),
        "sealed": inv(
            CAT_HEALTH,
            "the learned fact — key, value, confirmation and confidence — as a "
            f"packed EncryptedField, never plaintext at rest ({LEARNING_SCOPE})",
            _BASIS_LEARNING_PERSONAL,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
        "committed_at": inv(
            CAT_OPERATIONAL,
            "when the confirmation was recorded; orders the ledger and breaks "
            "ties between two confirmations bearing the same instant",
            _BASIS_LEARNING_PERSONAL,
            RET_RECORD,
            REC_INTERNAL,
        ),
        "withdrawn_at": inv(
            CAT_OPERATIONAL,
            "when the subject withdrew the fact (KVKK m.11); a tombstone, so the "
            "row is never deleted and the audit chain stays intact",
            "KVKK m.11 / m.13 — the data subject's rectification and erasure right",
            RET_RECORD,
            REC_INTERNAL,
        ),
    }.items()
}


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One row of *Hakkımda öğrendikleri* — the transparency ledger.

    Every provenance axis files/09 §3 asks for is a required field: where from
    (:attr:`source`, :attr:`source_ref`), when (:attr:`confirmed_at`) and by
    whom (:attr:`confirmed_by`, :attr:`confirmed_by_ref`). ``withdrawn_at`` is
    the only optional member, because "not withdrawn" is a real state and the
    absence of a provenance is not.
    """

    fact_id: str
    key: str
    value: JsonValue
    status: FactStatus
    confirmed_by: Confirmer
    confirmed_by_ref: str
    confirmed_at: datetime
    source: LearnedFactSource
    source_ref: str
    #: The instant the twelve-month window closes on this confirmation.
    reconfirm_due_at: datetime
    withdrawn_at: datetime | None = field(default=None)


#: "Now", supplied by the caller. Never read from the wall inside this module.
type Clock = Callable[[], datetime]


class FactSealer(Protocol):
    """The envelope seam — :class:`~intake_platform.envelope.EnvelopeCipher`
    satisfies it structurally, and a test can supply its own."""

    def encrypt_field(
        self, tenant_id: str, plaintext: bytes, aad: bytes | None = None
    ) -> EncryptedField: ...

    def decrypt_field(
        self, tenant_id: str, field: EncryptedField, aad: bytes | None = None
    ) -> bytes: ...


class OverlayAuditSink(Protocol):
    """The hash-chained audit log, as this store needs it (invariant 4).
    :class:`~intake_api.audit.AuditWriter` satisfies it."""

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None: ...


class OverlayFactRepository(Protocol):
    """Persistence for sealed learned facts.

    Deliberately narrow and append-only: three operations, none of which can
    edit a stored fact. A correction is a new confirmation and a withdrawal is
    a tombstone, so there is no update path for a repository to expose and no
    way for one to rewrite history.
    """

    async def append(self, row: SealedFactRow) -> None: ...

    async def list_for(self, *, tenant_ref: str, patient_ref: str) -> tuple[SealedFactRow, ...]: ...

    async def mark_withdrawn(
        self, *, tenant_ref: str, patient_ref: str, fact_id: str, at: datetime
    ) -> SealedFactRow | None: ...


def _fact_id(patient_ref: str, fact: ConfirmedFact) -> str:
    """Content-addressed over the confirmation, so committing the same
    confirmation twice is one fact rather than two ledger lines."""
    digest = hashlib.sha256()
    for part in (
        patient_ref,
        fact.key,
        fact.confirmation.by.value,
        fact.confirmation.actor_ref,
        fact.confirmation.at.isoformat(),
        fact.confirmation.source.value,
        fact.confirmation.source_ref,
    ):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()[:32]


def _aad(tenant_ref: str, patient_ref: str, fact_id: str) -> bytes:
    return f"learned_fact:{tenant_ref}:{patient_ref}:{fact_id}".encode()


def _pack(fact: ConfirmedFact) -> bytes:
    return json.dumps(
        {
            "key": fact.key,
            "value": fact.value,
            "confidence": fact.confidence,
            "by": fact.confirmation.by.value,
            "actor_ref": fact.confirmation.actor_ref,
            "at": fact.confirmation.at.isoformat(),
            "source": fact.confirmation.source.value,
            "source_ref": fact.confirmation.source_ref,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _unpack(raw: bytes) -> ConfirmedFact:
    payload = json.loads(raw.decode("utf-8"))
    value: JsonValue = payload["value"]
    return ConfirmedFact(
        key=payload["key"],
        value=value,
        confidence=payload["confidence"],
        confirmation=Confirmation(
            by=Confirmer(payload["by"]),
            actor_ref=payload["actor_ref"],
            at=datetime.fromisoformat(payload["at"]),
            source=LearnedFactSource(payload["source"]),
            source_ref=payload["source_ref"],
        ),
    )


@dataclass(frozen=True, slots=True)
class _Opened:
    """A row with its envelope opened — never leaves this module."""

    row: SealedFactRow
    fact: ConfirmedFact

    @property
    def ordering(self) -> tuple[datetime, datetime, str]:
        return (self.fact.confirmation.at, self.row.committed_at, self.row.fact_id)


class PatientOverlayStore:
    """Commit, read, materialise and withdraw one patient's learned facts."""

    def __init__(
        self,
        *,
        repository: OverlayFactRepository,
        sealer: FactSealer,
        clock: Clock,
        audit: OverlayAuditSink,
    ) -> None:
        self._repository = repository
        self._sealer = sealer
        self._clock = clock
        self._audit = audit

    # --- writes ---------------------------------------------------------------

    async def commit(
        self, *, tenant_ref: str, patient_ref: str, fact: ConfirmedFact, actor: str
    ) -> LedgerEntry:
        """Record one confirmation.

        ``fact`` is a :class:`~clinical_schemas.overlay.ConfirmedFact` and the
        annotation is the gate: an
        :class:`~clinical_schemas.overlay.UnconfirmedObservation` — the shape
        extraction and record import actually produce — is refused here by the
        type checker, at the call site (invariant 12, *(type-level)*).
        """
        fact_id = _fact_id(patient_ref, fact)
        sealed = self._sealer.encrypt_field(
            tenant_ref, _pack(fact), _aad(tenant_ref, patient_ref, fact_id)
        )
        await self._audit.record(
            actor=actor,
            action=COMMIT_ACTION,
            resource_ref=f"learned-fact:{fact_id}",
            consent_scope=LEARNING_SCOPE_REF,
        )
        await self._repository.append(
            SealedFactRow(
                fact_id=fact_id,
                tenant_ref=tenant_ref,
                patient_ref=patient_ref,
                sealed=sealed.pack(),
                committed_at=self._clock(),
            )
        )
        entries = await self._entries(tenant_ref=tenant_ref, patient_ref=patient_ref)
        for entry in entries:
            if entry.fact_id == fact_id:
                return entry
        raise OverlayFactNotFound(fact_id)  # unreachable via append; total by construction

    async def withdraw(
        self, *, tenant_ref: str, patient_ref: str, fact_id: str, actor: str
    ) -> LedgerEntry:
        """KVKK m.11 — the subject says a fact about them is not so.

        Audited against the statutory basis rather than the purpose it acts
        against: a correction right that the withdrawal of a purpose could lock
        is not a right. The row is tombstoned, never deleted (files/06 §2.2).
        """
        await self._audit.record(
            actor=actor,
            action=WITHDRAW_ACTION,
            resource_ref=f"learned-fact:{fact_id}",
            consent_scope=WITHDRAW_BASIS_REF,
        )
        updated = await self._repository.mark_withdrawn(
            tenant_ref=tenant_ref, patient_ref=patient_ref, fact_id=fact_id, at=self._clock()
        )
        if updated is None:
            raise OverlayFactNotFound(fact_id)
        entries = await self._entries(tenant_ref=tenant_ref, patient_ref=patient_ref)
        for entry in entries:
            if entry.fact_id == fact_id:
                return entry
        raise OverlayFactNotFound(fact_id)

    # --- reads ----------------------------------------------------------------

    async def ledger(
        self, *, tenant_ref: str, patient_ref: str, actor: str
    ) -> tuple[LedgerEntry, ...]:
        """Every recorded confirmation, newest first, with its status.

        The audit is written **ahead** of the read (files/10 §2), so an
        enumeration that fails midway has still left its trace; an audit that
        cannot be written propagates and the read does not answer.
        """
        await self._audit.record(
            actor=actor,
            action=READ_ACTION,
            resource_ref=f"patient:{patient_ref}",
            consent_scope=LEARNING_SCOPE_REF,
        )
        return await self._entries(tenant_ref=tenant_ref, patient_ref=patient_ref)

    async def overlay(self, *, tenant_ref: str, patient_ref: str, actor: str) -> PatientOverlay:
        """The INT-031 object a session is built with.

        Withdrawn and superseded confirmations are gone from it; **stale ones
        are not**. The twelve-month rule is applied by INT-081's
        ``decide_delta``, which withholds the fact *and records that it did* —
        applying it twice would give the ledger and the engine two answers that
        can drift, and would delete the session's own record of the withholding.
        """
        await self._audit.record(
            actor=actor,
            action=MATERIALISE_ACTION,
            resource_ref=f"patient:{patient_ref}",
            consent_scope=LEARNING_SCOPE_REF,
        )
        opened = await self._open_all(tenant_ref=tenant_ref, patient_ref=patient_ref)
        statuses = self._statuses(opened)
        facts: list[LearnedFact] = [
            item.fact.as_learned_fact()
            for item in sorted(opened, key=lambda item: item.fact.key)
            if statuses[item.row.fact_id] in (FactStatus.ASSERTED, FactStatus.STALE)
        ]
        withdrawals = sum(1 for item in opened if item.row.withdrawn_at is not None)
        return PatientOverlay(
            patient_ref=patient_ref,
            # files/09 §3: the object is versioned. One version per state
            # change — a confirmation or a withdrawal — so a client can tell
            # "nothing changed" from "changed back".
            version=1 + len(opened) + withdrawals,
            facts=tuple(facts),
        )

    # --- internals ------------------------------------------------------------

    async def _open_all(self, *, tenant_ref: str, patient_ref: str) -> tuple[_Opened, ...]:
        rows = await self._repository.list_for(tenant_ref=tenant_ref, patient_ref=patient_ref)
        return tuple(
            _Opened(
                row=row,
                fact=_unpack(
                    self._sealer.decrypt_field(
                        tenant_ref,
                        EncryptedField.unpack(row.sealed),
                        _aad(tenant_ref, patient_ref, row.fact_id),
                    )
                ),
            )
            for row in rows
        )

    def _statuses(self, opened: tuple[_Opened, ...]) -> dict[str, FactStatus]:
        """One status per row, resolved per key.

        The newest confirmation of a key wins; every earlier one is
        ``SUPERSEDED``. A withdrawal is absolute — if the newest is withdrawn
        the key is not asserted at all, and an older confirmation of the same
        key does not resurrect, because "that is not so" is a statement about
        the fact and not about one recording of it.
        """
        now = self._clock()
        by_key: dict[str, list[_Opened]] = {}
        for item in opened:
            by_key.setdefault(item.fact.key, []).append(item)
        statuses: dict[str, FactStatus] = {}
        for group in by_key.values():
            ordered = sorted(group, key=lambda item: item.ordering)
            newest = ordered[-1]
            for item in ordered[:-1]:
                statuses[item.row.fact_id] = (
                    FactStatus.WITHDRAWN
                    if item.row.withdrawn_at is not None
                    else FactStatus.SUPERSEDED
                )
            if newest.row.withdrawn_at is not None:
                statuses[newest.row.fact_id] = FactStatus.WITHDRAWN
            elif fact_needs_reconfirmation(newest.fact.as_learned_fact(), now):
                statuses[newest.row.fact_id] = FactStatus.STALE
            else:
                statuses[newest.row.fact_id] = FactStatus.ASSERTED
        return statuses

    async def _entries(self, *, tenant_ref: str, patient_ref: str) -> tuple[LedgerEntry, ...]:
        opened = await self._open_all(tenant_ref=tenant_ref, patient_ref=patient_ref)
        statuses = self._statuses(opened)
        entries = [
            LedgerEntry(
                fact_id=item.row.fact_id,
                key=item.fact.key,
                value=item.fact.value,
                status=statuses[item.row.fact_id],
                confirmed_by=item.fact.confirmation.by,
                confirmed_by_ref=item.fact.confirmation.actor_ref,
                confirmed_at=item.fact.confirmation.at,
                source=item.fact.confirmation.source,
                source_ref=item.fact.confirmation.source_ref,
                reconfirm_due_at=item.fact.confirmation.at + RECONFIRM_AFTER,
                withdrawn_at=item.row.withdrawn_at,
            )
            for item in opened
        ]
        entries.sort(key=lambda entry: (entry.confirmed_at, entry.fact_id), reverse=True)
        return tuple(entries)
