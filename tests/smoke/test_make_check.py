"""INT-001 smoke suite.

Acceptance (docs/backlog/issues.yaml INT-001), one test group per line:
  1. pnpm>=9 + uv workspaces per 07 §2 layout; `make setup` from a clean clone on macOS
  2. `make check` = ruff + mypy --strict + pytest + eslint + tsc + vitest across all packages
  3. docker-compose.dev.yml: postgres16+pgvector, redis, hapi, minio; `make dev` healthy
     with real containers (no stub services) — ehrbase corrected out per 00 §3 D8
  4. pre-commit: gitleaks, semgrep, ruff, eslint; Conventional Commits enforced by commitlint

The governing documents of 07 §3 are asserted byte-for-byte against the fenced
blocks in files/07_CLAUDE_CODE_MASTER_PROMPT.md, so "verbatim" stays true after
this PR, not only in it. Refining one of them requires changing 07 in the same
commit — which is exactly the blueprint-sync rule in docs/DoD.md.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
MASTER_PROMPT = REPO / "files" / "07_CLAUDE_CODE_MASTER_PROMPT.md"


def _extract_block(heading: str) -> str:
    """Return the first fenced code block that follows `heading` in files/07."""
    text = MASTER_PROMPT.read_text(encoding="utf-8")
    at = text.index(heading)
    fence_open = text.index("```", at)
    body_start = text.index("\n", fence_open) + 1
    fence_close = text.index("\n```", body_start)
    return text[body_start : fence_close + 1]


# --- acceptance 1: workspaces -------------------------------------------------


def test_pnpm_workspace_declared() -> None:
    ws = yaml.safe_load((REPO / "pnpm-workspace.yaml").read_text(encoding="utf-8"))
    assert "packages/*" in ws["packages"]
    assert "apps/*" in ws["packages"]


def test_root_package_json_engines() -> None:
    import json

    pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    assert pkg["private"] is True
    assert pkg["engines"]["node"].startswith(">=20.19.4")
    assert pkg["engines"]["pnpm"].startswith(">=9")
    dev = pkg.get("devDependencies", {})
    assert "@commitlint/cli" in dev and "@commitlint/config-conventional" in dev


def test_uv_workspace_declared() -> None:
    import tomllib

    root = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    members = root["tool"]["uv"]["workspace"]["members"]
    assert "packages/intake_platform" in members
    assert root["project"]["requires-python"] == ">=3.12"
    # mypy strict is config, not a CLI flag someone can forget
    assert root["tool"]["mypy"]["strict"] is True


def test_intake_platform_imports() -> None:
    import intake_platform

    assert re.fullmatch(r"\d+\.\d+\.\d+", intake_platform.__version__)


# --- acceptance 2: make check fan-out -----------------------------------------


def _make_database() -> str:
    out = subprocess.run(["make", "-npq"], cwd=REPO, capture_output=True, text=True, check=False)
    return out.stdout


def test_makefile_targets_exist() -> None:
    db = _make_database()
    for target in ("setup", "check", "check-py", "check-ts", "dev", "dev-down", "clean"):
        assert re.search(rf"^{target}:", db, re.M), f"missing make target: {target}"


def test_check_is_a_fanout_alias() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"^check:(.*)$", makefile, re.M)
    assert m, "no `check` target"
    assert "check-py" in m.group(1) and "check-ts" in m.group(1)


def test_check_py_runs_all_four_python_gates() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    body = makefile.split("check-py:")[1].split("\n\n")[0]
    for tool in ("ruff", "mypy", "pytest"):
        assert tool in body, f"check-py does not run {tool}"
    assert "--strict" in body or "strict" in body


def test_check_ts_runs_all_three_ts_gates() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    body = makefile.split("check-ts:")[1].split("\n\n")[0]
    for tool in ("lint", "typecheck", "test"):
        assert tool in body, f"check-ts does not run {tool}"


# --- acceptance 3: compose ------------------------------------------------------


def test_compose_dev_services() -> None:
    compose = yaml.safe_load(
        (REPO / "infra" / "docker-compose.dev.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    for name in ("postgres", "redis", "hapi", "minio"):
        assert name in services, f"missing service {name}"
        assert "healthcheck" in services[name], f"{name} has no healthcheck"
        assert ":" in services[name]["image"], f"{name} image is not tag-pinned"
    assert services["postgres"]["image"].startswith("pgvector/pgvector:pg16")
    # 00 §3 D8: openEHR/EHRbase is a P3 *export*. INT-032 built that tier, so
    # the services exist — but the default `make dev` tier must not start them,
    # or every P0 developer pays for a second JVM and a second Postgres for a
    # CDR no P0/P1 feature queries (HB-I1, HB-I2). The profile is the boundary.
    for name in ("ehrbase", "ehrbase-db"):
        assert name in services, f"missing service {name} (INT-032)"
        assert "healthcheck" in services[name], f"{name} has no healthcheck"
        assert ":" in services[name]["image"], f"{name} image is not tag-pinned"
        assert services[name].get("profiles") == ["export"], (
            f"{name} must sit behind the `export` profile — an EHRbase in the "
            "default P0 dev tier contradicts 00 §3 D8"
        )
    assert services["ehrbase"]["image"] == "ehrbase/ehrbase:2.35.1"


# --- acceptance 4: pre-commit + commitlint --------------------------------------


def test_precommit_hooks() -> None:
    cfg = yaml.safe_load((REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook_ids = {h["id"] for repo in cfg["repos"] for h in repo["hooks"]}
    for required in ("gitleaks", "semgrep", "ruff", "eslint", "commitlint"):
        assert any(required in h for h in hook_ids), f"missing pre-commit hook: {required}"


def test_commitlint_config_is_conventional() -> None:
    cfg = (REPO / "commitlint.config.cjs").read_text(encoding="utf-8")
    assert "@commitlint/config-conventional" in cfg


# --- governing documents: present, executable, and verbatim against files/07 ----

VERBATIM = {
    "CLAUDE.md": "### 3.1 `CLAUDE.md`",
    "docs/GOALS.md": "### 3.2 `docs/GOALS.md`",
    "docs/DoD.md": "### 3.3 `docs/DoD.md`",
    "docs/TDD.md": "### 3.4 `docs/TDD.md`",
    "LOOP.md": "### 3.5 `LOOP.md`",
    "PROMPT.md": "### 3.6 `PROMPT.md`",
    "loop.sh": "### 3.7 `loop.sh`",
    ".claude/settings.json": "### 3.8 `.claude/settings.json`",
}


def test_governing_docs_verbatim() -> None:
    for rel, heading in VERBATIM.items():
        expected = _extract_block(heading)
        actual = (REPO / rel).read_text(encoding="utf-8")
        assert actual == expected, f"{rel} is not verbatim against files/07 {heading}"


def test_loop_sh_and_hooks_executable() -> None:
    assert os.access(REPO / "loop.sh", os.X_OK), "loop.sh not executable"
    hooks = REPO / "scripts" / "hooks"
    for script in (
        "guard-bash.sh",
        "guard-protected-files.sh",
        "format-changed.sh",
        "assert-progress-entry.sh",
    ):
        assert os.access(hooks / script, os.X_OK), f"{script} missing or not executable"


def test_slash_commands_and_agents_present() -> None:
    commands = {
        "next-issue",
        "issue-start",
        "pr-open",
        "legal-review",
        "backlog-status",
        "ship",
        "clinical-review",
        "security-review",
        "new-pack",
        "threat-model",
        "slo",
        "runtime-review",
        "state-sync",
    }
    have = {p.stem for p in (REPO / ".claude" / "commands").glob("*.md")}
    assert commands <= have, f"missing commands: {commands - have}"
    agents = {
        "clinical-reviewer",
        "security-reviewer",
        "sre-reviewer",
        "runtime-reviewer",
        "test-writer",
        "legal-reviewer",
        "licence-auditor",
        "qa-gatekeeper",
    }
    have_agents = {p.stem for p in (REPO / ".claude" / "agents").glob("*.md")}
    assert agents <= have_agents, f"missing agents: {agents - have_agents}"


# --- backlog file (deep schema validation is INT-004) ---------------------------


def test_backlog_parses_and_is_complete() -> None:
    issues = yaml.safe_load((REPO / "docs" / "backlog" / "issues.yaml").read_text(encoding="utf-8"))
    ids = [i["id"] for i in issues]
    assert len(ids) == len(set(ids)), "duplicate issue ids"
    # 175 blueprint issues (07 §3.11) + INT-176..178 from the 2026-08-27
    # security review (tracker issue #195) + INT-294 (TTS admission eats the
    # clip deadline; the mute then latches) + INT-319 (dev on-prem TTS lane +
    # latency harness) + INT-320 (embeddable white-label integration, ADR-029)
    # + INT-321 (mobile intake mode chooser up front) + INT-322 (embed intake
    # mode bound inside the signed launch ticket) + INT-323 (department-dynamic
    # previsit routing); grows only with a stated reason.
    # previsit routing) + INT-372 (INT-354 slice S5, the visit-card chevron);
    # grows only with a stated reason.
    # previsit routing) + INT-370 (INT-354 slice S3, the visits calendar);
    # previsit routing) + INT-317 (previsit output store + hospital read-back,
    # filed on int-demo and carried to main by INT-354); grows only with a
    # stated reason.
    # previsit routing) ... + INT-376 (Frankfurt host move, split out of
    # INT-352; the full list is in tests/backlog/test_schema.py); grows only
    # with a stated reason.
    # previsit routing) + INT-318 (Acıbadem read source and /v1/visits/sync,
    # INT-354 slice S2); grows only with a stated reason.
    # previsit routing) + INT-377 (probe-results file fails closed on the
    # admin console, found by INT-181); grows only with a stated reason.
    # + INT-380 (INT-121 clause 3, the corpus score, awaiting-human) + INT-381
    # (INT-124's on-hardware latency and live smoke, gpu), both split out by
    # INT-124's PR; grows only with a stated reason.
    # + INT-385 (record quantities render with the locale's decimal separator,
    # found by INT-124's PR as GitHub #635); grows only with a stated reason.
    # previsit routing) + INT-373 (the Keycloak realm emits the admin
    # console's claims, found by INT-365); grows only with a stated reason.
    # previsit routing) + INT-392 (a session with a previsit output can be
    # deleted again, found on check-integration); grows only with a stated reason.
    # deleted again, found on check-integration) + INT-393 (a patient who issued
    # a Doctor Link can be erased, found by INT-392); grows only with a stated reason.
    # + INT-391 (the console accepts every valid WebAuthn credential id, found
    # by INT-378's PR as GitHub #646); grows only with a stated reason.
    # found by INT-124's PR as GitHub #635) + INT-386 (the typed rail, note,
    # summary and FHIR narrative quantities, INT-385's follow-up, GitHub #638);
    # grows only with a stated reason.
    # + INT-387 (the accessibility conformance report re-rated after the
    # INT-361..363 fixes, found by INT-360's PR as GitHub #640); grows only
    # with a stated reason.
    # + INT-397 (the three status lines INT-362 left silent are announced, found
    # by INT-387's MC-26 as GitHub #659); grows only with a stated reason.
    # + INT-390 (Keycloak upgrade and realm import, found by INT-378); grows
    # only with a stated reason.
    # + INT-396 (backlog status reconciliation and drift guard, GitHub #655);
    # grows only with a stated reason.
    # + INT-405 (the backlog sync pages past 500 issues and keeps issue state
    # in step with rows, found by INT-396, GitHub #675); grows only with a
    # stated reason.
    # + INT-398..400 (split out of INT-122 by its own PR, #663: the document
    # engine, the real samples, the on-device date-order defect); grows only
    # with a stated reason.
    # + INT-401 (console rollback, split out of INT-187) + INT-409 (Vizitlerim
    # reads today from the device clock instead of a date pinned in every
    # build, found by INT-179's close-out as GitHub #688); grows only with a
    # + INT-401 (console rollback, split out of INT-187) + INT-410 (release
    # bundles carry no synthetic seed accounts, audit F30, found by INT-179's
    # close-out as GitHub #689); grows only with a stated reason.
    # summary and FHIR narrative quantities, INT-385's follow-up, GitHub #638)
    # + INT-404 (triage rule evidence lines in the reader's locale, INT-386's
    # finding, GitHub #673); grows only with a stated reason.
    # ... + INT-382 (a suppress_slot in any layer that removes a slot a
    # red-flag rule reads is refused; H-1 of the PR #628 verification).
    # + INT-415 (ElevenLabs delivery profiles per question context and the
    # on-prem TTS wiring guide, owner request, GitHub #706); grows only with a
    # stated reason.
    # + INT-429 (the vulnerabilities gate: dependency upgrades and a time-boxed
    # node-forge exception, owner decision, GitHub #727); grows only with a
    # stated reason.
    # + INT-431 (the embed sample's JWT fixture is built at runtime, found
    # merging main into #481, GitHub #733); grows only with a stated reason.
    # + INT-395 (DSAR erasure and export cover every patient-deletable table,
    # found by INT-393); grows only with a stated reason.
    # + INT-406 (RED acknowledgement: the clinic Safety inbox and its SLA page,
    # invariant 49, found unowned by INT-020's PR as GitHub #681); grows only
    # with a stated reason.
    # + INT-426 (CI on AWS: the gate runner over S3 + SSM with the aws-ci
    # commit status, owner request, GitHub #721); grows only with a stated
    # reason.
    # + INT-407 (the files/02 §2b visit lifecycle state machine — a RED visit
    # cannot silently move; found by INT-406's PR as GitHub #684); grows only
    # with a stated reason.
    # + INT-432 (the clinical decisions register under owner decision D18,
    # GitHub #735); grows only with a stated reason.
    # + INT-378 (the Keycloak WebAuthn session-notes provider, GitHub #621) and
    # INT-389 (its TOTP clause, an owner decision, GitHub #644); grows only with
    # a stated reason.
    # + INT-448 (the #642 sign-off packet items under D18, GitHub #759); grows
    # only with a stated reason.
    # + INT-428 (hosted model lanes for the synthetic deployment, ADR-035,
    # GitHub #724); grows only with a stated reason.
    # + INT-442 (the synthetic host's egress forward proxy, split from INT-428,
    # GitHub #752); grows only with a stated reason.
    # + INT-424 (ElevenLabs delivery profiles v2 and the expressive-model ADR
    # proposal, owner request, GitHub #719); grows only with a stated reason.
    # + INT-443 (ElevenLabs as the synthetic host's hosted TTS, split from
    # INT-428, GitHub #753); grows only with a stated reason.
    assert len(ids) == 340, f"expected 175 blueprint + 165 added issues, got {len(ids)}"
    assert ids[0] == "INT-001" and "INT-253" in ids


# --- guards ----------------------------------------------------------------------


def test_no_vendor_calls_script() -> None:
    script = REPO / "scripts" / "ci" / "assert_no_vendor_calls.sh"
    assert os.access(script, os.X_OK)
    out = subprocess.run([str(script)], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, f"vendor-call scan failed:\n{out.stdout}{out.stderr}"


def test_env_example_has_no_secrets() -> None:
    # env.example, not .env.example: the agent harness denies writes to .env*
    # paths (the guard that protects the real .env). Documented in the file.
    env = (REPO / "env.example").read_text(encoding="utf-8")
    for line in env.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        _, value = line.split("=", 1)
        assert not re.search(r"(sk-|ghp_|AKIA|BEGIN [A-Z]+ PRIVATE KEY)", value), (
            "possible real secret in .env.example"
        )


def test_licences_present() -> None:
    root = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert "proprietary" in root.lower() or "all rights reserved" in root.lower()
    protocols = (REPO / "packages" / "protocols" / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in protocols and "Version 2.0" in protocols
