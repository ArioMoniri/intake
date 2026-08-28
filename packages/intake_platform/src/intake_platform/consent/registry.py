"""INT-038 — the closed consent-purpose registry (files/06 §2, verbatim).

files/06 §2: "Purposes exactly: ``core``, ``voice``, ``wellbeing``,
``lane:affect``, ``lane:linguistic``, ``documents``, ``learning:personal``
(on by default, inspectable — legal basis: performance of the very service
the patient configured), ``learning:service_improvement`` (de-identified
aggregates; opt-out costs no feature), ``satisfaction``,
``share:{recipient,visit,sections,expiry}``, ``research``."

The list is CLOSED: purposes come from there, never invented here. Two
consequences are encoded rather than commented:

- ``lane:acoustic`` is rejected by name — files/06 §2.4 turned it into an
  investigational-device informed-consent form, and "a device you may not
  place on the market is not made lawful by a toggle";
- ``share`` is a parameterised family: a grantable scope is always
  ``share:<qualifier>`` (e.g. ``share:previsit_note``), because a share
  consent without its parameters would be a bundled consent.

Defaults are the unbundling rule made data: every purpose whose lawful
basis is açık rıza (KVKK m.6) starts OFF — there is no pre-tick the server
could even represent — and only the two purposes files/06 §2 marks with a
non-consent basis start ON, each carrying its stated basis.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

__all__ = [
    "CHANNELS",
    "CORE",
    "PURPOSES",
    "REMOVED_PURPOSES",
    "LegalBasis",
    "PurposeDef",
    "UnknownPurposeError",
    "dependents_of",
    "purpose_ids",
    "resolve_scope",
]

CORE = "core"

# files/06 §1 (KVKK-10 + AYD-2018 row): layered aydınlatma at collection,
# per channel — app, kiosk, clinician, admin, web.
CHANNELS: tuple[str, ...] = ("app", "kiosk", "clinician", "admin", "web")

# files/06 §2.4: an ICF under TCKAY, "not stored as a {version, text_hash}
# row alongside the product purposes" — rejected by name so a stale caller
# fails loudly instead of minting a consent that must not exist.
REMOVED_PURPOSES: tuple[str, ...] = ("lane:acoustic",)


class UnknownPurposeError(LookupError):
    """A scope outside the closed files/06 §2 list. The message carries the
    offending id only — ids are the one shape that may travel (invariant 6)."""


class LegalBasis(enum.StrEnum):
    """Lawful basis per purpose, exactly as files/06 §2 states it."""

    # KVKK m.6 açık rıza — free, specific, informed, unbundled, revocable.
    EXPLICIT_CONSENT = "explicit_consent"
    # files/06 §2 on learning:personal: "performance of the very service the
    # patient configured" — on by default, inspectable, opt-out honoured.
    SERVICE_PERFORMANCE = "service_performance"
    # files/06 §2 on learning:service_improvement: de-identified aggregates
    # (k ≥ 10, files/06 §8); an opt-out purpose whose refusal costs no feature.
    DEIDENTIFIED_OPTOUT = "deidentified_optout"


@dataclass(frozen=True)
class PurposeDef:
    """One registry row. ``cascade_children`` names the purposes a
    withdrawal of this one drags down (files/06 §2.2–2.3): children add,
    never remove — withdrawal may only over-revoke, never under-revoke."""

    id: str
    legal_basis: LegalBasis
    default_granted: bool
    parameterised: bool = False
    cascade_children: tuple[str, ...] = field(default=())


_OPTIONAL = LegalBasis.EXPLICIT_CONSENT

PURPOSES: tuple[PurposeDef, ...] = (
    # core is itself a consent — nothing is implicit — and it is the root of
    # the cascade: withdrawing the service consent withdraws every purpose
    # that presupposes the service (children filled in below).
    PurposeDef(id="core", legal_basis=_OPTIONAL, default_granted=False),
    # lane:affect "infers emotional state from the sound of the voice"
    # (files/06 §2.1) — it rides the voice stream, so it falls with voice.
    PurposeDef(
        id="voice",
        legal_basis=_OPTIONAL,
        default_granted=False,
        cascade_children=("lane:affect",),
    ),
    PurposeDef(id="wellbeing", legal_basis=_OPTIONAL, default_granted=False),
    PurposeDef(id="lane:affect", legal_basis=_OPTIONAL, default_granted=False),
    # lane:linguistic is text-only (files/06 §2.1) — deliberately NOT a child
    # of voice; it stands and falls with core alone.
    PurposeDef(id="lane:linguistic", legal_basis=_OPTIONAL, default_granted=False),
    PurposeDef(id="documents", legal_basis=_OPTIONAL, default_granted=False),
    PurposeDef(
        id="learning:personal",
        legal_basis=LegalBasis.SERVICE_PERFORMANCE,
        default_granted=True,
    ),
    PurposeDef(
        id="learning:service_improvement",
        legal_basis=LegalBasis.DEIDENTIFIED_OPTOUT,
        default_granted=True,
    ),
    PurposeDef(id="satisfaction", legal_basis=_OPTIONAL, default_granted=False),
    PurposeDef(id="share", legal_basis=_OPTIONAL, default_granted=False, parameterised=True),
    PurposeDef(id="research", legal_basis=_OPTIONAL, default_granted=False),
)

_BY_ID: dict[str, PurposeDef] = {p.id: p for p in PURPOSES}


def purpose_ids() -> tuple[str, ...]:
    """The closed list, in files/06 §2 order."""
    return tuple(p.id for p in PURPOSES)


def resolve_scope(scope: str) -> PurposeDef:
    """Map a scope string to its registry row, or refuse.

    Literal ids resolve to themselves; ``share:<qualifier>`` resolves to the
    parameterised ``share`` family; the bare ``share`` id is NOT grantable
    (a share is always parameterised — files/06 §2); everything else —
    including ``lane:acoustic`` — is refused by id.
    """
    if scope in REMOVED_PURPOSES:
        raise UnknownPurposeError(scope)
    definition = _BY_ID.get(scope)
    if definition is not None and not definition.parameterised:
        return definition
    if scope.startswith("share:") and len(scope) > len("share:"):
        return _BY_ID["share"]
    raise UnknownPurposeError(scope)


def dependents_of(purpose_id: str) -> tuple[str, ...]:
    """Purposes a withdrawal of ``purpose_id`` cascades to. ``core`` reaches
    every other purpose — a withdrawn service consent leaves nothing to ride
    on; the rest follow their registry row."""
    definition = _BY_ID.get(purpose_id)
    if definition is None:
        raise UnknownPurposeError(purpose_id)
    if purpose_id == CORE:
        return tuple(p.id for p in PURPOSES if p.id != CORE)
    return definition.cascade_children
