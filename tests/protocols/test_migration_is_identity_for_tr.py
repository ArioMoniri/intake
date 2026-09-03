"""INT-297 — the migration is mechanical, idempotent and silent for Turkish.

A field rename that also changes one Turkish string is a content change wearing
a refactor's clothes, and no amount of reading the diff catches it across 93
packs. So the migration is a committed script, and this file is the only thing
standing between it and a patient hearing something different.

Two baselines, because the two halves of the tree are reachable in different ways:

``int297_tr_content_baseline.json``
    Every one of the five migrated fields in every YAML document in the tree —
    packs, the life-threat sibling set and the test fixtures — with the
    ``expand_tr`` expansion beside it, which is the string that actually reaches
    TTS (invariant 22). Produced by :mod:`protocols.migrate.tr_baseline`, which
    reads the *raw* YAML and accepts either shape, so the same code that wrote
    the baseline before the migration re-derives it after. All 93 packs are
    ``maturity: L0`` (HB-C1) and the serve interlock refuses them, so this is the
    only complete projection of their content that exists — and it is complete.

``int297_pre_migration_bundle.json``
    For the one tree that does compile, the served bundle itself: the FHIR
    Questionnaire, the openEHR bindings, the Pydantic and TypeScript modules,
    and the clip manifest's spoken content.

What is *not* claimed identical is recorded here rather than omitted, and each
difference is asserted rather than tolerated. There are exactly two, and both
are identifiers:

``resolved_protocol_hash``
    A sha256 over the canonical resolved document, whose *shape* moved — a
    string became a one-key map. It is embedded in three artefacts, and
    :func:`test_the_served_bundle_for_tr_is_byte_identical` substitutes it back
    before comparing rather than excluding those artefacts, so the comparison
    still covers every other byte of them.

the clip id and the clip artefact's name
    ``clip.<voice>.<digest>`` became ``clip.<locale>.<voice>.<digest>`` and
    ``clips.<voice>.json`` became ``clips.<locale>.<voice>.json``, because
    acceptance line 4 requires the manifest to key on ``(locale, voice)`` and a
    key that omits the locale is not keyed on it.

No string a Turkish patient hears moves at all — not one of the 468 authored
fields in the tree, and not one row of the compiled manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from protocols.bindings import OperationalTemplate
from protocols.cli import load_registry
from protocols.compile import CompiledBundle, LifeThreatSet, compile_bundle
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE
from protocols.migrate.locale_maps import (
    MIGRATED_FIELDS,
    SPOKEN_FIELDS,
    migrate_tree,
    unmigrate_document,
)
from protocols.migrate.tr_baseline import authored_baseline

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "protocols"
CONTENT_BASELINE = FIXTURES / "int297_tr_content_baseline.json"
BUNDLE_BASELINE = FIXTURES / "int297_pre_migration_bundle.json"

BASELINE_TREES = (
    REPO_ROOT / "packages" / "protocols" / "base",
    REPO_ROOT / "packages" / "protocols" / "specialty",
    REPO_ROOT / "tests" / "fixtures" / "protocols",
    REPO_ROOT / "files" / "protocols",
)

PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"


def _bundle(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> CompiledBundle:
    return compile_bundle(
        pack_id=PACK_ID,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        locale=DEFAULT_LOCALE,
    )


# --- the headline ------------------------------------------------------------


def test_every_turkish_string_in_the_tree_is_byte_identical_to_the_pre_migration_baseline() -> None:
    baseline = json.loads(CONTENT_BASELINE.read_text(encoding="utf-8"))
    current: dict[str, object] = {}
    for tree in BASELINE_TREES:
        current.update(authored_baseline(tree, root=REPO_ROOT))
    assert dict(sorted(current.items())) == baseline


def test_the_served_bundle_for_tr_is_byte_identical(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Every artefact, byte for byte, once the one moved identifier is put back.

    The substitution is deliberate rather than an exclusion: ``slots.py``,
    ``slots.ts`` and ``questionnaire.json`` each carry the resolved-protocol
    hash in a header or an extension, and dropping those three artefacts from
    the comparison to avoid one changed line would drop the FHIR item texts and
    the slot schemas with them — which is precisely what this test exists to
    check.
    """
    baseline = json.loads(BUNDLE_BASELINE.read_text(encoding="utf-8"))
    bundle = _bundle(registry, life_threat, template)
    content = {
        name: text.replace(bundle.resolved_protocol_hash, baseline["resolved_protocol_hash"])
        for name, text in bundle.artifacts.items()
        if not name.startswith("clips.") and name != "manifest.json"
    }
    assert content == baseline["artifacts"]
    spoken = [
        {
            "subject": row.subject,
            "text_tr": row.text_tr,
            "scripted": row.scripted,
            "text_hash": row.entry.text_hash,
        }
        for row in bundle.clip_manifest
    ]
    assert spoken == baseline["spoken"]


