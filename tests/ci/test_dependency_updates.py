"""INT-368 — continuous dependency security updates (Renovate) for every lockfile.

Acceptance (docs/backlog/issues.yaml INT-368), verbatim:
  "a committed Renovate configuration (files/10 §8) covers the uv, pnpm,
   container-digest and GitHub Actions pins, opens security updates without
   waiting for a schedule, and never auto-merges into main"

`legal: 2018-10` (measure 3ç: security updates followed continuously);
`sec_row: cicd`.

What this file pins:

1. **One config, where Renovate reads it.** `.github/renovate.json` parses and
   no second config file competes with it (Renovate takes the first it finds).
2. **Every ecosystem in the tree is covered.** Manifests and lockfiles are
   discovered from `git ls-files`, never listed by hand, and each must fall to
   an enabled manager. The table below also names ecosystems this repository
   does not use yet, so the first `go.mod` or `Chart.yaml` fails here instead
   of going unwatched (near-miss control: a planted one is caught).
3. **Every container digest is reachable**, including the two pins that live
   outside a Dockerfile or compose file (the staging `lib.sh` and the model
   registry), and the ignore list hides only fixtures and vendored trees.
4. **Security updates wait for nothing:** no schedule, no dashboard approval,
   no release-age delay, and a `security` label.
5. **Nothing auto-merges**, at any level, through any preset — so every update
   is a pull request that runs the CI, security and licence gates and waits for
   a human. The evidence and sec_row gates still refuse a bare Renovate title:
   the maintainer carries the update under an issue (runbook).
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = ".github/renovate.json"
RUNBOOK_PATH = "docs/runbooks/dependency-updates.md"

#: Every repository config location Renovate reads (renovate 44.115.10,
#: lib/config/app-strings.ts `configFileNames`), besides a `renovate` key in the
#: root package.json. Exactly one may exist.
CONFIG_LOCATIONS = tuple(
    [
        f"{d}renovate.{ext}"
        for d in ("", ".github/", ".gitlab/")
        for ext in ("json", "jsonc", "json5")
    ]
    + [".renovaterc", ".renovaterc.json", ".renovaterc.jsonc", ".renovaterc.json5"]
)

#: Tracked file → the Renovate manager that owns it. For the managers the config
#: enables these are Renovate's own default `managerFilePatterns` (renovate
#: 44.115.10, lib/modules/manager/<manager>/index.ts; copied into
#: docs/evidence/INT-368.md). The lockfile rows say which manager a lockfile
#: belongs to; the rest are ecosystems this repository does not use yet.
ECOSYSTEMS: tuple[tuple[str, str], ...] = (
    ("pep621", r"(^|/)pyproject\.toml$"),
    ("pep621", r"(^|/)uv\.lock$"),
    ("npm", r"(^|/)package\.json$"),
    ("npm", r"(^|/)pnpm-workspace\.yaml$"),
    ("npm", r"(^|/)(pnpm-lock\.yaml|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock)$"),
    ("dockerfile", r"(^|/|\.)([Dd]ocker|[Cc]ontainer)file$"),
    ("dockerfile", r"(^|/)([Dd]ocker|[Cc]ontainer)file[^/]*$"),
    ("docker-compose", r"(^|/)(?:docker-)?compose[^/]*\.ya?ml$"),
    (
        "github-actions",
        r"(^|/)(workflow-templates|\.(?:github|gitea|forgejo)/(?:workflows|actions))/.+\.ya?ml$",
    ),
    ("github-actions", r"(^|/)action\.ya?ml$"),
    ("pip_requirements", r"(^|/)[\w-]*requirements([-._]\w+)?\.(txt|pip)$"),
    ("pre-commit", r"(^|/)\.pre-commit-config\.ya?ml$"),
    ("pyenv", r"(^|/)\.python-version$"),
    ("poetry", r"(^|/)poetry\.lock$"),
    ("pipenv", r"(^|/)Pipfile(\.lock)?$"),
    ("bun", r"(^|/)bun\.lockb?$"),
    ("nvm", r"(^|/)\.nvmrc$"),
    ("asdf", r"(^|/)\.tool-versions$"),
    ("gomod", r"(^|/)go\.(mod|sum)$"),
    ("cargo", r"(^|/)Cargo\.(toml|lock)$"),
    ("bundler", r"(^|/)Gemfile(\.lock)?$"),
    ("composer", r"(^|/)composer\.(json|lock)$"),
    ("maven", r"(^|/|\.)pom\.xml$"),
    ("gradle", r"\.gradle(\.kts)?$"),
    ("helmv3", r"(^|/)Chart\.ya?ml$"),
    ("terraform", r"(\.tf|(^|/)\.terraform\.lock\.hcl)$"),
    ("cocoapods", r"(^|/)Podfile(\.lock)?$"),
    ("nuget", r"\.(cs|fs|vb)proj$"),
    ("pub", r"(^|/)pubspec\.ya?ml$"),
)

#: The managers holding the pins the acceptance names: uv, pnpm, container
#: digests (Dockerfiles and compose files) and GitHub Actions.
ACCEPTANCE_MANAGERS = ("pep621", "npm", "dockerfile", "docker-compose", "github-actions")
DIGEST_MANAGERS = ("dockerfile", "docker-compose", "github-actions", "custom.regex")
#: A tracked manifest may be ignored only when it is a fixture or vendored.
IGNORABLE_PREFIXES = ("tests/fixtures/", ".claude/")
MUST_IGNORE = (
    "**/node_modules/**",
    "tests/fixtures/**",
    ".claude/**",
    "files/**",
    "packages/protocols/review/**",
    "packages/protocols/dist/**",
)
IMAGE_DIGEST = re.compile(r"[A-Za-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}")
WEEKDAY = re.compile(r"\bon (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b")
CONVENTIONAL = re.compile(
    r"^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([^)]+\))?: .+"
)


def _config() -> dict[str, Any]:
    loaded = json.loads((REPO / CONFIG_PATH).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def _glob(pattern: str) -> re.Pattern[str]:
    """minimatch with `dot: true`, the subset Renovate's ignorePaths use."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("(?:/.*)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "{":
            end = pattern.index("}", i)
            out.append("(?:" + "|".join(map(re.escape, pattern[i + 1 : end].split(","))) + ")")
            i = end + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def ignored(path: str, ignore_paths: Sequence[str]) -> bool:
    """Renovate's own rule (extract/file-match.ts): substring OR glob match."""
    return any(p in path or _glob(p).match(path) for p in ignore_paths)


