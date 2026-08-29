"""INT-041 acceptance: two runs produce identical hashes; the resolved-protocol
hash is pinned per session; artefacts land under packages/protocols/dist.

The acceptance names this file. What it pins:

- **Byte-identical re-emission.** Compiling the same inputs twice yields the
  same artefact bytes and the same ``resolved_protocol_hash``, in the same
  process and across a fresh registry load (files/03 §6 "compiled into
  standards"; files/12 §3.3 total order).
- **Order independence.** Nothing depends on the order overlays are named
  (files/12 §3.3: "merged content is order-independent by construction, not
  by convention").
- **The hash is a session-recordable value.** ``SessionState.protocol_hash``
  is a ``Sha256`` (INT-031); the compiler's hash must be accepted by it
  verbatim, which turns files/03 §6's "resolved-protocol hash stored on every
  session" into a type-level fact rather than a convention.
- **The hash moves when the protocol moves.** An applied overlay changes it;
  re-emitting the same protocol does not.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from clinical_schemas.session import SessionBudget, SessionState
from protocols.bindings import OperationalTemplate
from protocols.cli import load_registry
from protocols.compile import CompiledBundle, LifeThreatSet, compile_bundle, write_bundle
from protocols.loader import PackRegistry

PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"


def _compile(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    overlays: tuple[str, ...] = (),
) -> CompiledBundle:
    return compile_bundle(
        pack_id=PACK_ID,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        overlays=overlays,
    )


def test_two_runs_produce_identical_artifacts_and_hash(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    pack_tree: Path,
) -> None:
    first = _compile(registry, life_threat, template)
    second = _compile(load_registry(pack_tree), life_threat, template)
    assert first == second
    assert first.resolved_protocol_hash == second.resolved_protocol_hash
    assert first.artifacts == second.artifacts


def test_overlay_naming_order_does_not_change_the_hash(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    pack_tree: Path,
) -> None:
    forward = _compile(
        registry, life_threat, template, ("overlay.sentetik_bir", "overlay.sentetik_iki")
    )
    reverse = _compile(
        load_registry(pack_tree),
        life_threat,
        template,
        ("overlay.sentetik_iki", "overlay.sentetik_bir"),
    )
    assert forward.resolved_protocol_hash == reverse.resolved_protocol_hash


def test_an_applied_overlay_moves_the_hash(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    pack_tree: Path,
) -> None:
    bare = _compile(registry, life_threat, template)
    tightened = _compile(load_registry(pack_tree), life_threat, template, ("overlay.sentetik_bir",))
    assert bare.resolved_protocol_hash != tightened.resolved_protocol_hash


def test_hash_is_accepted_verbatim_as_a_session_protocol_hash(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    bundle = _compile(registry, life_threat, template)
    state = SessionState(
        session_id="ses-sentetik",
        protocol_id=PACK_ID,
        protocol_version="1.2.0",
        protocol_hash=bundle.resolved_protocol_hash,
        mode="fast",
        status="active",
        reference_time=datetime(2026, 8, 29, tzinfo=UTC),
        budget=SessionBudget(turns_used=0, turns_remaining=18),
    )
    assert state.protocol_hash == bundle.resolved_protocol_hash


def test_write_bundle_is_byte_identical_on_a_second_write(
    tmp_path: Path,
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
) -> None:
    bundle = _compile(registry, life_threat, template)
    first = {path: path.read_bytes() for path in write_bundle(bundle, tmp_path)}
    second = {path: path.read_bytes() for path in write_bundle(bundle, tmp_path)}
    assert first == second
    assert first, "the bundle must write at least one artefact"


def test_manifest_records_the_hash_and_the_opt_pin(
    tmp_path: Path,
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
) -> None:
    bundle = _compile(registry, life_threat, template)
    written = write_bundle(bundle, tmp_path)
    manifest_path = next(path for path in written if path.name == "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["resolved_protocol_hash"] == bundle.resolved_protocol_hash
    assert manifest["opt_template_id"] == "previsit_intake.v1"
    assert len(manifest["opt_sha256"]) == 64
    # Every emitted artefact is itself hashed, so a hand-edited dist file is
    # detectable without recompiling (files/12 §8 questionnaire_definition).
    assert set(manifest["artifacts"]) == {
        name for name in bundle.artifacts if name != "manifest.json"
    }
