"""INT-327 — the specialty-pack generator emits one question per turn, keeps
packs L0 until signed, and carries invariant 17's pending-value marker only
inside the draft_needs_source stub."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

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


def test_a_d3_data_category_is_emitted_and_an_unknown_one_is_refused() -> None:
    """INT-432 CD-11: the owner approved workplace exposure as a data category,
    and the slot must carry it (invariant 18). Near misses: general_health is
    the default and never written, and a category outside the closed D3 set is
    refused rather than emitted for the loader to catch later."""
    tagged = PROPOSAL.replace(
        "gen: slot=bayginlik; type=boolean",
        "gen: slot=bayginlik; type=boolean; delivery=text_first; data_category=occupational",
    )
    qs, warnings = GEN.extract_questions(tagged)
    slot = GEN.build_pack(DRAFT, "ornek", qs)["sections"]["sorular"]["slots"]["bayginlik"]
    assert slot["data_category"] == "occupational" and slot["delivery"] == "text_first"
    assert not any("data_category" in w for w in warnings)
    for refused in ("general_health", "mesleki"):
        text = PROPOSAL.replace(
            "gen: slot=bayginlik; type=boolean",
            f"gen: slot=bayginlik; type=boolean; data_category={refused}",
        )
        qs, warnings = GEN.extract_questions(text)
        assert "bayginlik" not in {q.slot for q in qs}, refused
        assert any("unknown data_category" in w for w in warnings), refused


def test_the_gogus_occupational_item_carries_its_category_and_text_first() -> None:
    """The applied CD-11 owner answer, in the regenerated review pack."""
    import yaml

    pack = yaml.safe_load((GEN.REVIEW / "gogus_hastaliklari.yaml").read_text(encoding="utf-8"))
    slots = {k: v for s in pack["sections"].values() for k, v in s["slots"].items()}
    assert slots["mesleki_toz_duman_gaz"]["data_category"] == "occupational"
    assert slots["mesleki_toz_duman_gaz"]["delivery"] == "text_first"


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


# --- INT-469: a branch drops an inherited slot through one suppress_slot op ----

INHERITED = {
    "ziyaret_baglami": {
        "basvuru_nedeni": {"type": "string", "required": True},
        "sikayet_suresi": {"type": "duration"},
    },
    "sorular": {
        "bayginlik": {"type": "boolean"},
        "rapor_icin_basvuru": {"type": "boolean"},
        "rapor_amaci": {"type": "string", "ask_if": "rapor_icin_basvuru == true"},
        "kurum_sevk_yazisi": {"type": "boolean", "ask_if": "rapor_icin_basvuru == true"},
    },
    "hpi": {"onset": {"type": "string", "must_ask": True}},
}
SUPPRESS_OP = {"op": "suppress_slot", "pointer": "/sections/sorular/slots/rapor_amaci"}


def _with_pack_line(line: str) -> str:
    return PROPOSAL.replace(
        "## 4. Candidate B1 Turkish pre-visit questions (5)\n",
        f"## 4. Candidate B1 Turkish pre-visit questions (5)\n\npack: {line}\n",
    )


def test_a_pack_line_suppresses_an_inherited_slot_through_one_suppress_slot_op() -> None:
    text = _with_pack_line("suppress=sorular.rapor_amaci")
    options = GEN.extract_pack_options(text)
    qs, _ = GEN.extract_questions(text)
    pack = GEN.build_pack(DRAFT, "ornek", qs, options=options, inherited=INHERITED)
    assert pack["ops"] == [SUPPRESS_OP]
    assert list(pack)[-2:] == ["ops", "red_flags"]
    assert "rapor_amaci" not in pack["sections"]["sorular"]["slots"]


def test_near_miss_without_a_suppress_line_the_pack_carries_no_ops() -> None:
    qs, _ = GEN.extract_questions(PROPOSAL)
    pack = GEN.build_pack(DRAFT, "ornek", qs, options={}, inherited=INHERITED)
    assert "ops" not in pack


@pytest.mark.parametrize(
    ("spec", "why"),
    [
        ("sorular.olmayan_slot", "does not declare"),
        ("hpi.onset", "must_ask"),
        ("sorular.bayginlik", "declares itself"),
        ("sorular.rapor_icin_basvuru", "gate"),
    ],
)
def test_a_suppression_the_compiler_would_refuse_is_refused_by_the_generator(
    spec: str, why: str
) -> None:
    text = _with_pack_line(f"suppress={spec}")
    options = GEN.extract_pack_options(text)
    qs, _ = GEN.extract_questions(text)
    with pytest.raises(ValueError, match=why):
        GEN.build_pack(DRAFT, "ornek", qs, options=options, inherited=INHERITED)


@pytest.mark.parametrize(
    "spec", ["rapor_amaci", "sorular/rapor_amaci", "sorular.rapor_amaci,sorular.rapor_amaci"]
)
def test_a_malformed_or_repeated_suppress_target_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="suppress target"):
        GEN.extract_pack_options(_with_pack_line(f"suppress={spec}"))


def test_inherited_slots_are_the_base_and_the_extended_cluster_candidate() -> None:
    slots = GEN.inherited_slots("cluster.allied_and_reports")
    assert "rapor_amaci" in slots["sorular"]
    assert slots["sorular"]["rapor_amaci"].get("must_ask") is not True
    assert any(slot.get("must_ask") for section in slots.values() for slot in section.values())
    assert "rapor_amaci" not in GEN.inherited_slots("cluster.medical").get("sorular", {})


def test_the_adli_tip_candidate_is_what_the_generator_emits_from_its_proposal() -> None:
    import yaml

    slug = "adli_tip"
    text = (GEN.PROP / f"{slug}.md").read_text(encoding="utf-8")
    draft = yaml.safe_load((GEN.SPEC / f"{slug}.yaml").read_text(encoding="utf-8"))
    qs, _ = GEN.extract_questions(text)
    pack = GEN.build_pack(
        draft,
        slug,
        qs,
        base_slots=GEN.base_slot_names(),
        options=GEN.extract_pack_options(text),
        inherited=GEN.inherited_slots(draft["extends"]),
    )
    committed = (GEN.REVIEW / f"{slug}.yaml").read_text(encoding="utf-8")
    emitted = GEN.header(slug) + yaml.safe_dump(
        pack, allow_unicode=True, sort_keys=False, width=1000
    )
    assert committed == emitted
    assert pack["ops"] == [SUPPRESS_OP]


# --- held proposal items never reach a review candidate (CD-105) ---------------


def _held_items(md_text: str) -> list[tuple[str | None, str]]:
    """(slot id or None, question text) of every candidate item a `hold=` keeps out."""
    held: list[tuple[str | None, str]] = []
    for seg in re.split(r"\n\*\*Q", "\n" + GEN._question_region(md_text))[1:]:
        gm = re.search(r"^gen:\s*(.+)$", seg, re.M)
        qm = re.search(r'>\s*"(.+?)"', seg, re.S)
        if gm is None or qm is None:
            continue
        gen = GEN._parse_gen(gm.group(1))
        if "hold" in gen:
            text = re.sub(r"\s+", " ", re.sub(r"\s*\n>\s*", " ", qm.group(1))).strip()
            held.append((gen.get("slot"), text))
    return held


def _candidate_slots(path: Path) -> dict[str, Any]:
    pack = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {key: slot for s in pack["sections"].values() for key, slot in s["slots"].items()}


def _proposals_with_candidates() -> list[tuple[str, Path]]:
    pairs: list[tuple[str, Path]] = []
    for proposal in sorted(GEN.PROP.glob("*.md")):
        slug = proposal.stem
        if slug.startswith("_"):
            continue
        if slug.startswith(GEN.CLUSTER_PREFIX):
            path = GEN.REVIEW_CLUSTER / f"{slug.removeprefix(GEN.CLUSTER_PREFIX)}.yaml"
        else:
            path = GEN.REVIEW / f"{slug}.yaml"
        if path.exists():
            pairs.append((slug, path))
    return pairs


PROPOSALS_WITH_CANDIDATES = _proposals_with_candidates()


@pytest.mark.parametrize(
    ("slug", "path"), PROPOSALS_WITH_CANDIDATES, ids=[s for s, _ in PROPOSALS_WITH_CANDIDATES]
)
def test_no_held_proposal_item_reaches_its_review_candidate(slug: str, path: Path) -> None:
    slots = _candidate_slots(path)
    asks = {slot["ask_tr"]["tr"] for slot in slots.values()}
    for slot_id, text in _held_items((GEN.PROP / f"{slug}.md").read_text(encoding="utf-8")):
        assert slot_id not in slots, f"{slug}: held slot {slot_id} is in the candidate"
        assert text not in asks, f"{slug}: held question {text!r} is in the candidate"


def test_the_held_item_sweep_covers_the_review_queue() -> None:
    assert len(PROPOSALS_WITH_CANDIDATES) >= 90
    assert any(
        _held_items((GEN.PROP / f"{s}.md").read_text("utf-8")) for s, _ in PROPOSALS_WITH_CANDIDATES
    )


def test_near_miss_the_same_item_unheld_reaches_the_pack_and_held_does_not() -> None:
    line = "gen: slot=son_adet_tarihi; type=date"
    held_text = PROPOSAL.replace(line, f"{line}; hold=karar bekleniyor")
    for text, expected in ((PROPOSAL, True), (held_text, False)):
        qs, _ = GEN.extract_questions(text)
        slots = GEN.build_pack(DRAFT, "ornek", qs)["sections"]["sorular"]["slots"]
        assert ("son_adet_tarihi" in slots) is expected
    assert _held_items(held_text)[-1] == (
        "son_adet_tarihi",
        "Son adetinizin ilk günü hangi tarihti?",
    )
    assert ("son_adet_tarihi", "Son adetinizin ilk günü hangi tarihti?") not in _held_items(
        PROPOSAL
    )


def test_adli_tip_safety_items_held() -> None:
    """CD-105 (wave 1-3 finding 21): the feeling-safe, companion and
    neck-compression items each carry a hold line and are absent from the
    emitted adli_tip pack. Near miss: suregelen_hastalik stays emitted."""
    held = _held_items((GEN.PROP / "adli_tip.md").read_text(encoding="utf-8"))
    held_slots = {slot for slot, _ in held if slot is not None}
    assert held_slots == {"su_an_guvende", "boyun_baski_sonrasi_belirti"}
    assert any(text.startswith("Randevuya sizinle birlikte") for slot, text in held if slot is None)
    slots = _candidate_slots(GEN.REVIEW / "adli_tip.yaml")
    assert not held_slots & set(slots)
    assert "suregelen_hastalik" in slots and "doktora_onceden_not" in slots