def _re2(regex: str) -> re.Pattern[str]:
    """An RE2 pattern as Renovate writes it; named groups spelled the Python way."""
    return re.compile(regex.replace("(?<", "(?P<"))


def _pattern(raw: str) -> re.Pattern[str]:
    """A `managerFilePatterns` entry: `/regex/` or a glob."""
    if raw.startswith("/") and raw.endswith("/") and len(raw) > 1:
        return _re2(raw[1:-1])
    return _glob(raw)


def _is_manifest(path: str) -> bool:
    return any(re.search(regex, path) for _, regex in ECOSYSTEMS)


def hidden_manifests(config: dict[str, Any], paths: Sequence[str]) -> list[str]:
    """Manifests the ignore list hides that are neither fixtures nor vendored."""
    ignore = config.get("ignorePaths", ())
    return [
        path
        for path in paths
        if _is_manifest(path) and ignored(path, ignore) and not path.startswith(IGNORABLE_PREFIXES)
    ]


def uncovered(config: dict[str, Any], paths: Sequence[str]) -> set[tuple[str, str]]:
    """(manager, path) for every discovered manifest no enabled manager reads."""
    enabled = set(config.get("enabledManagers", ()))
    ignore = config.get("ignorePaths", ())
    missing: set[tuple[str, str]] = set()
    for path in paths:
        if ignored(path, ignore):
            continue
        for manager, regex in ECOSYSTEMS:
            if re.search(regex, path) and manager not in enabled:
                missing.add((manager, path))
    return missing


def unreachable_digests(config: dict[str, Any], files: dict[str, str]) -> list[str]:
    """Every `image:tag@sha256:…` line no enabled manager extracts."""
    enabled = set(config.get("enabledManagers", ()))
    ignore = config.get("ignorePaths", ())
    customs = [c for c in config.get("customManagers", ()) if c.get("customType") == "regex"]
    lost = []
    for path, text in files.items():
        if ignored(path, ignore):
            continue
        for line in text.splitlines():
            if not IMAGE_DIGEST.search(line):
                continue
            native = any(
                re.search(rx, path) and m in enabled
                for m, rx in ECOSYSTEMS
                if m in ("dockerfile", "docker-compose")
            )
            custom = "custom.regex" in enabled and any(
                any(_pattern(p).search(path) for p in c["managerFilePatterns"])
                and c.get("datasourceTemplate") == "docker"
                and any(
                    (m := _re2(s).search(line)) and m.group("depName") and m.group("currentDigest")
                    for s in c["matchStrings"]
                )
                for c in customs
            )
            if not (native or custom):
                lost.append(f"{path}: {line.strip()}")
    return lost


