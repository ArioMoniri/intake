"""INT-040 — unit tests for the DSL schema, loader and helper surfaces.

Fixture-file coverage lives in test_validator.py; this module exercises the
schema and loader branches that need no golden library: type/enum helpers,
registry behaviour, pointer/op edge cases, and the disjunction splitter that
backs the files/12 §4 layer-2 monotonicity check.
"""

from __future__ import annotations

import textwrap
from datetime import timedelta
from pathlib import Path

import pytest
from protocols import (
    EK4Level,
    FindingCode,
    InstrumentLicence,
    PackRegistry,
    PackSchemaError,
    clip_text_hash,
    load_pack,
    pack_compilable,
    validate_packs,
)
from protocols.dsl import ClipManifestEntry
from protocols.validator import split_top_level_disjuncts

MINIMAL = """\
kind: pack
id: {pack_id}
layer: {layer}
version: 1.0.0
schema_version: 2
maturity: L0
status: awaiting-clinical-review
language: tr
title_tr: "Sentetik birim testi paketi"
"""


def write_pack(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def minimal(pack_id: str, layer: str, extra: str = "") -> str:
    return MINIMAL.format(pack_id=pack_id, layer=layer) + textwrap.dedent(extra)


# ---------------------------------------------------------------------------
# Loader and registry
# ---------------------------------------------------------------------------


def test_loader_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    path = write_pack(tmp_path, "liste.yaml", "- bir\n- iki\n")
    with pytest.raises(PackSchemaError, match="mapping"):
        load_pack(path)


def test_loader_rejects_unknown_kind(tmp_path: Path) -> None:
    body = minimal("base.synthetic_tur", "base").replace("kind: pack", "kind: bilinmeyen")
    path = write_pack(tmp_path, "tur.yaml", body)
    with pytest.raises(PackSchemaError, match="kind"):
        load_pack(path)


def test_loader_rejects_invalid_yaml_syntax(tmp_path: Path) -> None:
    path = write_pack(tmp_path, "bozuk.yaml", "kind: [pack\n")
    with pytest.raises(PackSchemaError, match="YAML"):
        load_pack(path)


def test_registry_rejects_duplicate_pack_ids(tmp_path: Path) -> None:
    path = write_pack(tmp_path, "bir.yaml", minimal("base.synthetic_tek", "base"))
    registry = PackRegistry()
    registry.add(load_pack(path))
    with pytest.raises(PackSchemaError, match="duplicate"):
        registry.add(load_pack(path))


def test_registry_get_unknown_pack_raises() -> None:
    with pytest.raises(KeyError):
        PackRegistry().get("base.synthetic_yok")


def test_extends_cycle_is_a_finding(tmp_path: Path) -> None:
    a = write_pack(
        tmp_path,
        "a.yaml",
        minimal("specialty.synthetic_a", "specialty", "extends: specialty.synthetic_b\n"),
    )
    b = write_pack(
        tmp_path,
        "b.yaml",
        minimal("specialty.synthetic_b", "specialty", "extends: specialty.synthetic_a\n"),
    )
    registry = PackRegistry()
    registry.add(load_pack(a))
    registry.add(load_pack(b))
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.EXTENDS_CYCLE in codes


# ---------------------------------------------------------------------------
# Schema edges with no fixture file
# ---------------------------------------------------------------------------


def test_layer_must_match_id_prefix(tmp_path: Path) -> None:
    path = write_pack(tmp_path, "katman.yaml", minimal("cluster.synthetic_uyumsuz", "base"))
    with pytest.raises(PackSchemaError, match="layer"):
        load_pack(path)


def test_pack_kind_may_not_claim_the_life_threat_id(tmp_path: Path) -> None:
    path = write_pack(tmp_path, "sahte.yaml", minimal("base.life_threat", "base"))
    with pytest.raises(PackSchemaError, match="life_threat"):
        load_pack(path)


def test_quantity_slot_requires_unit(tmp_path: Path) -> None:
    extra = """\
    sections:
      ornek_bolum:
        slots:
          sure:
            type: quantity
            ask_tr: "Örnek soru: ne kadar sürdü?"
    """
    path = write_pack(tmp_path, "birimsiz.yaml", minimal("base.synthetic_birimsiz", "base", extra))
    with pytest.raises(PackSchemaError, match="unit"):
        load_pack(path)


def test_code_slot_requires_valueset(tmp_path: Path) -> None:
    extra = """\
    sections:
      ornek_bolum:
        slots:
          secim:
            type: code
            ask_tr: "Örnek soru: hangisini seçersiniz?"
    """
    path = write_pack(tmp_path, "kumesiz.yaml", minimal("base.synthetic_kumesiz", "base", extra))
    with pytest.raises(PackSchemaError, match="valueset"):
        load_pack(path)


def test_extends_self_is_rejected(tmp_path: Path) -> None:
    path = write_pack(
        tmp_path,
        "kendi.yaml",
        minimal("specialty.synthetic_kendi", "specialty", "extends: specialty.synthetic_kendi\n"),
    )
    with pytest.raises(PackSchemaError, match="extends"):
        load_pack(path)


# ---------------------------------------------------------------------------
# Op semantics without dedicated fixture files
# ---------------------------------------------------------------------------


def test_add_rule_refuses_an_existing_key(tmp_path: Path) -> None:
    valid_dir = Path(__file__).resolve().parent / "goldens" / "valid"
    extra = """\
    ops:
      - op: add_rule
        pointer: /red_flags
        rule:
          id: rf.synthetic_sari
          label_tr: "Sentetik kural — çakışan ekleme"
          when: "baska_bulgu == true"
          tense: today
          tense_anchor: olay_zamani
          level: SARI_K2
          route: EXPEDITE
          notify_clinic: never
          status: active
          source:
            guideline_id: SYN-GUIDE-D
            guideline_title: "Sentetik kılavuz D"
            version_or_date: "sürüm dört"
            url: "https://example.invalid/syn-guide-d"
            retrieved_on: 2026-08-28
            quote: "çakışma sentetik alıntısı"
    """
    path = write_pack(
        tmp_path,
        "cakisan.yaml",
        minimal(
            "specialty.synthetic_cakisan",
            "specialty",
            "extends: base.synthetic\n" + textwrap.dedent(extra),
        ),
    )
    registry = PackRegistry()
    registry.add(load_pack(valid_dir / "base.yaml"))
    registry.add(load_pack(path))
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.RULE_REDECLARED in codes


def test_tighten_unknown_parent_is_a_finding(tmp_path: Path) -> None:
    valid_dir = Path(__file__).resolve().parent / "goldens" / "valid"
    extra = """\
    ops:
      - op: tighten_rule
        parent_rule_id: rf.synthetic_yok
        rule:
          id: rf.synthetic_yok.genis
          label_tr: "Sentetik kural — ebeveyni yok"
          when: "bulgu_a == true || bulgu_b == true"
          tense: today
          tense_anchor: olay_zamani
          level: SARI_K2
          route: EXPEDITE
          notify_clinic: never
          status: active
          source:
            guideline_id: SYN-GUIDE-D
            guideline_title: "Sentetik kılavuz D"
            version_or_date: "sürüm dört"
            url: "https://example.invalid/syn-guide-d"
            retrieved_on: 2026-08-28
            quote: "ebeveynsiz sentetik alıntı"
    """
    path = write_pack(
        tmp_path,
        "ebeveynsiz.yaml",
        minimal(
            "specialty.synthetic_ebeveynsiz",
            "specialty",
            "extends: base.synthetic\n" + textwrap.dedent(extra),
        ),
    )
    registry = PackRegistry()
    registry.add(load_pack(valid_dir / "base.yaml"))
    registry.add(load_pack(path))
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.TIGHTEN_UNKNOWN_PARENT in codes


def test_set_attr_min_confidence_decrease_is_loosening(tmp_path: Path) -> None:
    valid_dir = Path(__file__).resolve().parent / "goldens" / "valid"
    base_extra = """\
    sections:
      ornek_bolum:
        slots:
          guvenli_soru:
            type: boolean
            required: true
            min_confidence: "0.9"
            ask_tr: "Örnek soru: emin misiniz?"
            follow_up_tr: "Evet ya da hayır diyebilir misiniz?"
    """
    overlay_extra = """\
    ops:
      - op: set_attr
        pointer: /sections/ornek_bolum/slots/guvenli_soru
        attr: min_confidence
        value: "0.5"
    """
    base = write_pack(
        tmp_path, "guvenli.yaml", minimal("base.synthetic_guvenli", "base", base_extra)
    )
    overlay = write_pack(
        tmp_path, "gevseten.yaml", minimal("overlay.synthetic_gevseten", "overlay", overlay_extra)
    )
    registry = PackRegistry()
    registry.add(load_pack(valid_dir / "base.yaml"))
    registry.add(load_pack(base))
    registry.add(load_pack(overlay))
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.ATTR_LOOSENED in codes


def test_set_attr_on_unknown_slot_fails_closed(tmp_path: Path) -> None:
    extra = """\
    ops:
      - op: set_attr
        pointer: /sections/ornek_bolum/slots/yok_boyle_soru
        attr: must_ask
        value: true
    """
    path = write_pack(
        tmp_path, "hedefsiz.yaml", minimal("overlay.synthetic_hedefsiz", "overlay", extra)
    )
    registry = PackRegistry()
    registry.add(load_pack(path))
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.UNKNOWN_TARGET in codes


def test_reorder_and_set_voice_ops_are_representable(tmp_path: Path) -> None:
    valid_dir = Path(__file__).resolve().parent / "goldens" / "valid"
    extra = """\
    ops:
      - op: reorder
        pointer: /sections/ornek_bolum/slots
        order: [bekleme_suresi, renk_tercihi, olay_zamani]
      - op: set_voice
        pointer: /sections/ornek_bolum
        voice:
          allow_paraphrase: false
          pace: slow
    """
    path = write_pack(tmp_path, "duzen.yaml", minimal("overlay.synthetic_duzen", "overlay", extra))
    registry = PackRegistry()
    registry.add(load_pack(valid_dir / "base.yaml"))
    registry.add(load_pack(path))
    assert validate_packs(registry) == ()


# ---------------------------------------------------------------------------
# The disjunction splitter behind files/12 §4 layer 2
# ---------------------------------------------------------------------------


def test_split_handles_nesting_and_quotes() -> None:
    parts = split_top_level_disjuncts("(a || b) || c == 'x || y'")
    assert parts == ["(a || b)", "c == 'x || y'"]


def test_split_returns_none_for_conjunction_root() -> None:
    assert split_top_level_disjuncts("(a || b) && c") is None


def test_split_returns_none_for_single_term() -> None:
    assert split_top_level_disjuncts("a == b") is None


# ---------------------------------------------------------------------------
# Clip refs (files/03 §6 compiler output (e): text_hash → clip_id per voice)
# ---------------------------------------------------------------------------


def test_clip_text_hash_is_deterministic() -> None:
    a = clip_text_hash("Örnek soru: hangi rengi seçersiniz?")
    b = clip_text_hash("Örnek soru: hangi rengi seçersiniz?")
    assert a == b
    assert len(a) == 64
    assert a != clip_text_hash("Örnek soru: hangi sayıyı seçersiniz?")


def test_clip_manifest_entry_shape() -> None:
    text = "Örnek soru: hangi rengi seçersiniz?"
    entry = ClipManifestEntry(
        text_hash=clip_text_hash(text), clip_id="clip.synthetic.bir", voice="ses_bir"
    )
    assert entry.text_hash == clip_text_hash(text)


# ---------------------------------------------------------------------------
# EK-4 helpers (files/12 §2.1)
# ---------------------------------------------------------------------------


def test_only_kirmizi_k2_has_a_time_target() -> None:
    assert EK4Level.KIRMIZI_K2.time_target == timedelta(minutes=10)
    for level in EK4Level:
        if level is not EK4Level.KIRMIZI_K2:
            assert level.time_target is None


def test_compilable_report_of_clean_pack(tmp_path: Path) -> None:
    path = write_pack(tmp_path, "temiz.yaml", minimal("base.synthetic_temiz", "base"))
    report = pack_compilable(load_pack(path), licences={"SYN-SCALE": InstrumentLicence.GO})
    assert report.fully_compilable
    assert report.excluded_rules == ()
    assert report.blocked_instruments == ()


# ---------------------------------------------------------------------------
# Model-level raise branches (constructed directly — no fixture needed)
# ---------------------------------------------------------------------------


def _location(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "primary": "GO_TO_IN_HOUSE_ACIL",
        "show_112": False,
        "action_tr": "Görevlilere haber verin ve bekleyin.",
        "notify_staff_immediate": True,
    }
    base.update(overrides)
    return base


def _rule_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "rf.synthetic_birim",
        "label_tr": "Sentetik birim kuralı",
        "when": "ornek_bulgu == true",
        "tense": "now",
        "tense_anchor": "olay_zamani",
        "level": "KIRMIZI_K2",
        "route": "EMERGENCY_NOW",
        "register": "ALERT",
        "notify_clinic": "always",
        "status": "active",
        "source": {
            "guideline_id": "SYN-GUIDE-E",
            "version_or_date": "sürüm beş",
            "url": "https://example.invalid/syn-guide-e",
            "retrieved_on": "2026-08-28",
            "quote": "birim testi sentetik alıntısı",
        },
        "action": {
            "REMOTE": _location(primary="CALL_112", show_112=True, notify_staff_immediate=False),
            "ON_SITE": _location(),
            "UNKNOWN": {
                "ask_one_tr": "Şu anda hastanede misiniz?",
                "on_yes": "ON_SITE",
                "on_no": "REMOTE",
                "on_no_answer": "REMOTE",
            },
        },
    }
    payload.update(overrides)
    return payload


