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
from protocols.compile.resolve import _apply_ops, _merge_chain, _ordered_ops
from protocols.loader import PackRegistry, load_pack
from protocols.pack import ProtocolPack
from protocols.validator import validate_packs

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
    # One `pack:` line: a second one is refused (verification 628 L-4).
    text = PROPOSAL.replace(
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


# --- One fact, one id along an extends chain (cluster verification §F) -------
#
# A branch pack extends its cluster, and the resolver's _merge_chain replaces a
# cluster slot with the branch slot of the SAME id. The same fact under another
# id is therefore asked twice. Each row below is a rebind applied from
# docs/evidence/verification/cluster-wave-a.md or cluster-wave-b.md §F:
# (branch slug, proposal question number, id before, cluster id). `soru_N` is
# the generator's id for an item that had no `gen:` line.

REVIEW_ROOT = ROOT / "packages/protocols/review"
SIBLING_REBINDS = [
    ("enfeksiyon_hastaliklari", 2, "ates_var_mi", "son_gunlerde_ates"),
    ("diyabet_poliklinigi", 5, "aciklanamayan_kilo_kaybi", "istemsiz_kilo_kaybi"),
    ("tibbi_ekoloji_ve_hidroklimatoloji", 8, "yuksek_tansiyon_oykusu", "yuksek_tansiyon_tanisi"),
    ("ic_hastaliklari", 3, "soru_2", "istemsiz_kilo_kaybi"),
    ("el_cerrahisi", 2, "yaralanma_sonrasi_basladi", "travma_sonrasi_basladi"),
    ("kulak_burun_bogaz_hastaliklari", 2, "soru_1", "ani_isitme_azalmasi"),
    ("kulak_burun_bogaz_hastaliklari", 8, "soru_7", "ses_kisikligi"),
    ("goz_hastaliklari", 7, "soru_6", "goz_agrisi"),
    ("goz_hastaliklari", 9, "soru_8", "isik_cevresinde_halka"),
    ("goz_hastaliklari", 11, "soru_10", "kontakt_lens"),
    ("gebe_poliklinigi", 11, "siddetli_bas_agrisi", "gebelikte_siddetli_bas_agrisi"),
    ("perinatoloji", 11, "gorme_bulanikligi", "gebelikte_gorme_bozuklugu"),
    ("jinekolojik_onkoloji", 8, "kasik_alt_karin_agrisi", "alt_karin_agrisi"),
    ("neonatoloji", 10, "ates", "ates_var_mi"),
    ("neonatoloji", 11, "asiri_uykululuk", "uykulu_tepkisiz"),
    ("cocuk_metabolizma_hastaliklari", 6, "uykulu_halsiz", "uykulu_tepkisiz"),
    ("cocuk_genetik_hastaliklari", 9, "alisilmadik_halsizlik", "uykulu_tepkisiz"),
    ("cocuk_enfeksiyon_hastaliklari", 2, "ates_oldu", "ates_var_mi"),
    ("cocuk_enfeksiyon_hastaliklari", 7, "asiri_uykulu_halsiz", "uykulu_tepkisiz"),
    ("cocuk_enfeksiyon_hastaliklari", 11, "suregen_hastalik_tanisi", "suregen_tani"),
    ("cocuk_gogus_hastaliklari", 8, "gogus_ice_cekilmesi", "gogus_icine_cekilme"),
    ("klinik_psikoloji_poliklinigi", 9, "psikiyatrik_ilac_kullanimi", "ruh_sagligi_ilaci"),
    ("amatem", 12, "destek_cevresi", "sosyal_destek"),
    ("endodonti", 3, "sicak_soguk_agri", "dis_hassasiyeti"),
    ("agiz_dis_ve_cene_cerrahisi", 2, "yuz_cene_dil_alti_sislik", "yuz_cene_sisligi"),
    ("agiz_dis_ve_cene_cerrahisi", 3, "nefes_yutma_zorlugu", "nefes_yutkunma_guclugu"),
    ("agiz_dis_ve_cene_cerrahisi", 4, "sislikle_ates", "sislik_ile_ates"),
    ("agiz_dis_ve_cene_cerrahisi", 5, "agiz_acma_zorlugu", "agiz_acma_guclugu"),
    ("agiz_dis_ve_cene_cerrahisi", 10, "uzamis_kanama_oykusu", "islem_sonrasi_uzun_kanama"),
    ("agiz_dis_cene_radyolojisi", 8, "yuz_cene_dil_alti_sislik", "yuz_cene_sisligi"),
    ("agiz_dis_cene_radyolojisi", 9, "nefes_yutma_zorlugu", "nefes_yutkunma_guclugu"),
]
# Near duplicates the clinician decides (review of PR #582, §D-1 and §D-3;
# HB-C1, plus a psychiatrist for amatem and klinik psikoloji). The branch ask
# differs from the cluster's in recall window or construct, so each keeps its
# pre-PR id until the clinician adopts the cluster text or keeps it apart: a
# repeated question fails closed, a wrong merge loses a window or a construct.
# (branch slug, proposal question number, own id, cluster id)
CLINICIAN_HELD = [
    ("ic_hastaliklari", 4, "soru_3", "son_gunlerde_ates"),
    ("ic_hastaliklari", 5, "soru_4", "gece_terlemesi"),
    ("kulak_burun_bogaz_hastaliklari", 5, "soru_4", "donme_hissi"),
    ("kulak_burun_bogaz_hastaliklari", 7, "soru_6", "boyunda_sislik"),
    ("amatem", 6, "gunluk_yasam_etkisi", "islevsellik_etkilenimi"),
    ("klinik_psikoloji_poliklinigi", 8, "onceki_psikoterapi", "onceki_ruh_sagligi_destegi"),
]
# Opposite polarity to the cluster's hydration items (`false` is the cluster's
# alarm direction): renaming would invert the answer. The paediatrician picks
# one polarity first (cluster-wave-b §F), so these keep their own ids.
POLARITY_HELD = [
    ("neonatoloji", "beslenmede_azalma", "beslenme_sivi_alimi"),
    ("neonatoloji", "islak_bez_azalmasi", "cis_miktari"),
    ("cocuk_gastroenterolojisi", "az_cis", "cis_miktari"),
    ("cocuk_nefrolojisi", "idrar_azalmasi", "cis_miktari"),
]


def _pack(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc


def _slots(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        sid: slot
        for section in (pack.get("sections") or {}).values()
        for sid, slot in ((section or {}).get("slots") or {}).items()
    }


def _chain(slug: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """(branch candidate, its cluster candidate, cluster proposal text)."""
    branch = _pack(REVIEW_ROOT / "specialty" / f"{slug}.yaml")
    name = branch["extends"].removeprefix("cluster.")
    cluster = _pack(REVIEW_ROOT / "cluster" / f"{name}.yaml")
    proposal = (GEN.PROP / f"cluster_{name}.md").read_text(encoding="utf-8")
    return branch, cluster, proposal


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _chains() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    out = []
    for path in sorted((REVIEW_ROOT / "specialty").glob("*.yaml")):
        branch = _pack(path)
        name = str(branch.get("extends", "")).removeprefix("cluster.")
        cluster_p = REVIEW_ROOT / "cluster" / f"{name}.yaml"
        if cluster_p.exists():
            out.append((path.stem, branch, _pack(cluster_p)))
    return out


def _question(slug: str, qnum: int) -> Any:
    """The branch proposal's question numbered `qnum`, as the generator parses it."""
    questions, _ = GEN.extract_questions((GEN.PROP / f"{slug}.md").read_text(encoding="utf-8"))
    (question,) = [q for q in questions if q.number == qnum]
    return question


@pytest.mark.parametrize(
    ("slug", "qnum", "old", "new"),
    SIBLING_REBINDS,
    ids=[f"{s}:Q{q}:{o}->{n}" for s, q, o, n in SIBLING_REBINDS],
)
def test_a_rebound_branch_slot_takes_its_cluster_id(
    slug: str, qnum: int, old: str, new: str
) -> None:
    branch, cluster, cluster_proposal = _chain(slug)
    slots, cluster_slots = _slots(branch), _slots(cluster)
    assert new in slots, f"{slug} does not declare the cluster id {new}"
    assert old not in slots, f"{slug} still declares {old}"
    # The id binds the question §F names, so two rebound ids swapped inside one
    # pack (in the proposal or in the candidate) fail here.
    question = _question(slug, qnum)
    assert question.slot == new, f"{slug} Q{qnum} binds {question.slot}, not {new}"
    assert slots[new]["ask_tr"]["tr"] == question.text, f"{slug}.{new} is not Q{qnum}'s ask"
    held = re.search(rf"^gen:\s*slot={new};.*\bhold=", cluster_proposal, re.M)
    assert new in cluster_slots or held, f"{branch['extends']} declares no {new}"
    if new in cluster_slots:
        assert slots[new]["type"] == cluster_slots[new]["type"]
    for sid, slot in slots.items():
        assert old not in GEN.gate_reads(slot), f"{slug}.{sid}"


def test_no_chain_asks_one_text_under_two_ids() -> None:
    twins = []
    for slug, branch, cluster in _chains():
        by_text = {_norm(s["ask_tr"]["tr"]): sid for sid, s in _slots(cluster).items()}
        for sid, slot in _slots(branch).items():
            other = by_text.get(_norm(slot["ask_tr"]["tr"]))
            if other is not None and other != sid:
                twins.append(f"{slug}.{sid} = {branch['extends']}.{other}")
    assert twins == []


def test_no_chain_declares_one_slot_id_with_two_types() -> None:
    clashes = []
    for slug, branch, cluster in _chains():
        cluster_slots = _slots(cluster)
        for sid, slot in _slots(branch).items():
            if sid in cluster_slots and cluster_slots[sid]["type"] != slot["type"]:
                clashes.append(f"{slug}.{sid}: {slot['type']} vs {cluster_slots[sid]['type']}")
    assert clashes == []


@pytest.mark.parametrize("slug", ["cocuk_sagligi_ve_hastaliklari", "cocuk_gogus_hastaliklari"])
def test_the_chest_indrawing_twins_carry_the_cluster_text(slug: str) -> None:
    branch, cluster, _ = _chain(slug)
    ask = _slots(branch).get("gogus_icine_cekilme", {}).get("ask_tr", {}).get("tr")
    assert ask == _slots(cluster)["gogus_icine_cekilme"]["ask_tr"]["tr"]


@pytest.mark.parametrize(
    ("slug", "sid"),
    [
        ("ruh_sagligi_ve_hastaliklari", "diger_madde_kullanimi"),
        ("klinik_psikoloji_poliklinigi", "zorlanmada_madde_kullanimi"),
    ],
)
def test_substance_items_are_gated_to_self_report(slug: str, sid: str) -> None:
    branch, _, _ = _chain(slug)
    assert _slots(branch)[sid].get("ask_if") == "subject_role == 'kendim'"


@pytest.mark.parametrize(("slug", "own", "cluster_id"), POLARITY_HELD)
def test_opposite_polarity_twins_keep_their_own_ids(slug: str, own: str, cluster_id: str) -> None:
    branch, cluster, _ = _chain(slug)
    assert own in _slots(branch)
    assert cluster_id not in _slots(branch)
    assert cluster_id in _slots(cluster)


@pytest.mark.parametrize(
    ("slug", "qnum", "own", "cluster_id"),
    CLINICIAN_HELD,
    ids=[f"{s}:Q{q}:{o}" for s, q, o, _ in CLINICIAN_HELD],
)
def test_a_near_duplicate_left_to_the_clinician_keeps_its_own_id(
    slug: str, qnum: int, own: str, cluster_id: str
) -> None:
    branch, cluster, _ = _chain(slug)
    slots = _slots(branch)
    question = _question(slug, qnum)
    # A `soru_N` id comes from a question with no `gen:` slot.
    assert question.slot in (None, own), f"{slug} Q{qnum} binds {question.slot}"
    assert slots[own]["ask_tr"]["tr"] == question.text, f"{slug}.{own} is not Q{qnum}'s ask"
    assert cluster_id not in slots
    assert cluster_id in _slots(cluster)


def test_committed_candidates_equal_the_generator_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every generated review candidate is byte-equal to a fresh run of its proposal."""
    monkeypatch.setattr(GEN, "REVIEW", tmp_path / "specialty")
    monkeypatch.setattr(GEN, "REVIEW_CLUSTER", tmp_path / "cluster")
    checked, drift = 0, []
    for layer in ("specialty", "cluster"):
        for path in sorted((REVIEW_ROOT / layer).glob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            if GEN.eligible(text, yaml.safe_load(text)) is not None:
                continue  # hand-authored or signed: the generator never rewrites it
            slug = path.stem if layer == "specialty" else GEN.CLUSTER_PREFIX + path.stem
            line, ok = GEN.gen(slug)
            if ok and line.startswith("skip "):
                continue  # the served pack is past L0, so the generator leaves it
            fresh = tmp_path / layer / path.name
            checked += 1
            if not ok or not fresh.exists() or fresh.read_bytes() != path.read_bytes():
                drift.append(f"{layer}/{path.name}: {line}")
    assert drift == []
    assert checked > 0


# --- INT-379: duration=omit, code answers, skip_if -----------------------------
#
# Three things the department verifications could not express (wave 7 §E-2,
# cluster-wave-b Q14, cluster-wave-a women's health Q13/Q14). Each key has an
# acceptance test, its refusals and a near-miss control. No committed proposal
# uses them: where to use them is the clinician's choice (HB-C1, HB-C3, HB-C5).
# Every patient-facing text below is one already in this file or in base.intake.

BASE_PACK = ROOT / "packages/protocols/base/intake.yaml"
REVIEW_CLUSTER_MEDICAL = REVIEW_ROOT / "cluster" / "medical.yaml"
# The refusal code for an answer option no base.intake label carries.
UNKNOWN_OPTION = "CODE_OPTION_NOT_IN_VOCABULARY"
REASON_TEXT = "Bugün sizi buraya getiren nedeni kısaca anlatır mısınız?"
REASON_Q = GEN.Question(text=REASON_TEXT, number=1)
ITEM_TEXTS = (
    "Son zamanlarda hiç bayıldınız mı?",
    "Bu baygınlık efor sırasında mı oldu?",
    "Karnınızda şişlik var mı?",
)


def _items(*gens: str | None) -> str:
    """A proposal: Q1 (the reason), then one item per `gen:` line (None: no line)."""
    body = '**Q1 — Reason** · source: general\n> "' + REASON_TEXT + '"\n'
    for number, (text, gen) in enumerate(zip(ITEM_TEXTS, gens, strict=False), 2):
        body += f'\n**Q{number} — Item** · source: S{number}\n> "{text}"\n'
        body += f"gen: {gen}\n" if gen else ""
    return "# Sample\n\n## 4. Candidate questions\n\n" + body + "\n## 5. Gaps\n"


def _pack_line(line: str) -> str:
    return _items("slot=bayginlik; type=boolean", None).replace(
        "## 4. Candidate questions\n", f"## 4. Candidate questions\n\npack: {line}\n"
    )


def _sorular(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    slots: dict[str, dict[str, Any]] = pack["sections"]["sorular"]["slots"]
    return slots


def _base_choices(ref: str) -> list[str]:
    section, key = ref.split(".")
    labels: list[str] = _pack(BASE_PACK)["sections"][section]["slots"][key]["choices_tr"]["tr"]
    return labels


# duration=omit ------------------------------------------------------------------
#
# Verification 628 H-1: the compiler refuses a suppress_slot that removes a slot a
# red flag reads for an overlay only (OVERLAY_REMOVES_RULE_SLOT); the same op in a
# chain pack compiles and the rule is served but never fires (INT-382 fixes the
# compiler). So the generator refuses `duration=omit` while any base, parent-chain or
# own rule, draft or signed, reads sikayet_suresi. Every generated stub anchors on it,
# so today omit is refused everywhere. That is the true state. The stubs are not
# re-anchored here: that is red-flag semantics, the clinician's (INT-383).

DURATION_REFUSAL = "DURATION_OMIT_RULE_READS_SLOT"
CLUSTERS = sorted(path.stem for path in (REVIEW_ROOT / "cluster").glob("*.yaml"))


@pytest.fixture
def stub_anchor_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a clinician-chosen stub anchor on base's dated `onset_date` (INT-383).

    The generator anchors every stub on sikayet_suresi and this change does not move
    it. Only under this simulation does `duration=omit` pass H-1's refusal, so these
    tests can pin what omit emits once no rule reads the slot.
    """
    monkeypatch.setattr(GEN, "STUB_TENSE_ANCHOR", "onset_date")


def _anchored_elsewhere(doc: dict[str, Any]) -> dict[str, Any]:
    """A copy of a pack document whose red flags anchor on `onset_date` (simulation)."""
    copy: dict[str, Any] = yaml.safe_load(yaml.safe_dump(doc, allow_unicode=True))
    for rule in copy.get("red_flags") or []:
        rule["tense_anchor"] = "onset_date"
    return copy


def test_duration_omit_emits_no_duration_slot(stub_anchor_elsewhere: None) -> None:
    options = GEN.extract_pack_options(_pack_line("duration=omit"))
    qs, _ = GEN.extract_questions(_pack_line("duration=omit"))
    pack = GEN.build_pack(DRAFT, "ornek", qs, options=options)
    assert list(pack["sections"]["ziyaret_baglami"]["slots"]) == ["basvuru_nedeni"]
    assert "ops" not in pack
    ProtocolPack.model_validate(pack)


def test_without_duration_omit_the_duration_slot_is_emitted() -> None:
    """Near-miss control: a pack line that sets the ask keeps the slot."""
    text = _pack_line(f"duration_ask={GEN.DURATION_ASK}")
    qs, _ = GEN.extract_questions(text)
    pack = GEN.build_pack(DRAFT, "ornek", qs, options=GEN.extract_pack_options(text))
    ctx = pack["sections"]["ziyaret_baglami"]["slots"]
    assert list(ctx) == ["basvuru_nedeni", "sikayet_suresi"]
    assert ctx["sikayet_suresi"]["type"] == "duration"


@pytest.mark.parametrize(
    "line",
    ["duration=omitted", "duration=Omit", "duration=", "duration=keep", "duration_omit=true"],
)
def test_duration_takes_the_single_value_omit(line: str) -> None:
    with pytest.raises(ValueError, match="duration"):
        GEN.extract_pack_options(_pack_line(line))


@pytest.mark.parametrize("key", ["duration_ask", "duration_follow_up"])
def test_duration_omit_with_a_duration_text_is_refused_as_contradictory(key: str) -> None:
    text = GEN.DURATION_ASK if key == "duration_ask" else GEN.DURATION_FOLLOW_UP
    with pytest.raises(ValueError, match="contradict"):
        GEN.extract_pack_options(_pack_line(f"duration=omit; {key}={text}"))


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (f"duration_ask={GEN.DURATION_ASK}", "duration=omit"),
        ("duration=omit", f"duration_ask={GEN.DURATION_ASK}"),
        (f"duration_ask={GEN.DURATION_ASK}", f"duration_ask={GEN.DURATION_ASK}"),
    ],
    ids=["ask-then-omit", "omit-then-ask", "one-key-on-two-lines"],
)
def test_a_second_pack_line_is_refused(first: str, second: str) -> None:
    """L-4: the omit/text contradiction is caught across lines, not only within one."""
    text = _pack_line(first).replace("## 5. Gaps", f"pack: {second}\n\n## 5. Gaps")
    with pytest.raises(ValueError, match="pack: line"):
        GEN.extract_pack_options(text)


def test_a_pack_key_given_twice_on_one_line_is_refused() -> None:
    line = f"duration_ask={GEN.DURATION_ASK}; duration_ask={GEN.DURATION_ASK}"
    with pytest.raises(ValueError, match="twice"):
        GEN.extract_pack_options(_pack_line(line))


def test_a_gate_on_the_omitted_duration_slot_is_refused(stub_anchor_elsewhere: None) -> None:
    gated = GEN.Question(text=ITEM_TEXTS[0], slot="bayginlik", ask_if="sikayet_suresi != ''")
    other = GEN.Question(text=ITEM_TEXTS[2], slot="sislik")
    with pytest.raises(ValueError, match="undeclared"):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, gated, other], options={"duration": "omit"})
    # Near-miss control: the same gate reads the slot when the pack keeps it.
    kept = GEN.build_pack(DRAFT, "ornek", [REASON_Q, gated, other])
    assert _sorular(kept)["bayginlik"]["ask_if"] == "sikayet_suresi != ''"


