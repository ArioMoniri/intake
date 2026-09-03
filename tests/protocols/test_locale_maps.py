"""INT-297 — the DSL's ``*_tr`` fields are locale-keyed maps, and ``tr`` is required.

Five fields — ``text_tr``, ``ask_tr``, ``follow_up_tr``, ``choices_tr`` and
``why_tr`` — carry a map keyed by locale rather than one string. The point is
*not* that a second language becomes possible: none is registered, and INT-296
ships the registry holding exactly ``tr``. The point is that the shape which
would let a pack lose its Turkish is unrepresentable, and that the shape which
would let a Turkish clip be served for another locale's string is too.

So every assertion below is about refusal:

* ``tr`` is required by the schema, exactly as a missing scalar field is today;
* a key the registry does not know is refused even when it is a real, well-
  formed language code — the near-miss that a shape-only check would pass;
* a locale whose entry is absent from any speakable field cannot be selected
  for that pack (invariant 10, restated per locale rather than weakened);
* the clip manifest keys on ``(locale, voice)`` and *fails* on a collision
  instead of preferring the first row it saw.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.bindings import OperationalTemplate
from protocols.compile import CompileError, LifeThreatSet, RefusalCode, resolve_protocol
from protocols.compile.emit_clips import clip_manifest
from protocols.dsl import (
    ClipManifestEntry,
    InstrumentItem,
    LocationAction,
    Slot,
    UnknownAction,
    clip_text_hash,
)
from protocols.loader import PackRegistry, PackSchemaError, load_pack
from protocols.locale_text import (
    DEFAULT_LOCALE,
    LOCALE_CODE_PATTERN,
    LocaleEntryAbsent,
    entry_for,
    known_locales,
    locales_of,
)
from protocols.pack_locale import selectable_locales
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKS_ROOT = REPO_ROOT / "packages" / "protocols"

MINIMAL_PACK: dict[str, Any] = {
    "kind": "pack",
    "id": "base.yerel",
    "layer": "base",
    "version": "1.0.0",
    "schema_version": 2,
    "maturity": "L0",
    "status": "sentetik",
    "language": "tr",
    "sections": {
        "oyku": {
            "slots": {
                "belirti": {
                    "type": "string",
                    "required": True,
                    "ask_tr": {"tr": "Şikâyetiniz nedir?"},
                    "follow_up_tr": {"tr": "Biraz daha anlatır mısınız?"},
                }
            }
        }
    },
}


def _write(tmp_path: Path, raw: dict[str, Any], name: str = "pack.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _patched_slot(**overrides: Any) -> dict[str, Any]:
    raw = yaml.safe_load(yaml.safe_dump(MINIMAL_PACK))
    raw["sections"]["oyku"]["slots"]["belirti"].update(overrides)
    return raw


# --- the seam between the DSL and the session registry -----------------------


def test_the_dsl_and_the_session_registry_agree_about_which_locales_exist() -> None:
    """The one place the two declarations of "which locales exist" are compared.

    ``protocols`` may not import ``intake_platform`` — files/09 §7 gives the
    authoring surface zero access to patient data and
    ``test_import_boundary_no_patient_data_access`` enforces it by AST scan — so
    INT-296's registry cannot be imported into the DSL and the closed set is
    restated in :mod:`protocols.locale_text`. This test is what stops the two
    drifting, and it is deliberately an equality in both directions: a locale
    registered for sessions but unknown to the DSL would be selectable with no
    content behind it, and a locale the DSL accepts but the registry does not
    know would be content in a pack that no session can ever reach.
    """
    from intake_platform.locale import DEFAULT_LOCALE as SESSION_DEFAULT
    from intake_platform.locale import LOCALE_CODE_PATTERN as SESSION_PATTERN
    from intake_platform.locale import LOCALE_REGISTRY

    assert known_locales() == frozenset(LOCALE_REGISTRY)
    assert DEFAULT_LOCALE == SESSION_DEFAULT
    assert LOCALE_CODE_PATTERN.pattern == SESSION_PATTERN.pattern


# --- the map shape ----------------------------------------------------------


def test_a_migrated_field_is_a_map_and_no_longer_a_bare_string(tmp_path: Path) -> None:
    """The pre-migration scalar shape is gone, not merely discouraged.

    A field that still accepts a bare string is a field where half the tree can
    quietly stay behind, and a half-migrated tree is the one where a locale
    lookup silently returns Turkish.
    """
    with pytest.raises(PackSchemaError):
        load_pack(_write(tmp_path, _patched_slot(ask_tr="Şikâyetiniz nedir?")))


def test_the_map_parses_and_keeps_its_turkish(tmp_path: Path) -> None:
    pack = load_pack(_write(tmp_path, MINIMAL_PACK))
    slot = pack.sections["oyku"].slots["belirti"]
    assert entry_for(slot.ask_tr, DEFAULT_LOCALE) == "Şikâyetiniz nedir?"
    assert locales_of(slot.ask_tr) == frozenset({DEFAULT_LOCALE})


def test_choices_are_a_map_of_lists_with_matching_arity() -> None:
    """A locale offering a different number of options is a different question."""
    Slot.model_validate(
        {"type": "code", "valueset": "vs.x", "choices_tr": {"tr": ["evet", "hayır"]}}
    )
    with pytest.raises(ValidationError):
        Slot.model_validate({"type": "code", "valueset": "vs.x", "choices_tr": {"tr": []}})


# --- the near-miss negative controls the acceptance names --------------------


def test_a_pack_whose_tr_entry_was_dropped_fails(tmp_path: Path) -> None:
    """Near-miss control 1. Structurally perfect, Turkish gone."""
    with pytest.raises(PackSchemaError):
        load_pack(_write(tmp_path, _patched_slot(ask_tr={"de": "Was fehlt Ihnen?"})))


def test_a_locale_key_the_schema_does_not_know_fails(tmp_path: Path) -> None:
    """Near-miss control 2. ``de`` is a real, well-formed language code; the
    registry does not know it, so content for it is refused rather than parked.
    """
    with pytest.raises(PackSchemaError):
        load_pack(
            _write(
                tmp_path,
                _patched_slot(ask_tr={"tr": "Şikâyetiniz nedir?", "de": "Was fehlt Ihnen?"}),
            )
        )


def test_a_malformed_locale_key_fails(tmp_path: Path) -> None:
    with pytest.raises(PackSchemaError):
        load_pack(_write(tmp_path, _patched_slot(ask_tr={"Turkish": "Şikâyetiniz nedir?"})))


# --- no fallback, per INT-296 -----------------------------------------------


def test_a_missing_locale_entry_raises_rather_than_returning_turkish() -> None:
    """INT-296's resolver has no fallback parameter and neither does this one."""
    with pytest.raises(LocaleEntryAbsent):
        entry_for({DEFAULT_LOCALE: "Şikâyetiniz nedir?"}, "de")