def _expect_rule_rejected(match: str, **overrides: object) -> None:
    from protocols import RedFlagRule
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=match):
        RedFlagRule.model_validate(_rule_payload(**overrides))


def test_location_action_needs_exactly_one_text_carrier() -> None:
    payload = _rule_payload()
    action = payload["action"]
    assert isinstance(action, dict)
    action["ON_SITE"] = _location(action_tr_ref="strings.synthetic.onsite_tr")
    _expect_rule_rejected("exactly one", action=action)


def test_draft_rule_may_not_carry_a_source_block() -> None:
    _expect_rule_rejected("never a source", status="draft_needs_source")


def test_red_rule_requires_an_action_block() -> None:
    _expect_rule_rejected("location-resolved", action=None)


def test_red_rule_requires_on_site_staff_notification() -> None:
    payload = _rule_payload()
    action = payload["action"]
    assert isinstance(action, dict)
    action["ON_SITE"] = _location(notify_staff_immediate=False)
    _expect_rule_rejected("notify_staff_immediate", action=action)


def test_red_rule_notify_clinic_is_always() -> None:
    _expect_rule_rejected("notify_clinic is always", notify_clinic="never")


def test_set_attr_min_confidence_must_be_decimal_in_range(tmp_path: Path) -> None:
    for value, match in (("bozuk", "decimal"), ("1.5", "0, 1")):
        extra = f"""\
        ops:
          - op: set_attr
            pointer: /sections/ornek_bolum/slots/renk_tercihi
            attr: min_confidence
            value: "{value}"
        """
        path = write_pack(
            tmp_path, f"sinir_{value}.yaml", minimal("overlay.synthetic_sinir", "overlay", extra)
        )
        with pytest.raises(PackSchemaError, match=match):
            load_pack(path)


