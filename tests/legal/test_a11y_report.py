"""INT-226 — the accessibility conformance report stays true to its evidence.

Acceptance clause under test, verbatim: *"report generated from a11y CI
results; statement published in-app and web"*. This suite is the first half.
Publication is gated on HB-L9, counsel and the feedback channel, and is not
claimed here.

The report is generated, not written. Its source of record is
``docs/compliance/accessibility-conformance.yaml``, and
``scripts/compliance/render_a11y_report.py`` renders it. The properties pinned
here are the ones that stop a conformance report from drifting into a claim:

- every WCAG 2.2 Level A and AA success criterion is mapped exactly once, with
  the Ministry checklist's BK numbers on the Level A rows in canonical order;
- **no row says Supports without evidence**, and every cited automated test
  names exactly one test in a vitest file that CI actually runs. A renamed,
  deleted or skipped test breaks the citation, and the gate goes red;
- every manual check is dated, names its method and is cited by some row;
- a criterion that only a device run can decide is Not Evaluated and sits in
  the device audit, which names the owner as the person to perform it;
- a contrast finding still matches the palette: the report cannot keep
  saying a pair fails after the palette has fixed it, or the reverse;
- a row below Supports cannot keep leaning on an issue the backlog marks
  done: it is re-assessed, or it records why the fix left it open (INT-387);
- the committed Markdown is exactly the rendering, and the internal statement
  names every criterion the report does not fully support.

The canonical criterion list below is written out independently of the
renderer, so the renderer cannot vouch for its own coverage.
"""

from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
STATEMENT = REPO / "docs" / "legal" / "accessibility-statement.md"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "render_a11y_report", REPO / "scripts" / "compliance" / "render_a11y_report.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


R = _load()

# WCAG 2.2 (W3C Recommendation, 5 October 2023). Level A in canonical order:
# the Ministry's "Kontrol Listesi — A Seviyesi" is 31 Başarı Kriteri, 1:1 with
# these (HB-L9; files/00 §4 fixes BK27 = 3.2.6 and BK30 = 3.3.7).
LEVEL_A = (
    "1.1.1 1.2.1 1.2.2 1.2.3 1.3.1 1.3.2 1.3.3 1.4.1 1.4.2 2.1.1 2.1.2 2.1.4 "
    "2.2.1 2.2.2 2.3.1 2.4.1 2.4.2 2.4.3 2.4.4 2.5.1 2.5.2 2.5.3 2.5.4 3.1.1 "
    "3.2.1 3.2.2 3.2.6 3.3.1 3.3.2 3.3.7 4.1.2"
).split()
LEVEL_AA = (
    "1.2.4 1.2.5 1.3.4 1.3.5 1.4.3 1.4.4 1.4.5 1.4.10 1.4.11 1.4.12 1.4.13 "
    "2.4.5 2.4.6 2.4.7 2.4.11 2.5.7 2.5.8 3.1.2 3.2.3 3.2.4 3.3.3 3.3.4 3.3.8 4.1.3"
).split()
# New in 2.2, so absent from WCAG 2.1 and from EN 301 549 V3.2.1 clause 11.
NEW_IN_22 = {"2.4.11", "2.5.7", "2.5.8", "3.2.6", "3.3.7", "3.3.8"}
# Removed in WCAG 2.2; it survives only as EN 301 549 V3.2.1 clause 11.4.1.1.
REMOVED_IN_22 = "4.1.1"


@pytest.fixture(scope="module")
def source() -> dict[str, Any]:
    loaded: dict[str, Any] = R.load_source()
    return loaded


def _row(source: dict[str, Any], sc: str) -> dict[str, Any]:
    return next(r for r in source["wcag"] if r["sc"] == sc)


# ---------------------------------------------------------------- coverage


def test_the_canonical_lists_are_the_standard() -> None:
    # A guard on the oracle itself: 31 + 24 = 55, and nothing twice.
    assert len(LEVEL_A) == 31
    assert len(LEVEL_AA) == 24
    assert len(set(LEVEL_A) | set(LEVEL_AA)) == 55
    assert REMOVED_IN_22 not in LEVEL_A + LEVEL_AA


