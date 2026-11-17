"""INT-257 — the committed openEHR OPT against the official OPT 1.4 schema.

INT-032 found, against a live EHRbase 2.35.1, that the committed template does
not upload: HTTP 500, a ``NullPointerException`` on a missing ``occurrences``.
Its evidence put that down to EHRbase dereferencing an element the schema made
optional. The schema says otherwise, and this module reads the schema rather
than recalling it. openEHR ITS-XML, tag ``Release-1.0.2``,
``components/ALL/Archetype.xsd``:

- ``C_OBJECT`` is the sequence ``rm_type_name, occurrences, node_id`` with no
  ``minOccurs`` on any of them — all three are mandatory;
- ``C_ATTRIBUTE`` requires ``existence``; ``C_MULTIPLE_ATTRIBUTE`` appends a
  mandatory ``cardinality`` after its ``children``;
- ``Template.xsd``'s ``C_ARCHETYPE_ROOT`` extends ``C_COMPLEX_OBJECT``, so its
  ``archetype_id`` comes *after* the ``attributes``.

The committed file broke all four. The schema set is vendored byte-for-byte
under ``tests/fixtures/openehr/its-xml-Release-1.0.2/`` with its Apache-2.0
LICENSE and pinned by digest below, so the validation runs offline and a
changed schema is a visible diff. Provenance (URL, tag commit, sha256) is in
docs/evidence/INT-257.md.

Where each value in the template comes from — nothing is chosen here:

- ``occurrences`` 0..* on each content root. The occurrences of an archetype
  root under ``COMPOSITION.content`` is stated by the composition archetype's
  content constraint. That archetype, ``openEHR-EHR-COMPOSITION.intake_previsit.v1``,
  is LOCAL and unauthored (files/03 §7; HUMAN_BLOCKERS HB-C12); the entry
  archetypes state no occurrences for their own root. What is left is the RM,
  which bounds ``content`` by nothing, and 0..* is exactly that.
- ``existence`` 0..1 and ``cardinality`` {0..*; ordered; non-unique} on
  ``content``: RM 1.0.2 ``COMPOSITION.content : List<CONTENT_ITEM>`` is
  ``0..1``, and ADL 1.4 §5.3.4.1 defines a logical list as ordered and
  non-unique.
- ``node_id`` present and empty. A non-empty node id must be a term code the
  template's terminology defines (AOM 1.4 §4.2.3.1), and the template carries
  no archetype terminology until HB-C12 authors it. EHRbase's own OPT parser
  dereferences that terminology for every non-blank node id, so an uncatalogued
  code is a 500 on upload, not a cosmetic gap —
  :func:`test_the_schema_admits_an_uncatalogued_node_id_so_the_catalogue_guard_is_needed`
  proves the schema alone would let one through.
"""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

import pytest
from lxml import etree
from protocols.bindings import OPT_PATH, OPT_SHA256, load_opt

REPO = Path(__file__).resolve().parents[2]
COMMITTED_OPT = REPO / OPT_PATH
XSD_DIR = REPO / "tests/fixtures/openehr/its-xml-Release-1.0.2"

#: openEHR ITS-XML tag Release-1.0.2 (commit f7a937778bf9ea43b01b0f9d8a616e47f35017c1),
#: ``components/ALL/<name>`` and the repository ``LICENSE``, byte-for-byte.
XSD_PINS = {
    "Template.xsd": "ae34d26444693a9c02072e0f936218f758f6e3c0356e6940469a6109e6ff6510",
    "OpenehrProfile.xsd": "faa8d67637e18578c62f24bb1548ab44198025a9c4fb8478c8c9246e74547355",
    "Archetype.xsd": "839727a41ba79d123c4c5e214fd05145aa71f19137aa682c68b43a2f2dd19140",
    "Resource.xsd": "976c4158b85d96f0c64ee8d351e6145fb7439fd3c90f7c565efc6ad24cae5520",
    "BaseTypes.xsd": "9b9e5b2d17d987fed9810ffb060d747e2d9e2de9a8896a890fb5bdb0275a7108",
    "LICENSE": "b40930bbcf80744c86c46a12bc9da056641d722716c378f5659b9e555ef833e1",
}

NS = "http://schemas.openehr.org/v1"
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
_O = f"{{{NS}}}"

#: The nine content roots, in file order — the set files/03 §7 names and
#: INT-041 transcribed. INT-257 changes their constraints, never the set.
CONTENT_ROOTS = (
    ("openEHR-EHR-EVALUATION.reason_for_encounter.v1", "EVALUATION"),
    ("openEHR-EHR-OBSERVATION.story.v1", "OBSERVATION"),
    ("openEHR-EHR-OBSERVATION.symptom_sign.v1", "OBSERVATION"),
    ("openEHR-EHR-EVALUATION.problem_diagnosis.v1", "EVALUATION"),
    ("openEHR-EHR-ACTION.medication.v1", "ACTION"),
    ("openEHR-EHR-EVALUATION.adverse_reaction_risk.v1", "EVALUATION"),
    ("openEHR-EHR-OBSERVATION.phq9.v1", "OBSERVATION"),
    ("openEHR-EHR-OBSERVATION.gad7.v1", "OBSERVATION"),
    ("openEHR-EHR-EVALUATION.triage_outcome.v1", "EVALUATION"),
)