# --- invariant 10, per locale ------------------------------------------------


def test_allow_paraphrase_is_per_locale_and_false_everywhere_on_an_instrument_item() -> None:
    item = InstrumentItem.model_validate(
        {"id": "phq9_1", "text_tr": {"tr": "Son iki haftada…"}, "allow_paraphrase": {"tr": False}}
    )
    assert item.allow_paraphrase == {DEFAULT_LOCALE: False}
    with pytest.raises(ValidationError):
        InstrumentItem.model_validate(
            {"id": "phq9_1", "text_tr": {"tr": "Son iki haftada…"}, "allow_paraphrase": {}}
        )


def test_a_locale_absent_from_any_speakable_field_is_not_selectable(tmp_path: Path) -> None:
    """The whole pack, not the field: a locale that can ask the first question
    and not the second cannot run the intake at all.
    """
    pack = load_pack(_write(tmp_path, MINIMAL_PACK))
    assert selectable_locales(pack) == frozenset({DEFAULT_LOCALE})


def test_selectable_locales_intersects_and_never_unions(tmp_path: Path) -> None:
    raw = yaml.safe_load(yaml.safe_dump(MINIMAL_PACK))
    slots = raw["sections"]["oyku"]["slots"]
    slots["ikinci"] = {
        "type": "string",
        "required": True,
        "ask_tr": {"tr": "İkinci soru?"},
        "follow_up_tr": {"tr": "Açar mısınız?"},
    }
    pack = load_pack(_write(tmp_path, raw))
    assert selectable_locales(pack) == frozenset({DEFAULT_LOCALE})


