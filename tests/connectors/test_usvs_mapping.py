"""INT-162 — the USVS mapping table, and what it refuses to guess.

The acceptance clause this file gates is *"mapping tables to USVS data
dictionary"*. The USVS (Ulusal Sağlık Veri Sözlüğü) is the Ministry of
Health's national health-data dictionary; a binding from a hospital's own code
to a USVS element is a clinical judgement, and no committed Turkish USVS source
lives in this repository. So the table ships as a **mechanism** with the USVS
code bindings marked ``draft_needs_source`` and a loader that refuses to serve
them — exactly the fail-closed shape INT-160's destination registry uses, and
exactly what invariant 17 prescribes when the content is a human's to supply.

Three properties are enforced here rather than trusted:

1. **A ``draft_needs_source`` binding never becomes a code.** The loader
   excludes it from the served map, and ``map_observation`` returns an
   unconfirmed item whose ``code`` is ``None`` — never a guessed one
   (``ExtractedRecordItem`` already forbids a guessed code; this keeps that
   true across the mapping seam).
2. **A sourced binding is checked against its committed source.** The HBYS
   field-id bindings cite ``docs/sources/hbys_intake_schema.md`` — an
   owner-supplied file committed verbatim — and a binding naming a field id
   that file does not contain is refused, not served.
3. **Nothing the message says becomes triage.** An inbound observation is data
   (invariant 1): the mapped item has no field a RED/YELLOW could occupy, and a
   numeric value crosses the seam as a ``Decimal`` (invariant 22), never a
   float.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from clinical_schemas.records import CodeSystem, ExtractedRecordItem, RecordItemKind
from intake_connectors.inbound import InboundObservation
from intake_connectors.usvs import (
    USVS_MAP_PATH,
    UsvsBinding,
    UsvsMap,
    UsvsMappingError,
    load_usvs_map,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HBYS_SOURCE = REPO_ROOT / "docs/sources/hbys_intake_schema.md"


def observation(**overrides: object) -> InboundObservation:
    base: dict[str, object] = {
        "raw_system": "LN",
        "raw_code": "14749-6",
        "raw_label": "Glucose",
        "kind": RecordItemKind.LAB,
        "value_token": "95",
        "unit_token": "mg/dL",
        "observed_at": None,
        "abnormal_flag": None,
    }
    base.update(overrides)
    return InboundObservation(**base)  # type: ignore[arg-type]


# --- 1. the committed table loads and is internally consistent ----------------------


def test_the_shipped_usvs_map_loads_and_validates() -> None:
    """The committed ``usvs_map.yaml`` parses under the strict schema."""
    usvs = load_usvs_map()
    assert isinstance(usvs, UsvsMap)
    assert len(usvs.bindings) > 0


def test_the_map_path_points_at_a_real_file() -> None:
    assert USVS_MAP_PATH.exists()


def test_every_usvs_code_binding_ships_as_draft_needs_source() -> None:
    """No USVS national code is asserted without a committed source.

    The honest state of the table today: every binding to a USVS *element* is
    ``draft_needs_source`` and carries no code, because no committed USVS
    dictionary vouches for one. The day a source is committed, a row flips to
    ``sourced`` and this test is updated with it — it exists to make the flip a
    deliberate, reviewed act, not a silent one.
    """
    usvs = load_usvs_map()
    for binding in usvs.usvs_code_bindings():
        assert binding.status == "draft_needs_source"
        assert binding.target_system is None
        assert binding.target_code is None
        assert binding.usvs_element is None


# --- 2. the loader refuses to serve a draft, and refuses a guessed code -------------


def test_served_bindings_exclude_every_draft() -> None:
    usvs = load_usvs_map()
    assert all(binding.status == "sourced" for binding in usvs.served_bindings())


def test_a_draft_binding_that_carries_a_code_is_refused_at_load() -> None:
    """``draft_needs_source`` and a resolved code are contradictory: a draft is
    precisely a row for which no code has been supplied. The schema refuses the
    contradiction rather than letting a plausible code ride in under a draft
    flag."""
    with pytest.raises(UsvsMappingError):
        UsvsBinding.model_validate(
            {
                "table": "usvs_code",
                "intake_kind": "lab",
                "source_system": "LN",
                "source_code": "14749-6",
                "target_system": "loinc",
                "target_code": "14749-6",
                "usvs_element": "USVS.LAB.GLUCOSE",
                "status": "draft_needs_source",
                "source_doc": None,
            }
        )


def test_a_sourced_binding_without_a_committed_source_doc_is_refused() -> None:
    with pytest.raises(UsvsMappingError):
        UsvsBinding.model_validate(
            {
                "table": "usvs_code",
                "intake_kind": "lab",
                "source_system": "LN",
                "source_code": "14749-6",
                "target_system": "loinc",
                "target_code": "14749-6",
                "usvs_element": "USVS.LAB.GLUCOSE",
                "status": "sourced",
                "source_doc": None,
            }
        )


# --- 3. the HBYS field bindings are checked against the committed source -------------


def test_every_hbys_field_binding_names_a_field_the_committed_source_contains() -> None:
    """The sourced half of the table is verifiable: each HBYS binding cites a
    field id that ``docs/sources/hbys_intake_schema.md`` actually defines."""
    committed = HBYS_SOURCE.read_text(encoding="utf-8")
    bindings = load_usvs_map().hbys_field_bindings()
    assert bindings, "the sourced positive-control half of the table is not empty"
    for binding in bindings:
        assert binding.status == "sourced"
        assert binding.source_doc == "docs/sources/hbys_intake_schema.md"
        assert f"id: '{binding.target_code}'" in committed


def test_a_hbys_binding_to_a_field_absent_from_the_source_is_refused() -> None:
    """The near-miss negative control: a field id that looks plausible
    (``td999``) but the committed source never defines must not validate into
    the served map."""
    usvs = load_usvs_map()
    forged = UsvsBinding(
        table="hbys_field",
        intake_kind=RecordItemKind.DIAGNOSIS,
        source_system="intake-field",
        source_code="soygecmis.anne.ht",
        target_system=None,
        target_code="td999",
        usvs_element=None,
        status="sourced",
        source_doc="docs/sources/hbys_intake_schema.md",
    )
    with pytest.raises(UsvsMappingError):
        usvs.verify_against_source(forged, HBYS_SOURCE.read_text(encoding="utf-8"))


# --- 4. mapping an observation: honest by default, correct when sourced --------------


def test_an_observation_with_no_sourced_binding_maps_to_an_item_with_no_code() -> None:
    """Today's honest outcome: the USVS half is all draft, so an inbound lab
    resolves to an unconfirmed item that carries the value and the sender's
    label but **no code** — never a guessed one."""
    item = load_usvs_map().map_observation(observation(), source_ref="acibadem-hbys-oru:MSG1")
    assert isinstance(item, ExtractedRecordItem)
    assert item.code is None
    assert item.value_magnitude == Decimal("95")
    assert item.unit == "mg/dL"
    assert item.verification_status.value == "unconfirmed"


def test_a_sourced_binding_makes_map_observation_emit_that_code() -> None:
    """The positive control the always-draft table cannot give on its own: a
    synthetic *sourced* binding proves the serve path emits the mapped code, so
    the fail-closed behaviour above is a real refusal and not a vacuous one."""
    usvs = UsvsMap(
        bindings=(
            UsvsBinding(
                table="usvs_code",
                intake_kind=RecordItemKind.LAB,
                source_system="LN",
                source_code="14749-6",
                target_system=CodeSystem.LOINC,
                target_code="14749-6",
                usvs_element=None,
                status="sourced",
                source_doc="tests/connectors/test_usvs_mapping.py",
            ),
        )
    )
    item = usvs.map_observation(observation(), source_ref="acibadem-hbys-oru:MSG1")
    assert item.code is not None
    assert item.code.system is CodeSystem.LOINC
    assert item.code.code == "14749-6"


def test_a_non_numeric_value_maps_without_a_magnitude_rather_than_crashing() -> None:
    item = load_usvs_map().map_observation(
        observation(raw_code="55233-1", value_token="stabil", unit_token=None),
        source_ref="acibadem-hbys-oru:MSG1",
    )
    assert item.value_magnitude is None
    assert item.summary  # the sender's label still renders for confirmation


def test_a_grouped_number_is_never_silently_reinterpreted() -> None:
    """Invariant 22: a value that is not an unambiguous decimal does not become
    a magnitude by guessing where a grouping separator was."""
    item = load_usvs_map().map_observation(
        observation(value_token="1,234"), source_ref="acibadem-hbys-oru:MSG1"
    )
    assert item.value_magnitude is None


def test_the_mapped_item_has_no_field_a_triage_level_could_occupy() -> None:
    """Invariant 1: an inbound message may carry candidate_flags only. The
    mapper's product is an ``ExtractedRecordItem``, which has no triage field at
    all — a document (or a message) is not a rules engine."""
    item = load_usvs_map().map_observation(
        observation(abnormal_flag="HH"), source_ref="acibadem-hbys-oru:MSG1"
    )
    assert not hasattr(item, "triage")
    assert not hasattr(item, "level")
    assert "HH" not in repr(item)


def test_the_map_declares_its_inventory_annotation() -> None:
    """Invariant 18 spirit: the table describes clinical data crossing to a
    hospital, so it carries the {category,purpose,basis,retention,recipients}
    inventory block."""
    usvs = load_usvs_map()
    for field in ("category", "purpose", "basis", "retention", "recipients"):
        assert usvs.inventory.get(field)
