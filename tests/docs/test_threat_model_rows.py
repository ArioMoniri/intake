"""INT-020 — the threat model covers every backlog sec_row (files/10 §9).

Acceptance line under test, verbatim:
  "docs/security/threat-model.md STRIDE+LINDDUN seeded from 10 §9; ..."

files/10 §8: "Backlog `sec_row:` fields point at the §9 rows below, so every
feature PR links its threat row by construction." That construction only holds
if the working threat model actually has a section for every row the backlog
uses — which is what this file pins.

The close-out audit (27 Sep 2026) added two more directions of drift, because
the backlog-row check alone let both through:

  * a files/10 §9 feature with no section that carries it — four of the 32
    features (offline drafts, break-glass, the sealed research store, RED
    acknowledgement) had none, although "seeded from 10 §9" is the acceptance;
  * a service, app or package with no threat-model row at all — nothing
    enforced that a new module under services/, apps/ or packages/ is owned by
    a row, so the first one would have shipped without one.

Both are read from maps inside threat-model.md, and each map is checked in both
directions (a missing entry and a stale one fail alike) with a near-miss
control proving the check bites.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "security" / "threat-model.md"
ISSUES = REPO / "docs" / "backlog" / "issues.yaml"
FILES_10 = REPO / "files" / "10_SECURITY_AND_TECHNICAL_MONITORING.md"

SEED_MAP_HEADING = "## Seeding map: files/10 §9 features"
MODULE_MAP_HEADING = "## Module map: services, apps and packages"
MODULE_ROOTS = ("services", "apps", "packages")
ROW_REF = re.compile(r"`([a-z0-9-]+)`")

# Every section heading is exactly "## `<slug>` — <title>" so both this test
# and scripts/ci/check_sec_row_linkage.py can match rows mechanically.
HEADING = re.compile(r"^## `([a-z0-9-]+)` — .+$", re.M)

SECTION_FIELDS = (
    "**Assets:**",
    "**Trust boundaries:**",
    "**Threats (STRIDE/LINDDUN):**",
    "**Controls (files/10):**",
    "**Signals:**",
    "**Tests:**",
)


def _sec_rows() -> set[str]:
    issues = yaml.safe_load(ISSUES.read_text(encoding="utf-8"))
    return {i["sec_row"] for i in issues if i.get("sec_row")}


def _doc() -> str:
    assert DOC.is_file(), "docs/security/threat-model.md is missing"
    return DOC.read_text(encoding="utf-8")


def test_every_backlog_sec_row_has_a_section_heading() -> None:
    headed = set(HEADING.findall(_doc()))
    missing = sorted(_sec_rows() - headed)
    assert not missing, f"threat-model.md has no section for sec_row(s): {missing}"


def test_no_section_for_a_row_the_backlog_does_not_carry() -> None:
    # A heading without a backlog row is either a typo or a row that was
    # renamed in issues.yaml without the model following — both are drift.
    stale = sorted(set(HEADING.findall(_doc())) - _sec_rows())
    assert not stale, f"threat-model.md sections without a backlog sec_row: {stale}"


def test_every_section_carries_the_six_required_fields() -> None:
    text = _doc()
    matches = list(HEADING.finditer(text))
    assert matches, "threat-model.md has no `## `row`` sections at all"
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start() : end]
        for field in SECTION_FIELDS:
            assert field in body, f"section for {m.group(1)!r} is missing {field}"


def test_model_states_its_derivation_from_files_10() -> None:
    text = _doc()
    for anchor in ("files/10", "§9", "STRIDE", "LINDDUN"):
        assert anchor in text, f"threat-model.md never mentions {anchor!r}"


# --- shared parsing ---------------------------------------------------------------


def _section_bodies(text: str) -> dict[str, str]:
    """Each `## `row`` section's text, heading included, keyed by its slug."""
    matches = list(HEADING.finditer(text))
    bodies: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        bodies[m.group(1)] = text[m.start() : end]
    return bodies


def _map_rows(text: str, heading: str) -> list[list[str]]:
    """Body rows of the table under `heading` (header and rule dropped)."""
    assert heading in text, f"threat-model.md has no {heading!r} section"
    after = text.split(heading, 1)[1]
    following = re.search(r"^## ", after, re.M)
    block = after[: following.start()] if following else after
    lines = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
    assert len(lines) > 2, f"{heading!r} carries no table rows"
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines[2:]]


# --- files/10 §9 seeding ------------------------------------------------------------


def section9_features(files10: str) -> list[str]:
    """The first-column cells of the files/10 §9 matrix, in file order."""
    start = files10.index("\n## 9. ")
    end = files10.index("\n### 9.1", start)
    rows = [line for line in files10[start:end].splitlines() if line.startswith("|")]
    return [row.split("|")[1].strip() for row in rows[2:]]


def seed_map_findings(
    features: list[str], rows: list[list[str]], bodies: dict[str, str]
) -> list[str]:
    """Every way the seeding map and files/10 §9 can disagree."""
    findings: list[str] = []
    mapped = {row[0]: row for row in rows}
    findings += [f"§9 feature with no map entry: {f!r}" for f in features if f not in mapped]
    findings += [f"map entry for no §9 feature: {f!r}" for f in mapped if f not in features]
    for feature, row in mapped.items():
        if len(row) != 3:
            findings.append(f"{feature!r}: expected feature | sections | anchor, got {row}")
            continue
        slugs = ROW_REF.findall(row[1])
        if not slugs:
            findings.append(f"{feature!r} names no section")
        missing = [s for s in slugs if s not in bodies]
        findings += [f"{feature!r} maps to `{s}`, which has no section" for s in missing]
        anchor = row[2].strip("`")
        if not anchor:
            findings.append(f"{feature!r} carries no anchor")
        elif slugs and not missing and not any(anchor in bodies[s] for s in slugs):
            findings.append(f"{feature!r}: anchor {anchor!r} appears in none of {slugs}")
    return findings


