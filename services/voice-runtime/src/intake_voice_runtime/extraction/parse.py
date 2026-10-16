"""Model output in, typed slot values out — and a refusal for everything else.

Two levels of strictness, and the split is deliberate:

- **A malformed *document* is refused.** Unknown or missing top-level keys, a
  non-JSON body, a candidate flag of the wrong shape: the model answered a
  schema that does not exist, so nothing in the answer is trustworthy and the
  whole extraction fails as ``schema_invalid``. Dropping the unknown key and
  keeping the rest would let the remainder of a hallucinated answer through —
  and the unknown key we most expect is ``level`` (CLAUDE.md invariant 1).
- **A malformed *slot* is flagged and withheld.** The slot map's keys are the
  model's guess at a ref and its values are the model's reading of a value;
  one bad guess should not throw away the turn's other answers. So the slot
  does not bind, an :class:`ExtractionFlag` records which and why, and the
  question stays unanswered — which is the state the engine already knows how
  to act on (files/13 §11.1 ``data_gaps``).

**Invariant 22 lives here**, in three rules that all fail toward *not binding*:

1. **Refs match by equality, never by prefix.** files/03 §4.9.6: *"never
   substring-match `üre` — `Üre 45 mg/dL` is near-normal while `BUN 45 mg/dL`
   is markedly azotaemic (factor 2.14), and `Üre Nitrojeni` contains the token
   'Üre' but means BUN."*
2. **A unit disagreement raises a flag and converts nothing.** Ranking the
   magnitude over the printed token — which is what §4.9.6 asks for — needs
   the analyte's expected magnitude, and that is a clinical table no human has
   supplied. The fail-closed reading of the same rule is available and is what
   runs: withhold the value, record the disagreement, convert nothing.
3. **A numeric slot answered with a string is refused, never parsed.**
   ``parseFloat("2,5")`` is 2 (−20 % on a dose), ``parseFloat("1.500")`` is 1.5
   (÷1000) and ``>100.000 mIU/mL`` under an en-US parse is 100.0 (×1000).
   §4.9.6 says the separator can only be resolved per value against an expected
   magnitude; without one, the answer is a refusal rather than a guess.

Numbers are read with ``parse_float=Decimal`` so a decimal literal never
touches binary floating point on the way in (files/13 §9.5).

**No message here names a value.** Keys, refs and counts only (invariant 6).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from clinical_schemas.triage import CandidateFlag
from protocols.dsl import Slot
from protocols.types import SlotType

from intake_voice_runtime.extraction.errors import ExtractionRefused
from intake_voice_runtime.extraction.result import (
    ExtractionFlag,
    ExtractionResult,
    FlagReason,
    SlotUpdate,
    SlotValue,
)
from intake_voice_runtime.extraction.schema import (
    CONFIDENCE_KEY,
    SLOT_ENTRY_KEYS,
    TOP_LEVEL_KEYS,
    UNIT_KEY,
    VALUE_KEY,
    date_choices,
)

__all__ = ["parse_extraction"]

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_CANDIDATE_KEYS = ("text", "evidence")


def _document(raw: str) -> dict[str, Any]:
    try:
        loaded = json.loads(raw, parse_float=Decimal)
    except (json.JSONDecodeError, InvalidOperation):
        raise ExtractionRefused(
            "the completion is not one JSON document. The body is deliberately not "
            "echoed: it is the model's reading of what a patient said (invariant 6)"
        ) from None
    if not isinstance(loaded, dict):
        raise ExtractionRefused("the completion is not a JSON object")
    present = set(loaded)
    unknown = sorted(present - set(TOP_LEVEL_KEYS))
    if unknown:
        raise ExtractionRefused(
            f"the completion carries keys the output schema does not declare: {unknown}. "
            "The document is refused rather than trimmed — the key set is closed, and "
            "the key most likely to appear here is a triage level the LLM may not "
            "produce (CLAUDE.md invariant 1). No value is echoed."
        )
    missing = sorted(set(TOP_LEVEL_KEYS) - present)
    if missing:
        raise ExtractionRefused(f"the completion is missing required keys: {missing}")
    return loaded


def _candidate_flags(raw: Any) -> tuple[CandidateFlag, ...]:
    if not isinstance(raw, list):
        raise ExtractionRefused("key 'candidate_flags' must be a JSON array")
    flags: list[CandidateFlag] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict) or set(entry) != set(_CANDIDATE_KEYS):
            raise ExtractionRefused(
                f"candidate_flags[{index}] must carry exactly {list(_CANDIDATE_KEYS)}"
            )
        text, evidence = entry["text"], entry["evidence"]
        if not isinstance(text, str) or not isinstance(evidence, str):
            raise ExtractionRefused(f"candidate_flags[{index}] fields must be strings")
        flags.append(CandidateFlag(text=text, evidence=evidence))
    return tuple(flags)


def _confidence(raw: Any) -> Decimal | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, Decimal)):
        return None
    value = Decimal(raw) if isinstance(raw, int) else raw
    return value if Decimal(0) <= value <= Decimal(1) else None


def _coerce(
    slot: Slot, raw: Any, valuesets: Mapping[str, tuple[str, ...]]
) -> SlotValue | FlagReason:
    """One value, coerced to the declared type — or the reason it did not."""
    if slot.type is SlotType.BOOLEAN:
        return raw if isinstance(raw, bool) else FlagReason.WRONG_TYPE
    if slot.type in {SlotType.INTEGER, SlotType.DECIMAL, SlotType.QUANTITY}:
        if isinstance(raw, str):
            return FlagReason.AMBIGUOUS_NUMERAL
        if isinstance(raw, bool) or not isinstance(raw, (int, Decimal)):
            return FlagReason.WRONG_TYPE
        if slot.type is SlotType.INTEGER:
            return raw if isinstance(raw, int) else FlagReason.WRONG_TYPE
        return Decimal(raw) if isinstance(raw, int) else raw
    if slot.type is SlotType.CODE:
        if not isinstance(raw, str):
            return FlagReason.WRONG_TYPE
        members = valuesets.get(slot.valueset or "", ())
        return raw if raw in members else FlagReason.VALUESET_VIOLATION
    if slot.type is SlotType.DATE:
        if not isinstance(raw, str):
            return FlagReason.WRONG_TYPE
        choices = date_choices(slot)
        if choices:
            # INT-522: a closed-choice date binds only an authored choice. A day
            # the model wrote itself is outside the set it was offered — it was
            # given no reference date to compute one from — and is refused.
            return raw if raw in choices else FlagReason.VALUESET_VIOLATION
        return raw if _ISO_DATE.match(raw) else FlagReason.WRONG_TYPE
    return raw if isinstance(raw, str) else FlagReason.WRONG_TYPE


def parse_extraction(
    *,
    raw: str,
    slots: Mapping[str, Slot],
    valuesets: Mapping[str, tuple[str, ...]],
    step_id: str,
) -> ExtractionResult:
    """Validate one completion against the step's declared slot schemas."""
    document = _document(raw)
    clarification_needed = document["clarification_needed"]
    if not isinstance(clarification_needed, bool):
        raise ExtractionRefused("key 'clarification_needed' must be a JSON boolean")
    candidate_flags = _candidate_flags(document["candidate_flags"])
    raw_slots = document["slots"]
    if not isinstance(raw_slots, dict):
        raise ExtractionRefused("key 'slots' must be a JSON object")

    updates: list[SlotUpdate] = []
    flags: list[ExtractionFlag] = []
    # Sorted, so the result of one completion does not depend on the order the
    # model happened to emit its keys in — a replayed session must reconcile
    # identically (files/13 §9.2, the fold).
    for ref in sorted(raw_slots):
        reason = _bind(
            ref=ref,
            entry=raw_slots[ref],
            slots=slots,
            valuesets=valuesets,
            updates=updates,
        )
        if reason is not None:
            flags.append(ExtractionFlag(ref=ref, reason=reason))
    return ExtractionResult(
        step_id=step_id,
        slot_updates=tuple(updates),
        candidate_flags=candidate_flags,
        clarification_needed=clarification_needed,
        flags=tuple(flags),
    )


