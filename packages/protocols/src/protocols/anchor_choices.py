"""Closed-choice tense anchors: each authored choice resolves to a day (CD-05, INT-522).

``chest_pain.onset_at`` is the tense anchor of both active chest-pain rules of
``base.life_threat``. It is a ``date`` slot, and the patient answers it with
one of four closed choices, never with a date. Clinical decision CD-05 decided
how each choice resolves to a calendar day against the session's reference
time (files/00_STATE.md D18; ``packages/protocols/decisions/CD-05.yaml``).
This module is the build of that decision and of nothing else:

- **The table is read from CD-05 through** :mod:`protocols.clinical_decisions`,
  which refuses a decision that does not hold its own provenance. No band, day
  or label is written here; a test pins that the table is CD-05's, choice for
  choice, and that the slot offers exactly CD-05's choices.
- **A band resolves to a whole calendar day**, ``reference_day`` or
  ``reference_day_minus_<n>``: the engine's tense windows are calendar days
  compared against ``reference_time.date()``
  (:func:`protocols.triage.context.temporal_within`), so the resolved day is
  computed from that same date, in the reference time's own timezone, and a
  resolved anchor and its window can never disagree by a timezone.
- **The reference time is the caller's** — the session's ``reference_time``,
  stamped once when the session is composed (files/13 §9.2). Nothing here
  reads a clock, and nothing here is handed anything a model produced except
  the authored choice it picked; a model never supplies a day.
- **The twelve-to-seventy-two-hour band stays open.** CD-05 leaves its final
  resolution to a signing clinician (the invariant-17 literal under
  ``draft_needs_source``, the D18 lane) and decides what applies while it is
  draft: the reference day, never Unknown, labelled ``while_draft_resolution``
  on the record. That while-draft resolution is what is built; the final one
  is not, and the table refuses a draft band whose final resolution has
  stopped being open, because that would be a decision this module never saw.
- **An answer that fits no choice** is recorded UNCLEAR and resolves to the
  more acute reading, the reference day (CD-05 ``unresolved_answer``,
  ``ambiguity: more_acute``); the table refuses an unresolved resolution less
  acute than any choice.
- **Neither a document nor the council feeds the anchor** (CD-05
  ``document_may_feed_anchor`` / ``council_may_fill``): a decision that allowed
  either is refused, because nothing here could honour it.

Everything else CD-05 might say — a token this grammar does not know, a status
outside the register's two, a draft band with no while-draft resolution — is
refused when the table is built, before a session is composed, and never
guessed, defaulted or left to read Unknown.

**Nothing here echoes a value** (invariant 6): a refusal names the anchor and
the field, never what a patient chose, and :class:`AnchorResolution`'s repr
shows neither the choice nor the day.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

from protocols.clinical_decisions import (
    REGISTER_DIR,
    ClinicalDecision,
    DecisionStatus,
    load_decision,
)
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

__all__ = [
    "ANCHOR_DECISION_ID",
    "AnchorBasis",
    "AnchorChoice",
    "AnchorChoiceError",
    "AnchorChoiceTable",
    "AnchorResolution",
    "anchor_choice_table",
    "load_anchor_choice_table",
    "reference_day",
]

#: The register entry this module builds (files/00_STATE.md D18).
ANCHOR_DECISION_ID: Final = "CD-05"

#: CD-05 ``unresolved_answer.answer_state``: the engine's state for an answer
#: that fits no choice once its bounded clarification is spent (files/13 §11.1).
_UNRESOLVED_STATE: Final = "UNCLEAR"
#: CD-05 ``ambiguity``: the only direction this module resolves doubt in.
_MORE_ACUTE: Final = "more_acute"
_TOKEN: Final = re.compile(r"^reference_day(?:_minus_(?P<days>[1-9][0-9]*))?$")


class AnchorChoiceError(ValueError):
    """A decision this module cannot follow exactly, or a resolution outside it."""


class AnchorBasis(enum.StrEnum):
    """Why an anchor holds the day it holds — carried on the record."""

    #: An active CD-05 choice.
    DECIDED = "decided"
    #: CD-05's own ``record_label`` for the draft band's while-draft resolution.
    WHILE_DRAFT = "while_draft_resolution"
    #: CD-05 ``unresolved_answer``: no choice fitted; the more acute reading.
    UNRESOLVED = "unresolved_answer"


@dataclass(frozen=True)
class AnchorChoice:
    """One authored choice and the day CD-05 resolves it to."""

    choice_tr: str
    days_before_reference: int
    basis: AnchorBasis


@dataclass(frozen=True, repr=False)
class AnchorResolution:
    """One anchor's resolved day, with the patient's choice kept beside it.

    CD-05: *"the record keeps the patient's choice beside the resolved date"*.
    ``choice_tr`` is ``None`` for an answer that fitted no choice.
    """

    anchor: str
    choice_tr: str | None
    resolved_on: str
    basis: AnchorBasis
    decision_id: str

    def __repr__(self) -> str:
        return (
            f"AnchorResolution(anchor={self.anchor!r}, basis={self.basis.value!r}, "
            f"decision_id={self.decision_id!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class AnchorChoiceTable:
    """CD-05 as the runtime reads it: the anchors, the question, each choice's day."""

    decision_id: str
    anchors: frozenset[str]
    question_tr: str
    choices: tuple[AnchorChoice, ...]
    unresolved_days_before_reference: int

    @property
    def choice_texts(self) -> tuple[str, ...]:
        """The authored choices, in the decision's order."""
        return tuple(choice.choice_tr for choice in self.choices)

    def resolve(self, anchor: str, choice_tr: str, reference_time: datetime) -> AnchorResolution:
        """The day ``choice_tr`` resolves to for ``anchor``, at ``reference_time``.

        Byte equality with an authored choice, never a fold or a synonym: a
        near spelling is not a choice, and a date is not something a caller
        may hand in for one.
        """
        self._require_anchor(anchor)
        for choice in self.choices:
            if choice.choice_tr == choice_tr:
                return AnchorResolution(
                    anchor=anchor,
                    choice_tr=choice.choice_tr,
                    resolved_on=reference_day(reference_time, choice.days_before_reference),
                    basis=choice.basis,
                    decision_id=self.decision_id,
                )
        raise AnchorChoiceError(
            f"{anchor}: the answer is not one of the {len(self.choices)} authored choices "
            f"of {self.decision_id} (the value is not echoed: invariant 6)"
        )

    def resolve_unresolved(self, anchor: str, reference_time: datetime) -> AnchorResolution:
        """The day an answer that fitted no choice resolves to (recorded UNCLEAR)."""
        self._require_anchor(anchor)
        return AnchorResolution(
            anchor=anchor,
            choice_tr=None,
            resolved_on=reference_day(reference_time, self.unresolved_days_before_reference),
            basis=AnchorBasis.UNRESOLVED,
            decision_id=self.decision_id,
        )

    def _require_anchor(self, anchor: str) -> None:
        if anchor not in self.anchors:
            raise AnchorChoiceError(
                f"{anchor} is not an active anchor of {self.decision_id}: it has no decided "
                "resolution, so nothing here resolves it"
            )