def _omit_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extends: str
) -> tuple[str, bool, Path]:
    """Run gen() on a specialty that extends `extends` and asks for `duration=omit`."""
    spec, review, prop = tmp_path / "specialty", tmp_path / "review", tmp_path / "proposals"
    spec.mkdir()
    prop.mkdir()
    (spec / "ornek.yaml").write_text(
        "kind: pack\nid: specialty.ornek\nmaturity: L0\ntitle_tr: Örnek (L0 taslak)\n"
        f"extends: {extends}\n",
        encoding="utf-8",
    )
    (prop / "ornek.md").write_text(_pack_line("duration=omit"), encoding="utf-8")
    monkeypatch.setattr(GEN, "SPEC", spec)
    monkeypatch.setattr(GEN, "REVIEW", review)
    monkeypatch.setattr(GEN, "PROP", prop)
    line, ok = GEN.gen("ornek")
    return line, ok, review / "ornek.yaml"


@pytest.mark.parametrize("cluster", CLUSTERS)
def test_duration_omit_is_refused_under_every_cluster_while_a_rule_reads_the_slot(
    cluster: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H-1, measured under all eight committed clusters: each cluster stub anchors on
    sikayet_suresi, so a suppress_slot of it would serve a rule that never fires."""
    line, ok, out = _omit_branch(tmp_path, monkeypatch, f"cluster.{cluster}")
    assert not ok
    assert DURATION_REFUSAL in line, line
    assert f"rf.cluster_{cluster}_l0_taslak" in line and "rf.ornek_l0_taslak" in line, line
    assert not out.exists()


def test_omit_is_refused_while_the_candidates_own_stub_anchors_on_the_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-4, subsumed by H-1: nothing above a cluster candidate reads sikayet_suresi,
    but its own stub does. A signed stub that kept that anchor would never fire, so
    omit is refused; the anchor itself stays the clinician's to move (INT-383)."""
    assert len(CLUSTERS) == len(GEN.CLUSTER_TITLES)
    review, served, prop = tmp_path / "review", tmp_path / "served", tmp_path / "proposals"
    prop.mkdir()
    (prop / "cluster_medical.md").write_text(_pack_line("duration=omit"), encoding="utf-8")
    monkeypatch.setattr(GEN, "REVIEW_CLUSTER", review)
    monkeypatch.setattr(GEN, "SERVED_CLUSTER", served)
    monkeypatch.setattr(GEN, "PROP", prop)
    line, ok = GEN.gen("cluster_medical")
    assert not ok
    assert DURATION_REFUSAL in line and "rf.cluster_medical_l0_taslak" in line, line
    above = [rule["id"] for rule in GEN.parent_chain_rules("base.intake")]
    assert above and not any(rule_id in line for rule_id in above), line
    assert not (review / "medical.yaml").exists()
    # No stub is re-anchored: every generated stub still anchors on sikayet_suresi.
    qs, _ = GEN.extract_questions(PROPOSAL)
    (stub,) = GEN.build_pack(DRAFT, "ornek", qs)["red_flags"]
    assert stub["tense_anchor"] == GEN.DURATION_SLOT


@pytest.mark.parametrize(
    ("rule", "reads"),
    [
        ({"when": "son_gunlerde_ates == true && sikayet_suresi != ''"}, True),
        ({"when": "ziyaret_baglami.sikayet_suresi != ''"}, True),
        ({"when": "!(sikayet_suresi in {'x'})"}, True),
        ({"when": "son_gunlerde_ates == true", "tense_anchor": "sikayet_suresi"}, True),
        ({"gate": "sikayet_suresi != ''"}, True),  # base.life_threat's spelling (ADR-024)
        ({"when": f"{GEN.PENDING_MARKER} a trigger over sikayet_suresi needs sign-off"}, True),
        ({"when": "son_gunlerde_ates == true"}, False),
        ({"when": "sikayet_suresi_notu != ''"}, False),
        ({"when": f"{GEN.PENDING_MARKER} a trigger requires clinical sign-off"}, False),
    ],
    ids=[
        "when",
        "when-qualified",
        "when-negated-set",
        "tense_anchor",
        "life-threat-gate",
        "draft-text-names-it",
        "near-miss-other-slot",
        "near-miss-prefix",
        "near-miss-draft",
    ],
)
def test_a_rule_reads_the_duration_slot_in_when_or_as_its_anchor(
    rule: dict[str, Any], reads: bool
) -> None:
    rule = {"id": "rf.ornek", "tense_anchor": "onset_date", **rule}
    assert (GEN.DURATION_SLOT in GEN.rule_reads(rule)) is reads


def test_duration_omit_suppresses_a_parent_slot_only_when_no_rule_reads_it(
    stub_anchor_elsewhere: None,
) -> None:
    """A child cannot drop a parent slot by leaving it out (the merge keeps it), and it
    may not suppress one a signed rule reads in `when` (H-1's second measured case)."""
    parent_visit = GEN.parent_section("cluster.medical", "ziyaret_baglami")
    assert "sikayet_suresi" in parent_visit
    signed = {
        "id": "rf.ornek_imzali",
        "status": "active",
        "when": "son_gunlerde_ates == true && sikayet_suresi != ''",
        "tense_anchor": "onset_date",
    }
    qs, _ = GEN.extract_questions(_items("slot=bayginlik; type=boolean", None))
    omit = {"duration": "omit"}
    with pytest.raises(ValueError, match=rf"{DURATION_REFUSAL}.*rf\.ornek_imzali"):
        GEN.build_pack(
            DRAFT, "ornek", qs, options=omit, parent_visit_slots=parent_visit, chain_rules=[signed]
        )
    # Near-miss: a parent rule reading another slot lets omit through, with the op.
    elsewhere = {**signed, "when": "son_gunlerde_ates == true"}
    pack = GEN.build_pack(
        DRAFT, "ornek", qs, options=omit, parent_visit_slots=parent_visit, chain_rules=[elsewhere]
    )
    assert pack["ops"] == [{"op": "suppress_slot", "pointer": GEN.DURATION_POINTER}]
    # Near-miss: without omit, nothing is suppressed and nothing is refused.
    kept = GEN.build_pack(DRAFT, "ornek", qs, parent_visit_slots=parent_visit, chain_rules=[signed])
    assert "ops" not in kept


@pytest.mark.parametrize("omit", [True, False], ids=["omit", "near-miss-kept"])
def test_the_resolved_chain_drops_sikayet_suresi_only_when_omitted(
    omit: bool, stub_anchor_elsewhere: None
) -> None:
    """M-1: omit removes the cluster/specialty `ziyaret_baglami.sikayet_suresi` only.
    base.intake's must_ask `hpi.onset_date` and `hpi.duration` are still asked, and no
    pack can suppress them (SUPPRESS_MUST_ASK). The committed cluster.medical is refused
    (above), so its stub is anchored elsewhere here, as a simulation."""
    cluster = _anchored_elsewhere(_pack(REVIEW_CLUSTER_MEDICAL))
    qs, _ = GEN.extract_questions(_items("slot=bayginlik; type=boolean", None))
    branch = ProtocolPack.model_validate(
        GEN.build_pack(
            DRAFT,
            "ornek",
            qs,
            options={"duration": "omit"} if omit else {},
            parent_visit_slots=cluster["sections"]["ziyaret_baglami"]["slots"],
            chain_rules=[*_pack(BASE_PACK)["red_flags"], *cluster["red_flags"]],
        )
    )
    chain = [load_pack(BASE_PACK), ProtocolPack.model_validate(cluster), branch]
    registry = PackRegistry()
    for pack in chain:
        registry.add(pack)
    assert validate_packs(registry) == ()
    merged = _merge_chain(chain)
    assert _apply_ops(merged, _ordered_ops(chain), "tr") == []
    assert ("sikayet_suresi" in merged["ziyaret_baglami"].slots) is not omit
    hpi = merged["hpi"].slots
    assert hpi["onset_date"].must_ask and hpi["duration"].must_ask


# gen: type=code; options=… ------------------------------------------------------


def test_every_code_option_is_a_label_base_intake_already_carries() -> None:
    assert GEN.CODE_OPTIONS
    for option, (label, ref) in GEN.CODE_OPTIONS.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]*", option), option
        assert label in _base_choices(ref), f"{option}: {label!r} is not in {ref}"
        assert not any(ch.isdigit() for ch in label), label  # invariant 22
    labels = [label for label, _ in GEN.CODE_OPTIONS.values()]
    assert len(labels) == len(set(labels))


