"""INT-327 — the specialty-pack generator emits one question per turn, keeps
packs L0 until signed, and carries invariant 17's pending-value marker only
inside the draft_needs_source stub."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_specialty_packs", ROOT / "scripts/dev/gen_specialty_packs.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


GEN = _load()

PROPOSAL = """# Sample

## 3. openEHR archetype mapping

| item | archetype |
|---|---|

## 4. Candidate B1 Turkish pre-visit questions (5)

**Q1 — Reason** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general
> "Bugün sizi buraya getiren nedeni kısaca anlatır mısınız?"

**Q2 — Fainting** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
> "Son zamanlarda hiç bayıldınız mı?"
gen: slot=bayginlik; type=boolean

**Q3 — Fainting on effort** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
> "Bu baygınlık efor sırasında mı oldu?"
gen: slot=efor_bayginlik; type=boolean; ask_if=bayginlik == true

**Q4 — Two questions** · source: S2
> "Ağrınız var mı? Ne zamandır sürüyor?"

**Q5 — Unsourced** · source: none
> "Karnınızda şişlik var mı?"
gen: hold=NO SOURCE FOUND

**Q6 — Digit** · source: S3
> "Son 3 günde ateşiniz oldu mu?"

**Q7 — Last menstrual period** · archetype: `OBSERVATION.menstrual_cycle.v1` · source: S4
> "Son adetinizin ilk günü hangi tarihti?"
gen: slot=son_adet_tarihi; type=date

