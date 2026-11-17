"""INT-206 — self-hosted runners in the TR DC + the no-PHI-in-CI policy.

Acceptance line under test, verbatim from docs/backlog/issues.yaml:
  "runner heartbeats probed; CI uses synthetic fixtures only (scan)"

Two halves, and the second is the substantive one.

**Runner heartbeats.** files/08 §6 gives the CI row of the self-hosting
registry as "GitHub Actions with self-hosted runners in the TR DC … probe:
runner heartbeat … fallback: GitHub-hosted runners (no PHI in CI ever)". The
probe and the pool declaration are built here; the pool list is EMPTY, and it
stays empty until a human supplies what nobody has — HB-I7 (does the owner spend
on CI capacity) and HB-L11 (physical residency is not legal residency, so "TR
DC" is a claim somebody has to defend). It is NOT HB-I5: that row is about GPU
supply, and a CI runner needs CPU. The gate therefore fails closed on any
self-hosted `runs-on` label, which is the correct posture — a runner label that
resolves to nothing is a job running somewhere nobody decided.

**No PHI in CI.** files/06 §5: "CI: no PHI, synthetic fixtures, TR-DC runners".
Invariant 6 is the law. The policy is enforced across six surfaces — fixtures,
env, logs, artefacts, cache and runners — and the detectors are the ones
:mod:`intake_platform.deid` already carries, so there is one definition of
"identifier-shaped" in this repo rather than two.

The scan's own output is part of the threat model: it runs in a CI job whose
stdout is a retained log, so a finding names a path, a line and a digest and
never the value it matched. A no-PHI gate that prints the PHI it found is the
leak.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from intake_platform.ci import (
    GITHUB_HOSTED_LABELS,
    RUNNER_POOL_ASK,
    CiPolicyError,
    IdentifierKind,
    RunsOnKind,
    Surface,
    evaluate_heartbeats,
    find_identifiers,
    identifier_digest,
    load_policy,
    load_runner_pools,
    load_workflows,
    resolve_runs_on,
    run_ci_policy,
    scan_environment,
    scan_fixture_tree,
    scan_workflows,
)
from intake_platform.ci.cli import main as cli_main

REPO = Path(__file__).resolve().parents[2]
POLICY_FILE = REPO / "infra" / "ci" / "no-phi-policy.yaml"
POOLS_FILE = REPO / "infra" / "ci" / "runners.yaml"
WORKFLOW_DIR = REPO / ".github" / "workflows"

# The canonical synthetic TC Kimlik this repo already uses for scrub tests
# (apps/mobile/src/lib/telemetry/scrub.ts, tests/platform/test_redaction.py).
# It is checksum-valid and belongs to nobody.
SYNTHETIC_TCKN = "10000000146"
SYNTHETIC_PHONE = "05321234567"
SYNTHETIC_IBAN = "TR330006100519786457841326"


# --- the identifier scanner ---------------------------------------------------------


def test_finds_the_four_identifier_classes() -> None:
    text = (
        f"tckn {SYNTHETIC_TCKN} tel {SYNTHETIC_PHONE} iban {SYNTHETIC_IBAN} mail hasta@ornek.com.tr"
    )
    kinds = {hit.kind for hit in find_identifiers(text)}
    assert kinds == {
        IdentifierKind.TCKN,
        IdentifierKind.PHONE,
        IdentifierKind.IBAN,
        IdentifierKind.EMAIL,
    }


def test_an_eleven_digit_order_id_is_not_a_tckn() -> None:
    """The checksum is the whole point: shredding every 11-digit run would make
    the gate noise, and noise is how a gate gets an allow-list."""
    assert find_identifiers("order 12345678901 processed") == ()


def test_a_date_is_not_an_identifier_here() -> None:
    """deid shifts dates because clinical intervals matter. A CI fixture full
    of ISO timestamps is not a PHI finding, and treating it as one would bury
    the classes that are."""
    assert find_identifiers("2026-08-27T10:00:01Z ve 27.08.2026 tarihinde") == ()


def test_a_hit_never_carries_the_matched_value() -> None:
    hits = find_identifiers(f"tckn {SYNTHETIC_TCKN}")
    assert len(hits) == 1
    rendered = repr(hits[0])
    assert SYNTHETIC_TCKN not in rendered
    assert hits[0].digest == identifier_digest(SYNTHETIC_TCKN)
    assert not hasattr(hits[0], "value")


def test_the_digest_is_stable_and_truncated() -> None:
    digest = identifier_digest(SYNTHETIC_TCKN)
    assert digest == hashlib.sha256(SYNTHETIC_TCKN.encode()).hexdigest()[:16]
    assert identifier_digest(SYNTHETIC_TCKN) == digest


# --- the policy declaration ----------------------------------------------------------


def test_the_committed_policy_loads() -> None:
    policy = load_policy(POLICY_FILE)
    assert policy.scanned_trees
    assert policy.synthetic_corpora


def test_every_declared_corpus_names_its_provenance_and_licence() -> None:
    for corpus in load_policy(POLICY_FILE).synthetic_corpora:
        assert corpus.provenance.strip()
        assert corpus.licence.strip()
        assert len(corpus.sha256) == 64


def test_every_declared_corpus_still_hashes_to_what_was_reviewed() -> None:
    """The hash is what makes the declaration a control rather than a label: a
    new identifier can only enter CI's fixture inputs through a reviewed change
    to this file."""
    for corpus in load_policy(POLICY_FILE).synthetic_corpora:
        target = REPO / corpus.path
        assert target.is_file(), f"declared corpus is missing: {corpus.path}"
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        assert actual == corpus.sha256, f"{corpus.path} changed since it was declared"


def test_an_unknown_policy_key_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "policy.yaml"
    bad.write_text(
        "scanned_trees: ['tests/fixtures']\nsynthetic_corpora: []\n"
        "cache_paths: []\nartefact_paths: []\npermitted_secrets: []\nallow_phi: true\n",
        encoding="utf-8",
    )
    with pytest.raises(CiPolicyError):
        load_policy(bad)


def test_a_corpus_without_a_hash_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "policy.yaml"
    bad.write_text(
        "scanned_trees: ['tests/fixtures']\n"
        "synthetic_corpora:\n"
        "  - path: tests/fixtures/x.jsonl\n"
        "    origin: authored\n"
        "    provenance: authored here\n"
        "    licence: proprietary\n"
        "cache_paths: []\nartefact_paths: []\npermitted_secrets: []\n",
        encoding="utf-8",
    )
    with pytest.raises(CiPolicyError):
        load_policy(bad)


# --- surface 1: fixtures --------------------------------------------------------------


def test_the_real_fixture_tree_is_clean() -> None:
    """Every identifier CI reads as data traces to a declared synthetic corpus."""
    findings = scan_fixture_tree(REPO, load_policy(POLICY_FILE))
    assert findings == (), [f"{f.where}: {f.detail}" for f in findings]


def test_an_undeclared_fixture_carrying_an_identifier_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    tree = tmp_path / "tests" / "fixtures"
    tree.mkdir(parents=True)
    (tree / "leak.jsonl").write_text(
        f'{{"text": "Hasta {SYNTHETIC_TCKN} geldi."}}\n', encoding="utf-8"
    )
    findings = scan_fixture_tree(tmp_path, policy)
    assert len(findings) == 1
    assert findings[0].surface is Surface.FIXTURES
    assert "leak.jsonl" in findings[0].where
    assert SYNTHETIC_TCKN not in findings[0].detail
    assert identifier_digest(SYNTHETIC_TCKN) in findings[0].detail


def test_a_declared_corpus_whose_bytes_changed_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    corpus = policy.synthetic_corpora[0]
    target = tmp_path / corpus.path
    target.parent.mkdir(parents=True)
    target.write_text(f"Hasta {SYNTHETIC_TCKN} geldi.\n", encoding="utf-8")
    findings = scan_fixture_tree(tmp_path, policy)
    assert any("no longer hashes" in f.detail for f in findings)


def test_a_fixture_with_no_identifiers_needs_no_declaration(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    tree = tmp_path / "tests" / "fixtures"
    tree.mkdir(parents=True)
    (tree / "plain.yaml").write_text("id: base.intake\nversion: 1\n", encoding="utf-8")
    assert scan_fixture_tree(tmp_path, policy) == ()


def test_a_binary_fixture_is_read_without_raising(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    tree = tmp_path / "tests" / "fixtures"
    tree.mkdir(parents=True)
    (tree / "clip.wav").write_bytes(b"RIFF\x00\xff\xfe\x00WAVE")
    assert scan_fixture_tree(tmp_path, policy) == ()


# --- surface 2: env -------------------------------------------------------------------


def test_a_phi_shaped_environment_variable_fails() -> None:
    findings = scan_environment({"PATIENT_TCKN": SYNTHETIC_TCKN, "PATH": "/usr/bin"})
    assert len(findings) == 1
    assert findings[0].surface is Surface.ENV
    assert findings[0].where == "PATIENT_TCKN"
    assert SYNTHETIC_TCKN not in findings[0].detail


def test_a_phi_shaped_variable_name_fails_even_with_an_empty_value() -> None:
    """The name is a disclosure too: `PATIENT_05321234567=` in a job's env is a
    phone number in the runner's process table."""
    findings = scan_environment({f"REF_{SYNTHETIC_PHONE}": ""})
    assert len(findings) == 1
    assert findings[0].surface is Surface.ENV