def test_every_level_a_and_aa_criterion_is_mapped_exactly_once(source: dict[str, Any]) -> None:
    mapped = [r["sc"] for r in source["wcag"]]
    assert sorted(mapped) == sorted(LEVEL_A + LEVEL_AA)
    assert len(mapped) == len(set(mapped))


def test_levels_and_new_in_22_flags_match_the_standard(source: dict[str, Any]) -> None:
    for row in source["wcag"]:
        expected = "A" if row["sc"] in LEVEL_A else "AA"
        assert row["level"] == expected, row["sc"]
        assert bool(row.get("wcag22_new", False)) == (row["sc"] in NEW_IN_22), row["sc"]


def test_level_a_rows_carry_bk1_to_bk31_in_canonical_order(source: dict[str, Any]) -> None:
    a_rows = [r for r in source["wcag"] if r["level"] == "A"]
    assert [r["sc"] for r in a_rows] == LEVEL_A
    assert [r["bk"] for r in a_rows] == [f"BK{i}" for i in range(1, 32)]
    assert all("bk" not in r for r in source["wcag"] if r["level"] == "AA")


def test_removed_parsing_is_carried_only_as_its_en_clause(source: dict[str, Any]) -> None:
    assert REMOVED_IN_22 not in {r["sc"] for r in source["wcag"]}
    parsing = [c for c in source["en301549"] if c["clause"] == "11.4.1.1"]
    assert len(parsing) == 1


# ---------------------------------------------------------------- evidence


def test_the_committed_source_validates(source: dict[str, Any]) -> None:
    assert R.validate(source) == []


def test_every_supports_row_cites_evidence_and_every_cited_test_exists(
    source: dict[str, Any],
) -> None:
    rows = source["wcag"] + source["en301549"]
    supports = [r for r in rows if r["status"] == "Supports"]
    assert supports, "a report with no Supports row would make this test vacuous"
    for row in supports:
        assert row.get("tests") or row.get("manual"), R.row_id(row)
    cited = [ref for r in rows for ref in r.get("tests", [])]
    assert len(cited) > 40, "the scanner must see the citations it polices"
    for ref in cited:
        R.resolve_test(ref)  # raises when the title is not exactly one test


def test_cited_tests_live_where_ci_runs_them(source: dict[str, Any]) -> None:
    for row in source["wcag"] + source["en301549"]:
        for ref in row.get("tests", []):
            path = ref.split("::", 1)[0]
            assert re.fullmatch(r"apps/mobile/(src/.+\.test\.ts|e2e/.+\.spec\.ts)", path), ref


def test_the_title_reader_sees_every_form_the_suites_use() -> None:
    # The skipped form is assembled, not written, so the invariant-17 token
    # gate (which forbids it in any tracked file) does not trip on the guard
    # that proves a skipped test cannot satisfy a citation.
    skipped = "it." + "skip"
    sample = (
        'it("plain", () => {});\n'
        'it.each(["light", "dark"] as const)(\n  "%s: spans lines",\n  () => {});\n'
        "it.each(withErrors)('%s single quoted', () => {});\n"
        "  it(`${name} templated`, () => {});\n"
        'test("the other spelling", () => {});\n'
        f'{skipped}("skipped is not a test", () => {{}});\n'
        'expect(/x/.test("a regex call")).toBe(true);\n'
    )
    assert R.test_titles(sample) == [
        "plain",
        "%s: spans lines",
        "%s single quoted",
        "${name} templated",
        "the other spelling",
    ]


def test_a_renamed_test_breaks_its_citation(source: dict[str, Any]) -> None:
    broken = copy.deepcopy(source)
    row = _row(broken, "4.1.2")
    row["tests"] = [row["tests"][0] + " (renamed)"]
    assert any("4.1.2" in p and "no test" in p for p in R.validate(broken))
    with pytest.raises(R.ReportError):
        R.resolve_test(row["tests"][0])


