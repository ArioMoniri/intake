"""INT-310 — the eight npm advisories are cleared by version, not by silence.

Acceptance lines under test, verbatim:

  "the advisories are cleared by upgrading rather than by suppression: vitest
   2 to 3 and vite 5 to 6 across the workspace, plus uuid, esbuild and
   decode-uri-component - and .trivyignore/.osv suppressions do NOT grow, which
   a test asserts by pinning their line counts"

  "the suite still proves what it proved before: the full mobile and platform
   vitest runs pass at the same counts or higher, and no test is deleted or
   skipped to accommodate the major bump"

INT-019 built the twelve-step gate set and refused to suppress what step 6
found, which is why `make security` was honestly red rather than falsely
green. The failure mode this file exists to prevent is the cheap version of
the same fix: adding a row to a scanner ignore file and calling the gate
passed. Every assertion here is therefore about *resolved versions* and about
suppression files *not growing* — never about the scanner's exit code, which a
mute would also make zero.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCKFILE = REPO / "pnpm-lock.yaml"

# The eight advisories osv-scanner 2.5.1 reported against pnpm-lock.yaml on
# 3 Sep 2026 (docs/evidence/INT-310.md, red run), with the fixed version each
# one names. A package resolving BELOW its fixed version is the advisory
# returning; the ids are carried alongside so the suppression sweep below can
# look for them by name.
FIXED_VERSIONS: dict[str, tuple[int, int, int]] = {
    "vitest": (3, 2, 6),  # GHSA-5xrq-8626-4rwp, CVSS 9.8
    "vite": (6, 4, 3),  # GHSA-fx2h-pf6j-xcff, GHSA-4w7w-66w2-5vf9, GHSA-v6wh-96g9-6wx3
    "esbuild": (0, 25, 0),  # GHSA-67mh-4wv8-2f99
    "uuid": (11, 1, 1),  # GHSA-w5hq-g745-h8pq (CVE-2026-41907, CVE-2026-41988)
    "decode-uri-component": (0, 5, 0),  # GHSA-vcc3-ghjq-m6fr (CVE-2026-45822)
}

ADVISORY_IDS = (
    "GHSA-5xrq-8626-4rwp",
    "GHSA-fx2h-pf6j-xcff",
    "GHSA-4w7w-66w2-5vf9",
    "GHSA-v6wh-96g9-6wx3",
    "GHSA-67mh-4wv8-2f99",
    "GHSA-w5hq-g745-h8pq",
    "GHSA-vcc3-ghjq-m6fr",
    "CVE-2026-47429",
    "CVE-2026-41907",
    "CVE-2026-41988",
    "CVE-2026-45822",
)

# Every suppression mechanism the two lockfile/filesystem scanners in
# `make security` [4/12] and [6/12] honour. Named exhaustively rather than
# globbed: a mechanism this list does not know about is one this gate cannot
# police, so the list is the reviewable part.
TRIVY_SUPPRESSION_FILES = (".trivyignore", ".trivyignore.yaml", ".trivyignore.yml")
OSV_SUPPRESSION_FILES = (
    "osv-scanner.toml",
    ".osv-scanner.toml",
    "osv-scanner.yaml",
    ".osv-scanner.yaml",
    "osv-detector.yaml",
)

# The pins. Both are counts of SUPPRESSION ENTRIES, not raw file lines: a
# comment costs nothing and a row costs everything, and pinning raw lines
# would make adding an explanatory sentence fail the build while adding a
# terse mute passed it.
#
# osv: 0, measured — this repository has never carried an osv-scanner config
# of any kind, on `main` or on INT-019's branch. It is the pin INT-310 must
# hold, because osv-scanner step [6/12] is the step this issue clears.
#
# trivy: at most 1. Measured 0 on this branch (no .trivyignore* file exists on
# `main` yet) and 1 once INT-019 lands `.trivyignore.yaml` — its single row is
# the workspace-root name collision with the unrelated PyData `intake` package
# on PyPI, which is provably not a dependency at all. The ceiling accommodates
# that one row and nothing else, and per CLAUDE.md invariant 17 it may only
# shrink.
MAX_OSV_SUPPRESSIONS = 0
MAX_TRIVY_SUPPRESSIONS = 1

# Floor for the TypeScript suites, measured on this branch: 86 vitest files in
# apps/mobile (1753 tests) and 2 in packages/clinical-schemas (6 tests).
# A major bump that "passes" by dropping a spec file trades one risk for
# another; like the coverage floors of invariant 8, this only rises.
MIN_TS_TEST_FILES = 88

TS_TEST_GLOBS = (
    ("apps/mobile/src", "*.test.ts"),
    ("apps/mobile/e2e", "*.spec.ts"),
    ("packages/clinical-schemas/src", "*.test.ts"),
)

# vitest's own skip vocabulary. Two members of it — the `it` and `test` forms
# of skip and todo — are already banned by scripts/ci/no_placeholders.sh, whose
# grep this file must therefore not itself trip; the rest of the family is not
# covered there. `.only` belongs here for the same reason a skip does: it
# silently narrows the run to one case while still reporting green.
SKIP_PATTERN = re.compile(
    r"\b(?:describe|it|test|suite|bench)\s*\.\s*(?:skip|only|todo|skipIf|runIf|concurrent\s*\.\s*skip)\b"
    r"|\bx(?:it|describe|test)\s*\("
)


def _parse_version(raw: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.match(r"(\d+)\.(\d+)\.(\d+)", raw).groups())


def _resolved_versions(package: str) -> list[str]:
    """Every version of `package` the pnpm lockfile resolves, peer suffix dropped."""
    text = LOCKFILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"^  '?{re.escape(package)}@(\d+\.\d+\.\d+[^:'(]*)'?[:(]", re.M)
    return sorted({m.group(1) for m in pattern.finditer(text)})


def _suppression_entries(path: Path) -> list[str]:
    """Non-comment, non-blank lines that introduce a suppression row."""
    if not path.exists():
        return []
    entries: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # trivy's YAML form: rows are `- id: CVE-...`. Its legacy plain form:
        # one bare id per line. Both start an entry; continuation keys
        # (purls:, statement:, indented prose) do not.
        if stripped.startswith("- ") or re.match(r"^(CVE|GHSA|AVD|DS)-", stripped):
            entries.append(stripped)
    return entries


def test_every_advisory_is_cleared_by_a_resolved_version() -> None:
    """The lockfile resolves nothing below a fixed version. Red before the bump."""
    for package, floor in FIXED_VERSIONS.items():
        resolved = _resolved_versions(package)
        assert resolved, f"{package} vanished from pnpm-lock.yaml"
        for raw in resolved:
            assert _parse_version(raw) >= floor, (
                f"{package}@{raw} is below the fixed version "
                f"{'.'.join(str(n) for n in floor)} — the advisory is back"
            )


def test_osv_suppressions_do_not_grow() -> None:
    total = 0
    for name in OSV_SUPPRESSION_FILES:
        total += len(_suppression_entries(REPO / name))
    assert total <= MAX_OSV_SUPPRESSIONS, (
        f"osv-scanner suppression entries rose to {total} (pin {MAX_OSV_SUPPRESSIONS}). "
        "INT-310 clears step [6/12] by upgrading; a suppression here undoes that."
    )


def test_trivy_suppressions_do_not_grow() -> None:
    total = 0
    for name in TRIVY_SUPPRESSION_FILES:
        total += len(_suppression_entries(REPO / name))
    assert total <= MAX_TRIVY_SUPPRESSIONS, (
        f"trivy suppression entries rose to {total} (pin {MAX_TRIVY_SUPPRESSIONS}). "
        "The pin may only shrink (CLAUDE.md invariant 17)."
    )


def test_no_suppression_file_names_any_of_the_eight_advisories() -> None:
    """A pin on counts is not enough: one row could replace another."""
    for name in TRIVY_SUPPRESSION_FILES + OSV_SUPPRESSION_FILES:
        path = REPO / name
        if not path.exists():
            continue
        body = path.read_text(encoding="utf-8")
        for advisory in ADVISORY_IDS:
            assert advisory not in body, (
                f"{name} names {advisory} — INT-310's contract is that these are "
                "cleared by upgrading, never by suppression"
            )


def test_osv_scanner_is_not_invoked_with_an_ignore_flag() -> None:
    """A flag on the command line mutes as effectively as a config file."""
    sources = [REPO / "Makefile"]
    workflows = REPO / ".github" / "workflows"
    if workflows.is_dir():
        sources.extend(sorted(workflows.glob("*.yml")))
        sources.extend(sorted(workflows.glob("*.yaml")))
    for path in sources:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "osv-scanner" not in line:
                continue
            for flag in ("--ignore-vuln", "--config", "--no-ignore", "--all-packages"):
                assert flag not in line, f"{path.name}: osv-scanner given {flag}: {line.strip()}"


def _ts_test_files() -> list[Path]:
    found: list[Path] = []
    for directory, pattern in TS_TEST_GLOBS:
        root = REPO / directory
        if root.is_dir():
            found.extend(sorted(root.rglob(pattern)))
    return found


def test_the_ts_suites_did_not_shrink_for_the_bump() -> None:
    files = _ts_test_files()
    assert len(files) >= MIN_TS_TEST_FILES, (
        f"{len(files)} vitest files, floor {MIN_TS_TEST_FILES}. A major bump that "
        "passes by deleting a spec has traded one risk for another."
    )


def test_no_ts_test_is_skipped_or_narrowed() -> None:
    offenders: list[str] = []
    for path in _ts_test_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SKIP_PATTERN.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{number}: {line.strip()}")
    assert not offenders, "skipped or narrowed vitest cases:\n" + "\n".join(offenders)