def test_a_code_question_offers_base_labels_under_its_own_valueset() -> None:
    qs, warnings = GEN.extract_questions(
        _items(
            "slot=bayginlik; type=boolean",
            None,
            "slot=sislik; type=code; options=evet|hayir|bilmiyorum",
        )
    )
    assert warnings == []
    pack = GEN.build_pack(DRAFT, "ornek", qs)
    slot = _sorular(pack)["sislik"]
    assert slot["type"] == "code"
    assert slot["valueset"] == "vs.sislik"
    assert slot["choices_tr"] == {"tr": _base_choices("meds_allergies.anticoagulant_use")}
    assert slot["ask_tr"] == {"tr": ITEM_TEXTS[2]}
    ProtocolPack.model_validate(pack)


def test_two_options_are_enough() -> None:
    """Near-miss control for the arity refusal below."""
    qs, warnings = GEN.extract_questions(
        _items("slot=bayginlik; type=boolean", None, "slot=sislik; type=code; options=evet|hayir")
    )
    assert warnings == []
    choices = _sorular(GEN.build_pack(DRAFT, "ornek", qs))["sislik"]["choices_tr"]["tr"]
    assert choices == _base_choices("meds_allergies.anticoagulant_use")[:2]


@pytest.mark.parametrize(
    ("gen", "reason"),
    [
        ("slot=sislik; type=code", "options"),
        ("slot=sislik; type=code; options=", "options"),
        ("slot=sislik; type=boolean; options=evet|hayir", "contradict"),
        ("slot=sislik; options=evet|hayir", "contradict"),
        ("slot=sislik; type=code; options=evet|aniden", UNKNOWN_OPTION),
        ("slot=sislik; type=code; options=evet|hayır", UNKNOWN_OPTION),
        ("slot=sislik; type=code; options=Evet|hayir", UNKNOWN_OPTION),
        ("slot=sislik; type=code; options=evet|evet", "twice"),
        ("slot=sislik; type=code; options=evet", "two"),
        ("type=code; options=evet|hayir", "slot="),
        ("slot=sislik; type=code; option=evet|hayir", "unknown gen key"),
    ],
)
def test_a_malformed_code_question_is_refused(gen: str, reason: str) -> None:
    qs, warnings = GEN.extract_questions(_items("slot=bayginlik; type=boolean", None, gen))
    assert ITEM_TEXTS[2] not in [q.text for q in qs]
    assert any(reason in w for w in warnings), warnings


