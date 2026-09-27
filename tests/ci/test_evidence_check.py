"""INT-002 — the evidence gate (and INT-020's row link inside it).

Acceptance line under test, verbatim:
  "scripts/ci/evidence_check.sh: PR must contain docs/evidence/<ISSUE>.md with
   red-run + green-run + gate outputs; PR title must be `INT-xxx: ...` and body
   must contain `Closes #<n>`"

INT-020's second acceptance line, verbatim:
  "PR template requires the 10 §9 row link; missing link fails evidence_check"

Until the INT-020 close-out the link was checked only by a sibling CI step, so
`evidence_check.sh` itself passed a body with no `Sec-Row:` line. It now runs
scripts/ci/check_sec_row_linkage.py (the one implementation) and fails with it.
Fixture runs point that check at a fixture backlog and threat model through
SEC_ROW_ISSUES / SEC_ROW_THREAT_MODEL, so INT-777 stays a fixture id.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "evidence_check.sh"

GOOD_EVIDENCE = """# Evidence — INT-777
## Red run
FAILED test_x - AssertionError (1 failed)
## Green run
1 passed
## make check
all gates green
"""

FIXTURE_ISSUES = """\
- id: INT-777
  epic: E01-platform
  phase: P0
  title: "carries a row"
  labels: []
  status: todo
  acceptance:
    - "x"
  sec_row: "sample-row"
"""

FIXTURE_MODEL = "# model\n\n## `sample-row` — a fixture section\n\nbody\n"


def run(
    title: str, body: str, evidence_dir: Path, linkage: tuple[Path, Path] | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("SEC_ROW_ISSUES", None)
    env.pop("SEC_ROW_THREAT_MODEL", None)
    if linkage is not None:
        env["SEC_ROW_ISSUES"], env["SEC_ROW_THREAT_MODEL"] = (str(p) for p in linkage)
    return subprocess.run(
        [str(SCRIPT), title, body, str(evidence_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
    )


def _dir_with(tmp_path: Path, name: str, content: str) -> Path:
    d = tmp_path / "evidence"
    d.mkdir(exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")
    return d


def _linkage(tmp_path: Path) -> tuple[Path, Path]:
    issues = tmp_path / "issues.yaml"
    issues.write_text(FIXTURE_ISSUES, encoding="utf-8")
    model = tmp_path / "threat-model.md"
    model.write_text(FIXTURE_MODEL, encoding="utf-8")
    return issues, model


def test_valid_pr_passes(tmp_path: Path) -> None:
    d = _dir_with(tmp_path, "INT-777.md", GOOD_EVIDENCE)
    body = "Some text\nCloses #12\nSec-Row: sample-row\nmore"
    out = run("INT-777: do the thing", body, d, _linkage(tmp_path))
    assert out.returncode == 0, out.stdout + out.stderr


def test_missing_row_link_fails_evidence_check(tmp_path: Path) -> None:
    # INT-020: "missing link fails evidence_check" — the gate itself, not a sibling step.
    d = _dir_with(tmp_path, "INT-777.md", GOOD_EVIDENCE)
    out = run("INT-777: do the thing", "Closes #12", d, _linkage(tmp_path))
    assert out.returncode == 1, out.stdout + out.stderr
    assert out.stdout.startswith("evidence_check: FAIL"), out.stdout
    assert "Sec-Row" in out.stdout


def test_wrong_row_link_fails_evidence_check(tmp_path: Path) -> None:
    d = _dir_with(tmp_path, "INT-777.md", GOOD_EVIDENCE)
    out = run("INT-777: do the thing", "Closes #12\nSec-Row: another-row", d, _linkage(tmp_path))
    assert out.returncode == 1, out.stdout + out.stderr
    assert "sample-row" in out.stdout


def test_real_repo_int_020_needs_its_own_row_link() -> None:
    # Near-miss pair on the real backlog: the same PR, with and without the link.
    evidence = REPO / "docs" / "evidence"
    bare = run("INT-020: close-out", "Closes #18", evidence)
    assert bare.returncode == 1, bare.stdout + bare.stderr
    linked = run("INT-020: close-out", "Closes #18\nSec-Row: incident-response", evidence)
    assert linked.returncode == 0, linked.stdout + linked.stderr


def test_bad_title_fails(tmp_path: Path) -> None:
    d = _dir_with(tmp_path, "INT-777.md", GOOD_EVIDENCE)
    assert run("do the thing", "Closes #12", d).returncode == 1
    assert run("INT777 do the thing", "Closes #12", d).returncode == 1


def test_missing_closes_fails(tmp_path: Path) -> None:
    d = _dir_with(tmp_path, "INT-777.md", GOOD_EVIDENCE)
    assert run("INT-777: do the thing", "no issue link here", d).returncode == 1


def test_missing_evidence_file_fails(tmp_path: Path) -> None:
    d = tmp_path / "evidence"
    d.mkdir()
    assert run("INT-777: do the thing", "Closes #12", d).returncode == 1


def test_evidence_without_red_run_fails(tmp_path: Path) -> None:
    d = _dir_with(tmp_path, "INT-777.md", "## Green run\n1 passed\n## make check\nok\n")
    assert run("INT-777: do the thing", "Closes #12", d).returncode == 1


def test_evidence_without_green_run_fails(tmp_path: Path) -> None:
    d = _dir_with(tmp_path, "INT-777.md", "## Red run\n1 failed\n## make check\nok\n")
    assert run("INT-777: do the thing", "Closes #12", d).returncode == 1


def test_real_repo_evidence_for_int001_passes() -> None:
    out = run("INT-001: bootstrap", "Closes #1\nSec-Row: platform", REPO / "docs" / "evidence")
    assert out.returncode == 0, out.stdout + out.stderr