def reference_day(reference_time: datetime, days_before: int) -> str:
    """The ISO day ``days_before`` calendar days before ``reference_time``'s own day.

    ``reference_time.date()`` in its own timezone — the day
    :func:`protocols.triage.context.temporal_within` compares against. A naive
    time cannot be placed on the session's clock, so it is refused.
    """
    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        raise AnchorChoiceError(
            "the reference time carries no timezone, so its calendar day cannot be "
            "placed on the session's clock"
        )
    if days_before < 0:
        raise AnchorChoiceError("a resolved anchor is never after the reference day")
    return (reference_time.date() - timedelta(days=days_before)).isoformat()


def load_anchor_choice_table(directory: Path = REGISTER_DIR) -> AnchorChoiceTable:
    """CD-05 from the committed register, provenance-checked, as a table."""
    return anchor_choice_table(load_decision(directory / f"{ANCHOR_DECISION_ID}.yaml"))


def anchor_choice_table(decision: ClinicalDecision) -> AnchorChoiceTable:
    """Build the table from one decision, refusing anything it cannot follow exactly."""
    where = decision.id
    if decision.status is not DecisionStatus.ACTIVE:
        raise AnchorChoiceError(
            f"{where} is {decision.status.value}: a draft decision resolves no anchor"
        )
    value = decision.value
    _require(value.get("document_may_feed_anchor") is False, where, "a document may feed it")
    _require(value.get("council_may_fill") is False, where, "the council may fill it")
    _require(value.get("ambiguity") == _MORE_ACUTE, where, "ambiguity is not more_acute")
    question = _text(value.get("anchor_question_tr"), where, "the anchor question is empty")
    choices = _choices(value.get("choices"), where)
    unresolved = _unresolved(value.get("unresolved_answer"), where)
    _require(
        all(unresolved <= choice.days_before_reference for choice in choices),
        where,
        "the unresolved answer resolves to a less acute day than a choice",
    )
    return AnchorChoiceTable(
        decision_id=decision.id,
        anchors=_active_anchors(value.get("anchors"), where),
        question_tr=question,
        choices=choices,
        unresolved_days_before_reference=unresolved,
    )