def test_an_option_without_a_base_label_names_the_clinician() -> None:
    _, warnings = GEN.extract_questions(
        _items("slot=bayginlik; type=boolean", None, "slot=sislik; type=code; options=aniden|evet")
    )
    (warning,) = warnings
    assert GEN.CODE_OPTION_UNKNOWN == UNKNOWN_OPTION
    assert UNKNOWN_OPTION in warning and "'aniden'" in warning and "HB-C1" in warning


def test_a_code_question_without_options_is_refused_by_build_pack_too() -> None:
    bare = GEN.Question(text=ITEM_TEXTS[2], slot="sislik", type="code")
    with pytest.raises(ValueError, match="options"):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, bare, bare])


CODE_ITEM = GEN.Question(
    text=ITEM_TEXTS[2], slot="sislik", type="code", options=("evet", "hayir", "bilmiyorum")
)


@pytest.mark.parametrize("field", ["ask_if", "skip_if"])
@pytest.mark.parametrize(
    "gate",
    [
        "sislik == 'hayır'",
        "sislik == 'var'",
        "sislik != 'hayır'",
        "sislik in {'evet', 'hayır'}",
        "sislik == true",
        "sislik",
    ],
    ids=["label-not-id", "unknown-word", "not-equal-label", "set-with-label", "boolean", "bare"],
)
def test_a_gate_on_a_code_slot_reads_only_its_option_ids(field: str, gate: str) -> None:
    """M-2: `'hayır'` is the label, `hayir` the id. A gate comparing a generated code
    slot with anything but its ids would never follow the answer."""
    gated = GEN.Question(text=ITEM_TEXTS[1], slot="efor", type="boolean", **{field: gate})
    with pytest.raises(ValueError, match="option ids"):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, CODE_ITEM, gated])


