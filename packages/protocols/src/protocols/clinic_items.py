"""CD-08's chest-pain clinic-inbox items, as the build reads them (INT-547, INT-525).

Three clinical decisions (files/00_STATE.md D18; ``packages/protocols/
decisions/``) decide two clinician-only items and where they go:

- **CD-04** ``value.unresolved_after_follow_up``: a CD-01 chest-pain slot
  *"still UNCLEAR after its follow_up_tr has been asked once"* raises a
  labelled CD-08 clinic-inbox item of kind ``chest_pain_arms_unresolved``,
  because under three-valued logic it can leave both chest-pain arms silent.
- **CD-01** declares the seven chest-pain slots CD-04's trigger names, and
  ``value.proxy_unasked_inbox_item``: a proxy session that leaves the seven
  unasked (CD-01's stop-gap until the DSL can select proxy copy) raises kind
  ``proxy_chest_pain_screen_unasked``, for a subject in the rules' adult age
  band or of unknown age, and never for a subject known to be outside it.
- **CD-08** routes both to the booked clinic's inbox (``channel:
  clinic_inbox``), pinned to the note and never dropped, and leaves the
  acknowledgement SLA, out-of-hours cover and escalation ``draft_needs_source``.

This module builds those two triggers and nothing else:

- **Everything is read from the decisions**, through
  :mod:`protocols.clinical_decisions`, which refuses a decision that does not
  hold its own provenance. The arms' slots are CD-04's ``applies_to``, and
  each must be one of CD-01's ``sections``; the screen is CD-01's one slot
  asked of every session (no ``ask_if``). No slot is written here, and a test
  pins that.
- **The follow-up bound is CD-04's "once"**, which the decision carries
  machine-readable as ``unclear_follow_up_tr_asks`` (INT-540).
- **No SLA is stated.** CD-08 leaves it draft; :attr:`ClinicItemRules.sla_decided`
  says only whether the D18 lane has decided it, never what it is.
- **A trigger yields slot ids and a kind**, never a level, a register or a
  priority (invariant 1): the item tells a clinician; only the rules engine
  decides triage.
- **What the decisions say that this build does not follow is refused** when
  the rules are built, before a session is composed.

CD-04's round-3 amendment (INT-519 items 5, 10 and 11: raise the onset's item
when a hedge is read with no follow-up, and at close for an onset never asked
or never answered) is pending its verifier and is not in the register this
build reads; the trigger is rounds 1 and 2 as verified.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from clinical_schemas.session import AnswerState

from protocols.clinical_decisions import (
    REGISTER_DIR,
    ClinicalDecision,
    DecisionStatus,
    load_decision,
)

__all__ = [
    "ARMS_DECISION_ID",
    "CHEST_PAIN_DECISION_ID",
    "CLINIC_INBOX_CHANNEL",
    "ROUTING_DECISION_ID",
    "ArmsUnresolvedRule",
    "ClinicItemError",
    "ClinicItemKind",
    "ClinicItemRules",
    "ProxyScreenRule",
    "SubjectAge",
    "clinic_item_rules",
    "load_clinic_item_rules",
]

#: The decision whose trigger raises the arms item.
ARMS_DECISION_ID: Final = "CD-04"
#: The decision that declares the chest-pain slots and raises the proxy item.
CHEST_PAIN_DECISION_ID: Final = "CD-01"
#: The decision that routes the items.
ROUTING_DECISION_ID: Final = "CD-08"
#: CD-08's channel: the booked clinic's named inbox (files/04 §4.2).
CLINIC_INBOX_CHANNEL: Final = "clinic_inbox"

#: CD-08 keys this build reads, each of which must be decided (active).
_ROUTING_KEYS: Final = ("applies_to", "item_kind_notes", "channel")


class ClinicItemError(ValueError):
    """A decision this build cannot follow exactly."""


class ClinicItemKind(enum.StrEnum):
    """The CD-08 item kinds this build raises, spelled as CD-08 routes them."""

    CHEST_PAIN_ARMS_UNRESOLVED = "chest_pain_arms_unresolved"
    PROXY_CHEST_PAIN_SCREEN_UNASKED = "proxy_chest_pain_screen_unasked"


class SubjectAge(enum.StrEnum):
    """What is known of the subject's age against the chest-pain rules' adult band.

    CD-01 decides on the band, not on a number: a subject in it or of unknown
    age raises the proxy item, one known to be outside it does not.
    """

    IN_ADULT_BAND = "in_adult_band"
    OUTSIDE_ADULT_BAND = "outside_adult_band"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ArmsUnresolvedRule:
    """CD-04 ``unresolved_after_follow_up``: which slots, and after how many asks."""

    kind: ClinicItemKind
    slots: frozenset[str]
    #: CD-04's "once": follow_up_tr asks before an UNCLEAR slot is unresolved.
    follow_up_asks: int
    decision_ids: tuple[str, ...]

    def unresolved(
        self, states: Mapping[str, AnswerState], follow_ups_asked: Mapping[str, int]
    ) -> tuple[str, ...]:
        """The slots still UNCLEAR after their follow-up was asked, sorted."""
        return tuple(
            sorted(
                slot
                for slot in self.slots
                if states.get(slot) is AnswerState.UNCLEAR
                and follow_ups_asked.get(slot, 0) >= self.follow_up_asks
            )
        )


@dataclass(frozen=True)
class ProxyScreenRule:
    """CD-01 ``proxy_unasked_inbox_item``: the seven slots, the screen, the condition."""

    kind: ClinicItemKind
    slots: frozenset[str]
    #: The one CD-01 slot asked of every session; the other six open on its yes.
    screen: str
    decision_ids: tuple[str, ...]
    #: CD-01's ``raised_when``, kept to check which reading the stop-gap rests on.
    raised_when: str = field(repr=False)

    def names_reading(self, ref: str) -> bool:
        """Whether CD-01 names ``ref`` in the condition that makes a session a proxy one."""
        return ref in self.raised_when

    def raised(self, *, screen_skipped: bool, slots_unasked: bool, subject_age: SubjectAge) -> bool:
        """The screen skipped for a proxy, the seven unasked, the subject not known
        to be outside the adult band."""
        return screen_skipped and slots_unasked and subject_age is not SubjectAge.OUTSIDE_ADULT_BAND


@dataclass(frozen=True)
class ClinicItemRules:
    """The triggers and their routing, read from CD-04, CD-01 and CD-08."""

    arms: ArmsUnresolvedRule
    proxy: ProxyScreenRule
    channel: str
    #: Whether CD-08's acknowledgement SLA is decided. While it is not, no SLA
    #: applies to either item (CD-08 ``fail_closed_while_draft``).
    sla_decided: bool


def load_clinic_item_rules(directory: Path = REGISTER_DIR) -> ClinicItemRules:
    """The three decisions from the committed register, provenance-checked."""
    return clinic_item_rules(
        routing=load_decision(directory / f"{ROUTING_DECISION_ID}.yaml"),
        arms=load_decision(directory / f"{ARMS_DECISION_ID}.yaml"),
        chest_pain=load_decision(directory / f"{CHEST_PAIN_DECISION_ID}.yaml"),
    )


def clinic_item_rules(
    *, routing: ClinicalDecision, arms: ClinicalDecision, chest_pain: ClinicalDecision
) -> ClinicItemRules:
    """Build the triggers, refusing anything the decisions say that this build does not do."""
    _require(routing.id == ROUTING_DECISION_ID, routing.id, f"is not {ROUTING_DECISION_ID}")
    _require(arms.id == ARMS_DECISION_ID, arms.id, f"is not {ARMS_DECISION_ID}")
    _require(
        chest_pain.id == CHEST_PAIN_DECISION_ID, chest_pain.id, f"is not {CHEST_PAIN_DECISION_ID}"
    )
    _routed_kinds(routing)
    seven, screen = _sections(chest_pain)
    return ClinicItemRules(
        arms=_arms(arms, seven),
        proxy=_proxy(chest_pain, seven, screen),
        channel=CLINIC_INBOX_CHANNEL,
        sla_decided=routing.value_status.get("sla") is DecisionStatus.ACTIVE,
    )


def _refuse(where: str, reason: str) -> ClinicItemError:
    return ClinicItemError(f"{where}: {reason}, which this build does not follow")


def _require(condition: bool, where: str, reason: str) -> None:
    if not condition:
        raise _refuse(where, reason)


def _active(decision: ClinicalDecision) -> None:
    _require(
        decision.status is DecisionStatus.ACTIVE,
        decision.id,
        f"is {decision.status.value}: a draft_needs_source decision raises no item",
    )


def _routed_kinds(routing: ClinicalDecision) -> frozenset[str]:
    """CD-08 routes every kind, each with its note, to the clinic inbox."""
    value = routing.value
    for key in _ROUTING_KEYS:
        _require(key in value, routing.id, f"{key} is missing")
        _require(
            routing.value_status.get(key) is DecisionStatus.ACTIVE,
            routing.id,
            f"{key} is not decided (value_status)",
        )
    _require(value["channel"] == CLINIC_INBOX_CHANNEL, routing.id, "the channel")
    routed = frozenset(_strings(value["applies_to"], routing.id, "applies_to"))
    notes = _mapping(value["item_kind_notes"], routing.id, "item_kind_notes")
    for kind in ClinicItemKind:
        _require(kind.value in routed, routing.id, f"{kind.value} is not routed")
        _require(kind.value in notes, routing.id, f"{kind.value} has no note")
    return routed


def _item(decision: ClinicalDecision, key: str, kind: ClinicItemKind) -> Mapping[str, Any]:
    """One decision's item block: active, of ``kind``, routed to CD-08, pinned."""
    _active(decision)
    node = _mapping(decision.value.get(key), decision.id, key)
    _require(node.get("kind") == kind.value, decision.id, f"the item's kind is not {kind.value}")
    _require(node.get("decision_ref") == ROUTING_DECISION_ID, decision.id, "decision_ref")
    _require(node.get("pinned_to_note") is True, decision.id, "the item is not pinned")
    return node


