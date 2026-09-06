"""INT-221 — USVS conformance for the public-hospital pack.

Acceptance clause under test, verbatim: *"… USVS conformance tests"*.

INT-162 shipped the USVS (Ulusal Sağlık Veri Sözlüğü) mapping tables as a
mechanism that refuses to guess. This suite is the *conformance* gate that the
public-hospital pack turns on: it asserts, over the committed
``usvs_map.yaml``, the properties a Turkish public-hospital exchange requires —
that only sourced rows ever serve, that an inbound code with no committed
source resolves to **no code** rather than a guessed one, that a sourced HBYS
field binding is one its committed source actually defines, and that a draft
row cannot smuggle a target in under its flag.

These are the conformance counterparts to the protocols compiler refusing to
serve a ``draft_needs_source`` rule: a mapping the national dictionary does not
vouch for never reaches a patient's record.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from clinical_schemas.records import RecordItemKind
from intake_connectors.inbound import InboundObservation
from intake_connectors.usvs import (
    USVS_MAP_PATH,
    UsvsBinding,
    UsvsMappingError,
    load_usvs_map,
)

REPO = Path(__file__).resolve().parents[2]
HBYS_SOURCE = REPO / "docs" / "sources" / "hbys_intake_schema.md"


def test_served_bindings_are_sourced_only() -> None:
    """Conformance: a draft_needs_source row never serves — the fail-closed
    counterpart to refusing a draft protocol rule."""
    usvs = load_usvs_map()
    served = usvs.served_bindings()
    assert served, "the committed map must have at least one sourced binding to serve"
    for binding in served:
        assert binding.status == "sourced", binding.source_code
    # every draft is excluded from the served set
    drafts = [b for b in usvs.bindings if b.status == "draft_needs_source"]
    for draft in drafts:
        assert draft not in served


def test_inbound_code_with_no_committed_source_resolves_to_no_code() -> None:
    """An inbound lab whose USVS code binding is a draft maps to an item with
    NO code — never a guessed one (invariant 17)."""
    usvs = load_usvs_map()
    observation = InboundObservation(
        raw_system="LN",
        raw_code="14749-6",  # glucose — draft_needs_source in the committed map
        raw_label="Glukoz",
        kind=RecordItemKind.LAB,
        value_token="5.4",
        unit_token="mmol/L",
        observed_at=datetime(2026, 1, 1, 9, 0, 0),
    )
    item = usvs.map_observation(observation, source_ref="doc:test")
    assert item.code is None, "a draft-only inbound code must not receive a guessed code"


def test_sourced_hbys_field_bindings_verify_against_their_committed_source() -> None:
    """Conformance: every sourced HBYS field id is one the committed,
    owner-supplied schema actually defines."""
    usvs = load_usvs_map()
    source_text = HBYS_SOURCE.read_text(encoding="utf-8")
    field_bindings = [b for b in usvs.served_bindings() if b.table == "hbys_field"]
    assert field_bindings, "the public-hospital pack needs served HBYS field bindings"
    for binding in field_bindings:
        # does not raise: the id is defined in the source
        usvs.verify_against_source(binding, source_text)


def test_a_field_id_the_source_does_not_define_is_refused() -> None:
    """The near-miss: a plausible-looking id the source never defines fails
    verification — a mapping the source does not vouch for is not sourced."""
    usvs = load_usvs_map()
    source_text = HBYS_SOURCE.read_text(encoding="utf-8")
    bogus = UsvsBinding(
        table="hbys_field",
        intake_kind=RecordItemKind.ALLERGY,
        source_system="intake-field",
        source_code="allergy.present",
        target_code="999_NOPE",  # not in the committed source
        status="sourced",
        source_doc="docs/sources/hbys_intake_schema.md",
    )
    with pytest.raises(UsvsMappingError):
        usvs.verify_against_source(bogus, source_text)


def test_a_draft_binding_cannot_carry_a_target() -> None:
    """Conformance: a draft row is precisely the one with no target — a
    plausible code riding in under a draft flag is refused at construction."""
    with pytest.raises(UsvsMappingError):
        UsvsBinding(
            table="usvs_code",
            intake_kind=RecordItemKind.LAB,
            source_system="LN",
            source_code="14749-6",
            target_code="14749-6",  # a target under a draft flag — refused
            status="draft_needs_source",
        )


def test_committed_map_path_is_the_one_that_ships() -> None:
    assert USVS_MAP_PATH.is_file()
    assert (
        USVS_MAP_PATH
        == REPO / "packages" / "connectors" / "src" / "intake_connectors" / "usvs_map.yaml"
    )