def _bind(
    *,
    ref: str,
    entry: Any,
    slots: Mapping[str, Slot],
    valuesets: Mapping[str, tuple[str, ...]],
    updates: list[SlotUpdate],
) -> FlagReason | None:
    """Bind one slot, or return the single reason it did not.

    At most one flag per slot: the first refusal wins, and the order below is
    the order of severity — a ref that names nothing cannot have a unit
    checked, and a value that cannot be read cannot be checked against a
    confidence floor.
    """
    slot = slots.get(ref)
    if slot is None:
        return FlagReason.UNKNOWN_SLOT_REF
    if not isinstance(entry, dict) or not set(entry) <= set(SLOT_ENTRY_KEYS):
        return FlagReason.WRONG_TYPE
    if VALUE_KEY not in entry or CONFIDENCE_KEY not in entry:
        return FlagReason.WRONG_TYPE
    if slot.type is SlotType.QUANTITY:
        unit = entry.get(UNIT_KEY)
        if not isinstance(unit, str):
            return FlagReason.WRONG_TYPE
        # Byte equality, never a fold and never a synonym table: files/03
        # §4.9.6 keeps `µ` U+00B5 and `μ` U+03BC distinct on purpose, and a
        # synonym table is where a silent conversion would be reintroduced.
        if unit != slot.unit:
            return FlagReason.UNIT_DISAGREEMENT
    elif UNIT_KEY in entry:
        return FlagReason.WRONG_TYPE
    confidence = _confidence(entry[CONFIDENCE_KEY])
    if confidence is None:
        return FlagReason.WRONG_TYPE
    coerced = _coerce(slot, entry[VALUE_KEY], valuesets)
    if isinstance(coerced, FlagReason):
        return coerced
    # The floor is the pack author's (files/12 §3.2 ``min_confidence``). Where
    # the author declared none, none applies: a default floor would be a
    # clinical value chosen by an engineer, which HUMAN_BLOCKERS rule 1
    # forbids outright.
    if slot.min_confidence is not None and confidence < slot.min_confidence:
        return FlagReason.BELOW_CONFIDENCE_FLOOR
    updates.append(SlotUpdate(ref=ref, value=coerced, confidence=confidence))
    return None