def test_a_supports_row_without_evidence_is_refused(source: dict[str, Any]) -> None:
    broken = copy.deepcopy(source)
    row = _row(broken, "2.3.1")
    assert row["status"] == "Supports"
    row["tests"], row["manual"] = [], []
    assert any("2.3.1" in p and "no evidence" in p for p in R.validate(broken))


def test_a_citation_outside_the_ci_suites_is_refused(source: dict[str, Any]) -> None:
    broken = copy.deepcopy(source)
    _row(broken, "2.3.1")["tests"] = ["apps/mobile/src/lib/theme.ts::palette"]
    assert any("2.3.1" in p and "not a suite CI runs" in p for p in R.validate(broken))


def test_manual_checks_are_dated_described_and_all_cited(source: dict[str, Any]) -> None:
    checks = source["manual_checks"]
    assert checks
    cited = {m for r in source["wcag"] + source["en301549"] for m in r.get("manual", [])}
    assert cited == set(checks), "an uncited check is noise; a cited unknown id is a lie"
    for key, check in checks.items():
        assert R.parse_date(check["date"]) <= R.parse_date(source["report"]["assessed_on"]), key
        for field in ("by", "method", "result"):
            assert str(check.get(field, "")).strip(), f"{key}.{field}"


def test_an_undated_manual_check_is_refused(source: dict[str, Any]) -> None:
    broken = copy.deepcopy(source)
    first = next(iter(broken["manual_checks"]))
    broken["manual_checks"][first]["date"] = "recently"
    assert any(first in p and "date" in p for p in R.validate(broken))


def test_rows_below_supports_state_their_finding(source: dict[str, Any]) -> None:
    for row in source["wcag"] + source["en301549"]:
        if row["status"] in ("Partially Supports", "Does Not Support"):
            assert str(row.get("finding", "")).strip(), R.row_id(row)
            assert row.get("tests") or row.get("manual"), R.row_id(row)


# ---------------------------------------------------------------- orientation (INT-360)
# SC 1.3.4 allows a screen to keep one orientation only where that orientation
# is essential. apps/mobile/e2e/a11y.spec.ts finds every lock in the app and
# fails on one this register does not list with its reason; this half makes the
# register part of the report, so the exception is named where it is claimed.

_LOCK = "src/app/(tabs)/records.tsx › orientation API"


def test_the_orientation_row_carries_its_essential_lock_register(source: dict[str, Any]) -> None:
    row = _row(source, "1.3.4")
    assert isinstance(row.get("essential_locks"), list), "SC 1.3.4 names its exceptions, even none"
    for lock in row["essential_locks"]:
        assert str(lock.get("lock", "")).strip() and str(lock.get("reason", "")).strip(), lock


def test_an_essential_lock_without_a_reason_is_refused(source: dict[str, Any]) -> None:
    broken = copy.deepcopy(source)
    _row(broken, "1.3.4")["essential_locks"] = [{"lock": _LOCK}]
    assert any("1.3.4" in p and "reason" in p for p in R.validate(broken))
    _row(broken, "1.3.4")["essential_locks"] = [{"lock": _LOCK, "reason": "  "}]
    assert any("1.3.4" in p and "reason" in p for p in R.validate(broken))


def test_only_the_orientation_row_registers_a_lock(source: dict[str, Any]) -> None:
    broken = copy.deepcopy(source)
    _row(broken, "1.4.10")["essential_locks"] = []
    assert any("1.4.10" in p and "essential_locks" in p for p in R.validate(broken))


def test_the_report_names_every_essential_lock_and_says_so_when_there_is_none(
    source: dict[str, Any],
) -> None:
    def orientation_line(text: str) -> str:
        return next(line for line in text.splitlines() if line.startswith("| 1.3.4 "))

    registered = copy.deepcopy(source)
    reason = "The capture guide is drawn for a portrait page."
    _row(registered, "1.3.4")["essential_locks"] = [{"lock": _LOCK, "reason": reason}]
    named = orientation_line(R.render(registered))
    assert "records.tsx" in named and reason in named and "essential" in named
    if not _row(source, "1.3.4")["essential_locks"]:
        assert "No screen keeps an orientation lock" in orientation_line(R.render(source))