@pytest.fixture(scope="module")
def schema() -> etree.XMLSchema:
    # The includes (Template -> OpenehrProfile -> Archetype -> Resource ->
    # BaseTypes) resolve relative to the vendored directory; no network.
    return etree.XMLSchema(etree.parse(str(XSD_DIR / "Template.xsd")))


@pytest.fixture()
def tree() -> etree._ElementTree:
    return etree.parse(str(COMMITTED_OPT))


def _definition(tree: etree._ElementTree) -> etree._Element:
    definition = tree.getroot().find(f"{_O}definition")
    assert definition is not None
    return definition


def _content(tree: etree._ElementTree) -> etree._Element:
    for attribute in _definition(tree).findall(f"{_O}attributes"):
        if attribute.findtext(f"{_O}rm_attribute_name") == "content":
            return attribute
    raise AssertionError("the template constrains no COMPOSITION.content attribute")


def _c_objects(tree: etree._ElementTree) -> list[etree._Element]:
    """Every C_OBJECT node: the definition root and every ``children``."""
    return [_definition(tree), *tree.getroot().iter(f"{_O}children")]


def _interval(node: etree._Element | None) -> dict[str, str | None]:
    assert node is not None, "interval element missing"
    fields = (
        "lower_included",
        "upper_included",
        "lower_unbounded",
        "upper_unbounded",
        "lower",
        "upper",
    )
    return {name: node.findtext(f"{_O}{name}") for name in fields}


def _uncatalogued_node_ids(tree: etree._ElementTree) -> list[str]:
    """Non-empty node ids with no ``term_definitions`` entry on their nearest
    enclosing archetype root — what EHRbase's parser would dereference into a
    NullPointerException (``OPTParser.buildNode``)."""
    missing: list[str] = []
    for node in _c_objects(tree):
        node_id = (node.findtext(f"{_O}node_id") or "").strip()
        if not node_id:
            continue
        root = next(
            (a for a in (node, *node.iterancestors()) if a.get(XSI_TYPE) == "C_ARCHETYPE_ROOT"),
            None,
        )
        catalogued = (
            set()
            if root is None
            else {term.get("code") for term in root.findall(f"{_O}term_definitions")}
        )
        if node_id not in catalogued:
            missing.append(node_id)
    return missing


# --- the schema itself ------------------------------------------------------------


def test_the_schema_set_is_the_pinned_upstream_release() -> None:
    on_disk = sorted(p.name for p in XSD_DIR.iterdir())
    assert on_disk == sorted(XSD_PINS), "a schema file was added or removed without a pin"
    for name, pinned in XSD_PINS.items():
        digest = hashlib.sha256((XSD_DIR / name).read_bytes()).hexdigest()
        assert digest == pinned, f"{name} is not the Release-1.0.2 bytes"
    assert (XSD_DIR / "LICENSE").read_text(encoding="utf-8").lstrip().startswith("Apache License")


def test_the_schema_makes_occurrences_and_node_id_mandatory_on_c_object() -> None:
    """Read from the vendored XSD, not from memory: INT-032's evidence said the
    opposite, and that is the claim this issue corrects."""
    archetype_xsd = etree.parse(str(XSD_DIR / "Archetype.xsd"))
    xs = {"xs": "http://www.w3.org/2001/XMLSchema"}
    sequence = archetype_xsd.xpath(
        "//xs:complexType[@name='C_OBJECT']//xs:sequence/xs:element", namespaces=xs
    )
    declared = {element.get("name"): element.get("minOccurs", "1") for element in sequence}
    assert declared == {"rm_type_name": "1", "occurrences": "1", "node_id": "1"}


# --- the committed template -------------------------------------------------------


def test_the_committed_template_validates_against_the_opt_14_schema(
    schema: etree.XMLSchema, tree: etree._ElementTree
) -> None:
    valid = schema.validate(tree)
    errors = [f"line {e.line}: {e.message}" for e in schema.error_log]
    assert valid, "the committed OPT is not Template.xsd-valid:\n" + "\n".join(errors)


def test_every_c_object_carries_occurrences_and_a_node_id(tree: etree._ElementTree) -> None:
    nodes = _c_objects(tree)
    assert len(nodes) == 1 + len(CONTENT_ROOTS)
    for node in nodes:
        rm_type = node.findtext(f"{_O}rm_type_name")
        assert node.find(f"{_O}occurrences") is not None, f"{rm_type} has no <occurrences>"
        assert node.find(f"{_O}node_id") is not None, f"{rm_type} has no <node_id>"


