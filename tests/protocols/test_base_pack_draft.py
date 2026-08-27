"""INT-043 — structural gates over the base.intake / base.red_flags drafts.

This is the pre-compiler half of the golden machinery (the compiler and full
golden suite arrive with INT-040/041/059). Everything here is enforceable
today and each check maps to a named CI gate from 04 §8.2 / CLAUDE.md:

- served interlock + empty clinical_signoff (D17; instrument_licence_gate kin)
- no non-GO instrument referenced anywhere (C-SSRS/WHO-5 — HB-L2/HB-L3)
- every must_ask slot carries follow_up_tr (04 §1 — ask-ahead requires it)
- no crisis string contains 182 (04 §4.1 — booking line, not a crisis line)
- unfilled clinical values use the literal sign-off form, never a number
- every red-flag rule has a golden positive AND a near-miss negative
- no_rule_references_an_undeclared_slot (04 §8.2 — with HB-C6 slots drafted)
- screening/sensitive delivery is text_only / text_first (13 §13)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "packages" / "protocols" / "base"

SIGNOFF_FORM = re.compile(r"TODO: .+ requires clinical sign-off")
BLOCKED_INSTRUMENTS = ("cssrs", "c-ssrs", "who5", "who-5")


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((BASE / name).read_text(encoding="utf-8"))


def _intake() -> dict[str, Any]:
    return _load("intake.yaml")


def _red_flags() -> dict[str, Any]:
    return _load("red_flags.yaml")


def _all_slots(intake: dict[str, Any]) -> list[dict[str, Any]]:
    return [slot for section in intake["sections"] for slot in section.get("slots", [])]


# --- serve interlock -------------------------------------------------------------


def test_packs_are_unservable_while_unsigned() -> None:
    for name in ("intake.yaml", "red_flags.yaml", "life_threat.yaml"):
        pack = _load(name)
        assert pack["served"] is False, f"{name}: an unsigned pack may never be served"
        assert pack["maturity"] == "L0"
        signoff = pack["clinical_signoff"]
        assert all(v is None for v in signoff.values()), (
            f"{name}: clinical_signoff must stay empty until a named physician signs (D17)"
        )


def test_hb_c6_slots_are_drafted() -> None:
    ids = {s["id"] for s in _all_slots(_intake())}
    for required in (
        "pregnancy_status",
        "lmp_date",
        "immunosuppression",
        "anticoagulant_use",
        "weight_kg",
        "time_last_known_well",
    ):
        assert required in ids, f"HB-C6 slot missing from the draft: {required}"


# --- instrument licence gate (structural form) -----------------------------------


def test_no_blocked_instrument_is_referenced() -> None:
    intake = _intake()
    declared = {i["id"] for i in intake.get("instruments", [])}
    assert declared <= {"phq2", "gad2", "phq9", "gad7"}, (
        f"non-GO instrument declared: {declared - {'phq2', 'gad2', 'phq9', 'gad7'}}"
    )
    for slot in _all_slots(intake):
        if "instrument" in slot:
            assert slot["instrument"] in declared


def test_a_pack_referencing_cssrs_fails(tmp_path: Path) -> None:
    # The 07 §5 negative control, structural form: the same validation that
    # passes the real pack must reject a pack declaring C-SSRS.
    fixture = {"instruments": [{"id": "cssrs", "licence": "BLOCKED"}], "sections": []}
    declared = {i["id"] for i in fixture["instruments"]}
    assert not declared <= {"phq2", "gad2", "phq9", "gad7"}, (
        "the licence gate failed to reject a C-SSRS-bearing pack"
    )


# --- voice / follow-up / delivery ------------------------------------------------


def test_every_must_ask_asked_slot_has_follow_up_tr() -> None:
    for slot in _all_slots(_intake()):
        if slot.get("must_ask") and "instrument" not in slot:
            assert slot.get("follow_up_tr"), f"{slot['id']}: must_ask without follow_up_tr (04 §1)"


def test_screening_is_text_only_and_sensitive_slots_text_first() -> None:
    intake = _intake()
    sections = {s["id"]: s for s in intake["sections"]}
    assert sections["screening"]["delivery"] == "text_only", "13 §13: screening is text_only"
    for slot in sections["screening"].get("slots", []):
        assert "ask_tr" not in slot, (
            f"{slot['id']}: a text_only instrument slot must carry no speakable ask text here — "
            "items are ingested verbatim in INT-116 and never spoken"
        )
    assert sections["gatekeepers"]["delivery"] == "text_first", (
        "pregnancy/LMP are sensitive (13 §13)"
    )


# --- crisis strings ---------------------------------------------------------------


def test_no_crisis_or_action_string_contains_182() -> None:
    for name in ("intake.yaml", "red_flags.yaml", "life_threat.yaml"):
        text = (BASE / name).read_text(encoding="utf-8")
        if re.search(r"(action_tr|ask_tr|why_tr|do_nots_tr)[\s\S]{0,400}?182", text):
            raise AssertionError(
                f"{name}: patient-facing string contains 182 — the MHRS booking line"
            )


# --- unfilled clinical values -----------------------------------------------------


def test_unfilled_clinical_values_use_the_signoff_form() -> None:
    intake = _intake()
    for key, value in intake.get("constants", {}).items():
        if isinstance(value, str):
            assert SIGNOFF_FORM.fullmatch(value), f"constants.{key}: not the literal sign-off form"
    for rule in _red_flags()["rules"]:
        ek4 = rule.get("ek4")
        valid = {"KIRMIZI_K1", "KIRMIZI_K2", "SARI_K1", "SARI_K2", "YESIL"}
        assert ek4 in valid or SIGNOFF_FORM.fullmatch(str(ek4)), (
            f"{rule['id']}: ek4 is neither a valid EK-4 level nor the sign-off form"
        )


def test_draft_needs_source_always_carries_a_source_gap() -> None:
    for rule in _red_flags()["rules"]:
        if rule.get("status") == "draft_needs_source":
            assert rule.get("source_gap", "").strip(), f"{rule['id']}: empty source_gap"
    for slot in _all_slots(_intake()):
        if slot.get("status") == "draft_needs_source":
            assert slot.get("source_gap", "").strip(), f"{slot['id']}: empty source_gap"


# --- goldens ----------------------------------------------------------------------


def test_every_rule_has_a_positive_and_a_near_miss_negative() -> None:
    for rule in _red_flags()["rules"]:
        assert rule.get("golden_positive", {}).get("case"), f"{rule['id']}: no golden positive"
        neg = rule.get("golden_negative", {})
        assert neg.get("case"), f"{rule['id']}: no golden negative"
        assert "NEAR MISS" in neg["case"], f"{rule['id']}: negative is not a near miss"
        assert neg.get("why_it_is_a_near_miss", "").strip(), (
            f"{rule['id']}: near-miss rationale missing — a random negative detects nothing"
        )


# --- slot references --------------------------------------------------------------


def _declared_ids(intake: dict[str, Any]) -> set[str]:
    ids = {s["id"] for s in _all_slots(intake)}
    ids |= {d["id"] for d in intake.get("derived_slots", [])}
    ids |= {f"constants.{k}" for k in intake.get("constants", {})}
    return ids


IDENT = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+\b|\b[a-z][a-z0-9_]*\b")
KEYWORDS = {"true", "false", "in", "and", "or", "not", "none"}


def test_no_rule_references_an_undeclared_slot() -> None:
    intake = _intake()
    declared = _declared_ids(intake)
    # dotted parents count as declared roots (fever.max_temp_c declares fever.*)
    roots = {d.split(".")[0] for d in declared}

    def check_gate(gate: str, origin: str) -> None:
        gate = re.sub(
            r"'[^']*'|\"[^\"]*\"", " ", gate
        )  # quoted enum literals are values, not slots
        for token in IDENT.findall(gate):
            if token in KEYWORDS or token.isdigit():
                continue
            if "." in token:
                ok = token in declared or token.split(".")[0] in roots
            else:
                ok = token in declared or token in roots
            assert ok, f"{origin}: gate references undeclared slot {token!r}"

    for rule in _red_flags()["rules"]:
        check_gate(rule["gate"], rule["id"])
    for slot in _all_slots(intake):
        if "gate" in slot:
            check_gate(slot["gate"], f"intake:{slot['id']}")
