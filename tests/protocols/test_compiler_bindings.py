"""INT-041 — the binding layer: FHIR linkIds and the committed openEHR `.opt`.

files/12 §8 pins two facts this module has to make true:

- ``fhir_link_id`` is **derived from the slot id, never a counter** — so
  reordering, adding or suppressing a slot cannot silently re-point an
  existing answer at a different question.
- Every declared ``aql_path`` resolves in the committed ``.opt`` with a
  matching ``rm_type`` (runtime invariant 31), and ``opt_sha256`` still
  matches the file (files/12 §8.1 ``test_opt_is_pinned``) — so re-authoring
  in Archetype Designer forces a new definition version and the binding-table
  diff becomes the review surface.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from protocols.bindings import (
    OPT_SHA256,
    OPT_TEMPLATE_ID,
    OperationalTemplate,
    OptError,
    fhir_link_id,
    load_opt,
)


def test_opt_is_pinned() -> None:
    """files/12 §8.1: the pin is what makes a re-authored template a visible
    definition-version change instead of a silent binding drift."""
    repo_root = Path(__file__).resolve().parents[2]
    opt = repo_root / "packages" / "protocols" / "openehr" / "previsit_intake.v1.opt"
    digest = hashlib.sha256(opt.read_bytes()).hexdigest()
    assert digest == OPT_SHA256


def test_template_id_matches_the_committed_file(template: OperationalTemplate) -> None:
    assert template.template_id == OPT_TEMPLATE_ID == "previsit_intake.v1"
    assert template.sha256 == OPT_SHA256


def test_load_opt_refuses_a_file_whose_digest_moved(tmp_path: Path) -> None:
    """A tampered or re-authored template must not load under the old pin."""
    tampered = tmp_path / "tampered.opt"
    tampered.write_text("<template/>", encoding="utf-8")
    with pytest.raises(OptError):
        load_opt(tampered)


def test_load_opt_accepts_an_explicit_expected_digest(tmp_path: Path) -> None:
    """Tests and future template versions supply their own pin; production
    callers take the committed default and never override it."""
    other = tmp_path / "other.opt"
    other.write_text("<template/>", encoding="utf-8")
    with pytest.raises(OptError) as excinfo:
        load_opt(other, expected_sha256=hashlib.sha256(other.read_bytes()).hexdigest())
    # digest matches, so the failure is now structural, not integrity
    assert "template_id" in str(excinfo.value)


@pytest.mark.parametrize(
    ("path", "rm_type"),
    [
        ("/content[openEHR-EHR-EVALUATION.reason_for_encounter.v1]", "EVALUATION"),
        ("/content[openEHR-EHR-OBSERVATION.story.v1]", "OBSERVATION"),
        ("/content[openEHR-EHR-OBSERVATION.symptom_sign.v1]", "OBSERVATION"),
        ("/content[openEHR-EHR-ACTION.medication.v1]", "ACTION"),
        ("/content[openEHR-EHR-EVALUATION.triage_outcome.v1]", "EVALUATION"),
    ],
)
def test_every_named_archetype_root_resolves_with_its_rm_type(
    path: str, rm_type: str, template: OperationalTemplate
) -> None:
    assert template.resolve(path) == rm_type


def test_an_unknown_archetype_does_not_resolve(template: OperationalTemplate) -> None:
    assert template.resolve("/content[openEHR-EHR-OBSERVATION.sentetik_yok.v1]") is None


def test_a_leaf_at_code_path_does_not_resolve(template: OperationalTemplate) -> None:
    """The committed template carries archetype ROOTS only: no at-code was
    invented, so a leaf path fails closed rather than resolving against a
    fabrication (HUMAN_BLOCKERS Rule 1)."""
    assert template.resolve("/content[openEHR-EHR-OBSERVATION.story.v1]/data[at0001]") is None


def test_a_malformed_path_does_not_resolve(template: OperationalTemplate) -> None:
    assert template.resolve("content[openEHR-EHR-OBSERVATION.story.v1]") is None
    assert template.resolve("/content") is None


def test_cluster_provenance_is_deliberately_absent(template: OperationalTemplate) -> None:
    """files/03 §7 names CLUSTER.provenance, but a CLUSTER is not a
    CONTENT_ITEM and no committed source states which structure hosts it;
    binding it would require an invented at-code path (deferred to INT-032)."""
    assert template.resolve("/content[openEHR-EHR-CLUSTER.provenance.v1]") is None


def test_fhir_link_id_is_derived_from_the_slot_id_never_a_counter() -> None:
    assert fhir_link_id("ziyaret", "basvuru_nedeni") == "ziyaret.basvuru_nedeni"
    assert fhir_link_id("ziyaret", "sure_dakika") == "ziyaret.sure_dakika"
    # position-independent: the same slot in a differently-ordered section
    # keeps its id, which is the whole point of files/12 §8.
    assert fhir_link_id("ziyaret", "basvuru_nedeni") == fhir_link_id("ziyaret", "basvuru_nedeni")
