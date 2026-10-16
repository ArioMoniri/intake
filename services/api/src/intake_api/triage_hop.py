"""INT-446 — the rules-engine hop for the app's dialogue and typed lanes.

Every bound answer the app commits is evaluated here by the deterministic
rules engine (``protocols.triage.evaluate_triage``), the only producer of
RED/YELLOW (CLAUDE.md invariant 1). There is no second implementation of a
rule anywhere: the device posts the answers it has bound, this route runs the
served rule set over them, and a RED comes back as exactly the packet the
voice runtime sends over the LiveKit data channel (``red_path.RedTriggerMessage``:
``kind``, ``ruleId``, ``register``, ``location``, ``scriptId``) — identifiers
and axes only, so the device decodes both with the one schema-constrained
decoder (apps/mobile/src/lib/livekit/red.ts ``decodeRedTrigger``).

Two routes:

- ``GET /v1/triage/red-scripts`` — the RED scripts of the served set, fetched
  by the device BEFORE any evaluation can return a RED, and held there. The
  words a RED shows are never fetched at RED time (invariant 21): the trigger
  names a script the device already holds. Every string is the rule's own
  ``tr`` entry, verbatim (invariant 10); nothing here composes text.
- ``POST /v1/triage/evaluate`` — the bound answers, the RED location axis the
  device derived from the visit lifecycle (files/02 §5.3 Axis 3; never guessed
  here) and the session's reference time. Returns the trigger or the level.

Fail closed, content empty (HUMAN_BLOCKERS rule 2). The served set comes from
``ApiSettings.triage_rules_path`` through ``triage_rules.load_served_red_rules``.
No path, an unreadable file, a RED rule whose action cannot be resolved to
verbatim ``tr`` text for all three locations or that names 112 under ON_SITE,
or a generic RED copy that is not servable (CD-24): every one of those is a 503
``triage_unconfigured`` on both routes — never an empty catalog and never a
GREEN, because "no rule fired" is not something a server without rules can say.
Which rules a tenant gets is the tenant's kind (INT-465). A real tenant needs a
set that declares ``served: true``, carries the complete clinical sign-off
(HB-C1) and holds no draft rule; nobody has signed, so its shipped state is that
503. A synthetic tenant on the AWS test host serves the set's active rules only
under the test-key signature over exactly those bytes and that rule list (D18;
owner decision of 3 Oct 2026; ``intake_platform.red_signature``), and a real
tenant refuses that key.

Consent: the evaluation processes the patient's intake answers, so both routes
run under the core intake scope. Nothing is stored, nothing is logged — not a
slot, not a value, not a rule id (invariant 6).
"""

from __future__ import annotations

from typing import Annotated, Literal

from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, TriageLevel
from fastapi import APIRouter
from protocols.dsl import RedFlagRule
from protocols.triage import TriageContext, TriageEvaluation, evaluate_triage
from protocols.triage.context import SlotAnswer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from intake_api.auth import Principal
from intake_api.consent_guard import require_scopes
from intake_api.errors import triage_unconfigured
from intake_api.state import State
from intake_api.triage_rules import CatalogOut, ServedRedRules, resolved_action, script_id

__all__ = ["MAX_ANSWERS", "router"]

CORE_SCOPE = "core"
#: Bounds at the system boundary: an intake has a few dozen questions; a
#: request with more slots than this is not an intake.
MAX_ANSWERS = 512
_MAX_TEXT = 2000

router = APIRouter(prefix="/v1/triage", tags=["triage"])

SlotRef = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)*$", max_length=128)]
BoundText = Annotated[str, StringConstraints(max_length=_MAX_TEXT)]
BoundValue = BoundText | Annotated[list[BoundText], Field(max_length=64)]


class EvaluateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: RedLocation = Field(
        description="files/02 §5.3 Axis 3, derived by the device from the visit "
        "lifecycle; required, no default (invariant 21)."
    )
    reference_time: AwareDatetime = Field(
        description="The session's 'now' (files/13 §9.2) — the clock the tense windows read."
    )
    answers: dict[SlotRef, BoundValue] = Field(
        max_length=MAX_ANSWERS,
        description="Bound answers only: what the patient confirmed or entered, keyed "
        "by slot reference. Every entry reads as asked-and-present.",
    )


class RedTriggerOut(BaseModel):
    """The data-channel packet, verbatim in shape (red_path.RedTriggerMessage)."""

    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["red_trigger"] = "red_trigger"
    ruleId: str  # noqa: N815
    # ``register`` on the wire; renamed here because BaseModel has a member of that name.
    red_register: RedRegister = Field(alias="register")
    location: RedLocation
    scriptId: str  # noqa: N815


class LevelOut(BaseModel):
    kind: Literal["triage_level"] = "triage_level"
    level: Literal["GREEN", "YELLOW"]


def _context(payload: EvaluateIn) -> TriageContext:
    answers: dict[str, SlotAnswer] = {}
    for ref, value in payload.answers.items():
        carried: JsonValue = list(value) if isinstance(value, list) else value
        answers[ref] = SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(carried,))
    return TriageContext(reference_time=payload.reference_time, answers=answers)


def _winner(
    rules: tuple[RedFlagRule, ...],
    evaluation: TriageEvaluation,
    register: RedRegister,
    location: RedLocation,
) -> str:
    """The fired rule whose register AND script the engine returned.

    ``result.rules`` is ordered by severity then id, which is not the engine's
    winner order (it breaks severity ties on register restrictiveness), so its
    first entry can name a rule whose script is not the one the engine chose.
    Register and script travel together (files/02 §5.3), so the id is found
    from the engine's own outputs — never re-decided here. Two rules that
    match on both carry the same register and the same verbatim action, so
    either id presents identically; the lowest is taken for determinism.
    """
    fired = {fire.id for fire in evaluation.result.rules}
    matches = sorted(
        rule.id
        for rule in rules
        if rule.id in fired
        and rule.level is evaluation.ek4
        and rule.register is register
        and resolved_action(rule, location) == evaluation.action
    )
    if not matches:  # unreachable: the engine's winner is always among them
        raise triage_unconfigured()
    return matches[0]


def _served(state: State) -> ServedRedRules:
    served = state.served_red_rules()
    if served is None:
        raise triage_unconfigured()
    return served


@router.get(
    "/red-scripts",
    response_model=CatalogOut,
    dependencies=[require_scopes(CORE_SCOPE)],
)
async def red_scripts(state: State, principal: Principal) -> CatalogOut:
    """The pre-positioned RED scripts of the served set."""
    return _served(state).catalog


@router.post(
    "/evaluate",
    response_model=RedTriggerOut | LevelOut,
    dependencies=[require_scopes(CORE_SCOPE)],
)
async def evaluate(
    payload: EvaluateIn, state: State, principal: Principal
) -> RedTriggerOut | LevelOut:
    """Run the served rules over the bound answers (invariant 1)."""
    served = _served(state)
    evaluation = evaluate_triage(served.rules, _context(payload), payload.location)
    result = evaluation.result
    if result.level is TriageLevel.RED:
        register, location = result.register, result.location
        if register is None or location is None:  # unreachable: RulesTriageResult validates
            raise triage_unconfigured()
        winner = _winner(served.rules, evaluation, register, location)
        return RedTriggerOut(
            ruleId=winner,
            register=register,
            location=location,
            scriptId=script_id(winner, location),
        )
    return LevelOut(level="YELLOW" if result.level is TriageLevel.YELLOW else "GREEN")
