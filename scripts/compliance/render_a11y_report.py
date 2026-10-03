"""Render the accessibility conformance report (INT-226).

Source of record: ``docs/compliance/accessibility-conformance.yaml``. It has one
row per WCAG 2.2 Level A and AA success criterion and one per EN 301 549 V3.2.1
clause assessed beyond them. Each row carries a status and the evidence behind
it. The output is ``docs/compliance/accessibility-conformance-report.md``.

Three parts of the report are generated rather than written:

- Every cited automated test is resolved against the vitest source that CI
  runs (``pnpm -r test``, therefore ``make check-ts``). A citation must name
  exactly one ``it``/``test`` title in that file, so a renamed, deleted or
  skipped test invalidates the row that leaned on it. A red test fails
  check-ts itself. Either way no row can stand on a test that is not there
  and passing.
- Every contrast figure is computed from ``apps/mobile/src/lib/theme.ts`` at
  render time, so a palette change reaches the report or fails the gate.
- The EN 301 549 clause 11.1-11.4 table is derived from the WCAG rows.
- SC 1.3.4's ``essential_locks`` register (INT-360) is named in that row's
  remarks, so a screen that keeps an orientation lock is named, with the
  reason its orientation is essential, where the report claims the criterion.
  ``apps/mobile/e2e/a11y.spec.ts`` fails on a lock in the app that the
  register does not list.

A row below Supports cannot outlive its fix (INT-387). Its issues are every
INT id its finding or remarks name, and every backlog issue filed against its
criterion (a title that opens ``WCAG <sc>:``), read from
``docs/backlog/issues.yaml``. When one of them is ``done``, the row is
re-assessed, or it records ``still_open_because:`` with what the fix left
open, and the report prints that reason in the row.

``--check`` exits 1 when the source is invalid or the committed report is
stale; ``tests/legal/test_a11y_report.py`` runs the same checks under pytest.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "docs" / "compliance" / "accessibility-conformance.yaml"
TARGET = REPO / "docs" / "compliance" / "accessibility-conformance-report.md"
THEME = REPO / "apps" / "mobile" / "src" / "lib" / "theme.ts"
BACKLOG = REPO / "docs" / "backlog" / "issues.yaml"
MOBILE = "apps/mobile/"

# The one criterion whose row carries an exception register (INT-360).
ORIENTATION_SC = "1.3.4"

STATUSES = (
    "Supports",
    "Partially Supports",
    "Does Not Support",
    "Not Applicable",
    "Not Evaluated",
)
BELOW = ("Partially Supports", "Does Not Support")

# The files vitest collects (apps/mobile/vitest.config.ts `include`).
CI_SUITE = re.compile(r"apps/mobile/(src/.+\.test\.ts|e2e/.+\.spec\.ts)")

# `it(` / `test(` / `it.each(...)(`, then the title literal. The lookbehind
# keeps `/re/.test("x")` out. A modified call (`it.<modifier>(`) other than
# `.each` never matches, so a skipped or pending test cannot satisfy a citation.
_TITLE = re.compile(
    r"(?<![.\w$])(?:it|test)"
    r"(?:\.each\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))?"
    r"\(\s*(?P<q>[\"'`])(?P<title>(?:\\.|(?!(?P=q)).)*)(?P=q)",
    re.DOTALL,
)
_HEX = re.compile(r"(\w+):\s*\"(#[0-9A-Fa-f]{6})\"")
# An issue id named in a row's prose, and a backlog title that files an issue
# against one or more criteria ("WCAG 3.3.1 / 4.1.3: …").
_ISSUE = re.compile(r"\bINT-\d{3,}\b")
_FILED_AGAINST = re.compile(r"WCAG (\d+\.\d+\.\d+(?:\s*/\s*\d+\.\d+\.\d+)*):")
REASON = "still_open_because"


class ReportError(Exception):
    """A citation or source value the report cannot stand on."""


# ------------------------------------------------------------------ inputs


def load_source(path: Path = SOURCE) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ReportError(f"{path}: not a mapping")
    return loaded


def load_backlog(path: Path = BACKLOG) -> dict[str, dict[str, Any]]:
    """The backlog's issues by id, for the status of each issue a row leans on."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ReportError(f"{path}: not a list of issues")
    return {str(issue["id"]): issue for issue in loaded}


def row_id(row: dict[str, Any]) -> str:
    return str(row["sc"]) if "sc" in row else f"EN {row['clause']}"


