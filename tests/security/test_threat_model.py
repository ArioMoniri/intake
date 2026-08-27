"""INT-020 — sec_row PR linkage gate + incident runbook shape + claims scan.

Acceptance lines under test, verbatim:
  "docs/security/threat-model.md STRIDE+LINDDUN seeded from 10 §9; docs/security/
   incident-runbook.md includes KVKK Board 72h form flow (2019/10), data-subject
   notice templates, USOM/Siber Guvenlik Baskanligi report per 7545, hospital DPA
   notice"
  "PR template requires the 10 §9 row link; missing link fails evidence_check"

Three groups:
  1. scripts/ci/check_sec_row_linkage.py — the gate itself, exercised the way
     tests/ci/test_evidence_check.py exercises evidence_check.sh, plus a parser
     parity check (the script's stdlib line parse of issues.yaml must agree with
     yaml.safe_load, or the gate silently checks the wrong thing).
  2. docs/security/incident-runbook.md — the executable skeleton's required
     sections, with the legal notification texts held as pointers to INT-214
     (legal texts render only from docs/legal/ — CLAUDE.md invariant 18).
  3. No performance-claim language in either security document (the spirit of
     invariant 20 applied to docs/security/).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "check_sec_row_linkage.py"
ISSUES = REPO / "docs" / "backlog" / "issues.yaml"
MODEL = REPO / "docs" / "security" / "threat-model.md"
RUNBOOK = REPO / "docs" / "security" / "incident-runbook.md"

FIXTURE_ISSUES = """\
- id: INT-777
  epic: E01-platform
  phase: P0
  title: "carries a row"
  labels: [area:security]
  status: todo
  acceptance:
    - "x"
  sec_row: "sample-row"
- id: INT-778
  epic: E01-platform
  phase: P0
  title: "carries no row"
  labels: []
  status: todo
  acceptance:
    - "x"
"""

FIXTURE_MODEL = "# model\n\n## `sample-row` — a fixture section\n\nbody\n"


def run(title: str, body: str, issues: Path, model: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own script, fixed argv
        [
            sys.executable,
            str(SCRIPT),
            title,
            body,
            "--issues",
            str(issues),
            "--threat-model",
            str(model),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def _fixtures(tmp_path: Path, model_text: str = FIXTURE_MODEL) -> tuple[Path, Path]:
    issues = tmp_path / "issues.yaml"
    issues.write_text(FIXTURE_ISSUES, encoding="utf-8")
    model = tmp_path / "threat-model.md"
    model.write_text(model_text, encoding="utf-8")
    return issues, model


def test_script_exists_and_is_executable_text() -> None:
    assert SCRIPT.is_file(), "scripts/ci/check_sec_row_linkage.py is missing"


def test_well_formed_pr_passes(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    out = run("INT-777: x", "Closes #1\nSec-Row: sample-row\n", issues, model)
    assert out.returncode == 0, out.stdout + out.stderr


def test_missing_sec_row_line_fails(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    out = run("INT-777: x", "Closes #1\nno linkage here\n", issues, model)
    assert out.returncode == 1
    assert "Sec-Row" in out.stdout


def test_mismatched_sec_row_fails(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    out = run("INT-777: x", "Sec-Row: another-row\n", issues, model)
    assert out.returncode == 1


def test_unfilled_template_line_fails(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    out = run("INT-777: x", "Sec-Row: <row>\n", issues, model)
    assert out.returncode == 1


def test_row_without_a_model_heading_fails(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path, model_text="# model\n\nno sections\n")
    out = run("INT-777: x", "Sec-Row: sample-row\n", issues, model)
    assert out.returncode == 1
    assert "heading" in out.stdout


def test_issue_without_sec_row_passes_without_the_line(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    assert run("INT-778: x", "Closes #1\n", issues, model).returncode == 0


def test_issue_without_sec_row_accepts_the_none_marker(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    assert run("INT-778: x", "Sec-Row: —\n", issues, model).returncode == 0


def test_issue_without_sec_row_rejects_a_claimed_row(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    assert run("INT-778: x", "Sec-Row: sample-row\n", issues, model).returncode == 1


def test_malformed_title_fails(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    assert run("not a pr title", "Sec-Row: sample-row\n", issues, model).returncode == 1


def test_unknown_issue_id_fails(tmp_path: Path) -> None:
    issues, model = _fixtures(tmp_path)
    assert run("INT-999: x", "Sec-Row: sample-row\n", issues, model).returncode == 1


def test_real_repo_int_020_linkage_passes() -> None:
    out = run("INT-020: threat model", "Sec-Row: incident-response\n", ISSUES, MODEL)
    assert out.returncode == 0, out.stdout + out.stderr


def test_line_parser_agrees_with_yaml_on_the_real_backlog() -> None:
    dump = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--dump-rows", "--issues", str(ISSUES)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert dump.returncode == 0, dump.stdout + dump.stderr
    parsed: dict[str, str | None] = {}
    for line in dump.stdout.splitlines():
        iid, _, row = line.partition(" ")
        parsed[iid] = row or None
    expected = {
        i["id"]: i.get("sec_row") for i in yaml.safe_load(ISSUES.read_text(encoding="utf-8"))
    }
    assert parsed == expected


# --- incident runbook skeleton -------------------------------------------------

RUNBOOK_HEADINGS = (
    "## Detection sources",
    "## Severity ladder",
    "## First 15 minutes",
    "## Roles",
    "## Evidence preservation",
    "## Notification pointers",
    "## Communications rules",
    "## Post-incident review",
)


def test_runbook_has_the_required_sections() -> None:
    assert RUNBOOK.is_file(), "docs/security/incident-runbook.md is missing"
    text = RUNBOOK.read_text(encoding="utf-8")
    for heading in RUNBOOK_HEADINGS:
        assert heading in text, f"incident-runbook.md is missing {heading!r}"


def test_runbook_points_notifications_at_the_legal_machinery() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for anchor in ("INT-214", "72", "2019/10", "7545", "USOM", "DPA"):
        assert anchor in text, f"notification pointers never mention {anchor!r}"
    assert "audit chain (INT-016)" in text, "evidence section must cite the audit chain"


def test_runbook_bans_phi_in_incident_communications() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "ids only" in text.lower(), "comms rules must require ids, never PHI"


# --- no performance-claim language in docs/security/ ---------------------------

CLAIM_PATTERNS: tuple[str, ...] = (
    r"\d\s*%",
    r"(?i)\bsensitivit",
    r"(?i)\bspecificit",
    r"(?i)\bAUROC\b",
    r"(?i)\bAUC\b",
    r"(?i)\bWER\b",
    r"(?i)\baccurac",
    r"(?i)\bF1[- ]score\b",
)


def test_security_docs_carry_no_performance_claims() -> None:
    for doc in (MODEL, RUNBOOK):
        assert doc.is_file(), f"{doc} is missing"
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in CLAIM_PATTERNS:
                assert not re.search(pattern, line), (
                    f"{doc.name}:{n} matches claim pattern {pattern!r}: {line!r}"
                )
