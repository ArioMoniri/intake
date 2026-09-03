"""INT-041 — the five compiler outputs of files/03 §6.

(a) FHIR R4 ``Questionnaire`` (items, ``enableWhen``, ValueSets)
(b) openEHR operational-template bindings (archetype paths per slot)
(c) Pydantic slot schemas for the engine
(d) TypeScript types for the app
(e) clip manifest (``text_hash -> clip_id`` per voice), consumed by the Talker

Plus the CLI that produces them, and the refusals that keep the real pack
tree unservable today.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from clinical_schemas.mappers.codes import EXT_PROTOCOL_HASH, PROTOCOL_CANONICAL_PREFIX
from protocols.bindings import OperationalTemplate
from protocols.cli import main
from protocols.compile import CompiledBundle, LifeThreatSet, compile_bundle
from protocols.dsl import clip_text_hash
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE as TR

PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"


@pytest.fixture
def bundle(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> CompiledBundle:
    return compile_bundle(
        pack_id=PACK_ID,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )


# ------------------------------------------------------------- (a) FHIR


def _questionnaire(bundle: CompiledBundle) -> dict[str, object]:
    payload = json.loads(bundle.artifacts["questionnaire.json"])
    assert isinstance(payload, dict)
    return payload


def test_questionnaire_is_a_fhir_r4_questionnaire(bundle: CompiledBundle) -> None:
    doc = _questionnaire(bundle)
    assert doc["resourceType"] == "Questionnaire"
    assert doc["url"] == f"{PROTOCOL_CANONICAL_PREFIX}{PACK_ID}"
    assert doc["version"] == "1.2.0"
    assert doc["language"] == "tr"
    assert doc["subjectType"] == ["Patient"]


def test_questionnaire_carries_the_resolved_protocol_hash_extension(
    bundle: CompiledBundle,
) -> None:
    doc = _questionnaire(bundle)
    extensions = doc["extension"]
    assert isinstance(extensions, list)
    assert {
        "url": EXT_PROTOCOL_HASH,
        "valueString": bundle.resolved_protocol_hash,
    } in extensions


def test_sections_become_groups_and_slots_become_items(bundle: CompiledBundle) -> None:
    doc = _questionnaire(bundle)
    groups = doc["item"]
    assert isinstance(groups, list)
    ziyaret = next(g for g in groups if g["linkId"] == "ziyaret")
    assert ziyaret["type"] == "group"
    link_ids = [item["linkId"] for item in ziyaret["item"]]
    assert link_ids == ["ziyaret.basvuru_nedeni", "ziyaret.sure_dakika", "ziyaret.renk_secimi"]


def test_slot_types_map_and_a_code_slot_carries_its_valueset(bundle: CompiledBundle) -> None:
    doc = _questionnaire(bundle)
    groups = doc["item"]
    assert isinstance(groups, list)
    items = {item["linkId"]: item for g in groups for item in g["item"]}
    assert items["ziyaret.basvuru_nedeni"]["type"] == "string"
    assert items["ziyaret.basvuru_nedeni"]["required"] is True
    assert items["ziyaret.sure_dakika"]["type"] == "quantity"
    assert items["ziyaret.renk_secimi"]["type"] == "choice"
    assert (
        items["ziyaret.renk_secimi"]["answerValueSet"]
        == "urn:intake:fhir:ValueSet:vs.sentetik_renk"
    )


def test_ask_if_projects_to_enable_when(bundle: CompiledBundle) -> None:
    doc = _questionnaire(bundle)
    groups = doc["item"]
    assert isinstance(groups, list)
    items = {item["linkId"]: item for g in groups for item in g["item"]}
    assert items["ziyaret.renk_secimi"]["enableWhen"] == [
        {"question": "ziyaret.basvuru_nedeni", "operator": "=", "answerString": "sentetik"}
    ]
    assert items["ziyaret.renk_secimi"]["enableBehavior"] == "all"


def test_the_item_text_is_the_tr_expanded_script(bundle: CompiledBundle) -> None:
    """Invariant 5: the tr resource is the source of truth. Invariant 22:
    what the item carries is the expanded orthography, so nothing downstream
    re-derives it."""
    doc = _questionnaire(bundle)
    groups = doc["item"]
    assert isinstance(groups, list)
    items = {item["linkId"]: item for g in groups for item in g["item"]}
    assert items["ziyaret.basvuru_nedeni"]["text"] == "Bugün sizi buraya getiren nedir?"


# ------------------------------------------------------------- (b) openEHR


def test_binding_table_declares_a_path_or_a_reason_for_every_slot(
    bundle: CompiledBundle,
) -> None:
    """files/12 §8: ``aql_path`` **or** an explicit ``openehr_deferred_reason``
    — a CHECK constraint forbids both being null, so absence is a decision."""
    rows = json.loads(bundle.artifacts["openehr_bindings.json"])
    assert [row["fhir_link_id"] for row in rows] == [
        "ziyaret.basvuru_nedeni",
        "ziyaret.sure_dakika",
        "ziyaret.renk_secimi",
        "tarama.sessiz_soru",
    ]
    for row in rows:
        assert (row["aql_path"] is None) != (row["openehr_deferred_reason"] is None)
    bound = next(row for row in rows if row["fhir_link_id"] == "ziyaret.basvuru_nedeni")
    assert bound["rm_type"] == "EVALUATION"
    deferred = next(row for row in rows if row["fhir_link_id"] == "ziyaret.renk_secimi")
    assert deferred["rm_type"] is None
    assert deferred["openehr_deferred_reason"]


def test_binding_table_names_the_pinned_template(bundle: CompiledBundle) -> None:
    assert bundle.opt_template_id == "previsit_intake.v1"
    assert len(bundle.opt_sha256) == 64


# --------------------------------------------------- (c) Pydantic / (d) TS


def test_pydantic_module_is_importable_typed_source(bundle: CompiledBundle) -> None:
    source = bundle.artifacts["slots.py"]
    assert "class BaseDerlenebilirSlots(BaseModel):" in source
    assert "ziyaret_basvuru_nedeni: str | None" in source
    assert "ziyaret_sure_dakika: Decimal | None" in source
    assert "tarama_sessiz_soru: bool | None" in source
    # It must actually compile — a generated module that does not parse is a
    # generated module nobody notices is broken.
    compile(source, "slots.py", "exec")


def test_typescript_module_mirrors_the_pydantic_one(bundle: CompiledBundle) -> None:
    source = bundle.artifacts["slots.ts"]
    assert "export interface BaseDerlenebilirSlots {" in source
    assert '"ziyaret.basvuru_nedeni"?: string;' in source
    assert '"ziyaret.sure_dakika"?: number;' in source
    assert '"tarama.sessiz_soru"?: boolean;' in source


# ------------------------------------------------------------- (e) clips


def test_clip_manifest_is_keyed_by_text_hash_per_locale_and_voice(
    bundle: CompiledBundle,
) -> None:
    """INT-297: the key is (locale, voice), not voice alone.

    Two locales may be pinned to one voice, and after per-locale expansion two
    languages can produce the same bytes for a short string. A cache found by
    text hash and voice alone would then serve one language's clip into the
    other language's turn, so the locale is in the id as well as in the row.
    """
    rows = bundle.clip_manifest
    by_text = {row.text_tr: row for row in rows}
    ask = by_text["Bugün sizi buraya getiren nedir?"]
    assert ask.entry.voice == VOICE
    assert ask.entry.locale == TR
    assert ask.entry.text_hash == clip_text_hash(ask.text_tr)
    assert ask.entry.clip_id.startswith(f"clip.{TR}.{VOICE}.")


def test_clip_manifest_carries_the_expanded_text_not_the_authored_one(
    bundle: CompiledBundle,
) -> None:
    """Invariant 22: expansion happens BEFORE the entry is keyed, so the clip
    cache and the TTS request agree and no numeral or unit symbol survives."""
    texts = {row.text_tr for row in bundle.clip_manifest}
    assert "Sentetik doz alanı: miligram cinsinden mi?" in texts
    assert "Sentetik doz alanı: mg cinsinden mi?" not in texts


def test_no_emitted_patient_text_contains_a_digit(bundle: CompiledBundle) -> None:
    for row in bundle.clip_manifest:
        assert not any(ch.isdigit() for ch in row.text_tr)


def test_clip_rows_are_deduplicated_and_ordered(bundle: CompiledBundle) -> None:
    hashes = [row.entry.text_hash for row in bundle.clip_manifest]
    assert hashes == sorted(hashes)
    assert len(hashes) == len(set(hashes))


def test_red_action_scripts_are_in_the_clip_manifest(bundle: CompiledBundle) -> None:
    """Invariant 10: red-flag action scripts are spoken verbatim from
    text_tr, from the clip cache or TTS."""
    texts = {row.text_tr for row in bundle.clip_manifest}
    assert "Hemen yardım isteyin." in texts
    assert "Şu anda hastanede misiniz?" in texts


# ---------------------------------------------------------------- the CLI


def test_cli_compile_writes_the_bundle(tmp_path: Path, pack_tree: Path) -> None:
    fixtures = pack_tree.parent
    exit_code = main(
        [
            "compile",
            "--pack",
            PACK_ID,
            "--packs",
            str(pack_tree),
            "--life-threat",
            str(fixtures / "life_threat_signed.yaml"),
            "--voice",
            VOICE,
            "--out",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    written = sorted(p.name for p in (tmp_path / PACK_ID).iterdir())
    assert written == [
        f"clips.{TR}.{VOICE}.json",
        "manifest.json",
        "openehr_bindings.json",
        "questionnaire.json",
        "slots.py",
        "slots.ts",
    ]


def test_cli_compile_reports_every_refusal_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real pack tree is all L0 today, so `protocols compile` on it must
    refuse — loudly, and without writing anything (files/09 §2; invariant 13)."""
    repo_root = Path(__file__).resolve().parents[2]
    exit_code = main(
        [
            "compile",
            "--pack",
            "specialty.kardiyoloji",
            "--packs",
            str(repo_root / "packages" / "protocols"),
            "--life-threat",
            str(repo_root / "packages" / "protocols" / "base" / "life_threat.yaml"),
            "--voice",
            VOICE,
            "--out",
            str(tmp_path),
        ]
    )
    assert exit_code == 1
    assert not list(tmp_path.iterdir())
    assert "compile:" in capsys.readouterr().out


def test_cli_compile_refuses_an_unknown_pack(tmp_path: Path, pack_tree: Path) -> None:
    fixtures = pack_tree.parent
    exit_code = main(
        [
            "compile",
            "--pack",
            "base.yok",
            "--packs",
            str(pack_tree),
            "--life-threat",
            str(fixtures / "life_threat_signed.yaml"),
            "--voice",
            VOICE,
            "--out",
            str(tmp_path),
        ]
    )
    assert exit_code == 1
