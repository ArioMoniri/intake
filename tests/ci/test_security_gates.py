"""INT-019 — the security gate set: scanners, SBOM, signing, PHI/claims scans.

Acceptance (docs/backlog/issues.yaml INT-019), verbatim:

1. "gitleaks, semgrep+bandit, eslint-security, trivy fs/image/IaC + osv-scanner
   fail on critical/high, checkov, license allow-list (AGPL flagged), syft SBOM
   artifact, cosign keyless signing + SLSA provenance for images and protocol
   bundles on tags, schemathesis fuzz, PHI-pattern scan of fixtures"
2. "`make security` runs the same list locally; planted secret, planted critical
   CVE and planted PHI each fail (proved in evidence, then reverted)"

What this file pins, in the order the acceptance states it:

  - `.github/workflows/security.yml` exists, parses, triggers on PR / main /
    `v*` tags, pins every action to a full commit sha with the resolved tag in
    a trailing comment, declares read-only default permissions, and names every
    gate in the set.
  - `scripts/ci/security_gates.sh` — the local driver `make security` calls —
    declares the SAME ordered gate list as the workflow. That is acceptance
    clause 2's "runs the same list locally", pinned rather than asserted in
    prose, and it is the reason the list lives in exactly one place.
  - No gate may skip. A gate whose scanner is absent FAILS with a named error
    and an install hint; `|| true`, `continue-on-error` and `if: always()`
    shapes are refused by a text assertion over both files (CLAUDE.md
    invariant 14: the gates are never skipped, and disabling one is on the
    stop-and-ask list).
  - `scripts/ci/phi_scan.sh` catches a checksum-valid TCKN, an 05x mobile and a
    TR IBAN, withholds the matched value from its own output (invariant 6), and
    takes its fixture exemptions from the sha256-pinned corpus declarations in
    `infra/ci/no-phi-policy.yaml` (INT-206) instead of keeping a second,
    disagreeing list. Only `docs/**` has a prefix allow-list, and it may only
    shrink.
  - `scripts/ci/claims_scan.sh` catches performance-claim language in
    docs/regulatory, docs/legal and store copy (invariant 20).
  - `scripts/ci/check_licenses.py` fails an AGPL dependency, fails an unknown
    licence, and accepts the permissive allow-list including OR/AND expressions
    (invariant 19).
  - `scripts/ci/protocol_bundles.sh` — the protocol-bundle half of the signing
    path — enumerates the files a tag build signs and fails closed when the
    emit directory is empty, which is today's state (HB-C1: no pack compiles).
  - `security.yml` stays inside the INT-206 no-PHI-in-CI policy: it hands no
    path to `actions/upload-artifact` while `artefact_paths` in
    `infra/ci/no-phi-policy.yaml` is empty.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
#: `.github/workflows/security.yml` is hook-protected
#: (scripts/hooks/guard-protected-files.sh; 07 §3.8 / §F rule 2) and the guard
#: refused its creation from the session that built this issue — which is the
#: protection working. The byte-final content is committed at the template
#: path; every content assertion below reads whichever copy exists, and
#: `test_workflow_is_installed` stays RED until a human runs the sanctioned
#: move. The gate set is not done while it is not installed.
WORKFLOW_INSTALLED = REPO / ".github" / "workflows" / "security.yml"
WORKFLOW_TEMPLATE = REPO / "scripts" / "ci" / "security_workflow.yml"
WORKFLOW = WORKFLOW_INSTALLED if WORKFLOW_INSTALLED.exists() else WORKFLOW_TEMPLATE
DRIVER = REPO / "scripts" / "ci" / "security_gates.sh"
PHI_SCAN = REPO / "scripts" / "ci" / "phi_scan.sh"
PHI_ALLOW = REPO / "scripts" / "ci" / "phi_scan_docs_allow.txt"
TCKN_HELPER = REPO / "scripts" / "ci" / "tckn_check.py"
CLAIMS_SCAN = REPO / "scripts" / "ci" / "claims_scan.sh"
LICENCES = REPO / "scripts" / "ci" / "check_licenses.py"
BUNDLES = REPO / "scripts" / "ci" / "protocol_bundles.sh"
NO_PHI_POLICY = REPO / "infra" / "ci" / "no-phi-policy.yaml"
OSV_GATE = REPO / "scripts" / "ci" / "osv_severity_gate.py"
BANDIT_BASELINE = REPO / "scripts" / "ci" / "bandit_baseline.json"
CHECKOV_BASELINE = REPO / "scripts" / "ci" / "checkov_baseline.json"
ESLINT_BASELINE = REPO / "scripts" / "ci" / "eslint_security_baseline.json"

#: The gate set, in the order both the workflow and the local driver run it.
#: Every entry of invariant 14's list appears here; `trivy` is three gates
#: because the acceptance names fs, image and IaC separately.
EXPECTED_GATES = (
    "gitleaks",
    "semgrep",
    "bandit",
    "eslint-security",
    "trivy-fs",
    "trivy-image",
    "trivy-iac",
    "osv-scanner",
    "checkov",
    "licences",
    "sbom",
    "schemathesis",
    "phi-scan",
    "claims-scan",
    "ci-policy",
)


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args], cwd=REPO, capture_output=True, text=True, check=False
    )


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _driver_text() -> str:
    return DRIVER.read_text(encoding="utf-8")


def _driver_gates() -> list[str]:
    """The ordered gate ids declared by the local driver."""
    match = re.search(r"^GATES=\(\s*(.*?)^\)", _driver_text(), re.M | re.S)
    assert match, "scripts/ci/security_gates.sh declares no GATES=( ... ) array"
    return re.findall(r'"([a-z0-9-]+)"', match.group(1))


# --- the workflow exists and is well formed ------------------------------------------


def test_workflow_is_installed() -> None:
    """RED until a human places the gate set under ALLOW_PROTECTED=1.

    A workflow only runs from .github/workflows/. The content is committed and
    fully pinned, and every other test here reads it — but a gate set that is
    not installed does not gate anything, so this test fails until:

        ALLOW_PROTECTED=1 git mv scripts/ci/security_workflow.yml \\
            .github/workflows/security.yml

    (and the template is deleted in that same commit). Fail-closed, not a
    workaround: nothing merges with the gate set silently absent.
    """
    assert WORKFLOW_INSTALLED.is_file(), (
        ".github/workflows/security.yml is not installed — the gate set is not live "
        "until the human-sanctioned move from scripts/ci/security_workflow.yml "
        "(see docs/evidence/INT-019.md)"
    )


def test_installed_copy_matches_the_template_while_both_exist() -> None:
    """During the transition commit both copies may exist; they must not drift."""
    if WORKFLOW_INSTALLED.exists() and WORKFLOW_TEMPLATE.exists():
        assert WORKFLOW_INSTALLED.read_bytes() == WORKFLOW_TEMPLATE.read_bytes(), (
            "the installed security.yml drifted from scripts/ci/security_workflow.yml — "
            "delete the template in the commit that installs the workflow"
        )


def test_workflow_passes_the_int_206_no_phi_ci_policy(tmp_path: Path) -> None:
    """The workflow is checked by INT-206's policy engine before it is
    installed, not after: pinned actions, declared scopes, no repository
    secret, no undeclared cache or artefact path, no corpus named in a run
    step. Once installed, tests/infra/test_ci_no_phi.py checks it in place."""
    from intake_platform.ci.policy import load_policy, scan_workflows
    from intake_platform.ci.workflows import load_workflows

    staged = tmp_path / "workflows"
    staged.mkdir()
    (staged / "security.yml").write_bytes(WORKFLOW.read_bytes())
    findings = scan_workflows(load_workflows(staged), load_policy(NO_PHI_POLICY), None)
    assert not findings, "\n".join(f"{f.surface}: {f.where}: {f.detail}" for f in findings)


def test_security_workflow_parses() -> None:
    wf = yaml.safe_load(_workflow_text())
    assert isinstance(wf, dict) and wf.get("jobs"), "security workflow has no jobs"


def test_security_workflow_triggers() -> None:
    wf = yaml.safe_load(_workflow_text())
    on = wf.get("on", wf.get(True))  # YAML 1.1 reads a bare `on` as boolean True
    assert on is not None, "no trigger block"
    assert "pull_request" in on
    assert "main" in on["push"]["branches"]
    assert "v*" in on["push"]["tags"], "signing runs on tags, so the trigger needs v*"


def test_every_action_is_full_sha_pinned() -> None:
    """ci.yml's supply-chain rule: a tag can be silently repointed, a sha cannot."""
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)\s*(#.*)?$", _workflow_text(), re.M)
    assert uses, "no `uses:` lines found"
    for ref, comment in uses:
        action, _, pin = ref.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", pin), f"{action} not pinned to a full sha: {pin!r}"
        assert comment.strip().startswith("#"), f"{action}: missing the resolved-tag comment"


def test_workflow_default_permissions_are_read_only() -> None:
    wf = yaml.safe_load(_workflow_text())
    assert wf["permissions"] == {"contents": "read"}


# --- the gate set, and the same list locally -------------------------------------------


def test_workflow_names_every_gate() -> None:
    text = _workflow_text()
    for gate in EXPECTED_GATES:
        assert re.search(rf"gate:\s*{re.escape(gate)}\b", text), (
            f"security.yml does not declare gate: {gate}"
        )


def test_driver_declares_the_same_ordered_gate_list() -> None:
    """Acceptance clause 2 — `make security` runs the same list, in one place."""
    assert _driver_gates() == list(EXPECTED_GATES)


def test_every_invariant_14_tool_is_named() -> None:
    """The driver is where every tool is actually invoked, so every name in
    invariant 14's list must appear there. The workflow names the gate ids
    (pinned above) plus the tools it installs or runs itself."""
    for tool in (
        "gitleaks",
        "semgrep",
        "bandit",
        "eslint",
        "trivy",
        "osv-scanner",
        "checkov",
        "check_licenses",
        "syft",
        "schemathesis",
        "phi_scan",
        "claims_scan",
    ):
        assert tool in _driver_text(), f"invariant-14 tool missing from the local driver: {tool}"
    for tool in ("gitleaks", "trivy", "osv-scanner", "syft", "cosign", "security_gates.sh"):
        assert tool in _workflow_text(), f"invariant-14 tool missing from security.yml: {tool}"


def test_vulnerability_gates_fail_on_critical_and_high() -> None:
    for text, where in ((_workflow_text(), "security.yml"), (_driver_text(), "the driver")):
        assert "CRITICAL,HIGH" in text, f"trivy must fail on critical/high in {where}"
        assert "CRITICAL,HIGH" in text or "CRITICAL" in text
    assert re.search(r"osv-scanner", _driver_text())


# --- no gate may skip -------------------------------------------------------------------


def test_no_gate_is_softened() -> None:
    """Invariant 14: never skipped. No `|| true`, no continue-on-error, no if: always()."""
    for path in (WORKFLOW, DRIVER, PHI_SCAN, CLAIMS_SCAN, BUNDLES):
        text = path.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        assert "continue-on-error" not in body, f"{path.name}: continue-on-error softens a gate"
        assert "|| true" not in body, f"{path.name}: `|| true` softens a gate"
        assert "if: always()" not in body, f"{path.name}: if: always() softens a gate"


def test_a_missing_scanner_fails_with_an_install_hint() -> None:
    """A gate whose scanner is absent must FAIL, loudly and by name."""
    text = _driver_text()
    assert "require_tool" in text, "the driver needs one presence check per binary tool"
    assert text.count("command -v") >= 1
    assert "not installed" in text, "a missing tool must say so"
    assert "install:" in text, "a missing tool must print how to install it"


def test_absent_scanner_is_reported_as_a_failure_not_a_skip() -> None:
    """The driver's own vocabulary: PASS or FAIL, never SKIP."""
    body = "\n".join(
        line for line in _driver_text().splitlines() if not line.lstrip().startswith("#")
    )
    assert "SKIP" not in body, "the driver must have no skip verdict at all"
    assert "PASS" in body and "FAIL" in body, "the driver's only verdicts are PASS and FAIL"


# --- signing: images and protocol bundles, keyless, on tags ------------------------------


def test_signing_is_tags_only_keyless_with_slsa_provenance() -> None:
    text = _workflow_text()
    assert "startsWith(github.ref, 'refs/tags/v')" in text
    assert "id-token: write" in text, "cosign keyless needs the OIDC token"
    assert "attestations: write" in text, "SLSA provenance needs the attestations scope"
    assert "attest-build-provenance" in text
    assert "cosign" in text and "sign-blob" in text


def test_signing_covers_both_images_and_protocol_bundles() -> None:
    text = _workflow_text()
    assert re.search(r"gate:\s*sign-protocol-bundles\b", text)
    assert re.search(r"gate:\s*sign-images\b", text)


def test_protocol_bundle_enumerator_fails_closed_on_an_empty_emit_dir(tmp_path: Path) -> None:
    """HB-C1: no pack compiles today, so a tag build has nothing to sign — and
    signing nothing must fail, not silently succeed."""
    empty = tmp_path / "dist"
    empty.mkdir()
    out = run_script(BUNDLES, str(empty))
    assert out.returncode == 1, f"an empty emit dir must fail closed:\n{out.stdout}{out.stderr}"
    assert "no protocol bundle" in (out.stdout + out.stderr).lower()


def test_protocol_bundle_enumerator_ignores_a_gitkeep(tmp_path: Path) -> None:
    """packages/protocols/dist/ is held in git by a .gitkeep. Counting it as a
    signing subject would let a tag sign one empty marker file and call the
    release signed — the exact failure this enumerator exists to prevent."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / ".gitkeep").write_text("", encoding="utf-8")
    out = run_script(BUNDLES, str(dist))
    assert out.returncode == 1, out.stdout + out.stderr
    assert "no protocol bundle" in (out.stdout + out.stderr).lower()


def test_protocol_bundle_enumerator_matches_the_real_emit_root_today() -> None:
    """HB-C1: no pack compiles, so the committed emit root holds no bundle and
    `make sign` refuses. If this ever passes, a pack compiled — and the signing
    path is then exercised for real."""
    out = run_script(BUNDLES)
    assert out.returncode == 1, f"packages/protocols/dist is no longer empty:\n{out.stdout}"


def test_protocol_bundle_enumerator_lists_what_a_tag_would_sign(tmp_path: Path) -> None:
    dist = tmp_path / "dist" / "cluster.msk"
    dist.mkdir(parents=True)
    (dist / "pack.json").write_text("{}\n", encoding="utf-8")
    (dist / "clips.json").write_text("{}\n", encoding="utf-8")
    out = run_script(BUNDLES, str(tmp_path / "dist"))
    assert out.returncode == 0, out.stdout + out.stderr
    listed = out.stdout.split()
    assert any(line.endswith("cluster.msk/pack.json") for line in listed)
    assert any(line.endswith("cluster.msk/clips.json") for line in listed)


# --- the workflow stays inside the INT-206 no-PHI-in-CI policy ---------------------------


def test_workflow_uploads_no_undeclared_artefact_path() -> None:
    """`artefact_paths` in infra/ci/no-phi-policy.yaml is empty, so security.yml
    may hand no path to actions/upload-artifact (INT-206 owns that list)."""
    policy = yaml.safe_load(NO_PHI_POLICY.read_text(encoding="utf-8"))
    declared = policy.get("artefact_paths") or []
    wf = yaml.safe_load(_workflow_text())
    for job_name, job in wf["jobs"].items():
        for step in job.get("steps", []):
            uses = str(step.get("uses", ""))
            if uses.startswith("actions/upload-artifact"):
                path = str((step.get("with") or {}).get("path", ""))
                assert path in declared, (
                    f"{job_name} uploads {path!r}, which infra/ci/no-phi-policy.yaml "
                    "does not declare in artefact_paths"
                )


# --- the scripts exist and are executable --------------------------------------------


def test_gate_scripts_exist_and_are_executable() -> None:
    for script in (DRIVER, PHI_SCAN, CLAIMS_SCAN, BUNDLES):
        assert os.access(script, os.X_OK), f"{script.name} missing or not executable"
    for helper in (TCKN_HELPER, LICENCES):
        assert helper.is_file(), f"{helper.name} missing"


def test_make_targets_exist() -> None:
    out = subprocess.run(["make", "-npq"], cwd=REPO, capture_output=True, text=True, check=False)
    for target in ("security", "safety", "sign"):
        assert re.search(rf"^{target}:", out.stdout, re.M), f"missing make target: {target}"


def test_make_security_calls_the_driver() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    body = makefile.split("\nsecurity:")[1].split("\n\n")[0]
    assert "scripts/ci/security_gates.sh" in body


# --- licence allow-list (invariant 19: AGPL flagged) --------------------------------------


def _fake_node_package(root: Path, name: str, licence: str) -> None:
    pkg = root / name
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text(
        f'{{"name": "{name}", "version": "1.0.0", "license": "{licence}"}}\n', encoding="utf-8"
    )


def _run_licences(node_modules: Path, python_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(LICENCES),
            "--node-modules",
            str(node_modules),
            "--python-path",
            str(python_path),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_licence_gate_rejects_agpl(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "fine-lib", "MIT")
    _fake_node_package(nm, "viral-lib", "AGPL-3.0-only")
    site = tmp_path / "site"
    site.mkdir()
    out = _run_licences(nm, site)
    assert out.returncode == 1, f"AGPL must fail:\n{out.stdout}{out.stderr}"
    assert "viral-lib" in out.stdout and "AGPL" in out.stdout


def test_licence_gate_rejects_unknown(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "mystery-lib", "SEE LICENSE IN LICENSE.txt")
    site = tmp_path / "site"
    site.mkdir()
    out = _run_licences(nm, site)
    assert out.returncode == 1, "an unresolvable licence must fail, not pass silently"
    assert "mystery-lib" in out.stdout


def test_licence_gate_accepts_the_allow_list(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    for i, licence in enumerate(
        ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0", "Zlib")
    ):
        _fake_node_package(nm, f"lib-{i}", licence)
    _fake_node_package(nm, "dual-lib", "(MIT OR GPL-3.0-only)")
    _fake_node_package(nm, "joint-lib", "MIT AND Apache-2.0")
    site = tmp_path / "site"
    site.mkdir()
    out = _run_licences(nm, site)
    assert out.returncode == 0, f"the permissive set must pass:\n{out.stdout}{out.stderr}"


def test_licence_gate_and_with_a_denied_side_fails(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "tainted-lib", "MIT AND AGPL-3.0-only")
    site = tmp_path / "site"
    site.mkdir()
    assert _run_licences(nm, site).returncode == 1


def test_licence_gate_reads_python_dist_info(tmp_path: Path) -> None:
    site = tmp_path / "site"
    dist = site / "agpl_pkg-1.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: agpl-pkg\nVersion: 1.0\nLicense-Expression: AGPL-3.0-only\n",
        encoding="utf-8",
    )
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "fine-lib", "MIT")
    out = _run_licences(nm, site)
    assert out.returncode == 1
    assert "agpl-pkg" in out.stdout


# --- PHI-pattern scan ----------------------------------------------------------------------


def _valid_tckn(stem: str) -> str:
    """Built here independently so the helper is pinned, not mirrored."""
    d = [int(c) for c in stem]
    assert len(d) == 9 and d[0] != 0
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = (sum(d) + d10) % 10
    return stem + str(d10) + str(d11)


def test_phi_scan_catches_a_checksum_valid_tckn(tmp_path: Path) -> None:
    planted = tmp_path / "fixture.json"
    planted.write_text(f'{{"note": "kimlik {_valid_tckn("523467891")}"}}\n', encoding="utf-8")
    out = run_script(PHI_SCAN, str(planted))
    assert out.returncode == 1, f"a checksum-valid TCKN was not caught:\n{out.stdout}"
    assert "fixture.json" in out.stdout
    assert "TCKN" in out.stdout


def test_phi_scan_ignores_a_checksum_invalid_eleven_digit_run(tmp_path: Path) -> None:
    f = tmp_path / "fixture.txt"
    f.write_text("order id 12345678901 is not an identity number\n", encoding="utf-8")
    assert run_script(PHI_SCAN, str(f)).returncode == 0


def test_phi_scan_catches_tr_mobile_numbers(tmp_path: Path) -> None:
    for sample in ("+90 532 123 45 67", "05321234567", "0532 123 45 67"):
        f = tmp_path / "fixture.txt"
        f.write_text(f"beni arayin: {sample}\n", encoding="utf-8")
        out = run_script(PHI_SCAN, str(f))
        assert out.returncode == 1, f"mobile not caught: {sample}"
        assert "PHONE" in out.stdout


def test_phi_scan_catches_a_tr_iban(tmp_path: Path) -> None:
    for sample in ("TR330006100519786457841326", "TR33 0006 1005 1978 6457 8413 26"):
        f = tmp_path / "fixture.txt"
        f.write_text(f"iade {sample} hesabina\n", encoding="utf-8")
        out = run_script(PHI_SCAN, str(f))
        assert out.returncode == 1, f"IBAN not caught: {sample}"
        assert "IBAN" in out.stdout


def test_phi_scan_withholds_the_matched_value(tmp_path: Path) -> None:
    """Invariant 6: the gate reports locations, never content — otherwise the
    scan itself copies PHI-shaped strings into the CI log."""
    tckn = _valid_tckn("523467891")
    f = tmp_path / "fixture.txt"
    f.write_text(f"kimlik {tckn} tel 05321234567\n", encoding="utf-8")
    out = run_script(PHI_SCAN, str(f))
    assert out.returncode == 1
    assert tckn not in out.stdout and "05321234567" not in out.stdout


def test_phi_scan_passes_a_clean_file(tmp_path: Path) -> None:
    f = tmp_path / "fixture.txt"
    f.write_text("bas agrisi iki gundur suruyor; oda 12, kat 3\n", encoding="utf-8")
    assert run_script(PHI_SCAN, str(f)).returncode == 0


def test_phi_scan_passes_the_real_trees() -> None:
    out = run_script(PHI_SCAN)
    assert out.returncode == 0, f"fixtures/docs are not PHI-clean:\n{out.stdout}{out.stderr}"


def test_phi_scan_takes_its_fixture_exemptions_from_the_int_206_policy() -> None:
    """One mechanism, not two: a fixture is excused only by the sha256-pinned
    corpus declaration in infra/ci/no-phi-policy.yaml (INT-206), never by a
    prefix in this gate's own list."""
    text = PHI_SCAN.read_text(encoding="utf-8")
    assert "infra/ci/no-phi-policy.yaml" in text
    allow = PHI_ALLOW.read_text(encoding="utf-8")
    for line in allow.splitlines():
        entry = line.strip()
        if entry and not entry.startswith("#"):
            assert entry.startswith("docs/"), (
                f"{entry}: the prefix allow-list covers docs/ only; a fixture is "
                "excused by a declaration in infra/ci/no-phi-policy.yaml"
            )


def test_phi_docs_allowlist_only_shrinks() -> None:
    """The docs the redaction work quotes its canonical synthetic identifiers
    in. This set may only shrink (the no_placeholders discipline)."""
    entries = {
        line.strip()
        for line in PHI_ALLOW.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    pinned = {
        "docs/PROGRESS.md",
        "docs/evidence/INT-013.md",
        "docs/evidence/INT-145.md",
        "docs/evidence/INT-205.md",
        "docs/evidence/INT-206.md",
        "docs/evidence/INT-230.md",
    }
    assert entries <= pinned, f"the docs allow-list grew: {entries - pinned}"


def test_an_undeclared_fixture_carrying_an_identifier_fails(tmp_path: Path) -> None:
    """The negative control for the exemption path: a fixture that is not a
    declared corpus is caught even under tests/fixtures/deid/."""
    planted = tmp_path / "undeclared_corpus.jsonl"
    planted.write_text(f'{{"text": "TCKN {_valid_tckn("523467891")}"}}\n', encoding="utf-8")
    assert run_script(PHI_SCAN, str(planted)).returncode == 1


# --- claims scan (invariant 20) ------------------------------------------------------------


def test_claims_scan_catches_performance_claims(tmp_path: Path) -> None:
    for sample in (
        "sensitivity 95%",
        "specificity of 0.97",
        "AUROC 0.91 on the validation set",
        "%98 doğruluk ile çalışır",
        "WER below 8",
        "accuracy of 93%",
    ):
        f = tmp_path / "claims.md"
        f.write_text(f"The product achieves {sample}.\n", encoding="utf-8")
        out = run_script(CLAIMS_SCAN, str(f))
        assert out.returncode == 1, f"claim not caught: {sample}"
        assert "claims.md" in out.stdout


def test_claims_scan_passes_clean_copy(tmp_path: Path) -> None:
    f = tmp_path / "claims.md"
    f.write_text("Randevudan önce yakınmalarınızı sesli olarak anlatırsınız.\n", encoding="utf-8")
    assert run_script(CLAIMS_SCAN, str(f)).returncode == 0


def test_claims_scan_passes_the_real_trees() -> None:
    out = run_script(CLAIMS_SCAN)
    assert out.returncode == 0, f"performance claims found:\n{out.stdout}{out.stderr}"


# --- osv-scanner severity: fail on critical/high, report the rest ---------------------


def _osv_report(*advisories: tuple[str, str]) -> str:
    return json.dumps(
        {
            "results": [
                {
                    "source": {"path": "uv.lock", "type": "lockfile"},
                    "packages": [
                        {
                            "package": {"name": name, "version": "1.0.0", "ecosystem": "PyPI"},
                            "vulnerabilities": [
                                {
                                    "id": f"GHSA-{name}",
                                    "severity": (
                                        [{"type": "CVSS_V3", "score": vector}] if vector else []
                                    ),
                                }
                            ],
                        }
                        for name, vector in advisories
                    ],
                }
            ]
        }
    )


def _run_osv_gate(report: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(OSV_GATE)],
        input=report,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_osv_gate_computes_the_cvss_base_score_from_the_vector() -> None:
    """The score is computed from the vector (CVSS v3.1 §7.1 + Appendix A
    Roundup), not read from a vendor label. Two reference vectors from the
    specification's own worked examples."""
    sys.path.insert(0, str(REPO / "scripts" / "ci"))
    try:
        from osv_severity_gate import cvss3_base_score
    finally:
        sys.path.pop(0)
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") == 9.8
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H") == 10.0
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:U/C:L/I:L/A:N") == 3.7
    assert cvss3_base_score("not a vector") is None


def test_osv_gate_fails_on_a_critical_advisory() -> None:
    out = _run_osv_gate(_osv_report(("boom", "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")))
    assert out.returncode == 1, out.stdout
    assert "CRITICAL" in out.stdout and "9.8" in out.stdout


def test_osv_gate_reports_but_does_not_fail_on_a_low_advisory() -> None:
    out = _run_osv_gate(_osv_report(("meh", "CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:U/C:L/I:L/A:N")))
    assert out.returncode == 0, out.stdout
    assert "not blocking" in out.stdout and "GHSA-meh" in out.stdout


def test_osv_gate_fails_on_an_unscored_advisory() -> None:
    """An advisory nobody has rated is not an advisory rated harmless — and if
    it passed, "publish no vector" would be the cheapest way through the gate."""
    out = _run_osv_gate(_osv_report(("mystery", "")))
    assert out.returncode == 1, out.stdout
    assert "UNSCORED" in out.stdout


def test_osv_gate_passes_a_clean_report() -> None:
    out = _run_osv_gate(json.dumps({"results": []}))
    assert out.returncode == 0
    assert "no critical or high" in out.stdout


def test_osv_gate_fails_on_an_empty_report() -> None:
    """No report means the scanner did not run, which is not a pass."""
    assert _run_osv_gate("").returncode == 1


# --- the debt baselines: real files, and the gates refuse to run without them -----------


def test_the_debt_baselines_exist_and_the_gates_require_them() -> None:
    """bandit and checkov carry pre-existing findings in trees INT-019 does not
    own. They are recorded, not silenced: a NEW finding still fails, and a
    missing baseline file fails the gate rather than passing it."""
    for baseline in (BANDIT_BASELINE, CHECKOV_BASELINE):
        assert baseline.is_file(), f"{baseline.name} missing"
        json.loads(baseline.read_text(encoding="utf-8"))
    driver = _driver_text()
    for baseline in ("bandit_baseline.json", "checkov_baseline.json"):
        assert baseline in driver
        assert f"{baseline} is missing" in driver, (
            f"the gate must fail closed when {baseline} is absent"
        )


def test_eslint_security_baseline_is_a_shrink_only_debt_list() -> None:
    data = json.loads(ESLINT_BASELINE.read_text(encoding="utf-8"))
    assert data["findings"], "an empty baseline would mean the scan found nothing"
    gate = (REPO / "scripts" / "ci" / "eslint_security_gate.py").read_text(encoding="utf-8")
    assert "may only shrink" in gate
    assert "<parse-error>" in gate, "a file the rules could not parse is never a pass"