def test_the_composition_root_occurs_exactly_once(tree: etree._ElementTree) -> None:
    assert _interval(_definition(tree).find(f"{_O}occurrences")) == {
        "lower_included": "true",
        "upper_included": "true",
        "lower_unbounded": "false",
        "upper_unbounded": "false",
        "lower": "1",
        "upper": "1",
    }


def test_each_content_root_may_occur_zero_or_more_times(tree: etree._ElementTree) -> None:
    children = _content(tree).findall(f"{_O}children")
    assert [
        (c.findtext(f"{_O}archetype_id/{_O}value"), c.findtext(f"{_O}rm_type_name"))
        for c in children
    ] == list(CONTENT_ROOTS)
    for child in children:
        # openEHR Interval: upper_unbounded implies upper_included is absent.
        assert _interval(child.find(f"{_O}occurrences")) == {
            "lower_included": "true",
            "upper_included": None,
            "lower_unbounded": "false",
            "upper_unbounded": "true",
            "lower": "0",
            "upper": None,
        }


def test_the_content_attribute_is_the_rm_list(tree: etree._ElementTree) -> None:
    content = _content(tree)
    assert content.get(XSI_TYPE) == "C_MULTIPLE_ATTRIBUTE"
    assert _interval(content.find(f"{_O}existence")) == {
        "lower_included": "true",
        "upper_included": "true",
        "lower_unbounded": "false",
        "upper_unbounded": "false",
        "lower": "0",
        "upper": "1",
    }
    cardinality = content.find(f"{_O}cardinality")
    assert cardinality is not None
    assert cardinality.findtext(f"{_O}is_ordered") == "true"
    assert cardinality.findtext(f"{_O}is_unique") == "false"
    assert _interval(cardinality.find(f"{_O}interval")) == {
        "lower_included": "true",
        "upper_included": None,
        "lower_unbounded": "false",
        "upper_unbounded": "true",
        "lower": "0",
        "upper": None,
    }


def test_no_node_id_names_a_term_the_template_does_not_carry(
    tree: etree._ElementTree,
) -> None:
    assert _uncatalogued_node_ids(tree) == []
    # …and none is invented anywhere in the file, comments included.
    assert re.search(r"\bat\d{4}\b", COMMITTED_OPT.read_text(encoding="utf-8")) is None


def test_the_binding_walker_still_reads_the_same_nine_roots() -> None:
    """The constraints moved; the roots and their RM types did not."""
    template = load_opt(COMMITTED_OPT, expected_sha256=OPT_SHA256)
    assert template.roots == dict(CONTENT_ROOTS)


# --- near-miss negative controls --------------------------------------------------


def test_the_schema_rejects_a_content_root_without_occurrences(
    schema: etree.XMLSchema, tree: etree._ElementTree
) -> None:
    """The INT-032 defect, re-introduced on one node of the committed bytes: the
    schema — not this module's own assertions — is what refuses it."""
    mutated = copy.deepcopy(tree)
    first = _content(mutated).find(f"{_O}children")
    assert first is not None
    occurrences = first.find(f"{_O}occurrences")
    assert occurrences is not None
    first.remove(occurrences)
    assert not schema.validate(mutated)
    assert any("node_id" in e.message or "occurrences" in e.message for e in schema.error_log)


def test_the_schema_rejects_a_multiple_attribute_without_cardinality(
    schema: etree.XMLSchema, tree: etree._ElementTree
) -> None:
    mutated = copy.deepcopy(tree)
    content = _content(mutated)
    cardinality = content.find(f"{_O}cardinality")
    assert cardinality is not None
    content.remove(cardinality)
    assert not schema.validate(mutated)
    assert any("cardinality" in e.message for e in schema.error_log)


def test_the_schema_admits_an_uncatalogued_node_id_so_the_catalogue_guard_is_needed(
    schema: etree.XMLSchema, tree: etree._ElementTree
) -> None:
    """``node_id`` is ``xs:string``: the schema accepts any code, including the
    archetype root code with no terminology behind it. EHRbase 2.35.1 would not
    (``OPTParser.buildNode`` looks the code up and dereferences the miss), so
    the catalogue guard above carries a check the XSD cannot."""
    root_code = f"at{0:04d}"
    mutated = copy.deepcopy(tree)
    first = _content(mutated).find(f"{_O}children")
    assert first is not None
    node_id = first.find(f"{_O}node_id")
    assert node_id is not None
    node_id.text = root_code
    assert schema.validate(mutated), "the schema was expected to admit this"
    assert _uncatalogued_node_ids(mutated) == [root_code]

    # The guard is a catalogue check, not a ban: once the archetype's own
    # terminology travels with the root (HB-C12), the same code passes. The
    # term text below is a synthetic marker, not an archetype term.
    term = etree.SubElement(first, f"{_O}term_definitions", code=root_code)
    etree.SubElement(term, f"{_O}items", id="text").text = "synthetic"
    assert schema.validate(mutated), [e.message for e in schema.error_log]
    assert _uncatalogued_node_ids(mutated) == []