def test_base_layer_pack_is_the_chain_root(tmp_path: Path) -> None:
    path = write_pack(
        tmp_path,
        "kok.yaml",
        minimal("base.synthetic_kok", "base", "extends: base.synthetic\n"),
    )
    with pytest.raises(PackSchemaError, match="chain root"):
        load_pack(path)


def test_duplicate_rule_ids_within_a_pack_are_rejected(tmp_path: Path) -> None:
    rule = """\
      - id: rf.synthetic_cift
        label_tr: "Sentetik çift kural"
        when: "ornek_bulgu == true"
        tense: ever
        tense_anchor: olay_zamani
        level: YESIL
        route: EXPEDITE
        notify_clinic: never
        status: active
    """
    extra = "red_flags:\n" + textwrap.dedent(rule) + textwrap.dedent(rule)
    path = write_pack(tmp_path, "cift.yaml", minimal("base.synthetic_cift", "base", extra))
    with pytest.raises(PackSchemaError, match="duplicate rule id"):
        load_pack(path)


def test_strip_outer_parens_only_unwraps_true_wrappers() -> None:
    from protocols.validator import _strip_outer_parens

    assert _strip_outer_parens("((ornek_bulgu == true))") == "ornek_bulgu == true"
    assert _strip_outer_parens("(a) && (b)") == "(a) && (b)"