def _arms(decision: ClinicalDecision, seven: frozenset[str]) -> ArmsUnresolvedRule:
    kind = ClinicItemKind.CHEST_PAIN_ARMS_UNRESOLVED
    node = _item(decision, "unresolved_after_follow_up", kind)
    _require(node.get("action") == "clinic_inbox_item", decision.id, "the action")
    _require(node.get("never_dropped") is True, decision.id, "the item may be dropped")
    slots = frozenset(_strings(node.get("applies_to"), decision.id, "applies_to"))
    _require(slots <= seven, decision.id, "applies_to names a slot that is not CD-01's")
    return ArmsUnresolvedRule(
        kind=kind,
        slots=slots,
        follow_up_asks=_asks(decision.value.get("unclear_follow_up_tr_asks"), decision.id),
        decision_ids=(decision.id, ROUTING_DECISION_ID),
    )


def _proxy(decision: ClinicalDecision, seven: frozenset[str], screen: str) -> ProxyScreenRule:
    kind = ClinicItemKind.PROXY_CHEST_PAIN_SCREEN_UNASKED
    node = _item(decision, "proxy_unasked_inbox_item", kind)
    return ProxyScreenRule(
        kind=kind,
        slots=seven,
        screen=screen,
        decision_ids=(decision.id, ROUTING_DECISION_ID),
        raised_when=_text(node.get("raised_when"), decision.id, "raised_when"),
    )