def test_the_section9_parser_reads_the_whole_matrix() -> None:
    # A parser that returned nothing would pass every check below vacuously.
    features = section9_features(FILES_10.read_text(encoding="utf-8"))
    assert len(features) >= 30, features
    assert all(features), "an empty feature cell means the parser split the wrong table"
    for known in ("Onboarding / OTP / profile", "RED acknowledgement (`02 §8`)", "Billing (later)"):
        assert known in features


def test_every_section9_feature_is_seeded_into_a_section_that_carries_it() -> None:
    text = _doc()
    findings = seed_map_findings(
        section9_features(FILES_10.read_text(encoding="utf-8")),
        _map_rows(text, SEED_MAP_HEADING),
        _section_bodies(text),
    )
    assert findings == [], "\n".join(findings)


SEED_BODIES = {"triage": "## `triage` — x\n\nRED acknowledgement, inv. 49\n", "billing": "b\n"}
SEED_ROWS = [["RED acknowledgement", "`triage`", "`inv. 49`"]]


def test_near_miss_a_new_section9_feature_without_an_entry_fails() -> None:
    features = ["RED acknowledgement", "A surface files/10 adds tomorrow"]
    assert seed_map_findings(features, SEED_ROWS, SEED_BODIES) == [
        "§9 feature with no map entry: 'A surface files/10 adds tomorrow'"
    ]
    assert seed_map_findings(["RED acknowledgement"], SEED_ROWS, SEED_BODIES) == []


def test_near_miss_an_entry_for_a_dropped_feature_fails() -> None:
    assert seed_map_findings([], SEED_ROWS, SEED_BODIES) == [
        "map entry for no §9 feature: 'RED acknowledgement'"
    ]


def test_near_miss_an_anchor_its_section_does_not_carry_fails() -> None:
    # The map cannot claim coverage the section body does not deliver.
    rows = [["RED acknowledgement", "`billing`", "`inv. 49`"]]
    assert seed_map_findings(["RED acknowledgement"], rows, SEED_BODIES) == [
        "'RED acknowledgement': anchor 'inv. 49' appears in none of ['billing']"
    ]


def test_near_miss_an_entry_naming_a_missing_section_fails() -> None:
    rows = [["RED acknowledgement", "`safety-queue`", "`inv. 49`"]]
    assert seed_map_findings(["RED acknowledgement"], rows, SEED_BODIES) == [
        "'RED acknowledgement' maps to `safety-queue`, which has no section"
    ]


# --- every module owned by a row ---------------------------------------------------


def current_modules(repo: Path) -> list[str]:
    """Top-level directories under services/, apps/ and packages/."""
    found: list[str] = []
    for root in MODULE_ROOTS:
        base = repo / root
        if base.is_dir():
            found += [
                f"{root}/{p.name}"
                for p in sorted(base.iterdir())
                if p.is_dir() and not p.name.startswith((".", "_"))
            ]
    return found


def module_map_findings(modules: list[str], rows: list[list[str]], headed: set[str]) -> list[str]:
    """Every way the module map and the tree (or the headings) can disagree."""
    findings: list[str] = []
    mapped = {row[0].strip("`"): row for row in rows}
    findings += [f"module with no threat-model row: {m}" for m in modules if m not in mapped]
    findings += [f"map entry for an absent module: {m}" for m in mapped if m not in modules]
    for module, row in mapped.items():
        slugs = ROW_REF.findall(row[1]) if len(row) > 1 else []
        if not slugs:
            findings.append(f"{module} names no row")
        findings += [
            f"{module} maps to `{s}`, which has no section" for s in slugs if s not in headed
        ]
    return findings


def test_every_service_app_and_package_has_a_threat_model_row() -> None:
    text = _doc()
    modules = current_modules(REPO)
    assert "services/api" in modules and "apps/mobile" in modules, modules
    findings = module_map_findings(
        modules, _map_rows(text, MODULE_MAP_HEADING), set(HEADING.findall(text))
    )
    assert findings == [], "\n".join(findings)


def test_near_miss_a_new_module_without_a_row_fails(tmp_path: Path) -> None:
    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / "services" / "workers").mkdir()
    (tmp_path / "apps" / ".turbo").mkdir(parents=True)
    (tmp_path / "packages" / "__pycache__").mkdir(parents=True)
    modules = current_modules(tmp_path)
    assert modules == ["services/api", "services/workers"]
    rows = [["`services/api`", "`api`"]]
    assert module_map_findings(modules, rows, {"api"}) == [
        "module with no threat-model row: services/workers"
    ]
    assert module_map_findings(["services/api"], rows, {"api"}) == []


def test_near_miss_a_module_mapped_to_an_unheaded_row_fails() -> None:
    rows = [["`services/api`", "`api`, `api-gateway`"]]
    assert module_map_findings(["services/api"], rows, {"api"}) == [
        "services/api maps to `api-gateway`, which has no section"
    ]


def test_near_miss_a_map_entry_for_a_removed_module_fails() -> None:
    rows = [["`services/api`", "`api`"], ["`services/workers`", "`api`"]]
    assert module_map_findings(["services/api"], rows, {"api"}) == [
        "map entry for an absent module: services/workers"
    ]