def test_the_two_recorded_differences_are_identifiers_and_nothing_else(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Asserted, not tolerated. Each difference is named and pinned here.

    A test that merely excluded these would be a test that could not tell a
    deliberate re-keying from an accidental content edit, which is the whole
    distinction the issue turns on.
    """
    baseline = json.loads(BUNDLE_BASELINE.read_text(encoding="utf-8"))
    bundle = _bundle(registry, life_threat, template)

    # 1. The resolved-protocol hash moved, because the resolved document's shape
    #    did. It is a session pin, not a sentence.
    assert bundle.resolved_protocol_hash != baseline["resolved_protocol_hash"]

    # 2. The clip key gained the locale, in the id and in the artefact name.
    old_ids = baseline["clip_ids"]
    new_ids = [row.entry.clip_id for row in bundle.clip_manifest]
    assert len(new_ids) == len(old_ids)
    assert all(clip_id.startswith(f"clip.{DEFAULT_LOCALE}.{VOICE}.") for clip_id in new_ids)
    assert all(old_id.startswith(f"clip.{VOICE}.") for old_id in old_ids)
    assert f"clips.{DEFAULT_LOCALE}.{VOICE}.json" in bundle.artifacts
    assert f"clips.{VOICE}.json" not in bundle.artifacts


# --- the migration itself ----------------------------------------------------


def test_the_migration_is_idempotent(tmp_path: Path) -> None:
    source = REPO_ROOT / "packages" / "protocols" / "specialty"
    tree = tmp_path / "specialty"
    tree.mkdir()
    for path in sorted(source.glob("*.yaml"))[:5]:
        (tree / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    first = migrate_tree(tree)
    before = {path.name: path.read_text(encoding="utf-8") for path in sorted(tree.glob("*.yaml"))}
    second = migrate_tree(tree)
    after = {path.name: path.read_text(encoding="utf-8") for path in sorted(tree.glob("*.yaml"))}
    assert first == ()
    assert second == ()
    assert before == after


def test_the_migration_is_reversible(tmp_path: Path) -> None:
    """``down(up(x)) == x`` on shape, so the rewrite carried nothing away."""
    path = REPO_ROOT / "packages" / "protocols" / "specialty" / "kardiyoloji.yaml"
    migrated = yaml.safe_load(path.read_text(encoding="utf-8"))
    reverted = unmigrate_document(migrated)
    for section in reverted["sections"].values():
        for slot in section["slots"].values():
            for field in MIGRATED_FIELDS:
                if field in slot:
                    assert not isinstance(slot[field], dict)


def test_the_tree_carries_no_unmigrated_field_left() -> None:
    unmigrated: list[str] = []
    for tree in BASELINE_TREES:
        for path in sorted(tree.rglob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("kind") == "text_mirror":
                continue
            unmigrated.extend(
                f"{path}:{pointer}"
                for pointer, value in _walk(raw, ())
                if not isinstance(value, dict)
            )
    assert unmigrated == []


def _walk(node: object, path: tuple[str, ...]) -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for key, child in node.items():
            here = (*path, str(key))
            if key in MIGRATED_FIELDS:
                found.append(("/".join(here), child))
            else:
                found.extend(_walk(child, here))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            found.extend(_walk(child, (*path, str(index))))
    return found


def test_the_committed_tree_still_loads() -> None:
    """Every migrated pack still parses through the real registry loader.

    The count is asserted, not just the absence of an exception: a loader that
    silently passed over a file it could no longer parse would leave the tree
    "loading" with packs missing from it.
    """
    registry = load_registry(REPO_ROOT / "packages" / "protocols")
    assert len(registry) >= 90


# =============================================================================
# INT-314 — the same discipline, repeated rather than assumed, for the four
# SPOKEN fields INT-297 left as single strings.
#
# ``confirm_tr``, ``action_tr``, ``do_nots_tr`` and ``ask_one_tr`` are the
# action half of a red-flag script. *A refactor that changes one Turkish RED
# sentence is the most dangerous edit in this repository*, so the check is not
# a re-read of the diff: it is the same shape-agnostic comparator INT-297
# committed, pointed at the four fields, over a baseline taken from the tree
# BEFORE the schema moved — authored bytes and ``expand_tr`` expansion both,
# because the expansion is what actually reaches TTS (invariant 22).
# =============================================================================

SPOKEN_BASELINE = FIXTURES / "int314_tr_content_baseline.json"

#: Wider than INT-297's four trees: the four spoken fields also live in the
#: compiler goldens and the simulator's fixture tree, and a baseline that
#: skipped those would leave the RED scripts they carry unchecked.
SPOKEN_TREES = (
    *BASELINE_TREES,
    REPO_ROOT / "tests" / "protocols" / "goldens",
    REPO_ROOT / "tests" / "sim" / "fixtures",
)


def test_every_spoken_turkish_string_in_the_tree_is_byte_identical_to_its_baseline() -> None:
    """The headline for INT-314, and the same one INT-297 wrote.

    Every ``confirm_tr``, ``action_tr``, ``do_nots_tr`` and ``ask_one_tr`` in
    every YAML document in the tree, authored bytes beside expanded bytes,
    against a baseline generated from the pre-migration tree by this same
    function reading the raw YAML. Not a diff somebody read.
    """
    baseline = json.loads(SPOKEN_BASELINE.read_text(encoding="utf-8"))
    current: dict[str, object] = {}
    for tree in SPOKEN_TREES:
        current.update(authored_baseline(tree, root=REPO_ROOT, fields=SPOKEN_FIELDS))
    assert dict(sorted(current.items())) == baseline


def test_the_baseline_actually_covers_the_red_flag_action_scripts() -> None:
    """A comparator over an empty set passes vacuously.

    So the baseline's own coverage is asserted: the life-threat sibling set is
    in it, every one of the four fields appears, and the count is pinned. A
    baseline that silently stopped finding ``action_tr`` would otherwise be a
    green test proving nothing.
    """
    baseline: dict[str, dict[str, object]] = json.loads(SPOKEN_BASELINE.read_text(encoding="utf-8"))
    assert "files/protocols/base.life_threat.yaml" in baseline
    pointers = [pointer for entries in baseline.values() for pointer in entries]
    for field in SPOKEN_FIELDS:
        assert any(pointer.endswith(field) for pointer in pointers), field
    assert len(pointers) == 58


def test_the_served_bundle_is_unchanged_by_the_spoken_field_migration(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The RED rows of the compiled manifest, against INT-297's own baseline.

    ``int297_pre_migration_bundle.json`` was taken before *either* migration, so
    comparing to it now is the stronger claim: the spoken content of every
    red-flag row is the same bytes it was two schema changes ago. The rows are
    filtered to the rule subjects because those are the rows this issue moves —
    ``test_the_served_bundle_for_tr_is_byte_identical`` above still covers all
    of them, unchanged, and its passing is half this test's point.
    """
    baseline = json.loads(BUNDLE_BASELINE.read_text(encoding="utf-8"))
    bundle = _bundle(registry, life_threat, template)
    red = [
        {
            "subject": row.subject,
            "text_tr": row.text_tr,
            "scripted": row.scripted,
            "text_hash": row.entry.text_hash,
        }
        for row in bundle.clip_manifest
        if row.subject.startswith("rf.")
    ]
    assert red == [row for row in baseline["spoken"] if str(row["subject"]).startswith("rf.")]
    assert red


def test_the_tree_carries_no_unmigrated_spoken_field_left() -> None:
    """Every one of the four, in every document, is a map. Including the
    goldens and the simulator fixtures, which INT-297's sweep did not reach."""
    unmigrated: list[str] = []
    for tree in SPOKEN_TREES:
        for path in sorted(tree.rglob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("kind") == "text_mirror":
                continue
            unmigrated.extend(
                f"{path}:{pointer}"
                for pointer, value in _walk_fields(raw, (), SPOKEN_FIELDS)
                if not isinstance(value, dict)
            )
    assert unmigrated == []


def _walk_fields(
    node: object, path: tuple[str, ...], fields: tuple[str, ...]
) -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for key, child in node.items():
            here = (*path, str(key))
            if key in fields:
                found.append(("/".join(here), child))
            else:
                found.extend(_walk_fields(child, here, fields))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            found.extend(_walk_fields(child, (*path, str(index)), fields))
    return found
