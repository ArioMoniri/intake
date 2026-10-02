"""INT-427 — the dynamic department wave (GitHub #722).

Every branch already has a review candidate (INT-353). This wave makes eight
high-volume departments' candidates answer-driven: a detail question is asked
only after the "yes" that makes it meaningful (files/13 §9.5 gates, the
owner's "dynamic to previous questions and answers").

The candidates stay review-queue L0 (invariant 13): one red-flag stub, still
``draft_needs_source`` with invariant 17's sanctioned marker, and nothing else
that could reach triage (invariants 1 and 7). Each gate is a structural yes-gate
on an earlier boolean answer, read in the resolver's merged ask order, so the
compiler's later-slot refusal cannot fire. Each candidate is the byte-exact
generator output of its proposal, and its sign-off packet binds its sha256.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import policy_guard_for
from protocols.bindings import fhir_link_id
from protocols.compile.resolve import _apply_ops, _merge_chain, _ordered_ops
from protocols.gates import SlotNamespace, qualify_gate
from protocols.loader import load_pack
from protocols.pack import ProtocolPack
from protocols.triage.expr import parse_when, referenced_slots

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "packages" / "protocols" / "review"
BASE = ROOT / "packages" / "protocols" / "base" / "intake.yaml"
PROPOSALS = ROOT / "docs" / "evidence" / "proposals"
VERIFICATION = ROOT / "docs" / "evidence" / "verification"
SIGNOFF = ROOT / "docs" / "signoff"

WAVE = (
    "aile_hekimligi",
    "anesteziyoloji",
    "beyin_ve_sinir_cerrahisi",
    "fiziksel_tip_ve_rehabilitasyon",
    "gogus_cerrahisi",
    "gogus_hastaliklari",
    "hematoloji",
    "nefroloji",
)
MIN_GATES = 2
GATE_FORM = re.compile(r"^[a-z][a-z0-9_]* == true( \|\| [a-z][a-z0-9_]* == true)*$")
PENDING = "".join(("TO", "DO")) + ": "


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_specialty_packs", ROOT / "scripts/dev/gen_specialty_packs.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


GEN = _load_generator()


def _candidate(slug: str) -> dict[str, object]:
    doc = yaml.safe_load((REVIEW / "specialty" / f"{slug}.yaml").read_text("utf-8"))
    assert isinstance(doc, dict)
    return doc


def _slots(doc: dict[str, object]) -> dict[str, dict[str, object]]:
    sections = doc["sections"]
    assert isinstance(sections, dict)
    return {k: v for s in sections.values() for k, v in (s.get("slots") or {}).items()}


def _chain(slug: str) -> list[ProtocolPack]:
    branch = load_pack(REVIEW / "specialty" / f"{slug}.yaml")
    assert branch.extends is not None and branch.extends.startswith("cluster.")
    cluster = load_pack(REVIEW / "cluster" / f"{branch.extends.removeprefix('cluster.')}.yaml")
    return [load_pack(BASE), cluster, branch]


def _late_gates(chain: list[ProtocolPack]) -> list[str]:
    """Gates reading a slot at or after their own place in the engine's ask order."""
    merged = _merge_chain(chain)
    assert _apply_ops(merged, _ordered_ops(chain), "tr") == []
    ask_key: dict[str, tuple[int, int]] = {}
    for section_id, state in merged.items():
        for key, slot in state.slots.items():
            ask_key[fhir_link_id(section_id, key)] = (0 if slot.must_ask else 1, len(ask_key))
    namespace = SlotNamespace((s, k) for s, state in merged.items() for k in state.slots)
    late: list[str] = []
    for section_id, state in merged.items():
        for key, slot in state.slots.items():
            ref = fhir_link_id(section_id, key)
            for text in (slot.ask_if, slot.skip_if):
                if text is None:
                    continue
                node, issues = qualify_gate(parse_when(text), namespace)
                assert issues == (), f"{ref}: {issues}"
                late.extend(
                    f"{ref} reads {read}"
                    for read in sorted(referenced_slots(node))
                    if ask_key[read] >= ask_key[ref]
                )
    return late


@pytest.mark.parametrize("slug", WAVE)
def test_wave_candidate_is_answer_driven(slug: str) -> None:
    gated = [k for k, s in _slots(_candidate(slug)).items() if s.get("ask_if")]
    assert len(gated) >= MIN_GATES, f"{slug}: {len(gated)} gated questions"


@pytest.mark.parametrize("slug", WAVE)
def test_every_wave_gate_is_a_yes_gate_on_an_earlier_boolean(slug: str) -> None:
    slots = _slots(_candidate(slug))
    order = list(slots)
    for key, slot in slots.items():
        gate = slot.get("ask_if")
        if gate is None:
            continue
        assert isinstance(gate, str) and GATE_FORM.match(gate), f"{slug}.{key}: {gate!r}"
        for read in re.findall(r"([a-z][a-z0-9_]*) == true", gate):
            assert read in slots, f"{slug}.{key} reads {read}, not declared in this pack"
            assert slots[read]["type"] == "boolean", f"{slug}.{key} reads non-boolean {read}"
            assert order.index(read) < order.index(key), f"{slug}.{key} reads later {read}"