@pytest.mark.parametrize("field", ["ask_if", "skip_if"])
@pytest.mark.parametrize(
    "gate", ["sislik == 'hayir'", "sislik != 'bilmiyorum'", "sislik in {'evet', 'hayir'}"]
)
def test_a_gate_comparing_a_code_slot_with_its_option_ids_is_emitted(field: str, gate: str) -> None:
    """Near-miss control for the refusal above."""
    gated = GEN.Question(text=ITEM_TEXTS[1], slot="efor", type="boolean", **{field: gate})
    pack = GEN.build_pack(DRAFT, "ornek", [REASON_Q, CODE_ITEM, gated])
    assert _sorular(pack)["efor"][field] == gate
    ProtocolPack.model_validate(pack)


@pytest.mark.parametrize("sid", ["anticoagulant_use", "pregnancy_status", "onset_date"])
def test_a_code_slot_may_not_reuse_a_base_slot_id(sid: str) -> None:
    """M-3: a second slot of a base name makes bare reads ambiguous and rebinds vs.<id>."""
    item = GEN.Question(text=ITEM_TEXTS[2], slot=sid, type="code", options=("evet", "hayir"))
    other = GEN.Question(text=ITEM_TEXTS[0], slot="bayginlik", type="boolean")
    with pytest.raises(ValueError, match="reuse"):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, other, item], base_slots=GEN.base_slot_names())


