"""The resolved protocol the simulator runs on (INT-082).

**Why a synthetic pack.** Every pack in ``packages/protocols`` is
``maturity: L0``, ``status: awaiting-clinical-review``, with every red-flag
family ``status: draft_needs_source`` (HUMAN_BLOCKERS HB-C1, HB-C2, HB-C7).
:func:`protocols.triage.evaluate_triage` refuses a draft rule outright, so no
real pack can drive a simulated session at all, and authoring clinical
content here to get round that is exactly the bypass HUMAN_BLOCKERS Rule 2
forbids. files/04 §7 settles the direction anyway: *"packs and goldens
contain synthetic data only; simulator transcripts are synthetic"*.

**It is resolved through the real compiler, not hand-built.** The fixture
under ``fixtures/tree`` goes through :func:`protocols.cli.load_registry` and
:func:`protocols.compile.resolve.resolve_protocol` against the committed
operational template, so the simulator drives the document the runtime would
actually be handed — chain, delivery, paraphrase permission, valuesets and
rules included — rather than a second implementation of it.

The signed life-threat set is the committed INT-041 fixture, reused rather
than copied: a second signed set in the tree would be a second place the
HB-C1 sign-off interlock could drift.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from protocols.bindings import load_opt
from protocols.cli import load_registry
from protocols.compile import load_life_threat_set
from protocols.compile.resolve import (
    ResolvedProtocol,
    ResolvedSection,
    ResolvedSlot,
    resolve_protocol,
)
from protocols.dsl import Slot
from protocols.licences import InstrumentLicence
from protocols.types import Delivery, SlotType

__all__ = [
    "REFERENCE_TIME",
    "SIM_DETAILED_PACK_ID",
    "SIM_INSTRUMENT_ID",
    "SIM_PACK_ID",
    "IntakeMode",
    "protocol_with_free_text_must_ask",
    "sim_protocol",
]

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_TREE = _HERE / "fixtures" / "tree"
_LIFE_THREAT = _REPO / "tests" / "fixtures" / "protocols" / "compile" / "life_threat_signed.yaml"
_TEMPLATE = _REPO / "packages" / "protocols" / "openehr" / "previsit_intake.v1.opt"

SIM_PACK_ID = "base.sentetik_simulator"
SIM_DETAILED_PACK_ID = "visit_type.sentetik_detayli"
SIM_INSTRUMENT_ID = "SYN-OLCEK"

REFERENCE_TIME = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
"""The session's ``now`` (files/13 §9.2). Stamped once; never a wall clock,
so every scenario replays to the same answer."""


class IntakeMode(enum.StrEnum):
    """Hızlı and Detaylı — *"same engine, different protocol profile"*.

    The two values are exactly the two ``clinical_schemas.session.SessionState.
    mode`` records (``Literal["fast", "detailed"]``, files/04 §5 ``meta.mode``),
    because a simulator mode that no session could record would be a third
    product.

    **The mode is a resolution, not a parameter.** files/02 §2 closes its own
    table with *"Both modes run the Protocol Registry: ``base.intake`` →
    ``specialty.*`` → ``visit_type.*`` → patient overlays"*, and the engine
    agrees by having nowhere to put a flag: ``IntakeEngine`` takes a resolved
    protocol, a reference time and the overlay, and files/13 §9.5's GuardExpr
    whitelist — the only place a ``mode`` gate could be written — is refused at
    plan build (INT-081). So :attr:`FAST` resolves the base pack and
    :attr:`DETAILED` resolves the ``visit_type`` pack that extends it.

    **No turn budget is attached to either.** files/02 §2's ≤ 14 / ≤ 18 pair
    collides with its own content list in the same table and is an open
    clinical decision (HUMAN_BLOCKERS **HB-C5**); the simulator asserts
    composition, never minutes and never a turn count.
    """

    FAST = "fast"
    DETAILED = "detailed"


@lru_cache(maxsize=len(IntakeMode))
def sim_protocol(mode: IntakeMode = IntakeMode.FAST) -> ResolvedProtocol:
    """The synthetic pack for ``mode``, resolved through the real compiler."""
    return resolve_protocol(
        pack_id=SIM_PACK_ID if mode is IntakeMode.FAST else SIM_DETAILED_PACK_ID,
        registry=load_registry(_TREE),
        life_threat=load_life_threat_set(_LIFE_THREAT),
        template=load_opt(_TEMPLATE),
        # SYN-OLCEK is invented for this fixture; the licence registry is
        # closed (an unknown instrument is UNKNOWN, never GO), so the test
        # table names it explicitly rather than the pack asserting it.
        licences={SIM_INSTRUMENT_ID: InstrumentLicence.GO},
    )


@lru_cache(maxsize=1)
def protocol_with_free_text_must_ask() -> ResolvedProtocol:
    """The same pack plus one required free-text slot — the negative control
    for the low-literacy gate (files/02 §3 "no free text anywhere on the
    critical path"). Built here rather than committed as a second fixture,
    because it exists only to prove the gate can fail."""
    base = sim_protocol()
    offending = ResolvedSlot(
        section_id="oyku",
        key="serbest_metin",
        fhir_link_id="oyku.serbest_metin",
        slot=Slot(
            type=SlotType.STRING,
            required=True,
            must_ask=True,
            ask_tr={"tr": "Sentetik serbest metin sorusu."},
            follow_up_tr={"tr": "Sentetik serbest metin takip sorusu."},
        ),
        delivery=Delivery.VOICE,
    )
    sections = tuple(
        ResolvedSection(
            id=section.id,
            delivery=section.delivery,
            voice=section.voice,
            questionnaires=section.questionnaires,
            allow_paraphrase=section.allow_paraphrase,
            slots=(*section.slots, offending) if section.id == "oyku" else section.slots,
        )
        for section in base.sections
    )
    return base.model_copy(update={"sections": sections})