@pytest.mark.parametrize("slug", WAVE)
def test_no_wave_gate_reads_a_slot_the_chain_asks_after_it(slug: str) -> None:
    assert _late_gates(_chain(slug)) == []


@pytest.mark.parametrize("slug", WAVE)
def test_wave_candidate_stays_an_unservable_l0_stub(slug: str) -> None:
    text = (REVIEW / "specialty" / f"{slug}.yaml").read_text("utf-8")
    doc = _candidate(slug)
    assert GEN.GEN_MARKER in text
    assert doc["maturity"] == "L0" and "clinical_signoff" not in doc
    rules = doc["red_flags"]
    assert isinstance(rules, list) and len(rules) == 1
    (rule,) = rules
    assert rule["id"] == f"rf.{slug}_l0_taslak"
    assert rule["status"] == "draft_needs_source"
    assert rule["when"].startswith(PENDING) and rule["when"].endswith("requires clinical sign-off")
    assert (rule["level"], rule["route"], rule["notify_clinic"]) == ("YESIL", "EXPEDITE", "never")
    assert not GEN.eligible(text, doc)


@pytest.mark.parametrize("slug", WAVE)
def test_wave_candidate_is_the_generator_output_of_its_proposal(
    slug: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "specialty"
    out.mkdir()
    (out / f"{slug}.yaml").write_bytes((REVIEW / "specialty" / f"{slug}.yaml").read_bytes())
    monkeypatch.setattr(GEN, "REVIEW", out)
    line, ok = GEN.gen(slug)
    assert ok and line.startswith(f"OK {slug}"), line
    assert (out / f"{slug}.yaml").read_bytes() == (
        REVIEW / "specialty" / f"{slug}.yaml"
    ).read_bytes()


@pytest.mark.parametrize("slug", WAVE)
def test_wave_patient_text_is_one_guarded_question_without_numerals(slug: str) -> None:
    guard = policy_guard_for(locale="tr", profile=VoiceProfile("residency_tr"))
    for key, slot in _slots(_candidate(slug)).items():
        for field in ("ask_tr", "follow_up_tr"):
            entry = slot.get(field)
            if entry is None:
                continue
            assert isinstance(entry, dict)
            text = entry["tr"]
            assert isinstance(text, str)
            assert text.count("?") == 1, f"{slug}.{key}.{field}"
            assert not re.search(r"\d", text), f"{slug}.{key}.{field}"
            longest = max(len(p.split()) for p in re.split(r"[.?!]", text) if p.strip())
            assert longest <= 15, f"{slug}.{key}.{field}: {longest} words"
            assert guard.inspect_sentence(text) == (), f"{slug}.{key}.{field}"


@pytest.mark.parametrize("slug", WAVE)
def test_wave_has_its_verification_and_a_packet_bound_to_the_candidate(slug: str) -> None:
    verification = (VERIFICATION / f"{slug}.md").read_text("utf-8")
    assert "## 2. Independent verification" in verification
    body = verification.split("## 2. Independent verification", 1)[1].split("## 3.", 1)[0]
    assert body.strip(), f"{slug}: the independent verification section is empty"
    proposal = (PROPOSALS / f"{slug}.md").read_text("utf-8")
    assert "INT-427" in proposal
    digest = hashlib.sha256((REVIEW / "specialty" / f"{slug}.yaml").read_bytes()).hexdigest()
    assert digest in (SIGNOFF / f"{slug}.md").read_text("utf-8")


# --- near-miss controls: the checks above are not vacuous ------------------------


def _synthetic(slots: dict[str, dict[str, object]]) -> ProtocolPack:
    return ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": "specialty.ornek",
            "layer": "specialty",
            "version": "0.3.0",
            "schema_version": 2,
            "maturity": "L0",
            "status": "synthetic near-miss control",
            "language": "tr",
            "extends": "cluster.medical",
            "sections": {"sorular": {"slots": slots}},
        }
    )


def _yes_no(ask_if: str | None = None) -> dict[str, object]:
    slot: dict[str, object] = {"type": "boolean", "ask_tr": {"tr": "Sentetik soru mu?"}}
    if ask_if is not None:
        slot["ask_if"] = ask_if
    return slot


def test_a_gate_on_a_slot_asked_later_is_caught() -> None:
    chain = [load_pack(BASE), load_pack(REVIEW / "cluster" / "medical.yaml")]
    late = _synthetic({"ayrinti": _yes_no("ana_soru == true"), "ana_soru": _yes_no()})
    assert _late_gates([*chain, late]) == ["sorular.ayrinti reads sorular.ana_soru"]
    early = _synthetic({"ana_soru": _yes_no(), "ayrinti": _yes_no("ana_soru == true")})
    assert _late_gates([*chain, early]) == []


@pytest.mark.parametrize(
    "gate",
    [
        "ana_soru != false",
        "ana_soru == 'evet'",
        "subject_role == 'kendim'",
        "a == true && b == true",
    ],
)
def test_a_gate_that_is_not_a_structural_yes_gate_is_refused(gate: str) -> None:
    assert not GATE_FORM.match(gate)


def test_a_structural_yes_gate_is_admitted() -> None:
    assert GATE_FORM.match("ana_soru == true")
    assert GATE_FORM.match("ana_soru == true || yan_soru == true")
