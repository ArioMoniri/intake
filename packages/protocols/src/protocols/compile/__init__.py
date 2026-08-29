"""The protocol compiler (INT-041): resolved pack → standards artefacts.

files/03 §6 names five outputs and this package emits all five, deterministically:
(a) a FHIR R4 ``Questionnaire``, (b) openEHR operational-template bindings,
(c) Pydantic slot schemas for the engine, (d) TypeScript types for the app,
(e) the clip manifest the Talker consumes.

Everything else here is refusal. The compiler is the last place several
safety invariants can still be enforced before content reaches a patient, so
it re-checks them on the **compiled** artefact even where the DSL schema
already refused the shape — files/04 §8.2 asks for exactly that of
``on_site_action_never_offers_112``, "asserted on the compiled action, so an
author cannot set the flag true at all", and the same reasoning covers the
sign-off interlock (HB-C1), the maturity ladder (invariant 13), rule
provenance (invariant 17), RED's three axes (invariant 21), monotonic
inheritance (invariant 7), scripted delivery (invariant 10) and the
representation boundary (invariant 22).

There is no bypass, no ``dev_only`` flag and no demo mode: HUMAN_BLOCKERS
Rule 2 is explicit that designing a way for the product to work without the
missing thing converts a blocker into a defect.
"""

from __future__ import annotations

from protocols.compile.bundle import (
    DIST_ROOT,
    CompiledBundle,
    compile_bundle,
    write_bundle,
)
from protocols.compile.emit_clips import ClipRow, clip_manifest
from protocols.compile.emit_code import model_name, pydantic_module, typescript_module
from protocols.compile.emit_fhir import VALUESET_CANONICAL_PREFIX, questionnaire
from protocols.compile.errors import CompileError, Refusal, RefusalCode
from protocols.compile.life_threat import (
    SIGNOFF_FIELDS,
    AgeBand,
    ClinicalSignoff,
    ExcludedCriterion,
    GoldenCase,
    LifeThreatRule,
    LifeThreatSet,
    LifeThreatSetError,
    load_life_threat_set,
)
from protocols.compile.overlay import (
    MONOTONICITY_FINDINGS,
    OverlayComposition,
    OverlaySelection,
    activate_overlays,
    compose_overlay_rules,
)
from protocols.compile.resolve import (
    ResolvedProtocol,
    ResolvedSection,
    ResolvedSlot,
    resolve_protocol,
)
from protocols.compile.tr_orthography import (
    DOSE_FORM_CHIPS,
    DRUG_ORTHOGRAPHY,
    TR_UNITS,
    Expansion,
    Replacement,
    TrExpansionError,
    assert_round_trip,
    expand_tr,
    parse_turkish_cardinal,
    turkish_cardinal,
)

__all__ = [
    "DIST_ROOT",
    "DOSE_FORM_CHIPS",
    "DRUG_ORTHOGRAPHY",
    "MONOTONICITY_FINDINGS",
    "SIGNOFF_FIELDS",
    "TR_UNITS",
    "VALUESET_CANONICAL_PREFIX",
    "AgeBand",
    "ClinicalSignoff",
    "ClipRow",
    "CompileError",
    "CompiledBundle",
    "ExcludedCriterion",
    "Expansion",
    "GoldenCase",
    "LifeThreatRule",
    "LifeThreatSet",
    "LifeThreatSetError",
    "OverlayComposition",
    "OverlaySelection",
    "Refusal",
    "RefusalCode",
    "Replacement",
    "ResolvedProtocol",
    "ResolvedSection",
    "ResolvedSlot",
    "TrExpansionError",
    "activate_overlays",
    "assert_round_trip",
    "clip_manifest",
    "compile_bundle",
    "compose_overlay_rules",
    "expand_tr",
    "load_life_threat_set",
    "model_name",
    "parse_turkish_cardinal",
    "pydantic_module",
    "questionnaire",
    "resolve_protocol",
    "turkish_cardinal",
    "typescript_module",
    "write_bundle",
]