def issues_of(row: dict[str, Any], backlog: dict[str, dict[str, Any]]) -> list[str]:
    """The issues a row leans on: every INT id its finding or remarks name, and
    every backlog issue filed against its criterion (a title opening `WCAG <sc>:`)."""
    prose = f"{row.get('finding', '')} {row.get('remarks', '')}"
    linked = set(_ISSUE.findall(prose))
    sc = row.get("sc")
    if sc is not None:
        for iid, issue in backlog.items():
            filed = _FILED_AGAINST.match(str(issue.get("title", "")))
            if filed and str(sc) in re.split(r"\s*/\s*", filed.group(1)):
                linked.add(iid)
    return sorted(linked)


def parse_date(value: object) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ReportError(f"{value!r} is not an ISO date") from exc


def test_titles(source: str) -> list[str]:
    """The titles of the tests a vitest file declares, in source order."""
    return [m.group("title") for m in _TITLE.finditer(source)]


def resolve_test(ref: str) -> tuple[str, str]:
    """Split ``path::title`` and prove the title names exactly one test."""
    path, sep, title = ref.partition("::")
    if not sep or not title:
        raise ReportError(f"{ref!r}: expected <path>::<test title>")
    if CI_SUITE.fullmatch(path) is None:
        raise ReportError(
            f"{ref!r}: not a suite CI runs (apps/mobile src/**/*.test.ts or e2e/**/*.spec.ts)"
        )
    file = REPO / path
    if not file.is_file():
        raise ReportError(f"{ref!r}: no test file at {path}")
    found = test_titles(file.read_text(encoding="utf-8")).count(title)
    if found == 0:
        raise ReportError(f"{ref!r}: no test with that title in {path}")
    if found > 1:
        raise ReportError(f"{ref!r}: {found} tests share that title in {path}")
    return path, title


def theme_palette(path: Path = THEME) -> dict[str, dict[str, str]]:
    """The light and dark token hexes, read from theme.ts's `palette` literal."""
    text = path.read_text(encoding="utf-8")
    start = text.index("export const palette")
    end = text.index("} as const;", start)
    body = text[start:end]
    dark_at = body.index("dark: {")
    return {
        "light": dict(_HEX.findall(body[:dark_at])),
        "dark": dict(_HEX.findall(body[dark_at:])),
    }


def _channel(v: int) -> float:
    s = v / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    n = int(hex_colour[1:], 16)
    return (
        0.2126 * _channel((n >> 16) & 0xFF)
        + 0.7152 * _channel((n >> 8) & 0xFF)
        + 0.0722 * _channel(n & 0xFF)
    )


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio of two #RRGGBB colours."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _sc_key(sc: str) -> tuple[int, ...]:
    return tuple(int(part) for part in sc.split("."))


def en_clause_11(source: dict[str, Any]) -> list[dict[str, str]]:
    """EN 301 549 V3.2.1 clauses 11.1-11.4, one per WCAG 2.1 A/AA criterion."""
    rows = [r for r in source["wcag"] if not r.get("wcag22_new", False)]
    rows.sort(key=lambda r: _sc_key(str(r["sc"])))
    return [
        {"clause": f"11.{r['sc']}", "sc": str(r["sc"]), "name": r["name"], "status": r["status"]}
        for r in rows
    ]


# ------------------------------------------------------------------ validation