def test_a_code_slot_may_not_reuse_a_parent_chain_slot_id() -> None:
    parent = {"asi": {"type": "boolean", "ask_tr": {"tr": ITEM_TEXTS[0]}}}
    code = GEN.Question(text=ITEM_TEXTS[2], slot="asi", type="code", options=("evet", "hayir"))
    other = GEN.Question(text=ITEM_TEXTS[0], slot="bayginlik", type="boolean")
    with pytest.raises(ValueError, match="reuse"):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, other, code], parent_slots=parent)
    # Near-miss controls: a boolean re-declaring the parent id is the INT-353 rebind,
    # and a code slot under a fresh id reuses nothing.
    rebind = GEN.Question(text=ITEM_TEXTS[2], slot="asi", type="boolean")
    assert "asi" in _sorular(
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, other, rebind], parent_slots=parent)
    )
    assert "sislik" in _sorular(
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, other, CODE_ITEM], parent_slots=parent)
    )


# gen: skip_if=… -----------------------------------------------------------------


def test_skip_if_is_emitted_and_reads_an_earlier_slot() -> None:
    qs, warnings = GEN.extract_questions(
        _items(
            "slot=bayginlik; type=boolean",
            "slot=efor_bayginlik; type=boolean; skip_if=bayginlik == false",
        )
    )
    assert warnings == []
    slot = _sorular(GEN.build_pack(DRAFT, "ornek", qs))["efor_bayginlik"]
    assert slot["skip_if"] == "bayginlik == false"
    assert "ask_if" not in slot


