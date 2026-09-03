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
from protocols.dsl import ClipManifestEntry, InstrumentItem, Slot, clip_text_hash
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