def validate(
    source: dict[str, Any],
    *,
    palette: dict[str, dict[str, str]] | None = None,
    backlog: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Every reason the source cannot be rendered as a truthful report."""
    issues = backlog if backlog is not None else load_backlog()
    problems: list[str] = []
    rows: list[dict[str, Any]] = list(source["wcag"]) + list(source["en301549"])
    checks: dict[str, Any] = source["manual_checks"]
    audit = source["device_audit"]

    assessed = parse_date(source["report"]["assessed_on"])
    for key, check in checks.items():
        try:
            if parse_date(check.get("date")) > assessed:
                problems.append(f"manual check {key}: dated after the assessment")
        except ReportError as exc:
            problems.append(f"manual check {key}: date {exc}")
        for field in ("by", "method", "result"):
            if not str(check.get(field, "")).strip():
                problems.append(f"manual check {key}: no {field}")

    decided: dict[str, str] = {}
    for key, item in audit["items"].items():
        for rid in item["decides"]:
            decided[rid] = key
    known = {row_id(r) for r in rows}
    for key, item in audit["items"].items():
        for rid in list(item["decides"]) + list(item.get("confirms", [])):
            if rid not in known:
                problems.append(f"device audit {key}: names {rid}, which no row carries")

    for row in rows:
        rid = row_id(row)
        status = row.get("status")
        if status not in STATUSES:
            problems.append(f"{rid}: unknown status {status!r}")
            continue
        tests = list(row.get("tests", []))
        manual = list(row.get("manual", []))
        for ref in tests:
            try:
                resolve_test(ref)
            except ReportError as exc:
                problems.append(f"{rid}: cites {exc}")
        for key in manual:
            if key not in checks:
                problems.append(f"{rid}: cites manual check {key}, which is not recorded")
        if status != "Not Evaluated" and not (tests or manual):
            problems.append(f"{rid}: {status} with no evidence")
        if status in BELOW and not str(row.get("finding", "")).strip():
            problems.append(f"{rid}: {status} with no finding")
        if not str(row.get("remarks", "")).strip():
            problems.append(f"{rid}: no remarks")
        if status == "Not Evaluated" and rid not in decided:
            problems.append(f"{rid}: Not Evaluated but no device audit item decides it")
        if status != "Not Evaluated" and rid in decided:
            problems.append(
                f"{rid}: decided by the device audit ({decided[rid]}) but says {status}"
            )
        problems.extend(_lock_problems(row))
        problems.extend(_staleness_problems(row, issues))

    problems.extend(_contrast_problems(source, palette or theme_palette()))
    return problems


def _staleness_problems(row: dict[str, Any], backlog: dict[str, dict[str, Any]]) -> list[str]:
    """A row below Supports is re-assessed once an issue it leans on is done,
    or it records what that fix left open (INT-387)."""
    rid = row_id(row)
    status = row["status"]
    has_reason = REASON in row
    reason = str(row.get(REASON, "")).strip()
    if status not in BELOW:
        if has_reason:
            return [f"{rid}: says {status} but carries {REASON}; only a row below Supports is open"]
        return []
    problems: list[str] = []
    done: list[str] = []
    for iid in issues_of(row, backlog):
        if iid not in backlog:
            problems.append(f"{rid}: cites {iid}, which the backlog does not carry")
        elif backlog[iid].get("status") == "done":
            done.append(iid)
    if done and not reason:
        problems.append(
            f"{rid}: says {status} but {', '.join(done)} is done in the backlog — "
            f"re-assess the row, or record {REASON}"
        )
    elif has_reason and not done:
        problems.append(f"{rid}: {REASON} excuses no done issue this row leans on")
    return problems


def _lock_problems(row: dict[str, Any]) -> list[str]:
    """SC 1.3.4 names every essential orientation lock with its reason, and only it does."""
    rid = row_id(row)
    if "essential_locks" not in row:
        return [f"{rid}: no essential_locks register"] if rid == ORIENTATION_SC else []
    if rid != ORIENTATION_SC:
        return [f"{rid}: essential_locks belongs to SC {ORIENTATION_SC} alone"]
    locks = row["essential_locks"]
    if not isinstance(locks, list):
        return [f"{rid}: essential_locks is not a list"]
    problems: list[str] = []
    for lock in locks:
        if not isinstance(lock, dict) or not str(lock.get("lock", "")).strip():
            problems.append(f"{rid}: an essential_locks entry names no lock")
        elif not str(lock.get("reason", "")).strip():
            problems.append(f"{rid}: essential lock {lock['lock']} states no reason")
    return problems


def _contrast_problems(source: dict[str, Any], palette: dict[str, dict[str, str]]) -> list[str]:
    problems: list[str] = []
    by_sc = {str(r["sc"]): r for r in source["wcag"]}
    for sc, pairs in source["contrast"].items():
        status = by_sc[sc]["status"]
        failing = []
        for p in pairs:
            ratio = contrast(palette[p["scheme"]][p["fg"]], palette[p["scheme"]][p["bg"]])
            if ratio < p["required"]:
                failing.append(p)
                if status == "Supports":
                    problems.append(
                        f"{sc}: says Supports but {p['fg']} on {p['bg']} ({p['scheme']}) "
                        f"measures {ratio:.2f} against {p['required']}"
                    )
        if status in BELOW and not failing:
            problems.append(f"{sc}: says {status} but every listed pair now passes — re-assess")
    return problems


# ------------------------------------------------------------------ rendering


def _cell(text: object) -> str:
    """One table cell: whitespace collapsed, pipes escaped, and `<`/`>` outside
    code spans escaped so a title such as `not on <Modal>` is not read as HTML."""
    spans = " ".join(str(text).split()).split("`")
    for i in range(0, len(spans), 2):
        spans[i] = spans[i].replace("<", "&lt;").replace(">", "&gt;")
    return "`".join(spans).replace("|", "\\|")


def _evidence(row: dict[str, Any], decided: dict[str, str], measured: set[str]) -> str:
    parts = []
    for ref in row.get("tests", []):
        path, _, title = ref.partition("::")
        parts.append(f"`{path.removeprefix(MOBILE)}` › {_cell(title)}")
    parts.extend(f"manual {key}" for key in row.get("manual", []))
    if row.get("sc") in measured:
        parts.append("contrast measured in §4")
    rid = row_id(row)
    if rid in decided:
        parts.append(f"device audit {decided[rid]} (pending)")
    return "<br>".join(parts) if parts else "—"


def _essential_locks(row: dict[str, Any]) -> str:
    """The SC 1.3.4 exception, named where the criterion is claimed (INT-360)."""
    if "essential_locks" not in row:
        return ""
    locks = row["essential_locks"]
    if not locks:
        return " " + _cell("**Essential exception:** none. No screen keeps an orientation lock.")
    named = " ".join(f"`{lock['lock']}`: {str(lock['reason']).strip()}" for lock in locks)
    return " " + _cell(
        "**Essential exception:** these screens keep an orientation lock, each because that "
        f"orientation is essential: {named}"
    )


def _remarks(row: dict[str, Any]) -> str:
    finding = str(row.get("finding", "")).strip()
    reason = str(row.get(REASON, "")).strip()
    remarks = _cell(row.get("remarks", "")) + _essential_locks(row)
    if reason:
        remarks = f"**Still open because:** {_cell(reason)} {remarks}"
    return f"**Finding:** {_cell(finding)} {remarks}" if finding else remarks


def _counts(rows: list[dict[str, Any]]) -> str:
    return " · ".join(f"{s} {sum(1 for r in rows if r['status'] == s)}" for s in STATUSES)


def render(source: dict[str, Any], *, palette: dict[str, dict[str, str]] | None = None) -> str:
    palette = palette or theme_palette()
    report = source["report"]
    audit = source["device_audit"]
    decided = {rid: key for key, item in audit["items"].items() for rid in item["decides"]}
    measured = set(source["contrast"])
    wcag = list(source["wcag"])
    en = list(source["en301549"])
    out: list[str] = [
        f"# Accessibility conformance report — {report['product_short']}",
        "",
        "> Generated from `docs/compliance/accessibility-conformance.yaml` by",
        "> `scripts/compliance/render_a11y_report.py` (INT-226). Do not edit this file by",
        "> hand: edit the YAML and re-render. `tests/legal/test_a11y_report.py` fails",
        "> when the two drift, when a cited test no longer exists, and when a contrast",
        "> finding no longer matches the palette.",
        "",
        "| | |",
        "|---|---|",
        f"| Product | {_cell(report['product'])} |",
        f"| Platforms | {_cell(report['platforms'])} |",
        f"| Assessed on | {parse_date(report['assessed_on']).isoformat()} |",
        f"| Assessed tree | {_cell(report['tree'])} |",
        f"| Assessed by | {_cell(report['assessed_by'])} |",
        f"| Standards | {_cell(report['standards'])} |",
        f"| Method | {_cell(report['method'])} |",
        f"| Not done | {_cell(report['not_done'])} |",
        "",
        "## 0 · How to read this report",
        "",
    ]
    out += [str(p).strip() + "\n" for p in report["reading_notes"]]
    out += [
        "| Status | Meaning in this report |",
        "|---|---|",
    ]
    out += [f"| **{s}** | {_cell(report['status_meanings'][s])} |" for s in STATUSES]
    out += [
        "",
        f"**WCAG 2.2 Level A and AA ({len(wcag)} criteria):** {_counts(wcag)}.",
        "",
        f"**EN 301 549 clauses beyond clause 11.1-11.4 ({len(en)}):** {_counts(en)}.",
        "",
        "## 1 · WCAG 2.2 Level A — the Ministry checklist (BK1-BK31)",
        "",
        "| BK | SC | Status | Evidence | Remarks |",
        "|---|---|---|---|---|",
    ]
    for r in (r for r in wcag if r["level"] == "A"):
        new = " *(new in 2.2)*" if r.get("wcag22_new") else ""
        out.append(
            f"| {r['bk']} | {r['sc']} {_cell(r['name'])}{new} | **{r['status']}** "
            f"| {_evidence(r, decided, measured)} | {_remarks(r)} |"
        )
    out += [
        "",
        "## 2 · WCAG 2.2 Level AA",
        "",
        "| SC | Status | Evidence | Remarks |",
        "|---|---|---|---|",
    ]
    for r in (r for r in wcag if r["level"] == "AA"):
        new = " *(new in 2.2)*" if r.get("wcag22_new") else ""
        out.append(
            f"| {r['sc']} {_cell(r['name'])}{new} | **{r['status']}** "
            f"| {_evidence(r, decided, measured)} | {_remarks(r)} |"
        )
    out += [
        "",
        "## 3 · EN 301 549 V3.2.1",
        "",
        "### 3.1 · Clauses 11.1-11.4, derived from §1 and §2",
        "",
        _cell(report["en_clause_11_note"]),
        "",
        "| Clause | WCAG 2.1 SC | Status |",
        "|---|---|---|",
    ]
    out += [
        f"| {d['clause']} | {d['sc']} {_cell(d['name'])} | {d['status']} |"
        for d in en_clause_11(source)
    ]
    out += [
        "",
        "### 3.2 · Clauses assessed on their own",
        "",
        "| Clause | Status | Evidence | Remarks |",
        "|---|---|---|---|",
    ]
    out += [
        f"| {r['clause']} {_cell(r['name'])} | **{r['status']}** "
        f"| {_evidence(r, decided, measured)} | {_remarks(r)} |"
        for r in en
    ]
    out += [
        "",
        "## 4 · Contrast, computed from `apps/mobile/src/lib/theme.ts`",
        "",
        "| SC | Scheme | Foreground on background | Measured | Required | Result |",
        "|---|---|---|---|---|---|",
    ]
    for sc, pairs in source["contrast"].items():
        for p in pairs:
            fg, bg = palette[p["scheme"]][p["fg"]], palette[p["scheme"]][p["bg"]]
            ratio = contrast(fg, bg)
            result = "meets" if ratio >= p["required"] else "**below**"
            pair = f"`{p['fg']}` {fg} on `{p['bg']}` {bg} — {_cell(p['use'])}"
            out.append(
                f"| {sc} | {p['scheme']} | {pair} "
                f"| {ratio:.2f} : 1 | {p['required']} : 1 | {result} |"
            )
    out += [
        "",
        f"## 5 · Device audit — **{audit['status']}**, to be performed by the {audit['owner']}",
        "",
        _cell(audit["purpose"]),
        "",
        "| Item | What | Platforms | Decides | Confirms |",
        "|---|---|---|---|---|",
    ]
    for key, item in audit["items"].items():
        decides = ", ".join(item["decides"]) or "—"
        confirms = ", ".join(item.get("confirms", [])) or "—"
        out.append(
            f"| {key} | {_cell(item['title'])} | {_cell(', '.join(item['platforms']))} "
            f"| {decides} | {confirms} |"
        )
    out.append("")
    for key, item in audit["items"].items():
        out += [f"**{key} · {_cell(item['title'])}.** {_cell(item['steps'])}", ""]
    out += [
        "## 6 · Recorded manual checks",
        "",
        "| Check | Date | By | Method | Result |",
        "|---|---|---|---|---|",
    ]
    for key, check in source["manual_checks"].items():
        out.append(
            f"| {key} | {parse_date(check['date']).isoformat()} | {_cell(check['by'])} "
            f"| {_cell(check['method'])} | {_cell(check['result'])} |"
        )
    cited_by: dict[str, list[str]] = defaultdict(list)
    for r in wcag + en:
        for ref in r.get("tests", []):
            cited_by[ref].append(row_id(r))
    out += [
        "",
        "## 7 · Automated evidence index",
        "",
        "Each test below is collected by `apps/mobile/vitest.config.ts` and runs in",
        "`pnpm -r test`, therefore in `make check-ts` and `make check`.",
        "",
        "| Test file | Test | Cited by |",
        "|---|---|---|",
    ]
    for ref in sorted(cited_by):
        path, _, title = ref.partition("::")
        out.append(f"| `{path}` | {_cell(title)} | {', '.join(cited_by[ref])} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when stale or invalid")
    args = parser.parse_args(argv)
    source = load_source()
    problems = validate(source)
    if problems:
        print("accessibility conformance source is invalid:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    rendered = render(source)
    if args.check:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != rendered:
            print(f"{TARGET.relative_to(REPO)} is stale — re-render it", file=sys.stderr)
            return 1
        print(f"{TARGET.relative_to(REPO)} matches its source")
        return 0
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