def test_an_ordinary_ci_environment_is_clean() -> None:
    assert scan_environment({"CI": "true", "GITHUB_SHA": "a" * 40, "HOME": "/root"}) == ()


def test_a_github_provided_environment_is_clean() -> None:
    """`make ci-policy` scans the runner's own environment, so the variables
    GitHub injects have to survive it. The numeric ones are the risk: the phone
    pattern matches a ten-digit run beginning 5 or 05, and a run id is eleven
    digits today. Pinned as a test rather than assumed, because the day a run id
    is ten digits again this fails here instead of in the owner's CI."""
    github = {
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "GITHUB_ACTOR": "ArioMoniri",
        "GITHUB_ACTOR_ID": "512345678",
        "GITHUB_JOB": "check-py",
        "GITHUB_REF": "refs/pull/352/merge",
        "GITHUB_REPOSITORY": "ArioMoniri/intake",
        "GITHUB_REPOSITORY_ID": "598765432",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "51234567890",
        "GITHUB_RUN_NUMBER": "512",
        "GITHUB_SHA": "b" * 40,
        "GITHUB_WORKFLOW": "ci",
        "GITHUB_WORKSPACE": "/home/runner/work/intake/intake",
        "RUNNER_ARCH": "X64",
        "RUNNER_NAME": "GitHub Actions 5",
        "RUNNER_OS": "Linux",
        "RUNNER_TEMP": "/home/runner/work/_temp",
    }
    findings = scan_environment(github)
    assert findings == (), [f"{f.where}: {f.detail}" for f in findings]


