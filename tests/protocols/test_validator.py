"""INT-040 — Protocol DSL: schema, loader, validator.

Acceptance, verbatim: "yaml schema with sections/slots/red_flags/overlays/
visit_types/voice fields; validator enforces monotonicity, follow_up_tr
presence, instruments allow_paraphrase=false".

Every case here has a golden fixture: valid packs under
tests/protocols/goldens/valid/, schema-level near misses under
goldens/invalid_schema/, validator-level near misses under
goldens/invalid_findings/, and the sign-off-literal fixtures under
tests/fixtures/protocols/ (the no_placeholders gate permits the literal only
there and under packages/protocols/**). All fixture content is SYNTHETIC —
mechanism only, zero clinical content (INT-040 scope).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from protocols import (
    EK4Level,
    FindingCode,
    InstrumentLicence,
    PackRegistry,
    PackSchemaError,
    instrument_licence,
    load_pack,
    pack_compilable,
    validate_packs,
)
from protocols.validator import resolve_red_flags

HERE = Path(__file__).resolve().parent
GOLDENS = HERE / "goldens"
VALID = GOLDENS / "valid"
INVALID_SCHEMA = GOLDENS / "invalid_schema"
INVALID_FINDINGS = GOLDENS / "invalid_findings"
SIGNOFF_FIXTURES = HERE.parent / "fixtures" / "protocols"

# Synthetic licence registry for goldens — the production stub knows nothing
# about SYN-SCALE, and licensing fails closed (files/04 header table).
TEST_LICENCES = {"SYN-SCALE": InstrumentLicence.GO}


def build_registry(*paths: Path) -> PackRegistry:
    registry = PackRegistry()
    for path in paths:
        registry.add(load_pack(path))
    return registry


# ---------------------------------------------------------------------------
# Valid goldens — the whole library loads, validates clean, and the child's
# tighten_rule resolves monotonically.
# ---------------------------------------------------------------------------


def test_valid_goldens_validate_clean() -> None:
    registry = build_registry(*sorted(VALID.glob("*.yaml")))
    findings = validate_packs(registry, licences=TEST_LICENCES)
    assert findings == (), [f"{f.code}: {f.message}" for f in findings]


def test_child_tighten_resolves_monotonically() -> None:
    registry = build_registry(VALID / "base.yaml", VALID / "child.yaml")
    resolved, findings = resolve_red_flags(registry.get("specialty.synthetic_dal"), registry)
    assert findings == ()
    # files/12 §4 layer 2: tighten never replaces — the parent rule stays
    # live, byte-identical, and the tightened sibling is added under a new id.
    base = registry.get("base.synthetic")
    assert resolved["rf.synthetic_kirmizi"] == base.red_flags[0]
    assert "rf.synthetic_kirmizi.genis" in resolved
    assert "rf.synthetic_dal_sari" in resolved


def test_draft_rule_loads_validates_and_is_excluded_from_compile() -> None:
    registry = build_registry(SIGNOFF_FIXTURES / "draft_ok.yaml")
    assert validate_packs(registry) == ()
    report = pack_compilable(registry.get("base.synthetic_taslak"))
    assert report.excluded_rules == ("rf.synthetic_taslak",)
    assert report.blocked_instruments == ()
    assert not report.fully_compilable


def test_go_instrument_compiles_blocked_instrument_does_not() -> None:
    registry = build_registry(VALID / "base.yaml", VALID / "instruments.yaml")
    pack = registry.get("specialty.synthetic_olcek")
    assert pack_compilable(pack, licences=TEST_LICENCES).fully_compilable
    # The same pack against the production registry fails closed: SYN-SCALE
    # is unknown there, and a non-GO instrument blocks the pack build
    # (CLAUDE.md clinical content rules; HB-L2/HB-L3 mechanism).
    report = pack_compilable(pack)
    assert report.blocked_instruments == ("SYN-SCALE",)
    assert not report.fully_compilable


# ---------------------------------------------------------------------------
# Schema-level near misses — each fixture is one attribute away from a valid
# golden and must be rejected at load (pydantic), before any validator runs.
# ---------------------------------------------------------------------------

SCHEMA_REJECTIONS = {
    "extends_life_threat.yaml": "base.life_threat",
    "red_missing_register.yaml": "register",
    "red_missing_location.yaml": "UNKNOWN",
    "onsite_offers_112.yaml": "112",
    "remove_rule_op.yaml": "op",
    "deny_prefix_pointer.yaml": "deny",
    "deny_suffix_pointer.yaml": "deny",
    "set_attr_loosen.yaml": "tighten",
    "draft_missing_source_gap.yaml": "source_gap",
    "missing_source_active.yaml": "source",
}


@pytest.mark.parametrize("name", sorted(SCHEMA_REJECTIONS))
def test_schema_rejects(name: str) -> None:
    with pytest.raises(PackSchemaError) as excinfo:
        load_pack(INVALID_SCHEMA / name)
    assert SCHEMA_REJECTIONS[name] in str(excinfo.value)


def test_schema_fixture_dir_is_fully_covered() -> None:
    assert sorted(p.name for p in INVALID_SCHEMA.glob("*.yaml")) == sorted(SCHEMA_REJECTIONS)


# ---------------------------------------------------------------------------
# Validator-level near misses — each fixture loads (the schema accepts it)
# and must produce exactly the finding its comment names.
# ---------------------------------------------------------------------------

FINDING_FIXTURES = {
    "redeclare_inherited_rule.yaml": FindingCode.RULE_REDECLARED,
    "narrowed_tighten.yaml": FindingCode.TIGHTEN_NOT_DISJUNCTION,
    "tighten_downgrade.yaml": FindingCode.TIGHTEN_LEVEL_DOWNGRADE,
    "tighten_bad_id.yaml": FindingCode.TIGHTEN_BAD_ID,
    "missing_follow_up.yaml": FindingCode.MISSING_FOLLOW_UP_TR,
    "instrument_paraphrase.yaml": FindingCode.INSTRUMENT_PARAPHRASE,
    "unknown_instrument.yaml": FindingCode.INSTRUMENT_LICENCE_NOT_GO,
    "numeral_in_tr.yaml": FindingCode.NUMERAL_IN_TR,
    "suppress_must_ask.yaml": FindingCode.SUPPRESS_MUST_ASK,
    "hospital_add_required_slot.yaml": FindingCode.CAPABILITY_VIOLATION,
    "override_text_non_hospital.yaml": FindingCode.CAPABILITY_VIOLATION,
    "missing_parent.yaml": FindingCode.MISSING_PARENT,
}


@pytest.mark.parametrize("name", sorted(FINDING_FIXTURES))
def test_validator_flags(name: str) -> None:
    registry = build_registry(VALID / "base.yaml", INVALID_FINDINGS / name)
    findings = validate_packs(registry)
    codes = {f.code for f in findings}
    assert FINDING_FIXTURES[name] in codes, [f"{f.code}: {f.message}" for f in findings]


def test_finding_fixture_dir_is_fully_covered() -> None:
    assert sorted(p.name for p in INVALID_FINDINGS.glob("*.yaml")) == sorted(FINDING_FIXTURES)


# ---------------------------------------------------------------------------
# The invariant-17 sole exception — form-enforced, draft-only.
# ---------------------------------------------------------------------------


def test_malformed_signoff_literal_is_flagged() -> None:
    registry = build_registry(SIGNOFF_FIXTURES / "draft_wrong_form.yaml")
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.PLACEHOLDER_FORM in codes


def test_signoff_literal_in_active_rule_is_flagged() -> None:
    registry = build_registry(SIGNOFF_FIXTURES / "active_with_todo.yaml")
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.PLACEHOLDER_OUTSIDE_DRAFT in codes


# ---------------------------------------------------------------------------
# Numerals — the near-miss pair (CLAUDE.md invariant 22): "iki gün" passes,
# the digit twin fails. Both directions asserted so the gate cannot rot into
# a tautology.
# ---------------------------------------------------------------------------


def test_numeral_near_miss_pair() -> None:
    clean = build_registry(VALID / "near_miss_numeral.yaml")
    assert validate_packs(clean) == ()
    dirty = build_registry(INVALID_FINDINGS / "numeral_in_tr.yaml")
    codes = {f.code for f in validate_packs(dirty)}
    assert codes == {FindingCode.NUMERAL_IN_TR}


# ---------------------------------------------------------------------------
# Licence registry stub — files/04 header table; HUMAN_BLOCKERS HB-L2/HB-L3.
# ---------------------------------------------------------------------------


def test_production_licence_registry_matches_blueprint() -> None:
    assert instrument_licence("PHQ-9") is InstrumentLicence.GO
    assert instrument_licence("PHQ-2") is InstrumentLicence.GO
    assert instrument_licence("GAD-7") is InstrumentLicence.GO
    assert instrument_licence("GAD-2") is InstrumentLicence.GO
    assert instrument_licence("C-SSRS") is InstrumentLicence.BLOCKED
    assert instrument_licence("WHO-5") is InstrumentLicence.BLOCKED
    assert instrument_licence("HAQ-DI") is InstrumentLicence.NEEDS_PERMISSION


def test_unknown_instrument_fails_closed() -> None:
    assert instrument_licence("SYN-UNLISTED") is InstrumentLicence.UNKNOWN
    assert instrument_licence("SYN-UNLISTED") is not InstrumentLicence.GO


# ---------------------------------------------------------------------------
# EK-4 acuity ordering (files/12 §2.1) backs the level-downgrade check.
# ---------------------------------------------------------------------------


def test_ek4_severity_order() -> None:
    order = [
        EK4Level.YESIL,
        EK4Level.SARI_K2,
        EK4Level.SARI_K1,
        EK4Level.KIRMIZI_K2,
        EK4Level.KIRMIZI_K1,
    ]
    severities = [level.severity for level in order]
    assert severities == sorted(severities)
    assert EK4Level.KIRMIZI_K1.is_red and EK4Level.KIRMIZI_K2.is_red
    assert not EK4Level.SARI_K1.is_red


# ---------------------------------------------------------------------------
# INT-254 — a structurally incomplete RED action is a Finding, not a crash.
#
# packages/protocols/src/protocols/compile/resolve.py already carries the
# guard (`action is None or action.remote is None or action.on_site is None
# or action.unknown is None`) because a location branch can be absent on any
# object that reached the validator without full validation. The validator
# did not, so _tr_texts dereferenced the branch and validate_packs raised
# AttributeError — which is not a report, cannot be attributed to a rule, and
# aborts every remaining pack in the registry. INT-041 ordered its own
# RED-axis check first rather than edit this file; the fix belongs here.
# ---------------------------------------------------------------------------


def _pack_with_broken_red_action(branch: str) -> PackRegistry:
    registry = build_registry(VALID / "base.yaml")
    pack = registry.get("base.synthetic")
    rule = next(rule for rule in pack.red_flags if rule.id == "rf.synthetic_kirmizi")
    assert rule.action is not None
    broken = rule.model_copy(update={"action": rule.action.model_copy(update={branch: None})})
    others = tuple(other for other in pack.red_flags if other.id != rule.id)
    patched = PackRegistry()
    patched.add(pack.model_copy(update={"red_flags": (broken, *others)}))
    return patched


@pytest.mark.parametrize("branch", ["remote", "on_site", "unknown"])
def test_incomplete_red_action_is_a_finding_not_an_attribute_error(branch: str) -> None:
    findings = validate_packs(_pack_with_broken_red_action(branch))
    codes = {finding.code for finding in findings}
    assert FindingCode.RED_ACTION_UNRESOLVED in codes, [f"{f.code}: {f.message}" for f in findings]
    unresolved = [f for f in findings if f.code is FindingCode.RED_ACTION_UNRESOLVED]
    assert [f.subject for f in unresolved] == ["rf.synthetic_kirmizi"]


@pytest.mark.parametrize("branch", ["remote", "on_site", "unknown"])
def test_incomplete_red_action_still_reports_the_rest_of_the_pack(branch: str) -> None:
    """The near miss the AttributeError hid: a crash inside _tr_texts takes
    every other finding in the registry with it, so a broken action used to
    mask the numeral and follow_up_tr checks on the same pack rather than
    adding to them."""
    registry = _pack_with_broken_red_action(branch)
    pack = registry.get("base.synthetic")
    broken = next(rule for rule in pack.red_flags if rule.id == "rf.synthetic_kirmizi")
    assert broken.action is not None
    slot = pack.sections["ornek_bolum"].slots["olay_zamani"]
    section = pack.sections["ornek_bolum"].model_copy(
        update={
            "slots": {
                **pack.sections["ornek_bolum"].slots,
                "olay_zamani": slot.model_copy(update={"ask_tr": "Bu 3 gün önce mi oldu?"}),
            }
        }
    )
    registry = PackRegistry()
    registry.add(pack.model_copy(update={"sections": {**pack.sections, "ornek_bolum": section}}))
    codes = {finding.code for finding in validate_packs(registry)}
    assert FindingCode.RED_ACTION_UNRESOLVED in codes
    assert FindingCode.NUMERAL_IN_TR in codes


def test_a_complete_red_action_raises_no_unresolved_finding() -> None:
    """Negative control: the same pack, untouched, must not acquire the new
    finding — a check that fires on everything reports nothing."""
    registry = build_registry(VALID / "base.yaml")
    codes = {finding.code for finding in validate_packs(registry)}
    assert FindingCode.RED_ACTION_UNRESOLVED not in codes


def test_an_incomplete_action_on_a_non_red_rule_is_not_reported() -> None:
    """Invariant 21 binds RED. A YESIL/SARI rule carries no action at all, and
    the finding must not start firing on every non-RED rule in the repo."""
    registry = build_registry(VALID / "base.yaml")
    pack = registry.get("base.synthetic")
    sari = next(rule for rule in pack.red_flags if rule.id == "rf.synthetic_sari")
    assert sari.action is None
    codes = {finding.code for finding in validate_packs(registry)}
    assert FindingCode.RED_ACTION_UNRESOLVED not in codes
