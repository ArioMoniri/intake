"""INT-446 — the served red-flag rule set the rules-engine hop evaluates,
and the device RED-script catalog projected from it.

Loading is the interlock: a set is served only when it declares
``served: true``, carries a complete clinical sign-off (HB-C1), holds no
``draft_needs_source`` rule, and every RED rule resolves to verbatim ``tr``
text for REMOTE, ON_SITE and UNKNOWN (CLAUDE.md invariants 10, 17 and 21).
Anything else loads as ``None`` and the routes answer 503 — fail closed,
content empty. The refusal reason is never put in a response body.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from clinical_schemas.triage import RedLocation
from protocols.compile.life_threat import LifeThreatSet, LifeThreatSetError, load_life_threat_set
from protocols.dsl import LocationAction, RedFlagRule, UnknownAction
from protocols.generic_red import (
    GENERIC_RED_SCRIPT_IDS,
    GenericRedCopy,
    GenericRedError,
    generic_red_refusals,
    load_generic_red,
)
from protocols.types import RuleStatus
from pydantic import BaseModel, ConfigDict

__all__ = [
    "CatalogOut",
    "QuestionOut",
    "ScriptOut",
    "ServedRedRules",
    "load_served_red_rules",
    "resolved_action",
    "script_id",
]


def script_id(rule_id: str, location: RedLocation) -> str:
    """The id a trigger names and the catalog keys on: rule plus location.
    Lower-case so it matches the device's id shape (``^[a-z0-9][a-z0-9._-]*$``)."""
    return f"{rule_id}.{location.value.lower()}"


class ScriptOut(BaseModel):
    """One location's action, verbatim. Field names mirror the device's
    ``RedScript`` so the catalog drops in without a translation layer."""

    model_config = ConfigDict(frozen=True)

    primary: str
    show112: bool
    actionTr: str  # noqa: N815 — wire name of the device's RedScript
    doNotsTr: tuple[str, ...]  # noqa: N815
    whyTr: str | None  # noqa: N815


class QuestionOut(BaseModel):
    """The UNKNOWN branch: one question, then the rule's own branch targets."""

    model_config = ConfigDict(frozen=True)

    askTr: str  # noqa: N815
    onYes: Literal["ON_SITE", "REMOTE"]  # noqa: N815
    onNo: Literal["ON_SITE", "REMOTE"]  # noqa: N815
    onNoAnswer: Literal["ON_SITE", "REMOTE"]  # noqa: N815


class CatalogOut(BaseModel):
    version: str
    scripts: dict[str, ScriptOut]
    questions: dict[str, QuestionOut]


@dataclass(frozen=True)
class ServedRedRules:
    """The served set, its content hash, and the device catalog built from it."""

    version: str
    rules: tuple[RedFlagRule, ...]
    catalog: CatalogOut


class _Unservable(ValueError):
    """The set cannot be served; the reason never reaches a response body."""


def _tr(text: Mapping[str, str] | None) -> str:
    if text is None or not text.get("tr"):
        raise _Unservable("a RED script has no verbatim tr text")
    return text["tr"]


def _script(action: LocationAction) -> ScriptOut:
    return ScriptOut(
        primary=action.primary,
        show112=action.show_112,
        actionTr=_tr(action.action_tr),
        doNotsTr=tuple(action.do_nots_tr.get("tr", ())),
        whyTr=None if action.why_tr is None else _tr(action.why_tr),
    )


def _question(action: UnknownAction) -> QuestionOut:
    return QuestionOut(
        askTr=_tr(action.ask_one_tr),
        onYes=action.on_yes,
        onNo=action.on_no,
        onNoAnswer=action.on_no_answer,
    )


def _catalog(version: str, rules: tuple[RedFlagRule, ...], generic: GenericRedCopy) -> CatalogOut:
    scripts: dict[str, ScriptOut] = {}
    questions: dict[str, QuestionOut] = {}
    # INT-453: the generic escalation is pre-positioned beside every rule's
    # scripts, so a RED whose own script cannot be addressed still has words.
    if generic.action is None:  # unreachable: a servable generic carries its copy
        raise _Unservable("the generic RED carries no copy")
    scripts[GENERIC_RED_SCRIPT_IDS[RedLocation.REMOTE]] = _script(generic.action.remote)
    scripts[GENERIC_RED_SCRIPT_IDS[RedLocation.ON_SITE]] = _script(generic.action.on_site)
    questions[GENERIC_RED_SCRIPT_IDS[RedLocation.UNKNOWN]] = _question(generic.action.unknown)
    for rule in rules:
        if not rule.level.is_red:
            continue
        if rule.register is None or rule.action is None:
            raise _Unservable("a RED rule without register or action block")
        scripts[script_id(rule.id, RedLocation.REMOTE)] = _script(rule.action.remote)
        # A pack that authorises 112 under ON_SITE never loads (the DSL refuses
        # it), and the device clamps it again in resolveRed (invariant 21).
        scripts[script_id(rule.id, RedLocation.ON_SITE)] = _script(rule.action.on_site)
        questions[script_id(rule.id, RedLocation.UNKNOWN)] = _question(rule.action.unknown)
    return CatalogOut(version=version, scripts=scripts, questions=questions)


def _servable(life_threat: LifeThreatSet) -> None:
    if not life_threat.served:
        raise _Unservable("the set declares served: false")
    if life_threat.clinical_signoff.missing(needs_paediatrician=life_threat.needs_paediatrician):
        raise _Unservable("clinical sign-off incomplete (HB-C1)")
    if any(entry.rule.status is not RuleStatus.ACTIVE for entry in life_threat.rules):
        raise _Unservable("a draft_needs_source rule is never served")


def load_served_red_rules(
    path: Path | None, generic_path: Path | None = None
) -> ServedRedRules | None:
    """The served rule set at ``path``, or None (the routes answer 503).

    Serve precondition (INT-453): the generic RED escalation at
    ``generic_path`` must be servable — present and not ``draft_needs_source``
    (``protocols.generic_red``). A blank generic can never reach a live tenant,
    so with it absent or draft nothing is served at all.
    """
    if path is None or generic_path is None:
        return None
    try:
        generic = load_generic_red(generic_path)
        if generic_red_refusals(generic):
            raise _Unservable("the generic RED copy is not servable (CD-24)")
        raw = path.read_bytes()
        life_threat = load_life_threat_set(path)
        _servable(life_threat)
        rules = tuple(entry.rule for entry in life_threat.rules)
        version = hashlib.sha256(raw + generic_path.read_bytes()).hexdigest()
        return ServedRedRules(
            version=version, rules=rules, catalog=_catalog(version, rules, generic)
        )
    except (OSError, LifeThreatSetError, GenericRedError, _Unservable):
        return None


def resolved_action(
    rule: RedFlagRule, location: RedLocation
) -> LocationAction | UnknownAction | None:
    """The rule's own frozen action object for one location (or None)."""
    if rule.action is None:
        return None
    if location is RedLocation.REMOTE:
        return rule.action.remote
    if location is RedLocation.ON_SITE:
        return rule.action.on_site
    return rule.action.unknown