def test_an_author_chosen_branch_name_is_still_scanned() -> None:
    """The narrowing is a bare integer in a reserved variable, not the reserved
    variable itself: GITHUB_HEAD_REF carries a branch name the PR author picked,
    so it stays in scope."""
    findings = scan_environment({"GITHUB_HEAD_REF": f"fix-{SYNTHETIC_TCKN}"})
    assert len(findings) == 1
    assert findings[0].surface is Surface.ENV


def test_a_reserved_variable_holding_a_non_integer_is_still_scanned() -> None:
    findings = scan_environment({"GITHUB_REF": f"refs/heads/{SYNTHETIC_PHONE}"})
    assert len(findings) == 1


def test_an_ordinary_variable_holding_a_bare_integer_is_still_scanned() -> None:
    """Nothing outside GitHub's reserved namespace gets the narrowing — a
    workflow can set those, and a spoken TC Kimlik is exactly a bare integer."""
    findings = scan_environment({"SEED_ID": SYNTHETIC_TCKN})
    assert len(findings) == 1


# --- surfaces 3-6: the workflows ------------------------------------------------------


def test_the_committed_workflows_pass_the_policy() -> None:
    policy = load_policy(POLICY_FILE)
    pools = load_runner_pools(POOLS_FILE)
    findings = scan_workflows(load_workflows(WORKFLOW_DIR), policy, pools)
    assert findings == (), [f"{f.where}: {f.detail}" for f in findings]


