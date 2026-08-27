"""INT-002 — the evidence gate.

Acceptance line under test, verbatim:
  "scripts/ci/evidence_check.sh: PR must contain docs/evidence/<ISSUE>.md with
   red-run + green-run + gate outputs; PR title must be `INT-xxx: ...` and body
   must contain `Closes #<n>`"
"""

from __future__ import annotations

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


def run(title: str, body: str, evidence_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), title, body, str(evidence_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def _dir_with(tmp_path: Path, name: str, content: str) -> Path:
    d = tmp_path / "evidence"
    d.mkdir(exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")
    return d


def test_valid_pr_passes(tmp_path: Path) -> None:
    d = _dir_with(tmp_path, "INT-777.md", GOOD_EVIDENCE)
    out = run("INT-777: do the thing", "Some text\nCloses #12\nmore", d)
    assert out.returncode == 0, out.stdout + out.stderr


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
    out = run("INT-001: bootstrap", "Closes #1", REPO / "docs" / "evidence")
    assert out.returncode == 0, out.stdout + out.stderr
