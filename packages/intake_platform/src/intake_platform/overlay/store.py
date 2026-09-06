"""INT-170 — persistence for one patient's confirmed learned facts.

CLAUDE.md invariant 12: *``PatientOverlay`` facts require patient or clinician
confirmation (type-level)*. This module is the storage half of that sentence,
and it keeps the guarantee the same way ``clinical_schemas.overlay`` does —
by having no way to say the forbidden thing:

- **The write path takes a candidate and a confirmation, never a fact.**
  :meth:`OverlayStore.confirm_fact` has no ``LearnedFact`` parameter; it mints
  the fact itself through :func:`~clinical_schemas.overlay.confirm`. There is
  no second entry point, so "store this fact I built" is not an operation this
  class offers.
- **There is no unconfirmed table.** A
  :class:`~clinical_schemas.overlay.FactCandidate` has nowhere to be written,
  so an unconfirmed value cannot be read back by anything — including this
  store's own reader. The alternative (one table with a nullable ``source``)
  is precisely the runtime check invariant 12 refuses to depend on.
- **The reader returns a** :class:`~clinical_schemas.overlay.PatientOverlay`,
  whose ``facts`` is typed ``tuple[LearnedFact, ...]``. That is the only
  object INT-081's ``decide_delta`` and INT-258's ``activate_overlays`` accept,
  so there is no shape in which an unconfirmed value could reach a rule.

Two rules this module deliberately does **not** implement:

- **The twelve-month window.** files/09 §3's *"a fact older than 12 months is
  re-confirmed before use"* is
  :func:`~clinical_schemas.overlay.fact_needs_reconfirmation`, which
  ``decide_delta`` and ``activate_overlays`` already share. The store hands
  over every confirmed fact and lets that one predicate decide — a store that
  silently dropped stale facts would also hide them from *Me → Hakkımda
  öğrendikleri*, where the patient has to see a fact in order to re-confirm
  it, and would give the tree a second, drifting definition of "in date".
- **Consent.** Invariant 4 puts every read of clinical data behind the ONE
  ``ensure_consent`` evaluator in ``services/api``. A second check here would
  be a second thing to keep in step; the route calls the evaluator, then calls
  this store.

At rest, the value and its confidence are one EncryptedField envelope
(invariant 14: field-level envelope encryption for *"transcripts/notes/learned
facts"*). Every query carries an explicit ``tenant_id`` predicate even though
postgres enforces the same boundary with RLS — the unit lane exercises the
predicates, the integration lane proves the policies.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from clinical_schemas.common import encode_json_value
from clinical_schemas.overlay import (
    Confirmation,
    FactCandidate,
    LearnedFact,
    LearnedFactSource,
    PatientOverlay,
    confirm,
)
from prometheus_client import Counter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.db.models import OverlayFact, Patient, PatientOverlayHeader
from intake_platform.envelope import EnvelopeCipher

__all__ = [
    "OVERLAY_FACTS_CONFIRMED_TOTAL",
    "OVERLAY_FACTS_WITHDRAWN_TOTAL",
    "OverlayStore",
]

#: files/09 §3's Loop 1 has no metric id in files/08 §4, so the names are ours
#: (the INT-171/INT-172 precedent). Both label sets are minimal for the same
#: reason those two record: a label carrying a fact key would publish the
#: cohort to Prometheus, which retains it (invariant 6). ``source`` is one of
#: the three ``LearnedFactSource`` members and ``action`` is one of two verbs —
#: closed vocabularies, never a key, a patient or a tenant.
OVERLAY_FACTS_CONFIRMED_TOTAL = Counter(
    "overlay_facts_confirmed_total",
    "PatientOverlay facts committed after a patient or clinician confirmation, "
    "by confirmed provenance class.",
    ["source"],
)

OVERLAY_FACTS_WITHDRAWN_TOTAL = Counter(
    "overlay_facts_withdrawn_total",
    "PatientOverlay facts a patient took back, by action (deleted, unshared).",
    ["action"],
)

#: The overlay every patient starts with: no facts, and no header row. Every
#: mutation is a new version, so the first commit lands at 2.
INITIAL_VERSION = 1


class OverlayStore:
    """Read and write one patient's confirmed learned facts."""

    def __init__(self, cipher: EnvelopeCipher) -> None:
        self._cipher = cipher

    # --- write --------------------------------------------------------------

    async def confirm_fact(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID,
        candidate: FactCandidate,
        confirmation: Confirmation,
    ) -> LearnedFact:
        """Commit a candidate as a confirmed fact, or re-confirm an existing
        one in place.

        The signature is the mechanism: a candidate carries no provenance and
        no confirmation instant, a :class:`Confirmation` carries both, and
        there is no third parameter through which an unconfirmed commit could
        be expressed. Re-confirmation replaces the row and restarts the
        twelve-month clock (files/09 §3).
        """
        fact = confirm(candidate, confirmation)
        row = await self._row(session, tenant_id=tenant_id, patient_id=patient_id, key=fact.key)
        payload = self._encrypt(tenant_id, fact)
        if row is None:
            session.add(
                OverlayFact(
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    fact_key=fact.key,
                    payload=payload,
                    source=fact.source,
                    source_ref=fact.source_ref,
                    confirmed_at=fact.confirmed_at,
                    shared=fact.shared,
                )
            )
        else:
            row.payload = payload
            row.source = fact.source
            row.source_ref = fact.source_ref
            row.confirmed_at = fact.confirmed_at
        await self._bump(session, tenant_id=tenant_id, patient_id=patient_id)
        OVERLAY_FACTS_CONFIRMED_TOTAL.labels(source=fact.source.value).inc()
        return fact

    async def forget_fact(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID,
        key: str,
    ) -> bool:
        """Delete one fact (files/09 §3: *"can be corrected or deleted by the
        patient"*). The row goes; no tombstone stays behind, because a
        tombstone that keeps the key keeps the health fact.

        ``False`` means there was no such fact — not an error, and never a
        message that names what was or was not there.
        """
        row = await self._row(session, tenant_id=tenant_id, patient_id=patient_id, key=key)
        if row is None:
            return False
        await session.execute(
            delete(OverlayFact).where(OverlayFact.tenant_id == tenant_id, OverlayFact.id == row.id)
        )
        await self._bump(session, tenant_id=tenant_id, patient_id=patient_id)
        OVERLAY_FACTS_WITHDRAWN_TOTAL.labels(action="deleted").inc()
        return True

    async def set_shared(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID,
        key: str,
        shared: bool,
    ) -> bool:
        """Set one fact's per-field share scope (files/09 §3 guardrails)."""
        row = await self._row(session, tenant_id=tenant_id, patient_id=patient_id, key=key)
        if row is None:
            return False
        row.shared = shared
        await self._bump(session, tenant_id=tenant_id, patient_id=patient_id)
        if not shared:
            OVERLAY_FACTS_WITHDRAWN_TOTAL.labels(action="unshared").inc()
        return True

    # --- read ---------------------------------------------------------------

    async def load_overlay(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> PatientOverlay | None:
        """The object delta mode and overlay activation read.

        ``None`` means there is no such patient in this tenant — distinct from
        a patient who has learned nothing, who gets version 1 and no facts.
        """
        pseudonym = await session.scalar(
            select(Patient.pseudonym).where(
                Patient.tenant_id == tenant_id, Patient.id == patient_id
            )
        )
        if pseudonym is None:
            return None
        return PatientOverlay(
            patient_ref=pseudonym,
            version=await self.version(session, tenant_id=tenant_id, patient_id=patient_id),
            facts=await self.list_facts(session, tenant_id=tenant_id, patient_id=patient_id),
        )

    async def list_facts(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> tuple[LearnedFact, ...]:
        """Every confirmed fact, in key order, with its provenance.

        Stale facts are included: the twelve-month window belongs to
        ``fact_needs_reconfirmation`` at the point of use, and the patient
        cannot re-confirm a fact this store has hidden from them.
        """
        rows = await session.scalars(
            select(OverlayFact)
            .where(OverlayFact.tenant_id == tenant_id, OverlayFact.patient_id == patient_id)
            .order_by(OverlayFact.fact_key)
        )
        return tuple(self._decrypt(tenant_id, row) for row in rows)

    async def version(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> int:
        """The overlay's current version — monotonic across mutations."""
        header = await self._header(session, tenant_id=tenant_id, patient_id=patient_id)
        return INITIAL_VERSION if header is None else header.version

    # --- internals ----------------------------------------------------------

    def _encrypt(self, tenant_id: uuid.UUID, fact: LearnedFact) -> dict[str, object]:
        """The envelope plaintext.

        ``encode_json_value`` is the carrier's own JSON form
        (``clinical_schemas.common``), not a ``default=`` hook invented
        here. Before INT-309 this was a bare ``json.dumps``, so a fact whose
        value is a ``Decimal`` — a blood pressure, a temperature, a dose —
        could not be stored at all: ``TypeError: Object of type Decimal is
        not JSON serializable``, raised after the fact had been minted. The
        two obvious repairs are both worse than the crash, because they
        succeed: ``default=str`` reads back a string the comparison grammar
        cannot use, and ``default=float`` reads back a different number.
        Sharing the codec is what makes the read side free — the
        ``LearnedFact`` validator decodes on the way in.
        """
        plaintext = json.dumps(
            {"value": encode_json_value(fact.value), "confidence": fact.confidence},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        return dict(encrypted_field_to_json(self._cipher.encrypt_field(str(tenant_id), plaintext)))

    def _decrypt(self, tenant_id: uuid.UUID, row: OverlayFact) -> LearnedFact:
        plaintext = self._cipher.decrypt_field(
            str(tenant_id), encrypted_field_from_json(dict(row.payload))
        )
        body = json.loads(plaintext.decode("utf-8"))
        # No decode step here on purpose: ``LearnedFact.value`` is a
        # ``JsonValue``, whose validator is the inverse of the encoder used
        # on the way in (INT-309). A second, local decode would be a second
        # definition of the wire form, and the two would drift.
        return LearnedFact(
            key=row.fact_key,
            value=body["value"],
            source=LearnedFactSource(row.source),
            source_ref=row.source_ref,
            confidence=body["confidence"],
            confirmed_at=_aware(row.confirmed_at),
            shared=row.shared,
        )

    async def _row(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID,
        key: str,
    ) -> OverlayFact | None:
        row: OverlayFact | None = await session.scalar(
            select(OverlayFact).where(
                OverlayFact.tenant_id == tenant_id,
                OverlayFact.patient_id == patient_id,
                OverlayFact.fact_key == key,
            )
        )
        return row

    async def _header(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> PatientOverlayHeader | None:
        header: PatientOverlayHeader | None = await session.scalar(
            select(PatientOverlayHeader).where(
                PatientOverlayHeader.tenant_id == tenant_id,
                PatientOverlayHeader.patient_id == patient_id,
            )
        )
        return header

    async def _bump(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> None:
        """One increment per mutation, deletions included — which is why the
        counter is a column and not a ``max()`` over the surviving facts."""
        header = await self._header(session, tenant_id=tenant_id, patient_id=patient_id)
        now = datetime.now(UTC)
        if header is None:
            session.add(
                PatientOverlayHeader(
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    version=INITIAL_VERSION + 1,
                    updated_at=now,
                )
            )
            return
        header.version += 1
        header.updated_at = now


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; postgres hands back aware ones. The
    schema's ``AwareDatetime`` accepts only the latter, so the unit lane and
    the live lane produce the same object."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
