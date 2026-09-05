"""Flag governance — mandatory change reasons and four-eyes on safety flags (INT-188).

INT-188's one-line acceptance — *"change reasons mandatory; safety flags list
incl. device_functions, s2s, learning-apply"* — was written before the 25 Aug
admin-console security audit, which is the authority this module follows where
the two meet (files/08 §0b F1/F2, §3, §8.2; files/10 §9 inv. 12/34).

The write side of :mod:`intake_platform.flags`. That module is the read side:
safety flags read False and cannot be defaulted open. This module is where a
change *originates*, and it holds three properties the read side cannot:

- **invariant 34 — no safety key in the generic flag store.** Unleash API
  tokens flip flags with no audit row and CI runners hold them, so a safety key
  in the generic store is a governance hole regardless of its value.
  :func:`guard_generic_flag_write` and :func:`scan_generic_store` are that
  scan; :meth:`FlagGovernor.set_operational` refuses a safety key rather than
  writing one. Safety flags are decided only by the ceremony below.
- **invariant 12 — a flag governs rollout/exposure, never clinical semantics.**
  A flag can never modify red-flag levels, instruments, consent texts, the
  Talker tool list, PolicyGuard or profile routing. Those surfaces are not even
  nameable as flag keys (:func:`guard_flag_key`), and the governed set is
  disjoint from them. ``learning_apply`` is a safety flag, but even ON it only
  gates whether a learning *proposal* may be applied through the gated PR path
  (inv. 12 keeps learning proposal-only) — it is not a lever over any clinical
  value.
- **four-eyes on the dangerous direction, one key on the safe direction.**
  Enabling a safety-list capability opens the tier-3 ceremony
  (:data:`~intake_platform.admin.actions.SAFETY_FLAG_ENABLE`) and applies only
  after a distinct human, credential and session — a distinct organisation at
  tier 3 — approves with a fresh single-use assertion. Pulling a flag to its
  safe state is one eligible key (:data:`SAFETY_FLAG_DISABLE_ROLES`), because a
  second approver on the safe direction is an availability control on a safety
  control (files/08 §0c F17).

Like :mod:`~intake_platform.admin.break_glass`, this module is pure rule: it
holds no audit chain and no metric. The write-ahead ``admin_audit.v1`` row and
the self-approval counter belong to the calling surface (``services/api/admin``),
which is the one choke point that already attaches them.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, MutableMapping
from datetime import timedelta

from intake_platform.admin.actions import SAFETY_FLAG_ENABLE
from intake_platform.admin.four_eyes import (
    ActorBlock,
    FourEyesService,
    Justification,
    PendingAction,
)
from intake_platform.admin.roles import AdminRole
from intake_platform.flags import SAFETY_FLAG_DEFAULTS

__all__ = [
    "CLINICAL_SEMANTIC_SURFACES",
    "MIN_CHANGE_REASON_CHARS",
    "SAFETY_FLAG_DISABLE_ROLES",
    "SAFETY_FLAG_ENABLE",
    "SAFETY_FLAG_KEYS",
    "ChangeReasonMissing",
    "ChangeReasonTooShort",
    "ClinicalSemanticSurface",
    "DisableRoleIneligible",
    "FlagChangeReason",
    "FlagGovernanceRefused",
    "FlagGovernor",
    "NotASafetyFlag",
    "SafetyKeyInGenericStore",
    "build_flag_change_justification",
    "guard_flag_key",
    "guard_generic_flag_write",
    "is_safety_flag",
    "scan_generic_store",
]

#: The safety-flag set IS the read-side facade's set, verbatim — one source of
#: truth. "safety" must mean the same thing on the read path and the write path,
#: so a flag added to :data:`intake_platform.flags.SAFETY_FLAG_DEFAULTS` is
#: governed here by construction rather than by a second list kept in step.
SAFETY_FLAG_KEYS: frozenset[str] = frozenset(SAFETY_FLAG_DEFAULTS)

#: invariant 12: the levers a flag may NEVER pull. These are not flag keys and
#: naming one as a flag is refused — the boundary is structural, not a review
#: note. Matched by name against the surfaces invariant 12 enumerates.
CLINICAL_SEMANTIC_SURFACES: frozenset[str] = frozenset(
    {
        "red_flag_levels",
        "instruments",
        "consent_texts",
        "talker_tool_list",
        "policyguard",
        "profile_routing",
    }
)

#: files/08 §0c F17 / asymmetric authority: the SAFE direction (a safety flag
#: OFF) takes one key. clinical_lead and sre_oncall are F17's named pair —
#: "any single sre_oncall or clinical_lead may … turn device_functions off";
#: platform_owner is the platform authority above them. Turning a flag OFF only
#: ever reduces capability.
SAFETY_FLAG_DISABLE_ROLES: frozenset[AdminRole] = frozenset(
    {AdminRole.CLINICAL_LEAD, AdminRole.SRE_ONCALL, AdminRole.PLATFORM_OWNER}
)

#: A change reason must be a real explanation. The floor rejects a non-reason
#: ("x", "."); it is lighter than break-glass's 20 (files/08 §2.5) because a
#: flag edit is not a read of patient content — the requirement INT-188 states
#: is that a reason is MANDATORY, which is the empty-text refusal below.
MIN_CHANGE_REASON_CHARS = 12


class FlagChangeReason(enum.StrEnum):
    """The closed category a flag change is filed under. Small on purpose: every
    member is a class a change can be grouped by and an alert written against,
    which an open reason string could never be."""

    ROLLOUT_EXPANSION = "rollout_expansion"
    ROLLOUT_ROLLBACK = "rollout_rollback"
    INCIDENT_MITIGATION = "incident_mitigation"
    EXPERIMENT_START = "experiment_start"
    EXPERIMENT_END = "experiment_end"
    CONFIG_CORRECTION = "config_correction"
    STUDY_ENABLEMENT = "study_enablement"


class FlagGovernanceRefused(Exception):
    """Base refusal. ``code`` is a stable machine code — a refusal reaches an
    HTTP body and a metric label, and narrative in either is how PHI travels
    (invariant 6)."""

    code = "flag_governance_refused"


class ChangeReasonMissing(FlagGovernanceRefused):
    code = "flag_change_reason_missing"


class ChangeReasonTooShort(FlagGovernanceRefused):
    code = "flag_change_reason_too_short"


class SafetyKeyInGenericStore(FlagGovernanceRefused):
    """invariant 34: a safety-list key may not live in the generic flag store."""

    code = "flag_safety_key_in_generic_store"


class ClinicalSemanticSurface(FlagGovernanceRefused):
    """invariant 12: a flag key names a clinical-semantic surface."""

    code = "flag_clinical_semantic_surface"


class NotASafetyFlag(FlagGovernanceRefused):
    """The safety-flag ceremony was asked to govern an operational flag."""

    code = "flag_not_a_safety_flag"


class DisableRoleIneligible(FlagGovernanceRefused):
    """A role outside :data:`SAFETY_FLAG_DISABLE_ROLES` tried the safe direction."""

    code = "flag_disable_role_ineligible"


def is_safety_flag(key: str) -> bool:
    """True if ``key`` is on the safety list (:data:`SAFETY_FLAG_KEYS`)."""
    return key in SAFETY_FLAG_KEYS


def guard_flag_key(key: str) -> None:
    """invariant 12: a clinical-semantic surface is not a flag. Naming one as a
    flag key is refused before anything else looks at the key, so no code path
    from a flag change can reach a clinical value."""
    if key in CLINICAL_SEMANTIC_SURFACES:
        raise ClinicalSemanticSurface(
            f"{key!r} is a clinical-semantic surface, not a rollout flag: a flag "
            "governs exposure and can never modify red-flag levels, instruments, "
            "consent texts, the Talker tool list, PolicyGuard or profile routing "
            "(invariant 12)"
        )


def guard_generic_flag_write(key: str) -> None:
    """invariant 34: no safety-list key enters the generic flag store. A safety
    key is decided only by the four-eyes ceremony, never by an operational write
    and never by an Unleash API token."""
    if is_safety_flag(key):
        raise SafetyKeyInGenericStore(
            f"{key!r} is a safety flag: it may not enter the generic flag store "
            "(invariant 34) — a safety flag changes only through the four-eyes ceremony"
        )


def scan_generic_store(store: Mapping[str, bool]) -> frozenset[str]:
    """The flag-store scan half of invariant 34's ``device_flag_gate_guard``:
    every safety-list key present in a generic store, whatever its value. A
    non-empty result is a governance hole."""
    return frozenset(key for key in store if is_safety_flag(key))


def build_flag_change_justification(
    *, reason_class: FlagChangeReason, free_text: str
) -> Justification:
    """A mandatory change reason: a closed category plus a real explanation. The
    submitted text is never echoed on refusal (invariant 6). A flag change is
    not a processor break-glass, so it carries no controller-instruction
    reference."""
    stripped = free_text.strip()
    if not stripped:
        raise ChangeReasonMissing("a flag change needs a reason (INT-188): the free text is empty")
    if len(stripped) < MIN_CHANGE_REASON_CHARS:
        raise ChangeReasonTooShort(
            f"a flag change reason needs at least {MIN_CHANGE_REASON_CHARS} characters "
            "of explanation; the submitted text is not echoed here (invariant 6)"
        )
    return Justification(
        reason_class=reason_class, free_text=stripped, controller_instruction_ref=None
    )


def _require_reason(justification: Justification) -> None:
    """A change reason is mandatory at the WRITE, not only at the builder: a
    caller that hand-builds a blank :class:`Justification` is refused too."""
    if not justification.free_text.strip():
        raise ChangeReasonMissing("a flag change needs a reason (INT-188)")


def _require_safety(key: str) -> None:
    if not is_safety_flag(key):
        raise NotASafetyFlag(
            f"{key!r} is not a safety flag; a rollout flag goes through set_operational"
        )


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


class FlagGovernor:
    """The write side of the flag facade — the "flag proxy" of files/08 §3.

    Two stores, kept apart by invariant 34:

    - the **generic** operational store, which a safety key may never enter; and
    - the **gated** safety store, whose keys start at their read-side default
      (all False) and are flipped only through the four-eyes ceremony (enable —
      two keys) or a single eligible key (disable — the safe direction, F17).

    The governor holds no chain and no metric. The write-ahead audit row and the
    self-approval counter are the caller's (the route's) to write, exactly as
    break-glass leaves them to ``services/api/admin``. What lives here is the
    rule that makes "safety flags need four-eyes" checkable.
    """

    def __init__(
        self, four_eyes: FourEyesService, *, store: MutableMapping[str, bool] | None = None
    ) -> None:
        seed = dict(store or {})
        planted = scan_generic_store(seed)
        if planted:
            raise SafetyKeyInGenericStore(
                f"the generic flag store was seeded with safety keys {sorted(planted)} "
                "(invariant 34)"
            )
        self._four_eyes = four_eyes
        self._generic: dict[str, bool] = seed
        self._safety: dict[str, bool] = dict(SAFETY_FLAG_DEFAULTS)

    # -- operational flags: one key, generic store -------------------------

    def set_operational(self, key: str, enabled: bool, *, justification: Justification) -> bool:
        """Edit an operational flag with a mandatory change reason. Refuses a
        clinical-semantic surface (inv. 12) and a safety key (inv. 34)."""
        guard_flag_key(key)
        guard_generic_flag_write(key)
        _require_reason(justification)
        self._generic[key] = enabled
        return enabled

    def effective_operational(self, key: str, default: bool = False) -> bool:
        return self._generic.get(key, default)

    def generic_store(self) -> Mapping[str, bool]:
        """A copy of the operational store — for the flag-store scan and views;
        never the live mapping, which only :meth:`set_operational` may change."""
        return dict(self._generic)

    # -- safety flags, enable: the dangerous direction, two keys -----------

    def open_enable(
        self, *, key: str, actor: ActorBlock, justification: Justification, ttl: timedelta
    ) -> PendingAction:
        """Open the four-eyes ceremony to turn a safety flag ON. Nothing takes
        effect here — the flip lands only in :meth:`approve_enable`."""
        guard_flag_key(key)
        _require_safety(key)
        _require_reason(justification)
        return self._four_eyes.open(
            action=SAFETY_FLAG_ENABLE,
            actor=actor,
            target_ref=f"flag:{key}",
            evidence={"flag": key, "enabled": _bool_str(True)},
            justification=justification,
            ttl=ttl,
        )

    def approve_enable(self, pending_id: str, *, approver: ActorBlock, assertion_id: str) -> bool:
        """A distinct second key approves and the flag flips ON. The distinctness
        checks (account, credential, session, org at tier 3, fresh assertion) are
        the :class:`FourEyesService`'s; a one-person attempt raises before the
        flip, so the flag stays in its safe state."""
        approved = self._four_eyes.approve(pending_id, approver=approver, assertion_id=assertion_id)
        self._safety[approved.evidence["flag"]] = True
        return True

    # -- safety flags, disable: the safe direction, one key (F17) ----------

    def disable(self, key: str, *, actor_role: AdminRole, justification: Justification) -> bool:
        """Pull a safety flag to its safe (OFF) state with one eligible key. The
        change reason is still mandatory; the second approver is not, because a
        ceremony on the safe direction is an availability control on a safety
        control (files/08 §0c F17)."""
        guard_flag_key(key)
        _require_safety(key)
        _require_reason(justification)
        if actor_role not in SAFETY_FLAG_DISABLE_ROLES:
            raise DisableRoleIneligible(
                f"{actor_role.value} may not disable a safety flag; the safe direction is "
                "still an incident role (files/08 §0c F17)"
            )
        self._safety[key] = False
        return False

    def effective_safety(self, key: str) -> bool:
        """The gated safety state, defaulting to the read-side False."""
        return self._safety.get(key, SAFETY_FLAG_DEFAULTS.get(key, False))