# --- the clip manifest keys on (locale, voice) -------------------------------


def test_a_clip_manifest_entry_carries_its_locale() -> None:
    entry = ClipManifestEntry(
        text_hash=clip_text_hash("merhaba"), clip_id="clip.tr.ses.abc", voice="ses", locale="tr"
    )
    assert entry.locale == DEFAULT_LOCALE


def test_the_clip_id_discriminates_the_locale(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A clip id that omits the locale is not keyed on the locale, whatever the
    surrounding dictionary is keyed on.
    """
    document = resolve_protocol(
        pack_id="base.derlenebilir",
        registry=registry,
        life_threat=life_threat,
        template=template,
    )
    rows, _prompts, refusals = clip_manifest(document, "sentetik-ses", locale=DEFAULT_LOCALE)
    assert not refusals
    assert rows
    for row in rows:
        assert row.entry.locale == DEFAULT_LOCALE
        assert row.entry.clip_id.startswith(f"clip.{DEFAULT_LOCALE}.sentetik-ses.")


def test_the_manifest_fails_on_a_collision_rather_than_preferring_one() -> None:
    """Two rows wanting one key is a refusal, not a first-writer-wins dedupe.

    Identical rows are the same clip and deduplicate; rows that disagree about
    whether the text may be paraphrased are two different obligations wearing
    one cache key, and serving either one of them is wrong.
    """
    from protocols.compile.emit_clips import SpeakableText, rows_from

    collide = (
        SpeakableText(subject="a", text="aynı metin", scripted=True, clipped=True),
        SpeakableText(subject="b", text="aynı metin", scripted=False, clipped=True),
    )
    _rows, _prompts, refusals = rows_from(collide, voice="ses", locale=DEFAULT_LOCALE)
    assert [refusal.code for refusal in refusals] == [RefusalCode.CLIP_KEY_COLLISION]


def test_an_unselectable_locale_is_refused_by_the_compiler(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id="base.derlenebilir",
            registry=registry,
            life_threat=life_threat,
            template=template,
            locale="de",
        )
    assert any(
        refusal.code is RefusalCode.LOCALE_NOT_SELECTABLE for refusal in excinfo.value.refusals
    )


# --- the whole tree ----------------------------------------------------------


def test_every_pack_in_the_tree_carries_tr_in_every_migrated_field() -> None:
    """Invariant 5, asserted over the real packs rather than over a fixture."""
    packs = sorted((PACKS_ROOT / "base").glob("*.yaml")) + sorted(
        (PACKS_ROOT / "specialty").glob("*.yaml")
    )
    assert len(packs) >= 90
    for path in packs:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("kind") != "pack":
            continue
        pack = load_pack(path)
        assert selectable_locales(pack) <= frozenset({DEFAULT_LOCALE})


# =============================================================================
# INT-314 — the four SPOKEN fields INT-297 left behind, and the clamp that
# stood in for them.
#
# ``confirm_tr``, ``action_tr``, ``do_nots_tr`` and ``ask_one_tr`` are spoken —
# they are the *action* half of a red-flag script, where invariant 10's
# "red-flag action scripts are spoken verbatim from the locale's own entry"
# actually bites — and INT-297 left all four as single strings. Rather than
# ignore that, ``selectable_locales`` clamped any pack carrying one of them to
# ``tr``, so no other language could speak a script nobody had written. This
# issue migrates the four and REMOVES the clamp: a clamp that outlives its
# reason is a silent restriction nobody can see.
# =============================================================================

RED_RULE: dict[str, Any] = {
    "id": "rf.sentetik",
    "label_tr": "Sentetik kural",
    "when": "belirti == 'x'",
    "tense": "now",
    "tense_anchor": "belirti",
    "level": "KIRMIZI_K2",
    "route": "EMERGENCY_NOW",
    "register": "ALERT",
    "notify_clinic": "always",
    "status": "active",
    "source": {
        "guideline_id": "SYN-GUIDE-A",
        "guideline_title": "Sentetik kılavuz A",
        "version_or_date": "sürüm bir",
        "url": "https://example.invalid/syn-guide-a",
        "retrieved_on": "2026-08-28",
        "quote": "sentetik alıntı metni",
    },
    "action": {
        "REMOTE": {
            "primary": "CALL_112",
            "show_112": True,
            "action_tr": {"tr": "Hemen yardım isteyin."},
            "do_nots_tr": {"tr": ["Yalnız kalmayın."]},
            "why_tr": {"tr": "Bu bir sentetik test metnidir."},
        },
        "ON_SITE": {
            "primary": "GO_TO_IN_HOUSE_ACIL",
            "show_112": False,
            "notify_staff_immediate": True,
            "action_tr": {"tr": "Görevlilere haber verin."},
            "why_tr": {"tr": "Bu bir sentetik test metnidir."},
        },
        "UNKNOWN": {
            "ask_one_tr": {"tr": "Şu anda hastanede misiniz?"},
            "on_yes": "ON_SITE",
            "on_no": "REMOTE",
            "on_no_answer": "REMOTE",
        },
    },
}


def _pack_with_rule(**rule_overrides: Any) -> dict[str, Any]:
    """The minimal pack, plus one RED rule carrying all four spoken fields."""
    raw = yaml.safe_load(yaml.safe_dump(MINIMAL_PACK))
    rule = yaml.safe_load(yaml.safe_dump(RED_RULE))
    for key, value in rule_overrides.items():
        rule[key] = value
    raw["red_flags"] = [rule]
    raw["sections"]["oyku"]["slots"]["belirti"]["confirm_tr"] = {"tr": "Doğru mu anladım?"}
    return raw


def _action_of(raw: dict[str, Any]) -> dict[str, Any]:
    action = raw["red_flags"][0]["action"]
    assert isinstance(action, dict)
    return action


# --- clause 1: the four become maps on the INT-297 schema ---------------------


def test_the_four_spoken_fields_are_maps_and_no_longer_bare_strings(tmp_path: Path) -> None:
    """The pre-migration scalar shape is gone for the action half too.

    One assertion per field, because a migration that reached three of four
    would leave exactly the half-migrated tree INT-297's §1 warns about — and
    ``action_tr`` is the one that closes invariant 10's red-flag clause.
    """
    scalar_shapes: tuple[tuple[str, Any], ...] = (
        ("REMOTE.action_tr", {"action_tr": "Hemen yardım isteyin."}),
        ("REMOTE.do_nots_tr", {"do_nots_tr": ["Yalnız kalmayın."]}),
    )
    for name, patch in scalar_shapes:
        raw = _pack_with_rule()
        _action_of(raw)["REMOTE"].update(patch)
        with pytest.raises(PackSchemaError, match="red_flags"):
            load_pack(_write(tmp_path, raw, name.replace(".", "_") + ".yaml"))

    raw = _pack_with_rule()
    _action_of(raw)["UNKNOWN"]["ask_one_tr"] = "Şu anda hastanede misiniz?"
    with pytest.raises(PackSchemaError):
        load_pack(_write(tmp_path, raw, "ask_one.yaml"))

    with pytest.raises(PackSchemaError):
        load_pack(_write(tmp_path, _patched_slot(confirm_tr="Doğru mu anladım?"), "confirm.yaml"))


def test_the_four_spoken_fields_keep_their_turkish_through_the_map(tmp_path: Path) -> None:
    pack = load_pack(_write(tmp_path, _pack_with_rule()))
    slot = pack.sections["oyku"].slots["belirti"]
    assert entry_for(slot.confirm_tr, DEFAULT_LOCALE) == "Doğru mu anladım?"
    action = pack.red_flags[0].action
    assert action is not None
    assert entry_for(action.remote.action_tr, DEFAULT_LOCALE) == "Hemen yardım isteyin."
    assert entry_for(action.remote.do_nots_tr, DEFAULT_LOCALE) == ("Yalnız kalmayın.",)
    assert entry_for(action.unknown.ask_one_tr, DEFAULT_LOCALE) == "Şu anda hastanede misiniz?"


def test_a_red_action_script_that_dropped_its_turkish_is_refused(tmp_path: Path) -> None:
    """Near-miss control. Structurally perfect map, Turkish gone (invariant 5)."""
    raw = _pack_with_rule()
    _action_of(raw)["REMOTE"]["action_tr"] = {"de": "Rufen Sie sofort Hilfe."}
    with pytest.raises(PackSchemaError):
        load_pack(_write(tmp_path, raw))


def test_an_unregistered_locale_on_a_red_action_script_is_refused(tmp_path: Path) -> None:
    """Near-miss control. ``de`` is real and well-formed; nobody signed it."""
    raw = _pack_with_rule()
    _action_of(raw)["REMOTE"]["action_tr"] = {
        "tr": "Hemen yardım isteyin.",
        "de": "Rufen Sie sofort Hilfe.",
    }
    with pytest.raises(PackSchemaError):
        load_pack(_write(tmp_path, raw))


def test_a_do_not_list_that_drops_an_instruction_in_one_locale_is_refused() -> None:
    """A do-not list is not prose: each line is a separate instruction, and a
    locale carrying fewer of them has dropped one rather than translated it."""
    LocationAction.model_validate(
        {
            "primary": "CALL_112",
            "show_112": True,
            "action_tr": {"tr": "Hemen yardım isteyin."},
            "do_nots_tr": {"tr": ["Yalnız kalmayın.", "Araç kullanmayın."]},
        }
    )
    with pytest.raises(ValidationError):
        LocationAction.model_validate(
            {
                "primary": "CALL_112",
                "show_112": True,
                "action_tr": {"tr": "Hemen yardım isteyin."},
                "do_nots_tr": {"tr": ["Yalnız kalmayın."], "de": []},
            }
        )


def test_an_absent_do_not_list_is_absent_and_not_an_empty_turkish_entry() -> None:
    """``do_nots_tr`` has no do-nots by default, in no locale.

    An empty map is *silence*, which constrains no locale; a ``{tr: []}`` entry
    is an author saying "this branch has no do-nots in Turkish", which does.
    Conflating them would make every pack without a do-not list unselectable in
    every language including Turkish.
    """
    action = LocationAction.model_validate(
        {"primary": "CALL_112", "show_112": True, "action_tr": {"tr": "Hemen arayın."}}
    )
    assert action.do_nots_tr == {}
    assert locales_of(None) == known_locales()


# --- clause 3: the clamp is removed, not left dormant ------------------------


def test_the_monolingual_clamp_is_gone_from_the_module() -> None:
    """The clamp is *removed*, not defanged.

    INT-297 named the four fields in ``pack_locale.MONOLINGUAL_SPOKEN_FIELDS``
    and intersected the answer with ``{tr}`` whenever a pack carried one. With
    the fields migrated the condition can never fire again, and a condition
    that can never fire is a restriction a future reader cannot tell from a
    live one. So the name has to be absent, not empty.
    """
    import protocols.pack_locale as pack_locale

    assert not hasattr(pack_locale, "MONOLINGUAL_SPOKEN_FIELDS")
    assert "MONOLINGUAL_SPOKEN_FIELDS" not in pack_locale.__all__


def test_a_pack_carrying_all_four_fields_in_a_second_locale_is_now_selectable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clamp lifted, demonstrated rather than asserted in the abstract.

    No second locale is registered — HB-O5 names which languages this build
    offers and HB-C19 signs what they say, and neither is answered here. So the
    registry is widened *for the duration of this test only*, which is the only
    way to show a restriction is gone: with one locale registered, a clamp to
    that one locale is invisible.
    """
    monkeypatch.setattr("protocols.locale_text.KNOWN_LOCALES", frozenset({DEFAULT_LOCALE, "de"}))
    raw = _pack_with_rule()
    slot = raw["sections"]["oyku"]["slots"]["belirti"]
    slot["ask_tr"]["de"] = "Was fehlt Ihnen?"
    slot["follow_up_tr"]["de"] = "Erzählen Sie mehr?"
    slot["confirm_tr"]["de"] = "Habe ich das richtig verstanden?"
    action = _action_of(raw)
    action["REMOTE"]["action_tr"]["de"] = "Rufen Sie sofort Hilfe."
    action["REMOTE"]["do_nots_tr"]["de"] = ["Bleiben Sie nicht allein."]
    action["REMOTE"]["why_tr"]["de"] = "Dies ist ein synthetischer Testtext."
    action["ON_SITE"]["action_tr"]["de"] = "Sagen Sie dem Personal Bescheid."
    action["ON_SITE"]["why_tr"]["de"] = "Dies ist ein synthetischer Testtext."
    action["UNKNOWN"]["ask_one_tr"]["de"] = "Sind Sie gerade im Krankenhaus?"

    pack = load_pack(_write(tmp_path, raw))
    assert selectable_locales(pack) == frozenset({DEFAULT_LOCALE, "de"})


def test_dropping_one_of_the_four_in_the_second_locale_takes_it_back_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The near-miss for the clause above: the same pack, one field short.

    Removing the clamp did not remove the rule it stood in for — it made the
    rule *apply to these four fields* instead of standing in front of them. A
    locale that can hear the action but not the do-nots still cannot run the
    pack, and each of the four is checked separately because a loop that
    covered three would look exactly like this test.
    """
    monkeypatch.setattr("protocols.locale_text.KNOWN_LOCALES", frozenset({DEFAULT_LOCALE, "de"}))

    def _fully_bilingual() -> dict[str, Any]:
        raw = _pack_with_rule()
        slot = raw["sections"]["oyku"]["slots"]["belirti"]
        slot["ask_tr"]["de"] = "Was fehlt Ihnen?"
        slot["follow_up_tr"]["de"] = "Erzählen Sie mehr?"
        slot["confirm_tr"]["de"] = "Habe ich das richtig verstanden?"
        action = _action_of(raw)
        action["REMOTE"]["action_tr"]["de"] = "Rufen Sie sofort Hilfe."
        action["REMOTE"]["do_nots_tr"]["de"] = ["Bleiben Sie nicht allein."]
        action["REMOTE"]["why_tr"]["de"] = "Dies ist ein synthetischer Testtext."
        action["ON_SITE"]["action_tr"]["de"] = "Sagen Sie dem Personal Bescheid."
        action["ON_SITE"]["why_tr"]["de"] = "Dies ist ein synthetischer Testtext."
        action["UNKNOWN"]["ask_one_tr"]["de"] = "Sind Sie gerade im Krankenhaus?"
        return raw

    removals: tuple[tuple[str, Any], ...] = (
        ("confirm_tr", lambda raw: raw["sections"]["oyku"]["slots"]["belirti"]["confirm_tr"]),
        ("action_tr", lambda raw: _action_of(raw)["REMOTE"]["action_tr"]),
        ("do_nots_tr", lambda raw: _action_of(raw)["REMOTE"]["do_nots_tr"]),
        ("ask_one_tr", lambda raw: _action_of(raw)["UNKNOWN"]["ask_one_tr"]),
    )
    for name, locate in removals:
        raw = _fully_bilingual()
        del locate(raw)["de"]
        pack = load_pack(_write(tmp_path, raw, f"without_{name}.yaml"))
        assert selectable_locales(pack) == frozenset({DEFAULT_LOCALE}), name


# --- clause 4: invariant 21 is untouched -------------------------------------


def test_a_locale_may_not_change_which_action_resolves_for_a_location() -> None:
    """Invariant 21 is about routing, and routing is not text.

    ``register`` and ``location`` are required with no permitted default, and
    the fields that decide *which action happens* — the action codes, the 112
    affordance, the crisis numbers and the three UNKNOWN branch targets — stay
    single-valued. Only the words moved. A per-locale action code would let the
    choice of language decide whether the patient is told to call 112.
    """
    for field, per_locale in (
        ("primary", {"tr": "CALL_112", "de": "GO_TO_IN_HOUSE_ACIL"}),
        ("secondary", {"tr": "NEAREST_ACIL_ADDRESS_AS_TEXT"}),
        ("show_112", {"tr": True, "de": False}),
        ("numbers", {"tr": [112]}),
    ):
        with pytest.raises(ValidationError):
            LocationAction.model_validate(
                {
                    "primary": "CALL_112",
                    "show_112": True,
                    "action_tr": {"tr": "Hemen arayın."},
                    field: per_locale,
                }
            )
    for field in ("on_yes", "on_no", "on_no_answer"):
        with pytest.raises(ValidationError):
            UnknownAction.model_validate(
                {
                    "ask_one_tr": {"tr": "Şu anda hastanede misiniz?"},
                    "on_yes": "ON_SITE",
                    "on_no": "REMOTE",
                    "on_no_answer": "REMOTE",
                    field: {"tr": "ON_SITE", "de": "REMOTE"},
                }
            )


def test_the_unknown_branch_asks_exactly_one_question_in_every_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one way a locale COULD have changed which action resolves.

    ``ask_one_tr`` is text, so it moved; but the answer to it picks the ON_SITE
    or the REMOTE branch. A second locale asking two questions in one breath is
    a patient answering "evet" to nobody knows which, and therefore a locale
    deciding which action resolves. So the gate runs over every entry in the
    map rather than over the Turkish one.

    **The limit of that claim, stated rather than implied.** ``_question_count``
    has two halves: counting question marks, which is language-neutral, and
    recognising a comma-joined second interrogative by its Turkish suffix
    (*-mi/-mı/-mu/-mü*), which is Turkish morphology and detects nothing in a
    language it was not written for. Running the gate per locale therefore
    makes the mark count apply everywhere and leaves the second half Turkish-
    only; it takes nothing away from Turkish. Naming another language's
    interrogative detector belongs with registering that language at all
    (HB-O5, HB-C19), not here.
    """
    monkeypatch.setattr("protocols.locale_text.KNOWN_LOCALES", frozenset({DEFAULT_LOCALE, "de"}))
    from protocols.compile.resolve import unknown_question_refusals

    def _unknown(**entries: str) -> UnknownAction:
        return UnknownAction.model_validate(
            {
                "ask_one_tr": entries,
                "on_yes": "ON_SITE",
                "on_no": "REMOTE",
                "on_no_answer": "REMOTE",
            }
        )

    # Turkish fine, the second locale asking two — refused because of the
    # SECOND locale, which is the assertion the per-locale loop exists for.
    second_locale_asks_two = _unknown(
        tr="Şu anda hastanede misiniz?",
        de="Sind Sie im Krankenhaus? Ist jemand bei Ihnen?",
    )
    assert [
        refusal.code for refusal in unknown_question_refusals("rf.sentetik", second_locale_asks_two)
    ] == [RefusalCode.UNKNOWN_NOT_ONE_QUESTION]

    # The Turkish comma form files/04 §8.2 names is still caught, unchanged.
    turkish_comma_form = _unknown(
        tr="Şu anda hastanede misiniz, yanınızda biri var mı?",
        de="Sind Sie gerade im Krankenhaus?",
    )
    assert [
        refusal.code for refusal in unknown_question_refusals("rf.sentetik", turkish_comma_form)
    ] == [RefusalCode.UNKNOWN_NOT_ONE_QUESTION]

    both_ask_one = _unknown(tr="Şu anda hastanede misiniz?", de="Sind Sie gerade im Krankenhaus?")
    assert unknown_question_refusals("rf.sentetik", both_ask_one) == []
