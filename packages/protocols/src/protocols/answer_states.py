"""CD-04 as the build reads it: the Turkish hedge table and its answer states (INT-540).

Clinical decision CD-04 (files/00_STATE.md D18; ``packages/protocols/decisions/
CD-04.yaml``) decides which answer state a hedged, qualified, double-negated or
'I do not know' answer to a scripted red-flag question takes: UNCLEAR or
PRESENT_QUALIFIED, never ASKED_ABSENT. This module is the build of that table
and of nothing else:

- **The table is read from CD-04 through** :mod:`protocols.clinical_decisions`,
  which refuses a decision that does not hold its own provenance. No surface,
  qualifier or slot is written here; a test pins that this module's source
  names none of the decision's entries.
- **The follow-up bound is the decision's own number.** CD-04: *"UNCLEAR
  reads Unknown and triggers the slot's follow_up_tr once"*, carried
  machine-readable as ``unclear_follow_up_tr_asks``. The D18 amendment open on
  INT-519 item 5 (resolve an explicit hedge at once) changes that number, and
  this module reads whatever it says.
- **A reading is per slot.** An entry naming ``*`` reads on any scripted slot;
  any other entry reads only on the slots it names. A PRESENT_QUALIFIED entry
  must name its slots: CD-04 makes that mapping "per rule and per slot".
- **Match order is CD-04's**: hedge entries, longest surface first. A surface
  matches whole words of the utterance after Unicode NFC, a Turkish lower-case
  fold (dotted and dotless I) and punctuation-to-space only — never a
  diacritic fold and never a substring, so a near spelling is not an entry and
  a hedged negative never reads as the plain negative inside it. Plain
  negatives are not entries of the table and are not matched here: what a
  plain answer binds is the slot's own business.
- **CD-04's two draft entries** take their sourced UNCLEAR floor (the CKM
  presence value set); whether either is PRESENT_QUALIFIED stays the
  invariant-17 literal under ``draft_needs_source`` (the D18 lane), and the
  table refuses one whose upgrade has stopped being open, because that would be
  a decision this module never saw.

Everything else CD-04 might say that this build does not follow — an UNCLEAR
that does not read Unknown, an unmatched hedge that is not UNCLEAR, a
PRESENT_QUALIFIED entry on every slot, a bound that is not a whole number — is
refused when the table is built, before a session is composed.

**Nothing here echoes a value** (invariant 6): a refusal names the decision and
the field, and :class:`HedgeReading`'s repr shows neither the surface matched
nor its qualifier — both describe what the patient's answer was taken to mean.
"""

from __future__ import annotations

import enum
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
    "ANSWER_STATE_DECISION_ID",
    "ANY_SLOT",
    "AnswerStateError",
    "AnswerStateTable",
    "HedgeBasis",
    "HedgeEntry",
    "HedgeReading",
    "HedgeState",
    "answer_state_table",
    "load_answer_state_table",
    "utterance_tokens",
]

#: The register entry this module builds (files/00_STATE.md D18).
ANSWER_STATE_DECISION_ID: Final = "CD-04"
#: CD-04's spelling of "any scripted slot".
ANY_SLOT: Final = "*"

#: What CD-04's value must say for this build to follow it, key by key.
_FIXED: Final[Mapping[str, str]] = {
    "unclear_evaluates_as": "unknown",
    "present_qualified_evaluates_as": "present",
    "unmatched_hedge": "UNCLEAR",
    "plain_negative_to_scripted_question": "ASKED_ABSENT",
}


class AnswerStateError(ValueError):
    """A decision this module cannot follow exactly, or a table outside it."""


class HedgeState(enum.StrEnum):
    """The two states CD-04 gives a hedged answer. Never ASKED_ABSENT."""

    UNCLEAR = "UNCLEAR"
    #: ASKED_PRESENT carrying the qualifier as an annotation (CD-04).
    PRESENT_QUALIFIED = "PRESENT_QUALIFIED"


class HedgeBasis(enum.StrEnum):
    """Why an entry holds the state it holds."""

    #: An active CD-04 entry.
    DECIDED = "decided"
    #: A draft entry: its sourced UNCLEAR floor; its upgrade is still open.
    DRAFT_FLOOR = "draft_unclear_floor"


@dataclass(frozen=True)
class HedgeEntry:
    """One CD-04 entry, its surface already split into the words it matches."""

    surface_tr: str
    tokens: tuple[str, ...]
    state: HedgeState
    qualifier: str
    slots: frozenset[str]
    basis: HedgeBasis

    def applies_to(self, slot: str) -> bool:
        return ANY_SLOT in self.slots or slot in self.slots


