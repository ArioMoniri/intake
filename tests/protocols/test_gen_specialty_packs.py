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
        assert old not in GEN.GATE_NAME.findall(slot.get("ask_if", "")), f"{slug}.{sid}"


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
