"""INT-215 — KVKK Board decision 2018/10 (special-category adequate measures),
mapped measure by measure to a control and a signal, exported as an auditor packet.

Acceptance, verbatim (docs/backlog/issues.yaml INT-215): *"each 2018/10 measure
mapped to a control and a live signal; export produces the auditor packet"*.
`legal: 2018-10`; `sec_row: compliance-evidence`.

What this file pins, in the order an auditor would ask:

1. **The requirement text is the Board's, not ours.** The mapping quotes each
   measure verbatim from a snapshot committed beside it, bound by sha256 to the
   bytes retrieved from the Kurum's own publication, alongside the Resmî Gazete
   PDF (07.03.2018, sayı 30353) it was checked against. A paraphrase fails.
2. **Nothing in the decision is skipped.** The measure ids are parsed out of
   the snapshot, not listed by hand, and the mapping must cover exactly them.
3. **Every reference resolves.** Each control path exists; each test id names
   a real test function; each signal is a catalogued metric (with the status
   the catalogue gives it) or a registered probe.
4. **Every gap names an owner and the one question they must answer.**
   Organisational measures (training, confidentiality undertakings, premises,
   removable media, paper) are the controller's and are never reported done.
5. **The export produces the packet**: one row per measure with a derived
   status, every control and every gap, bound to the source and sealed with a
   digest, every cell neutralised for a spreadsheet (invariant 47).
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.compliance.adequate_measures import (
    LEGAL_REFS,
    MAPPING_PATH,
    GapKind,
    MappingInvalid,
    MeasuresMapping,
    MeasureStatus,
    build_measures_packet,
    load_measures_mapping,
    main,
    packet_as_dict,
    parse_decision_measures,
    resolve_test_id,
)
from intake_platform.export_safety import FORMULA_LEADS
from intake_platform.legal.claims import scan_file
from intake_platform.slo import load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")

#: Resmî Gazete 07.03.2018, sayı 30353 — the decision's own numbering. Items 1
#: and 6 carry no letters; items 2-5 are lead-ins whose lettered sub-items are
#: the measures. Written out here as the second opinion against the parser.
EXPECTED_IDS = tuple("1 2a 2b 2c 2ç 2d 3a 3b 3c 3ç 3d 3e 4a 4b 5a 5b 5c 5ç 6".split())

#: Measures that bind the controller's people, premises and paper. No software
#: control discharges them, so each must carry an open organisational gap until
#: the owner supplies evidence — a closure here is a human act, visible in a diff.
ORGANISATIONAL = ("1", "2a", "2b", "4a", "4b", "5b", "5ç")


def _document() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / MAPPING_PATH).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _measure_doc(document: dict[str, Any], measure_id: str) -> dict[str, Any]:
    for row in document["measures"]:
        if row["id"] == measure_id:
            assert isinstance(row, dict)
            return row
    raise AssertionError(f"measure {measure_id} absent from the mapping")


def _refused(document: dict[str, Any]) -> tuple[str, ...]:
    with pytest.raises(MappingInvalid) as caught:
        load_measures_mapping(REPO, document=document)
    return caught.value.problems


@pytest.fixture(scope="module")
def mapping() -> MeasuresMapping:
    return load_measures_mapping(REPO)


# --- 1. the source ----------------------------------------------------------


class TestSourceSnapshot:
    def test_the_snapshot_is_bound_to_its_recorded_digest(self, mapping: MeasuresMapping) -> None:
        text = (REPO / mapping.source.text_file).read_bytes()
        assert hashlib.sha256(text).hexdigest() == mapping.source.text_sha256

    def test_the_gazette_pdf_is_committed_and_bound(self, mapping: MeasuresMapping) -> None:
        pdf = (REPO / mapping.source.gazette_pdf_file).read_bytes()
        assert pdf.startswith(b"%PDF-")
        assert hashlib.sha256(pdf).hexdigest() == mapping.source.gazette_pdf_sha256

    def test_the_source_names_the_gazette_issue_and_the_decision(
        self, mapping: MeasuresMapping
    ) -> None:
        source = mapping.source
        assert source.board_decision == "2018/10"
        assert source.decision_date == "2018-01-31"
        assert source.gazette_date == "2018-03-07"
        assert source.gazette_number == "30353"
        assert source.gazette_url.startswith("https://www.resmigazete.gov.tr/")
        assert source.text_url.startswith("https://www.kvkk.gov.tr/")

    def test_a_drifted_snapshot_digest_is_refused(self) -> None:
        document = _document()
        document["decision"]["text_sha256"] = "0" * 64
        problems = _refused(document)
        assert any("text_sha256" in problem for problem in problems)

    def test_a_drifted_gazette_digest_is_refused(self) -> None:
        document = _document()
        document["decision"]["gazette_pdf_sha256"] = "f" * 64
        assert any("gazette_pdf_sha256" in problem for problem in _refused(document))


# --- 2. coverage --------------------------------------------------------------


class TestCoverage:
    def test_the_parser_finds_exactly_the_decisions_nineteen_measures(
        self, mapping: MeasuresMapping
    ) -> None:
        text = (REPO / mapping.source.text_file).read_text(encoding="utf-8")
        parsed = parse_decision_measures(text)
        assert tuple(measure.id for measure in parsed) == EXPECTED_IDS

    def test_every_measure_in_the_decision_is_mapped_in_order(
        self, mapping: MeasuresMapping
    ) -> None:
        assert tuple(measure.id for measure in mapping.measures) == EXPECTED_IDS

    def test_every_quote_is_the_snapshot_text_verbatim(self, mapping: MeasuresMapping) -> None:
        text = (REPO / mapping.source.text_file).read_text(encoding="utf-8")
        by_id = {measure.id: measure for measure in parse_decision_measures(text)}
        for measure in mapping.measures:
            assert measure.quote == by_id[measure.id].text
            assert measure.lead_in == by_id[measure.id].lead_in

    def test_a_lettered_measure_carries_its_items_lead_in(self, mapping: MeasuresMapping) -> None:
        by_id = {measure.id: measure for measure in mapping.measures}
        assert by_id["1"].lead_in is None
        assert by_id["3e"].lead_in is not None
        assert by_id["3e"].lead_in.startswith("3- ")

    def test_a_mapping_that_drops_a_measure_is_refused(self) -> None:
        document = _document()
        document["measures"] = [row for row in document["measures"] if row["id"] != "3e"]
        assert any("3e" in problem for problem in _refused(document))

    def test_a_paraphrased_quote_is_refused(self) -> None:
        document = _document()
        row = _measure_doc(document, "3a")
        row["quote"] = "a) Veriler şifreli saklanır,"
        assert any("3a" in problem and "quote" in problem for problem in _refused(document))

    def test_a_measure_the_decision_does_not_contain_is_refused(self) -> None:
        document = _document()
        invented = copy.deepcopy(_measure_doc(document, "6"))
        invented["id"] = "7"
        document["measures"].append(invented)
        assert any("7" in problem for problem in _refused(document))


# --- 3. references resolve ------------------------------------------------------


def _independent_test_lookup(node_id: str) -> bool:
    """A second opinion on resolve_test_id, written separately on purpose."""
    path, _, rest = node_id.partition("::")
    file = REPO / path
    if not file.is_file() or not rest:
        return False
    tree = ast.parse(file.read_text(encoding="utf-8"))
    parts = rest.split("::")
    scope: list[ast.stmt] = tree.body
    for name in parts[:-1]:
        classes = [n for n in scope if isinstance(n, ast.ClassDef) and n.name == name]
        if not classes:
            return False
        scope = classes[0].body
    return any(
        isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == parts[-1] for n in scope
    )


class TestReferencesResolve:
    def test_every_control_path_exists_inside_the_repository(
        self, mapping: MeasuresMapping
    ) -> None:
        for measure in mapping.measures:
            for control in measure.controls:
                assert control.paths, f"{measure.id}/{control.id} names no path"
                for path in control.paths:
                    resolved = (REPO / path).resolve()
                    assert resolved.is_relative_to(REPO)
                    assert resolved.exists(), f"{measure.id}/{control.id}: {path}"

    def test_every_control_test_id_names_a_real_test(self, mapping: MeasuresMapping) -> None:
        for measure in mapping.measures:
            for control in measure.controls:
                assert control.tests, f"{measure.id}/{control.id} names no test"
                for node_id in control.tests:
                    assert node_id.startswith("tests/")
                    assert _independent_test_lookup(node_id), f"{measure.id}: {node_id}"
                    assert resolve_test_id(REPO, node_id)

    def test_every_metric_signal_is_catalogued_with_the_status_it_declares(
        self, mapping: MeasuresMapping
    ) -> None:
        catalog = {
            metric.name: metric.status
            for metric in load_metrics_catalog(
                REPO / "observability" / "metrics_catalog.yaml"
            ).metrics
        }
        for measure in mapping.measures:
            for control in measure.controls:
                for signal in control.signals:
                    if signal.kind == "metric":
                        assert catalog[signal.ref] == signal.status, f"{measure.id}: {signal.ref}"

    def test_every_probe_signal_is_a_registered_component_probe(
        self, mapping: MeasuresMapping
    ) -> None:
        registry = yaml.safe_load((REPO / "observability" / "registry.yaml").read_text("utf-8"))
        probed = {row["component"] for row in registry["components"] if row.get("probe")}
        for measure in mapping.measures:
            for control in measure.controls:
                for signal in control.signals:
                    if signal.kind == "probe":
                        assert signal.ref in probed
                        assert signal.status == "registered"

    def test_a_test_id_that_does_not_resolve_is_refused(self) -> None:
        document = _document()
        row = _measure_doc(document, "3a")
        row["controls"][0]["tests"].append(
            "tests/security/test_envelope_encryption.py::test_this_test_does_not_exist"
        )
        assert any("does not resolve" in problem for problem in _refused(document))

    def test_a_test_id_in_the_wrong_class_is_refused(self) -> None:
        assert resolve_test_id(
            REPO,
            "tests/admin/test_rbac_matrix.py::TestRoleRegistry::test_registry_is_exactly_the_spec_table",
        )
        assert not resolve_test_id(
            REPO,
            "tests/admin/test_rbac_matrix.py::TestFailClosed::test_registry_is_exactly_the_spec_table",
        )

    def test_a_path_that_escapes_the_repository_is_refused(self) -> None:
        document = _document()
        _measure_doc(document, "3a")["controls"][0]["paths"].append("../outside.py")
        assert any("../outside.py" in problem for problem in _refused(document))
        assert not resolve_test_id(REPO, "../tests/legal/test_2018_10_mapping.py::TestCoverage")

    def test_a_planned_metric_declared_live_is_refused(self) -> None:
        document = _document()
        control = _measure_doc(document, "3a")["controls"][0]
        control["signals"] = [{"metric": "sec_vulns_open", "status": "live"}]
        assert any("sec_vulns_open" in problem for problem in _refused(document))

    def test_an_uncatalogued_metric_is_refused(self) -> None:
        document = _document()
        control = _measure_doc(document, "3a")["controls"][0]
        control["signals"] = [{"metric": "envelope_encryption_ok", "status": "live"}]
        assert any("envelope_encryption_ok" in problem for problem in _refused(document))

    def test_an_unregistered_probe_is_refused(self) -> None:
        document = _document()
        control = _measure_doc(document, "3b")["controls"][0]
        control["signals"] = [{"probe": "vault-that-does-not-exist", "status": "registered"}]
        assert any("vault-that-does-not-exist" in problem for problem in _refused(document))


# --- 4. gaps name owners ----------------------------------------------------------


class TestGapsNameOwners:
    def test_every_gap_names_a_declared_owner_and_asks_one_question(
        self, mapping: MeasuresMapping
    ) -> None:
        assert mapping.owners, "the owner vocabulary is empty"
        gaps = [gap for measure in mapping.measures for gap in measure.gaps]
        assert gaps, "a mapping with no gap at all would be a claim of completeness"
        for gap in gaps:
            assert gap.owner in mapping.owners, gap.id
            assert mapping.owners[gap.owner].strip()
            assert gap.ask.strip().endswith("?"), gap.id
            assert gap.ask.count("?") == 1, gap.id

    def test_a_gap_without_an_owner_is_refused(self) -> None:
        document = _document()
        del _measure_doc(document, "2a")["gaps"][0]["owner"]
        assert any("owner" in problem for problem in _refused(document))

    def test_a_gap_naming_an_undeclared_owner_is_refused(self) -> None:
        document = _document()
        _measure_doc(document, "2a")["gaps"][0]["owner"] = "someone"
        assert any("someone" in problem for problem in _refused(document))

    def test_every_blocker_and_tracking_reference_exists(self, mapping: MeasuresMapping) -> None:
        blockers = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
        issues = {
            row["id"]
            for row in yaml.safe_load((REPO / "docs/backlog/issues.yaml").read_text("utf-8"))
        }
        for measure in mapping.measures:
            for gap in measure.gaps:
                if gap.human_blocker is not None:
                    assert f"**{gap.human_blocker}**" in blockers, gap.human_blocker
                for issue in gap.tracking:
                    assert issue in issues, issue

    def test_an_invented_blocker_id_is_refused(self) -> None:
        document = _document()
        _measure_doc(document, "2a")["gaps"][0]["human_blocker"] = "HB-Z99"
        assert any("HB-Z99" in problem for problem in _refused(document))

    def test_organisational_measures_are_never_reported_done(
        self, mapping: MeasuresMapping
    ) -> None:
        by_id = {measure.id: measure for measure in mapping.measures}
        for measure_id in ORGANISATIONAL:
            measure = by_id[measure_id]
            assert measure.status is not MeasureStatus.IMPLEMENTED
            assert any(gap.kind is GapKind.ORGANISATIONAL for gap in measure.gaps), measure_id

    def test_a_measure_with_no_control_and_no_gap_is_refused(self) -> None:
        document = _document()
        row = _measure_doc(document, "2a")
        row["gaps"] = []
        assert any("2a" in problem for problem in _refused(document))

    def test_a_control_with_no_live_signal_must_own_the_missing_signal(self) -> None:
        # 3a's encryption controls have no catalogued signal; the mapping says
        # so as a `signal` gap. Removing that gap must be refused, not accepted
        # as a silent "done".
        document = _document()
        row = _measure_doc(document, "3a")
        row["gaps"] = [gap for gap in row["gaps"] if gap["kind"] != "signal"]
        assert any("3a" in problem and "signal" in problem for problem in _refused(document))


# --- 5. the auditor packet ------------------------------------------------------------


class TestAuditorPacket:
    GENERATED_AT = "2026-09-26T12:00:00+00:00"

    def test_the_packet_carries_the_legal_refs_and_every_section(
        self, mapping: MeasuresMapping
    ) -> None:
        packet = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        assert packet.legal_refs == LEGAL_REFS == ("KVKK-12", "2018-10")
        assert [section.title for section in packet.sections] == [
            "decision_source",
            "measures_2018_10",
            "controls",
            "gaps",
            "summary",
        ]

    def test_one_measure_row_per_measure_with_the_derived_status(
        self, mapping: MeasuresMapping
    ) -> None:
        packet = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        section = next(s for s in packet.sections if s.title == "measures_2018_10")
        assert tuple(row[0] for row in section.rows) == EXPECTED_IDS
        status_column = section.columns.index("status")
        for row, measure in zip(section.rows, mapping.measures, strict=True):
            assert row[status_column] == measure.status.value

    def test_every_control_and_every_gap_is_exported_with_its_owner(
        self, mapping: MeasuresMapping
    ) -> None:
        packet = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        controls = next(s for s in packet.sections if s.title == "controls")
        gaps = next(s for s in packet.sections if s.title == "gaps")
        assert len(controls.rows) == sum(len(m.controls) for m in mapping.measures)
        assert len(gaps.rows) == sum(len(m.gaps) for m in mapping.measures)
        owner_column = gaps.columns.index("owner")
        assert all(row[owner_column] in mapping.owners for row in gaps.rows)
        # an absent blocker reads "none", never a lone "-" the guard would escape
        blocker_column = gaps.columns.index("human_blocker")
        assert {row[blocker_column] for row in gaps.rows} <= {"none", "HB-I8", "HB-I9", "HB-I12"}

    def test_the_summary_counts_agree_with_the_measures(self, mapping: MeasuresMapping) -> None:
        packet = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        summary = dict(next(s for s in packet.sections if s.title == "summary").rows)
        for status in MeasureStatus:
            expected = sum(1 for m in mapping.measures if m.status is status)
            assert summary[f"measures_{status.value}"] == str(expected)
        assert summary["measures_total"] == str(len(EXPECTED_IDS))

    def test_the_source_is_bound_without_a_chain_hash_shape(self, mapping: MeasuresMapping) -> None:
        # A bare 64-hex token is the shape of an audit-chain hash, which the
        # console must never hand back (HB-I12); digests are shown grouped.
        packet = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        source = dict(next(s for s in packet.sections if s.title == "decision_source").rows)
        assert source["text_sha256"].replace(" ", "") == mapping.source.text_sha256
        assert source["gazette_number"] == "30353"
        assert not HEX64.search(json.dumps(packet_as_dict(packet)))

    def test_no_cell_can_evaluate_in_a_spreadsheet(self) -> None:
        document = _document()
        _measure_doc(document, "2a")["gaps"][0]["ask"] = '=HYPERLINK("http://evil","x") who signs?'
        mapping = load_measures_mapping(REPO, document=document)
        packet = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        cells = [cell for section in packet.sections for row in section.rows for cell in row]
        assert not any(cell.startswith(FORMULA_LEADS) for cell in cells)
        assert any(cell.startswith("'=HYPERLINK") for cell in cells)

    def test_the_digest_is_deterministic_and_bound_to_content(
        self, mapping: MeasuresMapping
    ) -> None:
        first = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        again = build_measures_packet(mapping, generated_at=self.GENERATED_AT)
        assert first.digest == again.digest
        assert re.fullmatch(r"[A-Za-z0-9_-]+", first.digest)
        document = _document()
        _measure_doc(document, "2a")["gaps"][0]["ask"] = "Who signs the training record?"
        changed = build_measures_packet(
            load_measures_mapping(REPO, document=document), generated_at=self.GENERATED_AT
        )
        assert changed.digest != first.digest

    def test_the_export_command_prints_the_packet(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--repo", str(REPO)]) == 0
        body = json.loads(capsys.readouterr().out)
        assert body["legal_refs"] == list(LEGAL_REFS)
        assert body["digest"]
        assert {section["title"] for section in body["sections"]} >= {"measures_2018_10", "gaps"}

    def test_the_export_command_refuses_a_broken_mapping(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # an empty directory has no mapping, no snapshot and no catalogue
        assert main(["--repo", str(tmp_path)]) == 2
        assert "refused" in capsys.readouterr().err


# --- 6. honesty ---------------------------------------------------------------------


class TestHonesty:
    def test_the_mapping_makes_no_performance_claim(self) -> None:
        assert scan_file(REPO / MAPPING_PATH, ("performance", "satisfaction")) == ()

    def test_the_current_tally_is_pinned(self, mapping: MeasuresMapping) -> None:
        # A drift detector, not a target: closing a gap moves a count here in
        # the same diff that records the evidence for it.
        tally = {status: 0 for status in MeasureStatus}
        for measure in mapping.measures:
            tally[measure.status] += 1
        assert tally == {
            MeasureStatus.IMPLEMENTED: 0,
            MeasureStatus.PARTIAL: 10,
            MeasureStatus.NOT_IMPLEMENTED: 9,
        }