@dataclass(frozen=True, repr=False)
class HedgeReading:
    """What one answer to one slot reads as under CD-04."""

    slot: str
    state: HedgeState
    qualifier: str
    surface_tr: str
    basis: HedgeBasis
    decision_id: str

    def __repr__(self) -> str:
        return (
            f"HedgeReading(slot={self.slot!r}, state={self.state.value!r}, "
            f"decision_id={self.decision_id!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class AnswerStateTable:
    """CD-04 as the runtime reads it: the entries in match order, and the bound."""

    decision_id: str
    #: Longest surface first (CD-04 ``match_order``).
    entries: tuple[HedgeEntry, ...]
    #: CD-04's "once": follow_up_tr asks before an UNCLEAR answer stays UNCLEAR.
    unclear_follow_up_tr_asks: int

    @property
    def present_qualified_slots(self) -> frozenset[str]:
        """Every slot some PRESENT_QUALIFIED entry reads on."""
        return frozenset(
            slot
            for entry in self.entries
            if entry.state is HedgeState.PRESENT_QUALIFIED
            for slot in entry.slots
        )

    def read(self, slot: str, text: str) -> HedgeReading | None:
        """The first entry, in CD-04's order, that ``text`` says on ``slot``."""
        words = utterance_tokens(text)
        for entry in self.entries:
            if entry.applies_to(slot) and _contains(words, entry.tokens):
                return HedgeReading(
                    slot=slot,
                    state=entry.state,
                    qualifier=entry.qualifier,
                    surface_tr=entry.surface_tr,
                    basis=entry.basis,
                    decision_id=self.decision_id,
                )
        return None


def utterance_tokens(text: str) -> tuple[str, ...]:
    """The words of ``text``: NFC, Turkish lower case, punctuation as space."""
    folded = unicodedata.normalize("NFC", text).replace("I", "ı").replace("İ", "i").lower()
    return tuple("".join(ch if ch.isalnum() else " " for ch in folded).split())


def _contains(words: tuple[str, ...], run: tuple[str, ...]) -> bool:
    width = len(run)
    return any(words[start : start + width] == run for start in range(len(words) - width + 1))


def load_answer_state_table(directory: Path = REGISTER_DIR) -> AnswerStateTable:
    """CD-04 from the committed register, provenance-checked, as a table."""
    return answer_state_table(load_decision(directory / f"{ANSWER_STATE_DECISION_ID}.yaml"))


def answer_state_table(decision: ClinicalDecision) -> AnswerStateTable:
    """Build the table from one decision, refusing anything it cannot follow exactly."""
    where = decision.id
    if decision.status is not DecisionStatus.ACTIVE:
        raise AnswerStateError(
            f"{where} is {decision.status.value}: a draft decision reads no answer"
        )
    value = decision.value
    for key, expected in _FIXED.items():
        _require(value.get(key) == expected, where, f"{key} is not {expected}")
    entries = [_entry(raw, where) for raw in _list(value.get("entries"), where, "entries")]
    _require_one_reading_per_slot(entries, where)
    return AnswerStateTable(
        decision_id=decision.id,
        entries=tuple(sorted(entries, key=lambda entry: -len(" ".join(entry.tokens)))),
        unclear_follow_up_tr_asks=_asks(value.get("unclear_follow_up_tr_asks"), where),
    )


def _refuse(where: str, reason: str) -> AnswerStateError:
    return AnswerStateError(f"{where}: {reason}, which this build does not follow")


def _require(condition: bool, where: str, reason: str) -> None:
    if not condition:
        raise _refuse(where, reason)


def _asks(node: object, where: str) -> int:
    if isinstance(node, bool) or not isinstance(node, int) or node < 0:
        raise _refuse(where, "unclear_follow_up_tr_asks is not a whole number of asks")
    return node


def _list(node: object, where: str, what: str) -> Sequence[Any]:
    if not isinstance(node, list) or not node:
        raise _refuse(where, f"{what} is not a non-empty list")
    return node


def _text(node: object, where: str, what: str) -> str:
    if not isinstance(node, str) or not node.strip():
        raise _refuse(where, f"{what} is empty")
    return node


def _require_one_reading_per_slot(entries: Sequence[HedgeEntry], where: str) -> None:
    seen: set[tuple[tuple[str, ...], str]] = set()
    for entry in entries:
        for slot in entry.slots:
            key = (entry.tokens, slot)
            _require(key not in seen, where, "two entries read the same words on one slot")
            seen.add(key)


def _entry(raw: object, where: str) -> HedgeEntry:
    if not isinstance(raw, Mapping):
        raise _refuse(where, "an entry is not a mapping")
    surface = _text(raw.get("surface_tr"), where, "an entry's surface")
    tokens = utterance_tokens(surface)
    _require(bool(tokens), where, "an entry has no surface words")
    state = raw.get("answer_state")
    _require(state in {member.value for member in HedgeState}, where, "an entry's answer state")
    hedge_state = HedgeState(str(state))
    slots = frozenset(
        _text(slot, where, "a slot") for slot in _list(raw.get("slots"), where, "an entry's slots")
    )
    _require(
        hedge_state is HedgeState.UNCLEAR or ANY_SLOT not in slots,
        where,
        "a present-qualified entry reads on every slot",
    )
    return HedgeEntry(
        surface_tr=surface,
        tokens=tokens,
        state=hedge_state,
        qualifier=_text(raw.get("qualifier"), where, "an entry's qualifier"),
        slots=slots,
        basis=_basis(raw, hedge_state, where),
    )


def _basis(raw: Mapping[str, Any], state: HedgeState, where: str) -> HedgeBasis:
    status = raw.get("status")
    if status == DecisionStatus.ACTIVE.value:
        return HedgeBasis.DECIDED
    _require(status == DecisionStatus.DRAFT_NEEDS_SOURCE.value, where, "an entry's status")
    _require(state is HedgeState.UNCLEAR, where, "a draft entry above its UNCLEAR floor")
    upgrade = raw.get("present_qualified_upgrade")
    _require(
        isinstance(upgrade, str) and PLACEHOLDER_SIGNOFF_RE.fullmatch(upgrade.strip()) is not None,
        where,
        "a draft entry's upgrade is no longer open",
    )
    return HedgeBasis.DRAFT_FLOOR