def test_signoff_token_outside_any_rule_is_flagged(tmp_path: Path) -> None:
    token = "TO" + "DO"
    extra = f"""\
    sections:
      ornek_bolum:
        slots:
          bekleyen_soru:
            type: boolean
            ask_tr: "Örnek {token} bekleyen metin"
    """
    path = write_pack(tmp_path, "bekleyen.yaml", minimal("base.synthetic_bekleyen", "base", extra))
    registry = PackRegistry()
    registry.add(load_pack(path))
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.PLACEHOLDER_OUTSIDE_DRAFT in codes


def test_instrument_voice_hint_may_not_permit_paraphrase(tmp_path: Path) -> None:
    extra = """\
    instruments:
      - id: SYN-SCALE
        voice:
          allow_paraphrase: true
        items:
          - id: syn_madde_bir
            text_tr: "Örnek ölçek maddesi bir."
            allow_paraphrase: false
    """
    path = write_pack(
        tmp_path, "serbest_ses.yaml", minimal("base.synthetic_serbest_ses", "base", extra)
    )
    registry = PackRegistry()
    registry.add(load_pack(path))
    findings = validate_packs(registry, licences={"SYN-SCALE": InstrumentLicence.GO})
    assert {f.code for f in findings} == {FindingCode.INSTRUMENT_PARAPHRASE}


