"""INT-002 — the zero-placeholder gate (CLAUDE.md invariant 17).

Acceptance line under test, verbatim:
  "scripts/ci/no_placeholders.sh fails on TODO|FIXME|XXX|NotImplementedError|
   pytest.mark.skip|xfail|it.skip|test.todo|`pass  #`|lorem|placeholder|dummy|
   demo-only outside tests/fixtures allow-list"

Tokens are built by concatenation so this file exercises the gate rather than
tripping it (it is allow-listed as the gate's own test regardless).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "no_placeholders.sh"
ALLOW = REPO / "scripts" / "ci" / "no_placeholders_allow.txt"

TOKENS = [
    "TO" + "DO",
    "FIX" + "ME",
    "XX" + "X",
    "NotImplemented" + "Error",
    "pytest.mark." + "skip",
    "xf" + "ail",
    "it." + "skip",
    "test." + "todo",
    "pass" + "  #",
    "lor" + "em",
    "place" + "holder",
    "dum" + "my",
    "demo" + "-only",
]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(SCRIPT), *args], cwd=REPO, capture_output=True, text=True)


def test_clean_repo_passes() -> None:
    out = run()
    assert out.returncode == 0, f"repo not placeholder-clean:\n{out.stdout}{out.stderr}"


def test_every_token_is_detected(tmp_path: Path) -> None:
    for token in TOKENS:
        f = tmp_path / "module.py"
        f.write_text(f"x = 1  # {token}\n", encoding="utf-8")
        out = run(str(f))
        assert out.returncode == 1, f"token not detected: {token!r}\n{out.stdout}"
        assert "module.py" in out.stdout


def test_clean_file_passes(tmp_path: Path) -> None:
    f = tmp_path / "module.py"
    f.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    assert run(str(f)).returncode == 0


def test_clinical_signoff_form_is_permitted_only_under_protocols(tmp_path: Path) -> None:
    # Invariant 17's sole exception: the literal unfilled-clinical-value form,
    # inside packages/protocols only. Anywhere else it is a violation.
    sentence = 'threshold: "TO' + 'DO: threshold requires clinical sign-off"\n'
    inside = tmp_path / "packages" / "protocols" / "base" / "rule.yaml"
    inside.parent.mkdir(parents=True)
    inside.write_text(sentence, encoding="utf-8")
    assert run(str(inside)).returncode == 0, (
        "the permitted clinical form must pass under packages/protocols"
    )

    outside = tmp_path / "src" / "rule.yaml"
    outside.parent.mkdir(parents=True)
    outside.write_text(sentence, encoding="utf-8")
    assert run(str(outside)).returncode == 1, (
        "the clinical form is not permitted outside packages/protocols"
    )


def test_gate_self_reference_is_not_a_violation(tmp_path: Path) -> None:
    # ci.yml and the Makefile must be able to *invoke* the gate by name; the
    # script name contains a token but is never itself a placeholder marker.
    f = tmp_path / "workflow.yml"
    f.write_text("- run: scripts/ci/no_place" + "holders.sh\n", encoding="utf-8")
    assert run(str(f)).returncode == 0

    g = tmp_path / "mixed.yml"
    g.write_text("- run: scripts/ci/no_place" + "holders.sh  # TO" + "DO later\n", encoding="utf-8")
    assert run(str(g)).returncode == 1, "a real token beside the self-reference must still fail"


def test_allowlist_only_shrinks() -> None:
    """The allow-list may only shrink (CLAUDE.md invariant 17). Removing an entry
    is fine; adding one must consciously change this pinned set AND survive
    review of the reason."""
    entries = {
        line.strip()
        for line in ALLOW.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    pinned = {
        "files/",
        # the verbatim blueprint skeleton whose TODO block is spec-required
        # content (04 §8); the compiler serve-interlock is its gate, not grep
        "packages/protocols/base/life_threat.yaml",
        # docs/adr/ added with INT-004: ADR-019 *documents* the gate and names
        # it — same class as CLAUDE.md/DoD/TDD, which describe what they forbid.
        "docs/adr/",
        "docs/backlog/",
        "docs/evidence/",
        "docs/PROGRESS.md",
        "CLAUDE.md",
        "LOOP.md",
        "PROMPT.md",
        "docs/DoD.md",
        "docs/TDD.md",
        "docs/GOALS.md",
        ".claude/",
        "tests/fixtures/",
        "scripts/ci/no_placeholders.sh",
        "scripts/ci/no_placeholders_allow.txt",
        "tests/ci/test_no_placeholders.py",
    }
    assert entries <= pinned, f"allow-list grew beyond the pinned set: {entries - pinned}"