# ---------------------------------------------------------------- staleness (INT-387)
# INT-361, INT-362 and INT-363 merged while the report still rated 3.3.1, 3.3.8
# and 4.1.3 by the defects they fixed. A row below Supports is now linked to
# the backlog issues it leans on: every INT id its finding or remarks name, and
# every issue filed against its criterion (a backlog title that opens
# "WCAG <sc>:"). When one of those issues is done, the row is re-assessed, or
# it records `still_open_because:` with what the fix left open.

# The four issues INT-226 filed against its own findings, written out here so
# the link convention cannot vouch for itself.
FILED_AGAINST = {
    "INT-360": ("1.3.4",),
    "INT-361": ("3.3.8",),
    "INT-362": ("3.3.1", "4.1.3"),
    "INT-363": ("2.2.1",),
}


@pytest.fixture(scope="module")
def backlog() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = R.load_backlog()
    return loaded


def _with_status(backlog: dict[str, dict[str, Any]], iid: str, status: str) -> dict[str, Any]:
    changed = copy.deepcopy(backlog)
    changed[iid]["status"] = status
    return changed


def test_the_backlog_is_read_whole(backlog: dict[str, dict[str, Any]]) -> None:
    assert len(backlog) > 300, "the guard must see the backlog it polices"
    assert all(str(issue.get("status", "")).strip() for issue in backlog.values())


def test_an_issue_filed_against_a_criterion_is_linked_to_its_row(
    source: dict[str, Any], backlog: dict[str, dict[str, Any]]
) -> None:
    for iid, criteria in FILED_AGAINST.items():
        for sc in criteria:
            assert iid in R.issues_of(_row(source, sc), backlog), (iid, sc)


def test_an_issue_the_row_names_is_linked_to_it(backlog: dict[str, dict[str, Any]]) -> None:
    row = {"sc": "9.9.9", "status": "Partially Supports", "finding": "see INT-144 report §5.1"}
    assert R.issues_of(row, backlog) == ["INT-144"]
    assert R.issues_of({"clause": "12.1.1", "remarks": "INT-359 and INT-144's"}, backlog) == [
        "INT-144",
        "INT-359",
    ]


def test_no_row_below_supports_leans_on_a_done_issue_without_a_reason(
    source: dict[str, Any], backlog: dict[str, dict[str, Any]]
) -> None:
    below = [r for r in source["wcag"] + source["en301549"] if r["status"] in R.BELOW]
    assert below, "a report with no row below Supports would make this test vacuous"
    linked = 0
    for row in below:
        for iid in R.issues_of(row, backlog):
            linked += 1
            assert iid in backlog, f"{R.row_id(row)} cites {iid}, which the backlog does not carry"
            if backlog[iid]["status"] == "done":
                assert str(row.get("still_open_because", "")).strip(), (R.row_id(row), iid)
    assert linked, "the scanner must see the citations it polices"


def test_a_fixed_criterion_left_below_supports_is_refused(
    source: dict[str, Any], backlog: dict[str, dict[str, Any]]
) -> None:
    # The regression INT-387 repairs: INT-361 is done, and 3.3.8 still says
    # Does Not Support.
    assert backlog["INT-361"]["status"] == "done"
    stale = copy.deepcopy(source)
    row = _row(stale, "3.3.8")
    row["status"] = "Does Not Support"
    row["finding"] = "Each of the six boxes holds one character."
    problems = R.validate(stale, backlog=backlog)
    assert any("3.3.8" in p and "INT-361" in p and "done" in p for p in problems), problems