def test_suppress_slot_with_malformed_pointer_fails_closed(tmp_path: Path) -> None:
    extra = """\
    ops:
      - op: suppress_slot
        pointer: /bolumler/yanlis_yol
    """
    path = write_pack(
        tmp_path, "yanlis_yol.yaml", minimal("overlay.synthetic_yanlis", "overlay", extra)
    )
    registry = PackRegistry()
    registry.add(load_pack(path))
    codes = {f.code for f in validate_packs(registry)}
    assert FindingCode.UNKNOWN_TARGET in codes


def test_registry_len_counts_packs(tmp_path: Path) -> None:
    path = write_pack(tmp_path, "sayim.yaml", minimal("base.synthetic_sayim", "base"))
    registry = PackRegistry()
    assert len(registry) == 0
    registry.add(load_pack(path))
    assert len(registry) == 1


# ---------------------------------------------------------------------------
# INT-254 — the four schema gaps between RedFlagRule and the life-threat
# exemplars in files/protocols/base.life_threat.yaml.
# ---------------------------------------------------------------------------

# Anchors the `when` tokenizer accepts as ONE ident, so the DSL must accept
# them as a tense_anchor: files/12 §2.4 unions the anchor into the predicate's
# reference set (protocols/triage/engine.py) and TriageContext.answers is
# keyed "by the dotted slot reference exactly as the when predicate spells it".
REFERENCE_ANCHORS = (
    "olay_zamani",
    "sikayet_suresi",
    "chest_pain.onset_at",
    "airway.onset_at",
    "transcript.utterance_at",
    "a.b.c",
)

# Spellings that are NOT a single reference. Widening tense_anchor must not
# widen it past the grammar: each of these is either a different token
# sequence or no token at all.
NON_REFERENCE_ANCHORS = (
    "Chest_pain.onset_at",
    "chest_pain.Onset_at",
    "chest_pain.",
    ".onset_at",
    "chest_pain..onset_at",
    "_onset_at",
    "9onset",
    "chest pain.onset_at",
    "chest_pain.onset_at ",
    "",
)


@pytest.mark.parametrize("anchor", REFERENCE_ANCHORS)
def test_tense_anchor_accepts_a_section_qualified_reference(anchor: str) -> None:
    """Gap 1: every exemplar in files/protocols/base.life_threat.yaml writes a
    dotted `<section>.<slot>` anchor. A bare-key constraint makes them
    unrepresentable, and the only ways out are dropping the section (two
    sections may both carry `onset_at`) or a `__` rewrite — both of which
    put the anchor in a different namespace from the predicate it is unioned
    with."""
    from protocols import RedFlagRule

    rule = RedFlagRule.model_validate(_rule_payload(tense_anchor=anchor))
    assert rule.tense_anchor == anchor