## 5. Gaps
"""

DRAFT = {"id": "specialty.ornek", "title_tr": "Örnek (L0 taslak)", "extends": "cluster.medical"}


def test_questions_are_found_by_section_title_not_by_number() -> None:
    qs, _ = GEN.extract_questions(PROPOSAL)
    assert [q.text for q in qs][0].startswith("Bugün sizi buraya")
    assert len(qs) == 4


def test_multi_question_digit_and_held_items_are_refused_with_a_warning() -> None:
    qs, warnings = GEN.extract_questions(PROPOSAL)
    texts = " ".join(q.text for q in qs)
    assert "Ne zamandır sürüyor" not in texts
    assert "şişlik" not in texts
    assert not any(ch.isdigit() for ch in texts)
    assert any("invariant 2" in w for w in warnings)
    assert any("invariant 22" in w for w in warnings)
    assert any("hold" in w for w in warnings)


def test_gen_line_sets_slot_id_type_and_gate() -> None:
    qs, _ = GEN.extract_questions(PROPOSAL)
    pack = GEN.build_pack(DRAFT, "ornek", qs)
    slots = pack["sections"]["sorular"]["slots"]
    assert slots["bayginlik"]["type"] == "boolean"
    assert slots["efor_bayginlik"]["ask_if"] == "bayginlik == true"
    assert slots["son_adet_tarihi"]["type"] == "date"


def test_fixed_slots_ask_exactly_one_question_each_and_carry_a_follow_up() -> None:
    qs, _ = GEN.extract_questions(PROPOSAL)
    ctx = GEN.build_pack(DRAFT, "ornek", qs)["sections"]["ziyaret_baglami"]["slots"]
    for name in ("basvuru_nedeni", "sikayet_suresi"):
        assert ctx[name]["ask_tr"]["tr"].count("?") == 1
        assert ctx[name]["follow_up_tr"]["tr"].count("?") == 1


def test_every_emitted_ask_is_one_question_without_a_digit() -> None:
    qs, _ = GEN.extract_questions(PROPOSAL)
    pack = GEN.build_pack(DRAFT, "ornek", qs)
    for section in pack["sections"].values():
        for slot in section["slots"].values():
            for field in ("ask_tr", "follow_up_tr"):
                if field in slot:
                    text = slot[field]["tr"]
                    assert text.count("?") == 1, text
                    assert not any(ch.isdigit() for ch in text), text


def test_pack_stays_l0_until_signed_and_every_slot_records_its_openehr_deferral() -> None:
    qs, _ = GEN.extract_questions(PROPOSAL)
    pack = GEN.build_pack(DRAFT, "ornek", qs)
    assert pack["maturity"] == "L0"
    for section in pack["sections"].values():
        for slot in section["slots"].values():
            assert slot["openehr_deferred_reason"].startswith("INT-032")


def test_pending_marker_appears_only_inside_the_draft_needs_source_stub() -> None:
    qs, _ = GEN.extract_questions(PROPOSAL)
    pack = GEN.build_pack(DRAFT, "ornek", qs)
    (rule,) = pack["red_flags"]
    assert rule["status"] == "draft_needs_source"
    assert rule["when"].startswith("T" + "ODO:")
    assert rule["level"] == "YESIL"
    source = (ROOT / "scripts/dev/gen_specialty_packs.py").read_text(encoding="utf-8")
    assert ("T" + "ODO") not in source


def test_signed_and_hand_authored_packs_are_never_regenerated() -> None:
    assert GEN.eligible("", {"clinical_signoff": {"by": "x"}}) is not None
    assert GEN.eligible(
        "# hand written\n", {"maturity": "L0", "status": "questions-authored; x"}
    ) == ("hand-authored")
    assert (
        GEN.eligible(GEN.GEN_MARKER, {"maturity": "L0", "status": "questions-authored; x"}) is None
    )


def test_duplicate_slot_ids_are_refused() -> None:
    q = GEN.Question(text="Bir şey var mı?", slot="aynisi")
    with pytest.raises(ValueError):
        GEN.build_pack(DRAFT, "ornek", [q, q, q])


def test_generator_writes_only_the_review_queue_never_the_served_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, review, prop = tmp_path / "specialty", tmp_path / "review", tmp_path / "proposals"
    spec.mkdir()
    prop.mkdir()
    served = spec / "ornek.yaml"
    served.write_text(
        "kind: pack\nid: specialty.ornek\nmaturity: L0\ntitle_tr: Örnek (L0 taslak)\n",
        encoding="utf-8",
    )
    before = served.read_bytes()
    (prop / "ornek.md").write_text(PROPOSAL, encoding="utf-8")
    monkeypatch.setattr(GEN, "SPEC", spec)
    monkeypatch.setattr(GEN, "REVIEW", review)
    monkeypatch.setattr(GEN, "PROP", prop)
    line, ok = GEN.gen("ornek")
    assert ok, line
    assert served.read_bytes() == before
    candidate = (review / "ornek.yaml").read_text(encoding="utf-8")
    assert GEN.GEN_MARKER in candidate
    assert "maturity: L0" in candidate


def test_a_refused_q1_skips_the_pack_instead_of_promoting_q2_to_the_reason_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, review, prop = tmp_path / "specialty", tmp_path / "review", tmp_path / "proposals"
    spec.mkdir()
    prop.mkdir()
    (spec / "ornek.yaml").write_text(
        "kind: pack\nid: specialty.ornek\nmaturity: L0\ntitle_tr: Örnek (L0 taslak)\n",
        encoding="utf-8",
    )
    broken = PROPOSAL.replace(
        '> "Bugün sizi buraya getiren nedeni kısaca anlatır mısınız?"',
        '> "Neden geldiniz? Ne zamandır var?"',
    )
    (prop / "ornek.md").write_text(broken, encoding="utf-8")
    monkeypatch.setattr(GEN, "SPEC", spec)
    monkeypatch.setattr(GEN, "REVIEW", review)
    monkeypatch.setattr(GEN, "PROP", prop)
    line, ok = GEN.gen("ornek")
    assert not ok
    assert "Q1" in line
    assert not (review / "ornek.yaml").exists()


def test_delivery_is_emitted_and_unknown_gen_keys_are_refused() -> None:
    text = PROPOSAL.replace(
        "gen: slot=bayginlik; type=boolean",
        "gen: slot=bayginlik; type=boolean; delivery=text_first",
    ).replace(
        "gen: slot=son_adet_tarihi; type=date",
        "gen: slot=son_adet_tarihi; type=date; askif=bayginlik == true",
    )
    qs, warnings = GEN.extract_questions(text)
    pack = GEN.build_pack(DRAFT, "ornek", qs)
    assert pack["sections"]["sorular"]["slots"]["bayginlik"]["delivery"] == "text_first"
    assert "son_adet_tarihi" not in pack["sections"]["sorular"]["slots"]
    assert any("unknown gen key" in w for w in warnings)


def test_a_gate_on_an_undeclared_slot_is_refused_but_base_slots_are_readable() -> None:
    q1 = GEN.Question(text="Neden geldiniz?", number=1)
    gated = GEN.Question(text="Ne oldu?", slot="devam", ask_if="olmayan_slot == true")
    with pytest.raises(ValueError, match="undeclared"):
        GEN.build_pack(DRAFT, "ornek", [q1, gated, gated])
    base_gated = GEN.Question(text="Ne oldu?", slot="devam", ask_if="subject_role != 'kendim'")
    other = GEN.Question(text="Başka?", slot="baska")
    pack = GEN.build_pack(DRAFT, "ornek", [q1, base_gated, other], base_slots=GEN.base_slot_names())
    assert pack["sections"]["sorular"]["slots"]["devam"]["ask_if"] == "subject_role != 'kendim'"


def test_a_pack_line_overrides_the_duration_ask_with_one_question_only() -> None:
    text = PROPOSAL.replace(
        "## 5. Gaps",
        "pack: duration_ask=Sigarayı ne zamandır içiyorsunuz?\n\n## 5. Gaps",
    )
    text = text.replace(
        "## 4. Candidate B1 Turkish pre-visit questions (5)\n",
        "## 4. Candidate B1 Turkish pre-visit questions (5)\n\n"
        "pack: duration_ask=Sigarayı ne zamandır içiyorsunuz?\n",
    )
    options = GEN.extract_pack_options(text)
    qs, _ = GEN.extract_questions(text)
    pack = GEN.build_pack(DRAFT, "ornek", qs, options=options)
    ask = pack["sections"]["ziyaret_baglami"]["slots"]["sikayet_suresi"]["ask_tr"]["tr"]
    assert ask == "Sigarayı ne zamandır içiyorsunuz?"
    with pytest.raises(ValueError):
        GEN.extract_pack_options(text.replace("içiyorsunuz?", "içiyorsunuz? Kaç yıl?"))


def test_a_cluster_proposal_becomes_a_cluster_candidate_extending_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review, served, prop = tmp_path / "review", tmp_path / "served", tmp_path / "proposals"
    prop.mkdir()
    (prop / "cluster_medical.md").write_text(PROPOSAL, encoding="utf-8")
    monkeypatch.setattr(GEN, "REVIEW_CLUSTER", review)
    monkeypatch.setattr(GEN, "SERVED_CLUSTER", served)
    monkeypatch.setattr(GEN, "PROP", prop)
    line, ok = GEN.gen("cluster_medical")
    assert ok, line
    import yaml

    pack = yaml.safe_load((review / "medical.yaml").read_text(encoding="utf-8"))
    assert pack["id"] == "cluster.medical"
    assert pack["layer"] == "cluster"
    assert pack["extends"] == "base.intake"
    assert pack["maturity"] == "L0"
    assert not served.exists()


def test_an_unknown_cluster_is_refused() -> None:
    line, ok = GEN.gen("cluster_not_a_cluster")
    assert not ok
    assert "unknown cluster" in line