def test_skip_if_may_read_a_base_slot() -> None:
    """Near-miss control: base.intake slots are readable, as for ask_if."""
    gated = GEN.Question(text=ITEM_TEXTS[0], slot="devam", skip_if="subject_role != 'kendim'")
    other = GEN.Question(text=ITEM_TEXTS[2], slot="sislik")
    pack = GEN.build_pack(
        DRAFT, "ornek", [REASON_Q, gated, other], base_slots=GEN.base_slot_names()
    )
    assert _sorular(pack)["devam"]["skip_if"] == "subject_role != 'kendim'"
    ProtocolPack.model_validate(pack)


@pytest.mark.parametrize("field", ["ask_if", "skip_if"])
@pytest.mark.parametrize(
    ("reads", "reason"),
    [("olmayan_slot", "undeclared"), ("sislik", "later"), ("devam", "itself")],
    ids=["undeclared", "forward", "self"],
)
def test_a_gate_reads_only_slots_declared_before_it(field: str, reads: str, reason: str) -> None:
    """INT-375's order rule inside one pack: a gate reads fixed, base or earlier slots."""
    gated = GEN.Question(text=ITEM_TEXTS[0], slot="devam", **{field: f"{reads} == true"})
    later = GEN.Question(text=ITEM_TEXTS[2], slot="sislik")
    with pytest.raises(ValueError, match=reason):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, gated, later], base_slots=GEN.base_slot_names())


@pytest.mark.parametrize("field", ["ask_if", "skip_if"])
@pytest.mark.parametrize(
    ("gate", "reason"),
    [
        ("sislik", "later"),
        ("!sislik", "later"),
        ("sislik in {'evet'}", "later"),
        ("yok_boyle", "undeclared"),
        ("!devam", "itself"),
    ],
    ids=["bare-forward", "negated-forward", "set-forward", "bare-undeclared", "negated-self"],
)
def test_a_gate_is_read_with_the_dsl_parser_not_only_at_a_comparison(
    field: str, gate: str, reason: str
) -> None:
    """L-1: a bare, negated or `in` read is a read (protocols.triage.expr.parse_when)."""
    gated = GEN.Question(text=ITEM_TEXTS[0], slot="devam", type="boolean", **{field: gate})
    later = GEN.Question(text=ITEM_TEXTS[2], slot="sislik", type="boolean")
    with pytest.raises(ValueError, match=reason):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, gated, later], base_slots=GEN.base_slot_names())


@pytest.mark.parametrize("field", ["ask_if", "skip_if"])
def test_a_gate_outside_the_dsl_grammar_is_refused(field: str) -> None:
    """L-1: the compiler parses gates with the `when` grammar; so does the generator."""
    outside = "bayginlik in ['evet']"
    qs, warnings = GEN.extract_questions(
        _items("slot=bayginlik; type=boolean", f"slot=efor; type=boolean; {field}={outside}")
    )
    assert ITEM_TEXTS[1] not in [q.text for q in qs]
    assert any("gate grammar" in w for w in warnings), warnings
    first = GEN.Question(text=ITEM_TEXTS[0], slot="bayginlik", type="boolean")
    gated = GEN.Question(text=ITEM_TEXTS[1], slot="efor", type="boolean", **{field: outside})
    with pytest.raises(ValueError, match="gate grammar"):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, first, gated])


def test_build_pack_refuses_two_gates_on_one_item_too() -> None:
    """L-2: a caller that skips the parser cannot emit ask_if and skip_if together."""
    first = GEN.Question(text=ITEM_TEXTS[0], slot="bayginlik", type="boolean")
    both = GEN.Question(
        text=ITEM_TEXTS[1],
        slot="efor",
        type="boolean",
        ask_if="bayginlik == true",
        skip_if="bayginlik == false",
    )
    with pytest.raises(ValueError, match="one gate per item"):
        GEN.build_pack(DRAFT, "ornek", [REASON_Q, first, both])


def test_one_question_carries_one_gate() -> None:
    qs, warnings = GEN.extract_questions(
        _items(
            "slot=bayginlik; type=boolean",
            "slot=efor_bayginlik; type=boolean; ask_if=bayginlik == true; "
            "skip_if=bayginlik == false",
        )
    )
    assert ITEM_TEXTS[1] not in [q.text for q in qs]
    assert any("one gate" in w for w in warnings), warnings