def _refuse(where: str, reason: str) -> AnchorChoiceError:
    return AnchorChoiceError(f"{where}: {reason}, which this build does not follow")


def _require(condition: bool, where: str, reason: str) -> None:
    if not condition:
        raise _refuse(where, reason)


def _text(node: object, where: str, reason: str) -> str:
    if not isinstance(node, str) or not node.strip():
        raise _refuse(where, reason)
    return node


def _mapping(node: object, where: str, what: str) -> Mapping[str, Any]:
    if not isinstance(node, Mapping):
        raise _refuse(where, f"{what} is not a mapping")
    return node


def _list(node: object, where: str, what: str) -> Sequence[Any]:
    if not isinstance(node, list) or not node:
        raise _refuse(where, f"{what} is not a non-empty list")
    return node


def _days(token: object, where: str) -> int:
    """``reference_day`` → 0, ``reference_day_minus_<n>`` → n. Nothing else."""
    match = _TOKEN.match(token) if isinstance(token, str) else None
    if match is None:
        raise _refuse(where, "a resolution is not a reference_day token")
    days = match.group("days")
    return int(days) if days is not None else 0


def _choices(node: object, where: str) -> tuple[AnchorChoice, ...]:
    built: list[AnchorChoice] = []
    for raw in _list(node, where, "choices"):
        entry = _mapping(raw, where, "a choice")
        text = _text(entry.get("choice_tr"), where, "a choice has no text")
        built.append(AnchorChoice(text, *_choice_resolution(entry, where)))
    texts = [choice.choice_tr for choice in built]
    _require(len(set(texts)) == len(texts), where, "two choices share a text")
    return tuple(built)


def _choice_resolution(entry: Mapping[str, Any], where: str) -> tuple[int, AnchorBasis]:
    status = entry.get("status")
    if status == DecisionStatus.ACTIVE.value:
        return _days(entry.get("resolves_to"), where), AnchorBasis.DECIDED
    _require(status == DecisionStatus.DRAFT_NEEDS_SOURCE.value, where, "a choice's status")
    final = entry.get("resolves_to")
    _require(
        isinstance(final, str) and PLACEHOLDER_SIGNOFF_RE.fullmatch(final.strip()) is not None,
        where,
        "a draft choice's final resolution is no longer open",
    )
    while_draft = _mapping(entry.get("while_draft"), where, "a draft choice's while_draft")
    _require(while_draft.get("never_unknown") is True, where, "a draft choice may read Unknown")
    _require(
        while_draft.get("record_label") == AnchorBasis.WHILE_DRAFT.value,
        where,
        "a draft choice's record label",
    )
    return _days(while_draft.get("resolves_to"), where), AnchorBasis.WHILE_DRAFT


def _unresolved(node: object, where: str) -> int:
    entry = _mapping(node, where, "unresolved_answer")
    _require(
        entry.get("status") == DecisionStatus.ACTIVE.value, where, "the unresolved rule is draft"
    )
    _require(
        entry.get("answer_state") == _UNRESOLVED_STATE,
        where,
        "the unresolved answer is not recorded UNCLEAR",
    )
    return _days(entry.get("resolves_to"), where)


def _active_anchors(node: object, where: str) -> frozenset[str]:
    anchors: set[str] = set()
    for raw in _list(node, where, "anchors"):
        entry = _mapping(raw, where, "an anchor")
        if entry.get("status") != DecisionStatus.ACTIVE.value:
            continue  # a draft rule's anchor stays draft_needs_source in CD-05
        anchors.add(_text(entry.get("anchor"), where, "an anchor names no slot"))
    _require(bool(anchors), where, "no anchor is active")
    return frozenset(anchors)