def _walk(node: Any, where: str = "") -> Iterator[tuple[str, str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield where, key, value
            yield from _walk(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _walk(item, f"{where}[{index}]")


def automerge_problems(config: dict[str, Any]) -> list[str]:
    problems = []
    for key in ("automerge", "platformAutomerge"):
        if config.get(key) is not False:
            problems.append(f"top-level {key} is not explicitly false")
    if config.get("extends"):
        problems.append("extends pulls in presets; a preset can switch automerge on unseen")
    for where, key, value in _walk(config):
        if key in ("automerge", "platformAutomerge", "autoApprove") and value is not False:
            problems.append(f"{where}.{key} = {value!r}")
        elif "automerge" in key.lower() and key not in ("automerge", "platformAutomerge"):
            problems.append(f"{where}.{key} tunes auto-merge")
    return problems


def security_problems(config: dict[str, Any]) -> list[str]:
    alerts = config.get("vulnerabilityAlerts", {})
    problems = []
    if alerts.get("enabled") is not True:
        problems.append("vulnerabilityAlerts.enabled is not true")
    if alerts.get("schedule") != []:
        problems.append("vulnerabilityAlerts carries a schedule")
    if alerts.get("prCreation") != "immediate":
        problems.append("vulnerabilityAlerts.prCreation is not immediate")
    if alerts.get("dependencyDashboardApproval") is not False:
        problems.append("vulnerabilityAlerts waits for dashboard approval")
    if "minimumReleaseAge" not in alerts or alerts["minimumReleaseAge"] is not None:
        problems.append("vulnerabilityAlerts does not clear minimumReleaseAge")
    if "security" not in alerts.get("labels", ()):
        problems.append("vulnerabilityAlerts has no security label")
    return problems


# --- 1. one config, where Renovate reads it ----------------------------------------


def test_the_config_is_committed_where_renovate_reads_it_and_parses() -> None:
    config = _config()
    assert config["$schema"] == "https://docs.renovatebot.com/renovate-schema.json"
    present = [p for p in CONFIG_LOCATIONS if (REPO / p).exists()]
    assert present == [CONFIG_PATH]
    assert "renovate" not in json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    assert not CONFIG_PATH.startswith(".github/workflows/")


# --- 2. every ecosystem in the tree -------------------------------------------------


def test_every_acceptance_pin_family_is_present_in_the_tree_and_enabled() -> None:
    enabled = set(_config()["enabledManagers"])
    assert set(ACCEPTANCE_MANAGERS) <= enabled
    tracked = set(_tracked())
    assert {"uv.lock", "pnpm-lock.yaml", "pyproject.toml", "package.json"} <= tracked
    assert "[tool.uv" in (REPO / "pyproject.toml").read_text(encoding="utf-8")


def test_every_manifest_and_lockfile_in_the_tree_falls_to_an_enabled_manager() -> None:
    assert uncovered(_config(), _tracked()) == set()


def test_a_planted_ecosystem_the_config_does_not_enable_is_caught() -> None:
    config, tracked = _config(), _tracked()
    planted = [*tracked, "services/newsvc/go.mod", "services/newsvc/Dockerfile"]
    assert uncovered(config, planted) == {("gomod", "services/newsvc/go.mod")}
    # near-miss control: the same file inside a fixture tree is not a dependency
    assert uncovered(config, [*tracked, "tests/fixtures/newsvc/go.mod"]) == set()


def test_disabling_a_manager_the_tree_needs_is_caught() -> None:
    config = _config()
    config["enabledManagers"] = [m for m in config["enabledManagers"] if m != "pep621"]
    assert ("pep621", "uv.lock") in uncovered(config, _tracked())


def test_the_ignore_list_hides_only_fixtures_and_vendored_trees() -> None:
    config, tracked = _config(), _tracked()
    assert set(MUST_IGNORE) <= set(config["ignorePaths"])
    fixtures = [p for p in tracked if _is_manifest(p) and p.startswith(IGNORABLE_PREFIXES)]
    assert fixtures and all(ignored(p, config["ignorePaths"]) for p in fixtures)
    assert hidden_manifests(config, tracked) == []


def test_a_broad_ignore_entry_that_hides_real_manifests_is_caught() -> None:
    # one careless entry would also make the coverage test above pass vacuously
    broad = copy.deepcopy(_config())
    broad["ignorePaths"].append("infra/**")
    hidden = hidden_manifests(broad, _tracked())
    assert "infra/staging/Dockerfile.api" in hidden
    assert "infra/docker-compose.dev.yml" in hidden
    # Renovate also ignores on a bare substring, so a short entry reaches far
    substring = copy.deepcopy(_config())
    substring["ignorePaths"].append("staging")
    assert "infra/staging/compose.yaml" in hidden_manifests(substring, _tracked())


# --- 3. container digests and Actions pins ---------------------------------------------


def _pinned_files() -> dict[str, str]:
    files = {}
    for path in _tracked():
        full = REPO / path
        try:
            text = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        if IMAGE_DIGEST.search(text):
            files[path] = text
    return files


def test_every_digest_pinned_image_in_the_tree_is_reachable() -> None:
    files = _pinned_files()
    assert {"infra/staging/lib.sh", "observability/registry.yaml"} <= set(files)
    assert unreachable_digests(_config(), files) == []


def test_a_digest_pinned_image_in_an_unwatched_file_is_caught() -> None:
    line = 'IMAGE="redis:7.4.11-alpine@sha256:' + "ab" * 32 + '"'
    lost = unreachable_digests(_config(), {"infra/newsvc/run.sh": line})
    assert lost == [f"infra/newsvc/run.sh: {line}"]


def pinned_digest_managers(config: dict[str, Any]) -> set[str]:
    """Managers whose every dependency is digest-pinned; a `false` anywhere voids it."""
    rules = config.get("packageRules", ())
    if config.get("pinDigests") is False or any(r.get("pinDigests") is False for r in rules):
        return set()
    managers = set(DIGEST_MANAGERS) if config.get("pinDigests") is True else set()
    for rule in rules:
        if rule.get("pinDigests") is True and set(rule) <= {
            "description",
            "matchManagers",
            "pinDigests",
        }:
            managers |= set(rule["matchManagers"])
    return managers


def test_digests_are_pinned_for_containers_and_actions() -> None:
    assert set(DIGEST_MANAGERS) <= pinned_digest_managers(_config())


def test_a_rule_that_unpins_a_digest_is_caught() -> None:
    config = _config()
    config["packageRules"].append({"matchManagers": ["github-actions"], "pinDigests": False})
    assert not set(DIGEST_MANAGERS) <= pinned_digest_managers(config)


def test_every_workflow_action_is_sha_pinned_with_its_tag_for_renovate() -> None:
    uses = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")
    seen = 0
    for workflow in sorted((REPO / ".github/workflows").glob("*.y*ml")):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = uses.match(line)
            if not match or match.group(1).startswith("./"):
                continue
            seen += 1
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", match.group(1)), line
            assert re.match(r"\s*# v\d", match.group(2)), line
    assert seen


# --- 4. security updates wait for nothing ---------------------------------------------


def test_security_updates_open_without_a_schedule() -> None:
    config = _config()
    assert security_problems(config) == []
    assert config["osvVulnerabilityAlerts"] is True


def test_a_scheduled_or_gated_security_update_is_caught() -> None:
    for key, value in (
        ("schedule", ["before 6am on monday"]),
        ("dependencyDashboardApproval", True),
        ("minimumReleaseAge", "3 days"),
        ("labels", ["dependencies"]),
    ):
        config = _config()
        config["vulnerabilityAlerts"][key] = value
        assert security_problems(config), key


def test_regular_updates_are_weekly_grouped_per_ecosystem_and_throttled() -> None:
    config = _config()
    assert len(config["schedule"]) == 1 and WEEKDAY.search(config["schedule"][0])
    assert config["timezone"] == "Europe/Istanbul"
    assert 1 <= config["prConcurrentLimit"] <= 10 and config["prHourlyLimit"] >= 1
    groups = [r for r in config["packageRules"] if r.get("groupName")]
    for manager in set(config["enabledManagers"]) - {"pyenv"}:
        assert any(
            manager in r.get("matchManagers", ()) and "major" not in r.get("matchUpdateTypes", ())
            for r in groups
        ), manager
    majors = [r for r in config["packageRules"] if r.get("matchUpdateTypes") == ["major"]]
    assert majors and all(r["dependencyDashboardApproval"] is True for r in majors)
    maintenance = config["lockFileMaintenance"]
    assert maintenance["enabled"] is True and maintenance["automerge"] is False
    assert maintenance["schedule"] == ["before 6am on the first day of the month"]


def cooldown_problems(config: dict[str, Any]) -> list[str]:
    """Regular npm/PyPI releases wait >= 7 days, and every rule naming packages
    or dep types states its own age (semgrep p/ci renovate-missing-minimum-release-age,
    which the security workflow runs over this file)."""
    problems = []
    rules = config.get("packageRules", ())
    if not any(
        {"npm", "pypi"} <= set(r.get("matchDatasources", ())) and r.get("minimumReleaseAge")
        for r in rules
    ):
        problems.append("no cooldown rule for npm and PyPI")
    for index, rule in enumerate(rules):
        naming = {"matchPackageNames", "matchPackagePatterns", "matchDepTypes"} & set(rule)
        age = rule.get("minimumReleaseAge", "unset")
        if naming and age == "unset":
            problems.append(f"packageRules[{index}] names packages without a release age")
        if isinstance(age, str) and age != "unset":
            days = re.fullmatch(r"(\d+) days?", age)
            if not days or int(days.group(1)) < 7:
                problems.append(f"packageRules[{index}] release age {age!r} is under 7 days")
    return problems


def test_regular_releases_cool_down_for_seven_days() -> None:
    assert cooldown_problems(_config()) == []


def test_a_short_or_missing_cooldown_is_caught() -> None:
    short = _config()
    for rule in short["packageRules"]:
        if rule.get("matchDatasources") == ["npm", "pypi"]:
            rule["minimumReleaseAge"] = "3 days"
    missing = _config()
    missing["packageRules"].append({"matchPackageNames": ["left-pad"], "groupName": "x"})
    assert cooldown_problems(short) and cooldown_problems(missing)


def test_ranges_are_pinned_and_constraints_are_not() -> None:
    config = _config()
    assert config["rangeStrategy"] == "pin"
    constraints = {
        dep_type: rule["rangeStrategy"]
        for rule in config["packageRules"]
        if "rangeStrategy" in rule
        for dep_type in rule.get("matchDepTypes", ())
    }
    assert constraints["requires-python"] == "replace"
    assert constraints["engines"] == "replace"
    assert constraints["pnpm.overrides"] == "replace"
    assert constraints["peerDependencies"] == "widen"


def test_commit_messages_are_conventional_chore_deps() -> None:
    config = _config()
    assert config["semanticCommits"] == "enabled"
    header = f"{config['semanticCommitType']}({config['semanticCommitScope']}): update python"
    assert header.startswith("chore(deps): ") and CONVENTIONAL.match(header)
    for rule in config["packageRules"]:
        assert not {"semanticCommitType", "semanticCommitScope", "commitMessagePrefix"} & set(rule)


# --- 5. nothing auto-merges; the gates still stand ---------------------------------------


def test_nothing_auto_merges_anywhere() -> None:
    assert automerge_problems(_config()) == []


def test_an_automerge_anywhere_is_caught() -> None:
    rule = _config()
    rule["packageRules"][0]["automerge"] = True
    alerts = _config()
    alerts["vulnerabilityAlerts"]["automerge"] = True
    preset = _config()
    preset["extends"] = [":automergeMinor"]
    platform = _config()
    platform["platformAutomerge"] = True
    for config in (rule, alerts, preset, platform):
        assert automerge_problems(config), config


def test_the_evidence_and_sec_row_gates_still_refuse_a_bare_renovate_title() -> None:
    title, body = "chore(deps): update python dependencies", "Closes #595\nSec-Row: cicd"
    evidence = subprocess.run(
        ["bash", "scripts/ci/evidence_check.sh", title, body],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert evidence.returncode != 0 and "INT-xxx" in evidence.stdout
    linkage = subprocess.run(
        [sys.executable, "scripts/ci/check_sec_row_linkage.py", title, body],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert linkage.returncode != 0


def test_the_licence_gate_runs_on_every_pull_request() -> None:
    workflow = (REPO / ".github/workflows/security.yml").read_text(encoding="utf-8")
    assert re.search(r"^on:\n  pull_request:", workflow, re.M)
    assert "scripts/ci/check_licenses.py" in workflow


def test_every_pr_points_the_maintainer_at_the_runbook() -> None:
    config = _config()
    assert RUNBOOK_PATH in config["prFooter"]
    runbook = (REPO / RUNBOOK_PATH).read_text(encoding="utf-8")
    for needle in ("Renovate GitHub App", "ArioMoniri/intake", "Dependabot alerts", "INT-368"):
        assert needle in runbook, needle