def _sections(decision: ClinicalDecision) -> tuple[frozenset[str], str]:
    """CD-01's chest-pain slots, and the one asked of every session (no ``ask_if``)."""
    _active(decision)
    seven: set[str] = set()
    ungated: list[str] = []
    sections = _mapping(decision.value.get("sections"), decision.id, "sections")
    for section, slots in sections.items():
        for slot, spec in _mapping(slots, decision.id, "a section's slots").items():
            ref = f"{section}.{slot}"
            seven.add(ref)
            if _mapping(spec, decision.id, "a slot").get("ask_if") is None:
                ungated.append(ref)
    _require(len(ungated) == 1, decision.id, "not exactly one slot is asked of every session")
    return frozenset(seven), ungated[0]


def _mapping(node: object, where: str, what: str) -> Mapping[str, Any]:
    if not isinstance(node, Mapping) or not node:
        raise _refuse(where, f"{what} is not a non-empty mapping")
    return node


def _strings(node: object, where: str, what: str) -> Sequence[str]:
    if not isinstance(node, list) or not node:
        raise _refuse(where, f"{what} is not a non-empty list")
    return [_text(item, where, what) for item in node]


def _text(node: object, where: str, what: str) -> str:
    if not isinstance(node, str) or not node.strip():
        raise _refuse(where, f"{what} is empty")
    return node


def _asks(node: object, where: str) -> int:
    if isinstance(node, bool) or not isinstance(node, int) or node < 0:
        raise _refuse(where, "unclear_follow_up_tr_asks is not a whole number of asks")
    return node