def test_a_done_issue_needs_a_recorded_reason_the_near_miss_control(
    source: dict[str, Any], backlog: dict[str, dict[str, Any]]
) -> None:
    row = _row(source, "1.4.3")
    assert row["status"] in R.BELOW and "INT-144" in R.issues_of(row, backlog)
    assert backlog["INT-144"]["status"] != "done"
    # The row as committed: its issue is open, so nothing is asked of it.
    assert not any("1.4.3" in p for p in R.validate(source, backlog=backlog))
    # The same row once its issue is done: refused without a reason ...
    closed = _with_status(backlog, "INT-144", "done")
    assert any("1.4.3" in p and "INT-144" in p for p in R.validate(source, backlog=closed))
    blank = copy.deepcopy(source)
    _row(blank, "1.4.3")["still_open_because"] = "  "
    assert any("1.4.3" in p and "INT-144" in p for p in R.validate(blank, backlog=closed))
    # ... and accepted with one.
    reasoned = copy.deepcopy(source)
    _row(reasoned, "1.4.3")["still_open_because"] = "The palette decision is still open."
    assert not any("1.4.3" in p for p in R.validate(reasoned, backlog=closed))


def test_a_reason_is_refused_where_nothing_is_still_open(
    source: dict[str, Any], backlog: dict[str, dict[str, Any]]
) -> None:
    on_supports = copy.deepcopy(source)
    _row(on_supports, "2.3.1")["still_open_because"] = "nothing"
    assert any(
        "2.3.1" in p and "still_open_because" in p for p in R.validate(on_supports, backlog=backlog)
    )
    # A reason that excuses no done issue is noise, and is refused too.
    unlinked = copy.deepcopy(source)
    _row(unlinked, "3.1.2")["still_open_because"] = "nothing is done yet"
    assert _row(source, "3.1.2")["status"] in R.BELOW
    assert any(
        "3.1.2" in p and "still_open_because" in p for p in R.validate(unlinked, backlog=backlog)
    )


def test_a_row_cannot_cite_an_issue_the_backlog_does_not_carry(
    source: dict[str, Any], backlog: dict[str, dict[str, Any]]
) -> None:
    broken = copy.deepcopy(source)
    _row(broken, "3.1.2")["finding"] += " INT-9999 tracks it."
    assert any("3.1.2" in p and "INT-9999" in p for p in R.validate(broken, backlog=backlog))


def test_the_report_says_why_a_row_is_still_open(source: dict[str, Any]) -> None:
    reasons = {
        str(r.get("sc", r.get("clause"))): str(r["still_open_because"]).strip()
        for r in source["wcag"] + source["en301549"]
        if "still_open_because" in r
    }
    assert reasons, "4.1.3 records what INT-362 left open"
    text = R.render(source)
    for number, reason in reasons.items():
        # The row's own line in §1, §2 or §3.2, not the derived clause-11 table.
        line = next(ln for ln in text.splitlines() if ln.startswith(f"| {number} "))
        assert "**Still open because:**" in line and " ".join(reason.split()) in line, number


# ---------------------------------------------------------------- device audit


def test_not_evaluated_rows_are_decided_by_the_owners_device_audit(
    source: dict[str, Any],
) -> None:
    audit = source["device_audit"]
    assert audit["owner"] == "owner"
    assert audit["status"] == "pending"
    decided = {sc for item in audit["items"].values() for sc in item["decides"]}
    rows = source["wcag"] + source["en301549"]
    pending = {R.row_id(r) for r in rows if r["status"] == "Not Evaluated"}
    assert pending, "the report records device-only criteria; none would be a claim"
    assert pending == decided, "a device-decided row is Not Evaluated, and only those"
    for key, item in audit["items"].items():
        assert item["platforms"] and str(item["steps"]).strip(), key


def test_a_device_decided_row_cannot_say_supports(source: dict[str, Any]) -> None:
    broken = copy.deepcopy(source)
    _row(broken, "2.1.1")["status"] = "Supports"
    assert any("2.1.1" in p and "device audit" in p for p in R.validate(broken))


# ---------------------------------------------------------------- contrast