@pytest.mark.parametrize(
    "extra",
    [
        {"skip_if": "subject_role != 'kendim'"},
        {"type": "code", "options": ("evet", "hayir")},
        {"ask_if": "subject_role != 'kendim'"},
        {"slot": "neden"},
        {"type": "boolean"},
        {"follow_up": GEN.REASON_FOLLOW_UP_WHEN_NEDIR},
        {"delivery": "text_first"},
    ],
    ids=["skip_if", "code", "ask_if", "slot", "type", "follow_up", "delivery"],
)
def test_the_reason_question_takes_no_gate_and_no_code(extra: dict[str, Any]) -> None:
    """Q1 fills the fixed, required basvuru_nedeni slot: a new key on it would be dropped."""
    reason = GEN.Question(text=REASON_TEXT, number=1, **extra)
    items = [GEN.Question(text=t, slot=f"soru_{i}") for i, t in enumerate(ITEM_TEXTS[:2], 1)]
    with pytest.raises(ValueError, match="Q1"):
        GEN.build_pack(DRAFT, "ornek", [reason, *items], base_slots=GEN.base_slot_names())


@pytest.mark.parametrize(
    "gen",
    [
        "ask_if=subject_role != 'kendim'",
        "skip_if=subject_role != 'kendim'",
        "slot=neden",
        "type=string",
        f"follow_up={GEN.REASON_FOLLOW_UP_WHEN_NEDIR}",
        "delivery=text_first",
    ],
    ids=["ask_if", "skip_if", "slot", "type", "follow_up", "delivery"],
)
def test_a_gen_line_on_the_reason_question_is_refused_not_dropped(
    gen: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L-3: no gen key applies to Q1, so a key there refuses Q1 (and so the pack)."""
    text = _items("slot=bayginlik; type=boolean", None).replace(
        f'> "{REASON_TEXT}"\n', f'> "{REASON_TEXT}"\ngen: {gen}\n'
    )
    qs, warnings = GEN.extract_questions(text)
    assert REASON_TEXT not in [q.text for q in qs]
    assert any("Q1 fills basvuru_nedeni" in w for w in warnings), warnings
    review, served, prop = tmp_path / "review", tmp_path / "served", tmp_path / "proposals"
    prop.mkdir()
    (prop / "cluster_medical.md").write_text(text, encoding="utf-8")
    monkeypatch.setattr(GEN, "REVIEW_CLUSTER", review)
    monkeypatch.setattr(GEN, "SERVED_CLUSTER", served)
    monkeypatch.setattr(GEN, "PROP", prop)
    line, ok = GEN.gen("cluster_medical")
    assert not ok and "Q1" in line, line
    assert not (review / "medical.yaml").exists()


def test_a_skip_if_gate_is_ordered_like_an_ask_if_gate() -> None:
    """The merge keeps a re-declared parent slot in place; a skip_if on a new slot moves it."""
    parent = {
        "a": {"type": "boolean", "ask_tr": {"tr": ITEM_TEXTS[0]}},
        "y": {"type": "boolean", "ask_tr": {"tr": ITEM_TEXTS[1]}},
    }
    z = GEN.Question(text=ITEM_TEXTS[2], slot="z", type="boolean")
    y = GEN.Question(text=ITEM_TEXTS[1], slot="y", type="boolean", skip_if="z == true")
    pack = GEN.build_pack(DRAFT, "ornek", [REASON_Q, z, y], parent_slots=parent)
    assert pack["ops"] == [
        {"op": "reorder", "pointer": GEN.REORDER_POINTER, "order": ["a", "z", "y"]}
    ]
    # Near-miss control: the same skip_if on a new slot, which merges after its gate.
    w = GEN.Question(text=ITEM_TEXTS[1], slot="w", type="boolean", skip_if="z == true")
    assert "ops" not in GEN.build_pack(DRAFT, "ornek", [REASON_Q, z, w], parent_slots=parent)


@pytest.mark.parametrize(
    "gen", ["slot=efor_bayginlik; skipif=bayginlik == false", "slot=efor_bayginlik; omit=1"]
)
def test_near_miss_spellings_of_the_new_keys_stay_refused(gen: str) -> None:
    _, warnings = GEN.extract_questions(_items("slot=bayginlik; type=boolean", gen))
    assert any("unknown gen key" in w for w in warnings), warnings


# All three, end to end ---------------------------------------------------------


def test_a_cluster_candidate_using_all_three_loads_and_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_anchor_elsewhere: None
) -> None:
    """Under the anchor simulation only: with the committed anchor, omit is refused."""
    review, served, prop = tmp_path / "review", tmp_path / "served", tmp_path / "proposals"
    prop.mkdir()
    text = _items(
        "slot=bayginlik; type=boolean",
        "slot=efor_bayginlik; type=boolean; skip_if=bayginlik == false",
        "slot=sislik; type=code; options=evet|hayir|bilmiyorum; delivery=text_first",
    ).replace("## 4. Candidate questions\n", "## 4. Candidate questions\n\npack: duration=omit\n")
    (prop / "cluster_medical.md").write_text(text, encoding="utf-8")
    monkeypatch.setattr(GEN, "REVIEW_CLUSTER", review)
    monkeypatch.setattr(GEN, "SERVED_CLUSTER", served)
    monkeypatch.setattr(GEN, "PROP", prop)
    line, ok = GEN.gen("cluster_medical")
    assert ok, line
    pack = load_pack(review / "medical.yaml")
    assert list(pack.sections["ziyaret_baglami"].slots) == ["basvuru_nedeni"]
    assert pack.sections["sorular"].slots["efor_bayginlik"].skip_if == "bayginlik == false"
    assert pack.sections["sorular"].slots["sislik"].valueset == "vs.sislik"
    assert pack.ops == ()  # base.intake declares no duration slot, so none to suppress
    registry = PackRegistry()
    for member in (load_pack(BASE_PACK), pack):
        registry.add(member)
    assert validate_packs(registry) == ()