def _write_workflow(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "workflows"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "w.yml").write_text(body, encoding="utf-8")
    return directory


_MINIMAL = """
name: w
on: [push]
permissions:
  contents: read
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: make check
"""


def test_a_minimal_workflow_passes(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    pools = load_runner_pools(POOLS_FILE)
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, _MINIMAL)), policy, pools)
    assert findings == ()


def test_uploading_a_synthetic_corpus_as_an_artefact_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    corpus = policy.synthetic_corpora[0].path
    body = (
        _MINIMAL
        + f"""
      - uses: actions/upload-artifact@v4
        with:
          name: corpus
          path: {corpus}
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any(f.surface is Surface.ARTEFACTS for f in findings)


def test_an_undeclared_cache_path_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + """
      - uses: actions/cache@v4
        with:
          path: /var/lib/intake/uploads
          key: k
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any(f.surface is Surface.CACHE for f in findings)
    assert all(
        "/var/lib/intake/uploads" in f.detail for f in findings if f.surface is Surface.CACHE
    )


def test_the_declared_cache_path_passes(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + f"""
      - uses: actions/cache@v4
        with:
          path: {policy.cache_paths[0]}
          key: k
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert not [f for f in findings if f.surface is Surface.CACHE]


def test_printing_a_synthetic_corpus_into_the_job_log_fails(tmp_path: Path) -> None:
    """A corpus is only synthetic because a human declared it so. Dumping one
    into a retained job log is the shape of the leak whether or not this
    particular corpus is real."""
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + f"""
      - run: cat {policy.synthetic_corpora[0].path}
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any(f.surface is Surface.LOGS for f in findings)


def test_a_phi_shaped_workflow_env_value_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = f"""
name: w
on: [push]
permissions:
  contents: read
env:
  SEED_TCKN: "{SYNTHETIC_TCKN}"
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: make check
"""
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any(f.surface is Surface.ENV for f in findings)
    assert all(SYNTHETIC_TCKN not in f.detail for f in findings)


def test_an_undeclared_secret_reference_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace(
        "      - run: make check",
        "      - run: make check\n        env:\n          K: ${{ secrets.HOSPITAL_FHIR_TOKEN }}",
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any("HOSPITAL_FHIR_TOKEN" in f.detail for f in findings)


def test_a_workflow_without_declared_permissions_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace("permissions:\n  contents: read\n", "")
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any("permissions" in f.detail for f in findings)


def test_a_write_all_permission_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace("permissions:\n  contents: read", "permissions: write-all")
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any("write-all" in f.detail for f in findings)


def test_an_unpinned_action_fails(tmp_path: Path) -> None:
    """ci.yml's own header: a tag can be silently repointed. The gate is what
    keeps that true after the header stops being read."""
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + """
      - uses: actions/checkout@v4
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any("not pinned" in f.detail for f in findings)


# --- runner pools ---------------------------------------------------------------------


def test_the_only_declared_pool_is_the_aws_ci_pool() -> None:
    """INT-463 declared intake-aws-ci on the owner's order of 3 Oct 2026. Every
    field was read from the host and the GitHub API. The TR-DC pool stays
    undeclared (HB-I7 spend for an in-country pool, HB-L11 residency), so no TR
    location, provider or hostname is invented."""
    pools = load_runner_pools(POOLS_FILE).pools
    assert [pool.label for pool in pools] == ["intake-aws-ci"]
    assert "Türkiye" in pools[0].location
    assert pools[0].ephemeral is True
    assert pools[0].phi_path is False


def test_the_pool_ask_names_the_blocker_rows() -> None:
    """HB-I7 (spend) and HB-L11 (physical residency is not legal residency) are
    what is open. HB-I5 is named to be ruled OUT: it records that no in-country
    provider is contracted, but that row is about GPU supply and a CI runner
    needs CPU — files/00_STATE.md §2 has the AWS Istanbul Local Zone GA with
    C7i/M7i/R7i, this shape exactly. Reading HB-I5 as the blocker would postpone
    a decision that is available to be made, so the ask says so."""
    assert "HB-I7" in RUNNER_POOL_ASK
    assert "HB-L11" in RUNNER_POOL_ASK
    assert "HB-I5" in RUNNER_POOL_ASK
    assert "GPU" in RUNNER_POOL_ASK


def _pool_yaml(**overrides: str) -> str:
    fields = {
        "label": "intake-tr-1",
        "location": "a named TR facility",
        "provider": "a contracted provider",
        "runner_group": "intake-tr",
        "ephemeral": "true",
        "phi_path": "false",
        "heartbeat_url": "http://127.0.0.1:9999/healthz",
        "max_heartbeat_age_s": "300",
    }
    fields.update(overrides)
    body = "\n".join(f"    {k}: {v}" for k, v in fields.items())
    return f"pools:\n  - \n{body}\n"


def test_a_pool_must_be_ephemeral(tmp_path: Path) -> None:
    """A persistent runner keeps a workspace between jobs; a job that ever
    touched patient-shaped data would leave it there for the next repository."""
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(ephemeral="false"), encoding="utf-8")
    with pytest.raises(CiPolicyError):
        load_runner_pools(path)


def test_a_pool_may_not_declare_itself_on_the_phi_path(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(phi_path="true"), encoding="utf-8")
    with pytest.raises(CiPolicyError):
        load_runner_pools(path)


def test_a_pool_with_an_empty_location_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(location='""'), encoding="utf-8")
    with pytest.raises(CiPolicyError):
        load_runner_pools(path)


def test_a_well_formed_pool_loads(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(), encoding="utf-8")
    pools = load_runner_pools(path)
    assert [pool.label for pool in pools.pools] == ["intake-tr-1"]


def test_a_github_hosted_label_resolves() -> None:
    resolution = resolve_runs_on("ubuntu-latest", load_runner_pools(POOLS_FILE))
    assert resolution.kind is RunsOnKind.GITHUB_HOSTED
    assert "ubuntu-latest" in GITHUB_HOSTED_LABELS


def test_an_undeclared_self_hosted_label_fails_closed() -> None:
    """The TR-DC label is still undeclared, so it resolves to nothing."""
    resolution = resolve_runs_on(["self-hosted", "intake-tr-1"], load_runner_pools(POOLS_FILE))
    assert resolution.kind is RunsOnKind.UNRESOLVED
    assert "HB-I7" in resolution.reason


def test_a_self_hosted_label_resolves_once_its_pool_is_declared(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(), encoding="utf-8")
    resolution = resolve_runs_on(["self-hosted", "intake-tr-1"], load_runner_pools(path))
    assert resolution.kind is RunsOnKind.SELF_HOSTED
    assert resolution.pool is not None
    assert resolution.pool.label == "intake-tr-1"


def test_an_unknown_hosted_label_is_unresolved() -> None:
    resolution = resolve_runs_on("plan9-latest", load_runner_pools(POOLS_FILE))
    assert resolution.kind is RunsOnKind.UNRESOLVED


def test_a_bare_self_hosted_label_names_the_ask() -> None:
    resolution = resolve_runs_on("self-hosted", load_runner_pools(POOLS_FILE))
    assert resolution.kind is RunsOnKind.UNRESOLVED
    assert "self-hosted" in resolution.reason


def test_an_unreadable_pool_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text("pools: [ unclosed\n", encoding="utf-8")
    with pytest.raises(CiPolicyError):
        load_runner_pools(path)


def test_an_empty_pool_file_reads_as_no_pools(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text("# nothing declared yet\n", encoding="utf-8")
    assert load_runner_pools(path).pools == ()


def test_an_unreadable_policy_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text("scanned_trees: [ unclosed\n", encoding="utf-8")
    with pytest.raises(CiPolicyError):
        load_policy(path)


def test_a_workflow_naming_an_unregistered_self_hosted_runner_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace("runs-on: ubuntu-latest", "runs-on: [self-hosted, intake-tr-1]")
    findings = scan_workflows(
        load_workflows(_write_workflow(tmp_path, body)), policy, load_runner_pools(POOLS_FILE)
    )
    assert any(f.surface is Surface.RUNNERS for f in findings)


def test_a_runner_group_runs_on_is_read_through_its_labels(tmp_path: Path) -> None:
    """`runs-on: {group: …, labels: […]}` is the form a runner-group pool uses;
    the labels are what selects, so that is what resolution reads."""
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace(
        "runs-on: ubuntu-latest",
        "runs-on:\n      group: intake-tr\n      labels: [self-hosted, intake-tr-1]",
    )
    findings = scan_workflows(
        load_workflows(_write_workflow(tmp_path, body)), policy, load_runner_pools(POOLS_FILE)
    )
    assert any(f.surface is Surface.RUNNERS for f in findings)


def test_a_single_label_runner_group_form_is_read(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace(
        "runs-on: ubuntu-latest",
        "runs-on:\n      group: hosted\n      labels: ubuntu-latest",
    )
    findings = scan_workflows(
        load_workflows(_write_workflow(tmp_path, body)), policy, load_runner_pools(POOLS_FILE)
    )
    assert not [f for f in findings if f.surface is Surface.RUNNERS]


def test_a_job_with_no_runs_on_is_unresolved(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = "name: w\non: [push]\npermissions:\n  contents: read\njobs:\n  j:\n    steps: []\n"
    findings = scan_workflows(
        load_workflows(_write_workflow(tmp_path, body)), policy, load_runner_pools(POOLS_FILE)
    )
    assert any(f.surface is Surface.RUNNERS for f in findings)


def test_a_local_action_reference_needs_no_pin(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + """
      - uses: ./.github/actions/setup
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert not [f for f in findings if "not pinned" in f.detail]


def test_a_multi_line_cache_path_is_split(tmp_path: Path) -> None:
    """`path:` takes a block of newline-separated paths; every one is checked,
    so a declared path cannot carry an undeclared one in with it."""
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + f"""
      - uses: actions/cache@{"a" * 40}
        with:
          path: |
            {policy.cache_paths[0]}
            second/path
          key: k
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    caches = [f for f in findings if f.surface is Surface.CACHE]
    assert len(caches) == 1
    assert "second/path" in caches[0].detail


def test_a_list_valued_artefact_path_is_split(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + f"""
      - uses: actions/upload-artifact@{"b" * 40}
        with:
          path:
            - reports/one
            - reports/two
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    artefacts = [f for f in findings if f.surface is Surface.ARTEFACTS]
    assert len(artefacts) == 2


def test_a_step_with_no_path_input_is_ignored(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = (
        _MINIMAL
        + f"""
      - uses: actions/cache@{"c" * 40}
        with:
          key: k
"""
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert not [f for f in findings if f.surface is Surface.CACHE]


def test_a_job_level_write_all_permission_fails(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace(
        "    runs-on: ubuntu-latest", "    permissions: write-all\n    runs-on: ubuntu-latest"
    )
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert any("write-all" in f.detail for f in findings)


def test_a_read_all_permission_is_accepted(tmp_path: Path) -> None:
    policy = load_policy(POLICY_FILE)
    body = _MINIMAL.replace("permissions:\n  contents: read", "permissions: read-all")
    findings = scan_workflows(load_workflows(_write_workflow(tmp_path, body)), policy, pools=None)
    assert findings == ()


def test_an_unparseable_workflow_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "workflows"
    directory.mkdir(parents=True)
    (directory / "broken.yml").write_text("jobs: [ unclosed\n", encoding="utf-8")
    with pytest.raises(CiPolicyError):
        load_workflows(directory)


def test_a_missing_workflow_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CiPolicyError):
        load_workflows(tmp_path / "absent")


def test_a_non_yaml_file_in_the_workflow_directory_is_skipped(tmp_path: Path) -> None:
    directory = _write_workflow(tmp_path, _MINIMAL)
    (directory / "README.md").write_text("notes\n", encoding="utf-8")
    assert len(load_workflows(directory)) == 1


# --- the heartbeat --------------------------------------------------------------------


def test_heartbeats_with_no_pool_report_nothing_to_check(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text("pools: []\n", encoding="utf-8")
    report = evaluate_heartbeats(load_runner_pools(path), seen={}, now=0.0)
    assert report.checked == ()
    assert report.healthy is False
    assert "HB-I7" in report.detail


def test_a_fresh_heartbeat_is_healthy(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(), encoding="utf-8")
    pools = load_runner_pools(path)
    report = evaluate_heartbeats(pools, seen={"intake-tr-1": 1000.0}, now=1010.0)
    assert report.healthy is True
    assert report.checked == ("intake-tr-1",)
    assert report.stale == ()
    assert report.missing == ()


def test_a_stale_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(max_heartbeat_age_s="300"), encoding="utf-8")
    pools = load_runner_pools(path)
    report = evaluate_heartbeats(pools, seen={"intake-tr-1": 1000.0}, now=1400.0)
    assert report.healthy is False
    assert report.stale == ("intake-tr-1",)


def test_a_missing_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(), encoding="utf-8")
    report = evaluate_heartbeats(load_runner_pools(path), seen={}, now=1.0)
    assert report.healthy is False
    assert report.missing == ("intake-tr-1",)


def test_the_probe_is_wired_into_the_registry() -> None:
    from intake_probes.registry import ProbeId, load_registry

    registry = load_registry(REPO / "observability" / "registry.yaml")
    row = registry.get("ci-runners")
    assert row.probe is ProbeId.RUNNER_HEARTBEAT
    # files/08 §6: the fallback is GitHub-hosted runners, "no PHI in CI ever".
    assert row.phi_path is False
    assert row.self_hosted_now is False


def test_the_probe_reports_the_blocker_rather_than_a_fake_result(tmp_path: Path) -> None:
    from intake_probes.probes import Skipped, runner_heartbeat

    path = tmp_path / "runners.yaml"
    path.write_text("pools: []\n", encoding="utf-8")
    outcome = runner_heartbeat(load_runner_pools(path), seen={}, now=0.0)
    assert isinstance(outcome, Skipped)
    assert "HB-I7" in outcome.reason


def test_the_declared_pool_without_a_collected_heartbeat_is_not_healthy() -> None:
    """INT-463 declares intake-aws-ci, and no collector reads its status into
    the sweep yet. A missing heartbeat must report as a failure, never as
    healthy and never as skipped."""
    from intake_probes.probes import Failed, runner_heartbeat

    outcome = runner_heartbeat(load_runner_pools(POOLS_FILE), seen={}, now=0.0)
    assert isinstance(outcome, Failed)
    assert "intake-aws-ci" in outcome.detail


def test_the_probe_fails_on_a_stale_pool(tmp_path: Path) -> None:
    from intake_probes.probes import Failed, runner_heartbeat

    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(max_heartbeat_age_s="60"), encoding="utf-8")
    outcome = runner_heartbeat(load_runner_pools(path), seen={"intake-tr-1": 0.0}, now=600.0)
    assert isinstance(outcome, Failed)


def test_the_probe_is_ok_on_a_fresh_pool(tmp_path: Path) -> None:
    from intake_probes.probes import Ok, runner_heartbeat

    path = tmp_path / "runners.yaml"
    path.write_text(_pool_yaml(), encoding="utf-8")
    outcome = runner_heartbeat(load_runner_pools(path), seen={"intake-tr-1": 590.0}, now=600.0)
    assert isinstance(outcome, Ok)


# --- the whole policy, and its own output ---------------------------------------------


def test_the_repository_passes_the_policy_today() -> None:
    findings = run_ci_policy(REPO, env={"CI": "true"})
    assert findings == (), [f"{f.surface}/{f.where}: {f.detail}" for f in findings]


def test_the_cli_exits_zero_on_this_repository() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "intake_platform.ci", "--repo", str(REPO)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_cli_exits_one_and_prints_no_identifier(tmp_path: Path) -> None:
    """The gate runs in a job whose stdout is a retained log (files/10 §6:
    30 d hot / 1 y cold). Its own report must not be the disclosure."""
    (tmp_path / "infra" / "ci").mkdir(parents=True)
    (tmp_path / "infra" / "ci" / "no-phi-policy.yaml").write_text(
        POLICY_FILE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "infra" / "ci" / "runners.yaml").write_text(
        POOLS_FILE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    tree = tmp_path / "tests" / "fixtures"
    tree.mkdir(parents=True)
    (tree / "leak.txt").write_text(f"tckn {SYNTHETIC_TCKN}\n", encoding="utf-8")

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "intake_platform.ci", "--repo", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert SYNTHETIC_TCKN not in combined
    assert identifier_digest(SYNTHETIC_TCKN) in combined


def _policy_repo(tmp_path: Path) -> Path:
    (tmp_path / "infra" / "ci").mkdir(parents=True)
    (tmp_path / "infra" / "ci" / "no-phi-policy.yaml").write_text(
        POLICY_FILE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "infra" / "ci" / "runners.yaml").write_text(
        POOLS_FILE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def test_the_cli_main_returns_zero_on_a_clean_tree(tmp_path: Path) -> None:
    assert cli_main(["--repo", str(_policy_repo(tmp_path))]) == 0


def test_the_cli_main_scans_its_own_environment_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--scan-environment is the one surface a test cannot reach from outside
    the job: the runner's own environment."""
    repo = _policy_repo(tmp_path)
    monkeypatch.setenv("SEED_PATIENT_TCKN", SYNTHETIC_TCKN)
    assert cli_main(["--repo", str(repo), "--scan-environment"]) == 1
    assert cli_main(["--repo", str(repo)]) == 0


def test_the_cli_main_reports_an_unreadable_policy_rather_than_passing(tmp_path: Path) -> None:
    """A policy file that cannot be parsed is a failure, never "no rules"."""
    (tmp_path / "infra" / "ci").mkdir(parents=True)
    (tmp_path / "infra" / "ci" / "no-phi-policy.yaml").write_text(
        "scanned_trees: [ unclosed\n", encoding="utf-8"
    )
    (tmp_path / "infra" / "ci" / "runners.yaml").write_text("pools: []\n", encoding="utf-8")
    assert cli_main(["--repo", str(tmp_path)]) == 1