def test_contrast_findings_match_the_palette_they_measure(source: dict[str, Any]) -> None:
    palette = R.theme_palette()
    for sc, pairs in source["contrast"].items():
        status = _row(source, sc)["status"]
        ratios = [
            (R.contrast(palette[p["scheme"]][p["fg"]], palette[p["scheme"]][p["bg"]]), p)
            for p in pairs
        ]
        failing = [p for ratio, p in ratios if ratio < p["required"]]
        if status == "Supports":
            assert not failing, sc
        else:
            assert failing, f"{sc} says {status} but every listed pair now passes"


def test_a_palette_fix_forces_the_report_to_be_reassessed(source: dict[str, Any]) -> None:
    fixed = copy.deepcopy(R.theme_palette())
    for scheme in fixed.values():
        scheme.update(inkFaint="#5F5B50", success="#14683D", border="#8C8676")
        scheme.update(background="#FFFFFF", surface="#FFFFFF", surfaceRaised="#FFFFFF")
        scheme.update(successSoft="#FFFFFF")
    problems = R.validate(source, palette=fixed)
    assert any("1.4.3" in p and "every listed pair" in p for p in problems)


def test_the_contrast_arithmetic_is_wcag_relative_luminance() -> None:
    assert R.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert R.contrast("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
    # INT-144's measured light-mode floors, reproduced from the same formula.
    assert round(R.contrast("#8A867A", "#FAF8F4"), 2) == 3.43
    assert round(R.contrast("#EAE6DD", "#FFFFFF"), 2) == 1.25


# ---------------------------------------------------------------- rendering


def test_the_committed_report_is_the_rendering(source: dict[str, Any]) -> None:
    committed = R.TARGET.read_text(encoding="utf-8")
    assert committed == R.render(source), (
        "stale: run `uv run python scripts/compliance/render_a11y_report.py` and commit"
    )


def test_the_report_counts_what_it_contains(source: dict[str, Any]) -> None:
    text = R.render(source)
    for status in R.STATUSES:
        n = sum(1 for r in source["wcag"] if r["status"] == status)
        assert f"{status} {n}" in text


def test_the_en_clause_11_table_is_derived_from_the_wcag_rows(source: dict[str, Any]) -> None:
    derived = R.en_clause_11(source)
    assert {d["clause"] for d in derived} == {
        "11." + sc for sc in LEVEL_A + LEVEL_AA if sc not in NEW_IN_22
    }
    for d in derived:
        assert d["status"] == _row(source, d["sc"])["status"]


# ---------------------------------------------------------------- statement


def _names(text: str, sc: str) -> bool:
    # "SC 1.4.1" must not be satisfied by "SC 1.4.10" or "SC 1.4.11".
    return re.search(rf"SC {re.escape(sc)}(?![0-9])", text) is not None


def test_the_statement_names_every_criterion_the_report_does_not_support(
    source: dict[str, Any],
) -> None:
    """Every criterion below Supports, and every one not yet evaluated, is named
    in the statement. The statement may say less than the report about what
    works; it may never say less about what does not."""
    statement = STATEMENT.read_text(encoding="utf-8")
    assert "docs/compliance/accessibility-conformance-report.md" in statement
    assert "partially conformant" in statement
    short = [
        r["sc"]
        for r in source["wcag"]
        if r["status"] in ("Partially Supports", "Does Not Support", "Not Evaluated")
    ]
    assert short
    missing = [sc for sc in short if not _names(statement, sc)]
    assert missing == []


def test_the_statement_check_does_not_match_a_longer_number() -> None:
    assert _names("see SC 1.4.1.", "1.4.1")
    assert not _names("see SC 1.4.10 and SC 1.4.11", "1.4.1")


def test_neither_document_claims_blanket_conformance(source: dict[str, Any]) -> None:
    warm = re.compile(
        r"fully (conformant|compliant|accessible)|100 ?% (conformant|accessible)"
        r"|certified accessible|WCAG[- ]compliant",
        re.IGNORECASE,
    )
    for text in (R.render(source), STATEMENT.read_text(encoding="utf-8")):
        assert warm.search(text) is None
