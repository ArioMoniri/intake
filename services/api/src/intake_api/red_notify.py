"""INT-475 — the clinic hears every RED the app's hop fires, and staff hear an
on-site patient (files/02 §5.3 Axis 3; files/04 §8.1 rule 7; CLAUDE.md
invariants 4, 6, 21).

The ON_SITE RED copy says "Görevlilere haber verildi." (INT-465 finding 6). On
the voice lane the runtime's RED reaches the clinic Safety inbox (INT-406);
this module makes the same true for the app's hop and for the patient's answer
to the one location question, on both lanes. It is that same path, not a
parallel one: an :class:`~intake_platform.safety_inbox.InboxEntry` put in the
process's :class:`~intake_platform.safety_inbox.SafetyInboxOutbox`, which the
app pumps into the shared store the console reads.

- :func:`raise_red` — the hop's RED branch. One ``red`` entry (tenant, session,
  visit and work ids, the fired rule ids and the register), and at ``ON_SITE``
  the ``red_on_site`` staff notification beside it, in the same action. A put
  is an append under a lock: the RED answer never waits on the store, and a
  route that cannot put — no inbox wired, a refusal, or no id it may keep — is
  counted (``clinic_red_inbox_route_failures_total``, which pages), owes an
  ``api.triage.red_unrouted`` row naming the visit where it can, and never
  costs the RED.
- ``POST /v1/triage/red-location`` — the patient's answer, on time or late
  (LD-05): ids and the branch target only, for a KIRMIZI rule of the served set.
  ``ON_SITE`` puts the staff notification; ``REMOTE`` puts none. The device
  sends it fire-and-forget with retry; the RED on its screen never depends on
  this response.

**Ids kept, never identifiers** (invariant 14): :func:`stored_ref` keeps a
server-minted UUID as it is and any other id only as its keyed pseudonym — a
synced hospital visit's id carries the hospital's patient number.

**Exactly once per RED.** :func:`red_work_id` derives the RED's id from the
tenant, session, visit and the engine's winning rule, so a re-sent request, a
re-derived RED and the answer that names it all land on one entry (the store's
first write wins). The answer's staff notification therefore shares the hop
RED's ``work_id``. A voice-lane RED's own entry is keyed by the runtime's Work
queue id instead; its on-site notification from an answer still names the
same session, visit and rule, and is still one per RED.

**Audited by id, under the core scope** (invariant 4): ``api.triage.red_notified``,
``api.triage.red_on_site_notified``, ``api.triage.red_unrouted`` and
``api.triage.red_location.{on_site,remote}``.
The notification goes first and the row after it — staff before paperwork. On the
hop the row is written once the RED has been answered, and a failed append is
counted (``clinic_red_notification_unaudited_total``); on the answer route a
failed append is a 503 the device retries, landing on the same entry.

**Ids only** (invariant 6): no answer value has a field here, in an entry, in an
audit row or in a log line.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from clinical_schemas.triage import RedLocation, RedRegister
from fastapi import APIRouter
from intake_platform.safety_inbox import InboxEntry
from intake_platform.safety_inbox.metrics import (
    CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL,
    CLINIC_RED_NOTIFICATION_UNAUDITED_TOTAL,
)
from intake_platform.safety_inbox.model import ID_SHAPE, RULE_ID_SHAPE
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.errors import safety_inbox_refused, triage_unconfigured
from intake_api.state import ApiState, State

__all__ = [
    "AuditNote",
    "InboxRef",
    "audit_raised",
    "raise_red",
    "red_work_id",
    "router",
    "stored_ref",
]

logger = logging.getLogger("intake_api.red_notify")

CORE_SCOPE = "core"
_SCOPE_REF = f"scope:{CORE_SCOPE}"
#: What an unroutable RED's audit row names when its visit cannot be named.
_UNIDENTIFIED = "unidentified"
#: A server-minted id: a visit row (POST /v1/visits) or a voice session.
_CANONICAL_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

#: A session or visit id, in the shape the inbox entry takes.
InboxRef = Annotated[str, StringConstraints(pattern=ID_SHAPE)]
RuleRef = Annotated[str, StringConstraints(pattern=RULE_ID_SHAPE)]

router = APIRouter(prefix="/v1/triage", tags=["triage"])


def red_work_id(*, tenant_id: str, session_id: str, visit_id: str, rule_id: str) -> str:
    """``w_`` + the first 32 hex of sha256(tenant, session, visit, rule).

    Derived, not minted (files/12 §7.5's reason): the same RED — the same
    winning rule in the same session and visit — has the same id however often
    it is evaluated, at whatever location, and the location answer that names
    it re-derives it rather than carrying it.
    """
    digest = hashlib.sha256(
        "\x00".join(("red", tenant_id, session_id, visit_id, rule_id)).encode("utf-8")
    ).hexdigest()
    return f"w_{digest[:32]}"


def stored_ref(state: ApiState, raw: str | None) -> str | None:
    """How a device's session or visit id is kept in an entry and on the chain.

    A canonical UUID is one the server minted (a visit row, a voice session), so
    it is kept as it is — files/02 §2b finds a visit's REDs by it. Any other id is
    kept only as its keyed pseudonym (invariant 14): a synced hospital visit's id
    carries the hospital's patient number. The value is hex-encoded first so the
    tokenizer's phone normalisation cannot merge two ids. With no tokenization key
    configured, or no id at all, there is nothing safe to keep: ``None``.
    """
    if raw is None:
        return None
    if _CANONICAL_UUID.fullmatch(raw):
        return raw
    if state.tokenizer is None:
        return None
    return "px:" + state.tokenizer.pseudonym(raw.encode("utf-8").hex())


@dataclass(frozen=True)
class AuditNote:
    """One audit row the hop owes: what was done, named by id."""

    action: str
    resource_ref: str


def _inbox_ref(entry: InboxEntry) -> str:
    return f"safety_inbox:{entry.tenant_id}:{entry.entry_id}"


def raise_red(
    state: ApiState,
    *,
    tenant_id: str,
    session_id: str | None,
    visit_id: str | None,
    winner: str,
    rule_ids: tuple[str, ...],
    register: RedRegister,
    location: RedLocation,
) -> tuple[AuditNote, ...]:
    """Put the hop RED's entry, and at ON_SITE the staff notification.

    Never raises: the RED is answered whatever happens here. A route with no
    inbox wired, one that refuses, or a RED whose session and visit cannot be
    named (an app build that sends no ids; a non-UUID id with no tokenization
    key) is counted (which pages) and owes one ``api.triage.red_unrouted`` row
    naming the visit and the RED where it can, so the on-call can find from the
    audit chain which REDs the clinic never heard.
    """
    session_ref, visit_ref = stored_ref(state, session_id), stored_ref(state, visit_id)
    if session_ref is None or visit_ref is None:
        CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL.inc()
        logger.error("red clinic route unidentified: no session or visit to name")
        return (AuditNote("api.triage.red_unrouted", f"visit:{_UNIDENTIFIED}/red:{winner}"),)
    session_id, visit_id = session_ref, visit_ref
    work_id = red_work_id(
        tenant_id=tenant_id, session_id=session_id, visit_id=visit_id, rule_id=winner
    )
    unrouted = (AuditNote("api.triage.red_unrouted", f"visit:{visit_id}/red:{work_id}"),)
    outbox = state.red_outbox
    if outbox is None:
        CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL.inc()
        logger.error("red clinic route unwired: no safety inbox")
        return unrouted
    try:
        at = state.clock()
        entries = [
            (
                "api.triage.red_notified",
                InboxEntry.for_red(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    visit_id=visit_id,
                    work_id=work_id,
                    rule_ids=rule_ids,
                    at=at,
                    register=register,
                ),
            )
        ]
        if location is RedLocation.ON_SITE:
            # files/04 §8.1 rule 7: the staff notification fires with the alert
            entries.append(
                (
                    "api.triage.red_on_site_notified",
                    InboxEntry.for_on_site(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        visit_id=visit_id,
                        work_id=work_id,
                        rule_ids=rule_ids,
                        at=at,
                    ),
                )
            )
        for _, entry in entries:
            outbox.put(entry)
    except Exception as fault:  # noqa: BLE001 - the route never costs the RED
        CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL.inc()
        logger.error("red clinic route failed", extra={"error": type(fault).__name__})
        return unrouted
    return tuple(AuditNote(action, _inbox_ref(entry)) for action, entry in entries)


async def audit_raised(state: ApiState, actor: str, notes: Sequence[AuditNote]) -> None:
    """The hop's audit rows, written once the RED has been answered."""
    for note in notes:
        try:
            await state.audit.record(
                actor=actor,
                action=note.action,
                resource_ref=note.resource_ref,
                consent_scope=_SCOPE_REF,
            )
        except Exception as fault:  # noqa: BLE001 - counted; the RED is already out
            CLINIC_RED_NOTIFICATION_UNAUDITED_TOTAL.inc()
            logger.error("red notification unaudited", extra={"error": type(fault).__name__})


class RedLocationIn(BaseModel):
    """The patient's answer to the one location question: ids and the branch."""

    model_config = ConfigDict(extra="forbid")

    session_id: InboxRef
    visit_id: InboxRef
    rule_id: RuleRef = Field(description="The RED trigger's ruleId, as the device holds it.")
    location: Literal["ON_SITE", "REMOTE"] = Field(
        description="Where the answer sends the RED (files/02 §5.3 Axis 3). An answer "
        "resolves UNKNOWN, so UNKNOWN is never one."
    )


class RedLocationOut(BaseModel):
    kind: Literal["red_location"] = "red_location"
    staffNotified: bool  # noqa: N815 - the device's field name


@router.post(
    "/red-location",
    status_code=202,
    response_model=RedLocationOut,
    dependencies=[require_scopes(CORE_SCOPE)],
)
async def red_location(
    payload: RedLocationIn, state: State, principal: Principal
) -> RedLocationOut:
    """The location answer reaches the server; ON_SITE notifies staff, once."""
    patient, _ = require_patient(principal)
    tenant_id = str(patient.tenant_id)
    served = state.served_red_rules()
    if served is None:
        # nothing can say whether this rule is a RED the device could be shown
        raise triage_unconfigured()
    if payload.rule_id not in {rule.id for rule in served.rules if rule.level.is_red}:
        # only a RED of the served set can have asked the question (in memory)
        raise safety_inbox_refused(422, "rule_not_served")
    session_ref = stored_ref(state, payload.session_id)
    visit_ref = stored_ref(state, payload.visit_id)
    work_id = (
        red_work_id(
            tenant_id=tenant_id, session_id=session_ref, visit_id=visit_ref, rule_id=payload.rule_id
        )
        if session_ref is not None and visit_ref is not None
        else None
    )
    if payload.location == RedLocation.REMOTE.value:
        named = (
            f"visit:{visit_ref}/red:{work_id}"
            if visit_ref is not None and work_id is not None
            else f"visit:{_UNIDENTIFIED}/red:{payload.rule_id}"
        )
        try:
            await state.audit.record(
                actor=patient.account_id,
                action="api.triage.red_location.remote",
                resource_ref=named,
                consent_scope=_SCOPE_REF,
            )
        except Exception as fault:  # noqa: BLE001 - refused, and the device retries
            logger.error("red location answer unaudited", extra={"error": type(fault).__name__})
            raise safety_inbox_refused(503, "red_location_unaudited") from None
        return RedLocationOut(staffNotified=False)
    outbox = state.red_outbox
    if outbox is None:
        CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL.inc()
        logger.error("red clinic route unwired: no safety inbox")
        raise safety_inbox_refused(503, "safety_inbox_unconfigured")
    if session_ref is None or visit_ref is None or work_id is None:
        # a non-UUID id and no tokenization key: never stored raw (invariant 14)
        CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL.inc()
        logger.error("red clinic route unidentified: no session or visit to name")
        raise safety_inbox_refused(503, "safety_inbox_unidentified")
    entry = InboxEntry.for_on_site(
        tenant_id=tenant_id,
        session_id=session_ref,
        visit_id=visit_ref,
        work_id=work_id,
        rule_ids=(payload.rule_id,),
        at=state.clock(),
    )
    outbox.put(entry)
    try:
        await state.audit.record(
            actor=patient.account_id,
            action="api.triage.red_location.on_site",
            resource_ref=_inbox_ref(entry),
            consent_scope=_SCOPE_REF,
        )
    except Exception as fault:  # noqa: BLE001 - staff are told; the row is retried
        CLINIC_RED_NOTIFICATION_UNAUDITED_TOTAL.inc()
        logger.error("red notification unaudited", extra={"error": type(fault).__name__})
        raise safety_inbox_refused(503, "red_location_unaudited") from None
    return RedLocationOut(staffNotified=True)
