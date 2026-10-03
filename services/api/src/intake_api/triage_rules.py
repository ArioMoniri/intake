"""INT-446 — the served red-flag rule set the rules-engine hop evaluates,
and the device RED-script catalog projected from it.

Loading is the interlock, and it has two forms, chosen by the tenant's kind
(``intake_platform.red_tenant``).

**A real tenant** (the default, and any kind that is not synthetic). A set is
served only when all of these hold (CLAUDE.md invariants 10, 17 and 21):
- it declares ``served: true``;
- it carries a complete clinical sign-off (HB-C1);
- it holds no ``draft_needs_source`` rule;
- every RED rule resolves to verbatim ``tr`` text for REMOTE, ON_SITE and UNKNOWN.
INT-465: a real tenant never trusts the synthetic-only test key. A test-key
signature configured beside a real tenant's set makes it unservable, never
trusted.

**A synthetic tenant** (INT-465; the owner's decision of 3 Oct 2026 with D18:
simulated patients only, and a physician is required before any real patient).
The set is served only under a valid test-key signature over its exact bytes,
the generic RED's exact bytes, and the exact list of rules served
(``intake_platform.red_signature``). That signature stands in for the physician's
sign-off on that host. ``served:`` and ``clinical_signoff`` are left as the file
says (D17), and a draft rule is still never served: only the signed ``active``
rules are.

Anything else loads as ``None`` and the routes answer 503: fail closed, content
empty. The refusal reason is never put in a response body.

Every string in the catalog is rendered (``protocols.red_render``). Authoring
emphasis is removed, and the tenant's ``acil_location_tr`` segment is resolved,
or dropped when unset (files/04 §8.2). So no ``**`` or ``{{…}}`` reaches a
patient's screen, and no word is changed.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from clinical_schemas.triage import RedLocation
from intake_platform.red_signature import (
    COMMITTED_TRUST_REGISTRY,
    RedSignatureRefused,
    load_signature,
    load_trust_registry,
    verify_red_rule_set,
)
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from protocols.compile.life_threat import LifeThreatSet, LifeThreatSetError, load_life_threat_set
from protocols.dsl import LocationAction, RedFlagRule, UnknownAction
from protocols.generic_red import (
    GENERIC_RED_SCRIPT_IDS,
    GenericRedCopy,
    GenericRedError,
    generic_red_refusals,
    load_generic_red,
    on_site_112_problem,
)
from protocols.red_render import RedRenderError, render_red_text
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


logger = logging.getLogger("intake_api.triage_rules")


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
    onYes: Literal["ON_SITE"]  # noqa: N815 — yes is in the hospital (INT-465 round 4)
    onNo: Literal["REMOTE"]  # noqa: N815
    onNoAnswer: Literal["REMOTE"]  # noqa: N815 — never ON_SITE (INT-465; files/04 §8.1 rule 7)


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


def _render(text: str, tenant: TenantRedConfig) -> str:
    try:
        return render_red_text(text, acil_location_tr=tenant.acil_location_tr)
    except RedRenderError as exc:
        raise _Unservable("a RED script carries markup the renderer does not define") from exc


def _tr(text: Mapping[str, str] | None, tenant: TenantRedConfig) -> str:
    if text is None or not text.get("tr"):
        raise _Unservable("a RED script has no verbatim tr text")
    return _render(text["tr"], tenant)


def _script(action: LocationAction, tenant: TenantRedConfig) -> ScriptOut:
    return ScriptOut(
        primary=action.primary,
        show112=action.show_112,
        actionTr=_tr(action.action_tr, tenant),
        doNotsTr=tuple(_render(text, tenant) for text in action.do_nots_tr.get("tr", ())),
        whyTr=None if action.why_tr is None else _tr(action.why_tr, tenant),
    )


def _question(action: UnknownAction, tenant: TenantRedConfig) -> QuestionOut:
    return QuestionOut(
        askTr=_tr(action.ask_one_tr, tenant),
        onYes=action.on_yes,
        onNo=action.on_no,
        onNoAnswer=action.on_no_answer,
    )


def _catalog(
    version: str,
    rules: tuple[RedFlagRule, ...],
    generic: GenericRedCopy,
    tenant: TenantRedConfig,
) -> CatalogOut:
    scripts: dict[str, ScriptOut] = {}
    questions: dict[str, QuestionOut] = {}
    # INT-453: the generic escalation is pre-positioned beside every rule's
    # scripts, so a RED whose own script cannot be addressed still has words.
    if generic.action is None:  # unreachable: a servable generic carries its copy
        raise _Unservable("the generic RED carries no copy")
    scripts[GENERIC_RED_SCRIPT_IDS[RedLocation.REMOTE]] = _script(generic.action.remote, tenant)
    scripts[GENERIC_RED_SCRIPT_IDS[RedLocation.ON_SITE]] = _script(generic.action.on_site, tenant)
    questions[GENERIC_RED_SCRIPT_IDS[RedLocation.UNKNOWN]] = _question(
        generic.action.unknown, tenant
    )
    for rule in rules:
        if not rule.level.is_red:
            continue
        if rule.register is None or rule.action is None:
            raise _Unservable("a RED rule without register or action block")
        # INT-465: CD-24's ON_SITE 112 check, over every RED rule, not only the generic.
        if on_site_112_problem(rule.action) is not None:
            raise _Unservable("an ON_SITE script names 112 (invariant 21)")
        scripts[script_id(rule.id, RedLocation.REMOTE)] = _script(rule.action.remote, tenant)
        # A pack that authorises 112 under ON_SITE never loads (the DSL refuses
        # it), and the device clamps it again in resolveRed (invariant 21).
        scripts[script_id(rule.id, RedLocation.ON_SITE)] = _script(rule.action.on_site, tenant)
        questions[script_id(rule.id, RedLocation.UNKNOWN)] = _question(rule.action.unknown, tenant)
    return CatalogOut(version=version, scripts=scripts, questions=questions)


def _servable(life_threat: LifeThreatSet) -> None:
    if not life_threat.served:
        raise _Unservable("the set declares served: false")
    if life_threat.clinical_signoff.missing(needs_paediatrician=life_threat.needs_paediatrician):
        raise _Unservable("clinical sign-off incomplete (HB-C1)")
    if any(entry.rule.status is not RuleStatus.ACTIVE for entry in life_threat.rules):
        raise _Unservable("a draft_needs_source rule is never served")


def _served_rules(
    life_threat: LifeThreatSet,
    raw: bytes,
    generic_raw: bytes,
    tenant: TenantRedConfig,
    signature_path: Path | None,
    trust_registry_path: Path,
) -> tuple[RedFlagRule, ...]:
    """The rules this tenant may serve, or :class:`_Unservable`."""
    if tenant.kind is not TenantKind.SYNTHETIC:
        if signature_path is not None:
            # A test-key signature never helps a real tenant: verified here, it is
            # refused on scope before any cryptography (intake_platform.red_signature).
            verify_red_rule_set(
                load_signature(signature_path),
                registry=load_trust_registry(trust_registry_path),
                tenant=tenant,
                life_threat_bytes=raw,
                generic_red_bytes=generic_raw,
                served_rule_ids=(),
            )
            raise _Unservable("a real tenant trusts no test-key signature")  # pragma: no cover
        _servable(life_threat)
        return tuple(entry.rule for entry in life_threat.rules)
    if signature_path is None:
        raise _Unservable("a synthetic tenant serves only a test-key-signed set")
    active = tuple(
        entry.rule for entry in life_threat.rules if entry.rule.status is RuleStatus.ACTIVE
    )
    verify_red_rule_set(
        load_signature(signature_path),
        registry=load_trust_registry(trust_registry_path),
        tenant=tenant,
        life_threat_bytes=raw,
        generic_red_bytes=generic_raw,
        served_rule_ids=tuple(rule.id for rule in active),
    )
    return active


def load_served_red_rules(
    path: Path | None,
    generic_path: Path | None = None,
    *,
    signature_path: Path | None = None,
    tenant: TenantRedConfig | None = None,
    trust_registry_path: Path = COMMITTED_TRUST_REGISTRY,
    allow_fixture_snapshots: bool = False,
) -> ServedRedRules | None:
    """The served rule set at ``path``, or None (the routes answer 503).

    Serve precondition (INT-453): the generic RED escalation at
    ``generic_path`` must be servable: present and not ``draft_needs_source``
    (``protocols.generic_red``). A blank generic can never reach a live tenant,
    so with it absent or draft nothing is served at all.

    INT-465: ``tenant`` decides the interlock (module docstring). It defaults to
    a real tenant, which never trusts the test key. ``allow_fixture_snapshots``
    admits a set citing a tests/fixtures snapshot; ApiSettings.from_env never sets
    it, so only the test harness can.
    """
    if path is None or generic_path is None:
        return None
    served_for = tenant if tenant is not None else TenantRedConfig()
    try:
        # Each document is read once: the bytes hashed and checked against the
        # signature are the bytes parsed and served (INT-465).
        raw = path.read_bytes()
        generic_raw = generic_path.read_bytes()
        generic = load_generic_red(generic_path, data=generic_raw)
        if generic_red_refusals(generic):
            raise _Unservable("the generic RED copy is not servable (CD-24)")
        life_threat = load_life_threat_set(
            path, data=raw, allow_fixture_snapshots=allow_fixture_snapshots
        )
        rules = _served_rules(
            life_threat, raw, generic_raw, served_for, signature_path, trust_registry_path
        )
        version = hashlib.sha256(raw + generic_raw).hexdigest()
        return ServedRedRules(
            version=version, rules=rules, catalog=_catalog(version, rules, generic, served_for)
        )
    except RedSignatureRefused as refused:
        # An id-shaped code only: no key material, no rule content (invariant 6).
        # files/10 §9 protocol-registry signal: a signature failure is visible.
        logger.warning("red rule set signature refused: %s", refused.code)
        return None
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