@pytest.mark.parametrize("anchor", NON_REFERENCE_ANCHORS)
def test_tense_anchor_rejects_a_non_reference(anchor: str) -> None:
    from protocols import RedFlagRule
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RedFlagRule.model_validate(_rule_payload(tense_anchor=anchor))


def test_tense_anchor_and_the_when_grammar_share_one_reference_pattern() -> None:
    """The anchor and the predicate's references are the same namespace by
    construction — engine.py unions them. Two patterns would let them drift,
    so there is one, and this asserts the tokenizer really uses it."""
    import re

    from protocols.triage.expr import _TOKEN_RE
    from protocols.types import SLOT_REF_PATTERN

    assert f"(?P<ident>{SLOT_REF_PATTERN})" in _TOKEN_RE.pattern
    anchored = re.compile(f"^{SLOT_REF_PATTERN}$")
    for anchor in REFERENCE_ANCHORS:
        assert anchored.match(anchor), anchor
    for anchor in NON_REFERENCE_ANCHORS:
        assert anchored.match(anchor) is None, anchor


def test_rule_status_stays_required_with_no_default() -> None:
    """Gap 2: the two sourced exemplars omit `status`, and the tempting fix is
    a default of `active`. That makes a FORGOTTEN status read active — the
    unsafe direction, and exactly the "chosen once, by an engineer, for every
    future rule" failure CLAUDE.md invariant 17 and files/02 §5.3 name. The
    exemplars carry the value instead."""
    from protocols import RedFlagRule
    from pydantic import ValidationError

    assert RedFlagRule.model_fields["status"].is_required()
    payload = _rule_payload()
    del payload["status"]
    with pytest.raises(ValidationError, match="status"):
        RedFlagRule.model_validate(payload)


def test_source_block_carries_an_optional_note() -> None:
    """Gap 3: exemplar 1's evidence block carries a `note:` recording why the
    EK-4 chest-pain split is three sibling rules and naming the CI gate that
    asserts the third arm. It is provenance commentary, absent by default."""
    from protocols import RedFlagRule

    assert RedFlagRule.model_validate(_rule_payload()).source is not None
    assert RedFlagRule.model_validate(_rule_payload()).source.note is None
    payload = _rule_payload()
    source = payload["source"]
    assert isinstance(source, dict)
    source["note"] = "EK-4 bu tabloyu üç kola ayırır; bu kural o kollardan biridir."
    rule = RedFlagRule.model_validate(payload)
    assert rule.source is not None
    assert rule.source.note is not None


def test_location_action_carries_an_optional_secondary() -> None:
    """Gap 4: exemplar 1's REMOTE action is `primary: CALL_112` with
    `secondary: NEAREST_ACIL_ADDRESS_AS_TEXT`. Folding it into `primary`
    would make one field mean two actions."""
    from protocols import RedFlagRule

    payload = _rule_payload()
    action = payload["action"]
    assert isinstance(action, dict)
    assert RedFlagRule.model_validate(payload).action.remote.secondary is None
    action["REMOTE"] = _location(
        primary="CALL_112",
        secondary="NEAREST_ACIL_ADDRESS_AS_TEXT",
        show_112=True,
        notify_staff_immediate=False,
    )
    rule = RedFlagRule.model_validate(payload)
    assert rule.action is not None
    assert rule.action.remote.secondary == "NEAREST_ACIL_ADDRESS_AS_TEXT"


def test_secondary_action_carries_the_same_code_shape_as_primary() -> None:
    payload = _rule_payload()
    action = payload["action"]
    assert isinstance(action, dict)
    action["REMOTE"] = _location(
        primary="CALL_112", secondary="en yakın acil", show_112=True, notify_staff_immediate=False
    )
    _expect_rule_rejected("secondary", action=action)


def test_on_site_still_never_offers_112_when_a_secondary_action_is_set() -> None:
    """Adding a second action code must not open a second carrier for the
    ON_SITE 112 affordance (CLAUDE.md invariant 21; files/04 §8.2
    on_site_action_never_offers_112)."""
    payload = _rule_payload()
    action = payload["action"]
    assert isinstance(action, dict)
    action["ON_SITE"] = _location(secondary="NEAREST_ACIL_ADDRESS_AS_TEXT", show_112=True)
    _expect_rule_rejected("ON_SITE action never offers 112", action=action)
