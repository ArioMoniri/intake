"""INT-019 — security gate set: scanners, SBOM, signing skeleton, PHI/claims scans.

Acceptance (docs/backlog/issues.yaml INT-019), verbatim:
  1. "gitleaks, semgrep+bandit, eslint-security, trivy fs/image/IaC + osv-scanner
     fail on critical/high, checkov, license allow-list (AGPL flagged), syft SBOM
     artifact, cosign keyless signing + SLSA provenance for images and protocol
     bundles on tags, schemathesis fuzz, PHI-pattern scan of fixtures"
  2. "`make security` runs the same list locally; planted secret, planted critical
     CVE and planted PHI each fail (proved in evidence, then reverted)"

Placement state: .github/workflows/security.yml is installed and the
scripts/ci/security_workflow.yml template it was staged through is gone, so
test_workflow_is_installed is a live assertion rather than an interlock. The
path stays hook-protected (07 §3.8 / §F rule 2) and moves only under the
human-sanctioned ALLOW_PROTECTED=1 — which is why the two remaining defects in
that file (HB-O5: the gitleaks job's missing pull-requests scope and the
osv-scanner action path) are recorded for the owner instead of patched here.

What the rest of this file pins:
  - the workflow parses, every action is full-SHA-pinned with the resolved tag
    in a trailing comment (ci.yml convention), and every invariant-14 tool
    name is present as a job/step.
  - scripts/ci/phi_scan.sh and scripts/ci/claims_scan.sh exist, are executable,
    catch planted violations in scratch files, and pass over the real trees.
  - scripts/ci/check_licenses.py rejects an AGPL dependency and accepts the
    allow-list, including OR/AND licence expressions.
  - `make security` and `make safety` targets exist.
  - The PHI-scan allow-list (the de-id engine's own labeled corpus) may only
    shrink, mirroring the no_placeholders gate.

Deferred (documented in docs/evidence/INT-019.md, not silently dropped):
image scanning/signing until images exist; schemathesis until services/api
exposes an OpenAPI schema offline; eslint-plugin-security wiring decision.

INT-310 — the eight npm advisories are cleared by version, not by silence.

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

import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW_INSTALLED = REPO / ".github" / "workflows" / "security.yml"
WORKFLOW_TEMPLATE = REPO / "scripts" / "ci" / "security_workflow.yml"
WORKFLOW = WORKFLOW_INSTALLED if WORKFLOW_INSTALLED.exists() else WORKFLOW_TEMPLATE
PHI_SCAN = REPO / "scripts" / "ci" / "phi_scan.sh"
PHI_ALLOW = REPO / "scripts" / "ci" / "phi_scan_allow.txt"
TCKN_HELPER = REPO / "scripts" / "ci" / "tckn_check.py"
CLAIMS_SCAN = REPO / "scripts" / "ci" / "claims_scan.sh"
LICENSES = REPO / "scripts" / "ci" / "check_licenses.py"


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args], cwd=REPO, capture_output=True, text=True, check=False
    )


# --- placement: fail-closed until the human-sanctioned move happens --------------


def test_workflow_is_installed() -> None:
    """The gate set only runs from .github/workflows/; a template copy runs nothing.

    Kept as an assertion after the sanctioned placement landed, because the
    failure it guards against is silent: deleting or renaming the workflow
    removes eight gates at once and every remaining check still passes.
    """
    assert WORKFLOW_INSTALLED.exists(), (
        ".github/workflows/security.yml is not installed — the CI gate set is not "
        "live, and nothing else in this suite would notice"
    )


def test_installed_copy_matches_template_while_both_exist() -> None:
    """During the transition commit both copies may exist; they must not drift."""
    if WORKFLOW_INSTALLED.exists() and WORKFLOW_TEMPLATE.exists():
        assert WORKFLOW_INSTALLED.read_bytes() == WORKFLOW_TEMPLATE.read_bytes(), (
            "installed security.yml drifted from scripts/ci/security_workflow.yml — "
            "delete the template in the commit that installs the workflow"
        )


# --- the workflow content: parses, SHA-pinned, full invariant-14 tool list -------


def test_security_workflow_parses() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(wf, dict) and "jobs" in wf and wf["jobs"], "security workflow has no jobs"


def test_security_workflow_triggers() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))  # YAML 1.1 parses bare `on` as boolean True
    assert on is not None, "no trigger block"
    assert "pull_request" in on
    assert "main" in on["push"]["branches"]
    assert "v*" in on["push"]["tags"], "signing skeleton needs the v* tag trigger"


def test_every_action_is_full_sha_pinned() -> None:
    """Supply-chain rule from ci.yml: a tag can be silently repointed; every
    `uses:` must pin a 40-hex commit SHA, with the resolved tag as a comment."""
    text = WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)\s*(#.*)?$", text, re.M)
    assert uses, "no `uses:` lines found"
    for ref, comment in uses:
        action, _, pin = ref.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", pin), f"{action} not pinned to a full SHA: {pin!r}"
        assert comment.strip().startswith("#"), f"{action}: missing resolved-tag comment"


def test_invariant_14_tools_all_present() -> None:
    """Invariant 14 enumerates the gate set and says it is never skipped. Every
    wired tool must appear; deferrals (image scan/sign, schemathesis) are
    documented in evidence, not silently dropped from this list."""
    text = WORKFLOW.read_text(encoding="utf-8")
    for tool in (
        "gitleaks",
        "semgrep",
        "bandit",
        "trivy",
        "osv-scanner",
        "checkov",
        "check_licenses",
        "syft",
        "spdx-json",
        "cosign",
        "phi_scan",
        "claims_scan",
    ):
        assert tool in text, f"invariant-14 tool missing from the security workflow: {tool}"


def test_fail_on_critical_high() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "CRITICAL,HIGH" in text, "trivy must fail on critical/high"


def test_signing_job_is_tags_only_keyless_with_provenance() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "startsWith(github.ref, 'refs/tags/v')" in text
    assert "id-token: write" in text, "keyless signing needs the OIDC token"
    assert "attestations: write" in text, "SLSA provenance needs attestations"
    assert "attest-build-provenance" in text
    assert "sign-blob" in text


def test_workflow_default_permissions_read_only() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert wf["permissions"] == {"contents": "read"}


# --- scripts exist and are executable --------------------------------------------


def test_gate_scripts_exist_and_are_executable() -> None:
    for script in (PHI_SCAN, CLAIMS_SCAN):
        assert os.access(script, os.X_OK), f"{script.name} missing or not executable"
    for helper in (TCKN_HELPER, LICENSES):
        assert helper.is_file(), f"{helper.name} missing"


# --- make security / make safety ---------------------------------------------------


def test_make_security_and_safety_targets_exist() -> None:
    out = subprocess.run(["make", "-npq"], cwd=REPO, capture_output=True, text=True, check=False)
    for target in ("security", "safety"):
        assert re.search(rf"^{target}:", out.stdout, re.M), f"missing make target: {target}"


def test_make_security_runs_the_same_list_as_ci() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    body = makefile.split("\nsecurity:")[1].split("\n\n")[0]
    for tool in (
        "gitleaks",
        "semgrep",
        "bandit",
        "trivy fs",
        "trivy config",
        "osv-scanner",
        "checkov",
        "check_licenses",
        "syft",
        "phi_scan",
        "claims_scan",
    ):
        assert tool in body, f"make security does not run {tool}"


def test_make_security_never_silently_skips() -> None:
    """Invariant 14: a missing tool must FAIL with an install hint, never skip."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    body = makefile.split("\nsecurity:")[1].split("\n\n")[0]
    assert body.count("command -v") >= 4, "binary tools need presence checks"
    assert "exit 1" in body and "brew install" in body, (
        "a missing tool must fail with an actionable install hint"
    )


# --- licence allow-list ------------------------------------------------------------


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
            str(LICENSES),
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
    empty = tmp_path / "site"
    empty.mkdir()
    out = _run_licences(nm, empty)
    assert out.returncode == 1, f"AGPL dependency must fail:\n{out.stdout}{out.stderr}"
    assert "viral-lib" in out.stdout and "AGPL" in out.stdout
    assert "fine-lib" not in out.stdout.split("VIOLATIONS")[-1]


def test_licence_gate_rejects_unknown(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "mystery-lib", "SEE LICENSE IN LICENSE.txt")
    empty = tmp_path / "site"
    empty.mkdir()
    out = _run_licences(nm, empty)
    assert out.returncode == 1, "unknown licence must fail, not pass silently"
    assert "mystery-lib" in out.stdout


def test_licence_gate_accepts_the_allow_list(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    for i, licence in enumerate(
        ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0", "Zlib")
    ):
        _fake_node_package(nm, f"lib-{i}", licence)
    _fake_node_package(nm, "dual-lib", "(MIT OR GPL-3.0-only)")  # OR: one allowed side suffices
    _fake_node_package(nm, "joint-lib", "MIT AND Apache-2.0")  # AND: all sides allowed
    empty = tmp_path / "site"
    empty.mkdir()
    out = _run_licences(nm, empty)
    assert out.returncode == 0, f"allow-listed set must pass:\n{out.stdout}{out.stderr}"


def test_licence_gate_and_with_denied_side_fails(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "tainted-lib", "MIT AND AGPL-3.0-only")
    empty = tmp_path / "site"
    empty.mkdir()
    out = _run_licences(nm, empty)
    assert out.returncode == 1, "AND with a denied side must fail"


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


def _fake_python_dist(
    site: Path, name: str, licence: str | None, *, source_dir: Path | None = None
) -> None:
    """Write a dist-info. `source_dir` records PEP 610 provenance (an editable install)."""
    dist = site / f"{name.replace('-', '_')}-0.1.0.dist-info"
    dist.mkdir(parents=True)
    lines = ["Metadata-Version: 2.1", f"Name: {name}", "Version: 0.1.0"]
    if licence is not None:
        lines.append(f"License-Expression: {licence}")
    (dist / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if source_dir is not None:
        (dist / "direct_url.json").write_text(
            json.dumps({"url": source_dir.as_uri(), "dir_info": {"editable": True}}),
            encoding="utf-8",
        )


def test_first_party_python_tracks_the_uv_workspace() -> None:
    """The first-party set is derived, never hand-listed.

    A hand-written set goes stale the moment a workspace member lands, and it
    goes stale silently: the new package is simply reported as a third-party
    dependency with no licence metadata. That is exactly what happened — seven
    members were added after this gate was written and every one of them turned
    up as a licence violation.
    """
    spec = importlib.util.spec_from_file_location("check_licenses", LICENSES)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    root = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    expected = {root["project"]["name"]}
    for member in root["tool"]["uv"]["workspace"]["members"]:
        for member_dir in sorted(REPO.glob(member)):
            member_toml = member_dir / "pyproject.toml"
            if member_toml.is_file():
                expected.add(
                    tomllib.loads(member_toml.read_text(encoding="utf-8"))["project"]["name"]
                )

    assert module.first_party_python_names() == expected, (
        "the first-party set must be read from [tool.uv.workspace], not hand-listed"
    )
    assert len(expected) > 3, "the workspace has grown past the original hand-written set"


def test_licence_gate_accepts_a_workspace_package_with_no_licence_metadata(tmp_path: Path) -> None:
    """Our own packages declare no licence and must not be treated as dependencies."""
    site = tmp_path / "site"
    _fake_python_dist(site, "intake-platform", None, source_dir=REPO / "packages/intake_platform")
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "fine-lib", "MIT")
    out = _run_licences(nm, site)
    assert out.returncode == 0, f"a real workspace member must pass:\n{out.stdout}{out.stderr}"


def test_licence_gate_still_checks_a_dependency_squatting_a_workspace_name(
    tmp_path: Path,
) -> None:
    """Skipping by NAME alone is a dependency-confusion hole; provenance is required.

    This is the case that fails if the gate is defeated: a distribution named
    after a workspace member but installed from somewhere other than this
    checkout is a third-party package, and its licence must still be checked.
    """
    site = tmp_path / "site"
    _fake_python_dist(site, "intake-platform", "AGPL-3.0-only")  # no direct_url.json
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "fine-lib", "MIT")
    out = _run_licences(nm, site)
    assert out.returncode == 1, (
        "a package that only borrows a workspace NAME must still be licence-checked:\n"
        f"{out.stdout}{out.stderr}"
    )
    assert "intake-platform" in out.stdout and "AGPL" in out.stdout


def test_licence_gate_still_checks_a_workspace_name_installed_from_outside_the_repo(
    tmp_path: Path,
) -> None:
    """PEP 610 provenance pointing outside the checkout is not our package either."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    site = tmp_path / "site"
    _fake_python_dist(site, "intake-platform", "AGPL-3.0-only", source_dir=elsewhere)
    nm = tmp_path / "node_modules"
    _fake_node_package(nm, "fine-lib", "MIT")
    out = _run_licences(nm, site)
    assert out.returncode == 1, "provenance outside the repo must not confer first-party status"
    assert "intake-platform" in out.stdout


# --- PHI-pattern scan ----------------------------------------------------------------


def _valid_tckn(stem: str) -> str:
    """Independent checksum construction so the helper is pinned, not mirrored."""
    d = [int(c) for c in stem]
    assert len(d) == 9 and d[0] != 0
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = (sum(d) + d10) % 10
    return stem + str(d10) + str(d11)


def test_phi_scan_catches_checksum_valid_tckn(tmp_path: Path) -> None:
    planted = tmp_path / "fixture.json"
    planted.write_text(f'{{"not": "hasta kimlik {_valid_tckn("523467891")}"}}\n', encoding="utf-8")
    out = run_script(PHI_SCAN, str(planted))
    assert out.returncode == 1, f"checksum-valid TCKN not caught:\n{out.stdout}"
    assert "fixture.json" in out.stdout


def test_phi_scan_ignores_checksum_invalid_11_digits(tmp_path: Path) -> None:
    f = tmp_path / "fixture.txt"
    f.write_text("order id 12345678901 is not an identity number\n", encoding="utf-8")
    assert run_script(PHI_SCAN, str(f)).returncode == 0, "checksum-invalid digits are not PHI"


def test_phi_scan_catches_tr_mobile_numbers(tmp_path: Path) -> None:
    for sample in ("+90 532 123 45 67", "05321234567", "0532 123 45 67"):
        f = tmp_path / "fixture.txt"
        f.write_text(f"beni ara: {sample}\n", encoding="utf-8")
        out = run_script(PHI_SCAN, str(f))
        assert out.returncode == 1, f"phone not caught: {sample}"


def test_phi_scan_catches_tr_iban(tmp_path: Path) -> None:
    for sample in ("TR330006100519786457841326", "TR33 0006 1005 1978 6457 8413 26"):
        f = tmp_path / "fixture.txt"
        f.write_text(f"iade {sample} hesabina\n", encoding="utf-8")
        out = run_script(PHI_SCAN, str(f))
        assert out.returncode == 1, f"IBAN not caught: {sample}"


def test_phi_scan_withholds_content_from_its_own_output(tmp_path: Path) -> None:
    """Invariant 6: the scanner reports locations, never the matched values —
    otherwise the gate itself would copy PHI-shaped strings into CI logs."""
    tckn = _valid_tckn("523467891")
    f = tmp_path / "fixture.txt"
    f.write_text(f"kimlik {tckn} tel 05321234567\n", encoding="utf-8")
    out = run_script(PHI_SCAN, str(f))
    assert out.returncode == 1
    assert tckn not in out.stdout and "05321234567" not in out.stdout


def test_phi_scan_clean_file_passes(tmp_path: Path) -> None:
    f = tmp_path / "fixture.txt"
    f.write_text("bas agrisi iki gundur suruyor; oda 12, kat 3\n", encoding="utf-8")
    assert run_script(PHI_SCAN, str(f)).returncode == 0


def test_phi_scan_passes_the_real_fixture_and_docs_trees() -> None:
    out = run_script(PHI_SCAN)
    assert out.returncode == 0, f"repo fixtures/docs are not PHI-clean:\n{out.stdout}{out.stderr}"


def test_phi_allowlist_only_shrinks() -> None:
    """Only the de-id engine's own labeled corpus (synthetic, checksum-valid by
    construction — tests/fixtures/deid/vendor/ATTRIBUTION.md) and the evidence
    file quoting it may carry PHI-shaped strings. This set may only shrink."""
    entries = {
        line.strip()
        for line in PHI_ALLOW.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    pinned = {
        "tests/fixtures/deid/",
        "tests/fixtures/logs/app_lines.txt",
        "docs/evidence/INT-013.md",
        "docs/evidence/INT-019.md",
    }
    assert entries <= pinned, f"PHI allow-list grew beyond the pinned set: {entries - pinned}"


# --- claims scan (invariant 20) --------------------------------------------------------


def test_claims_scan_catches_planted_performance_claims(tmp_path: Path) -> None:
    for sample in (
        "sensitivity 95%",
        "specificity of 0.97",
        "AUROC 0.91 on the validation set",
        "%98 doğruluk ile çalışır",
        "WER below 8",
    ):
        f = tmp_path / "claims.md"
        f.write_text(f"The product achieves {sample}.\n", encoding="utf-8")
        out = run_script(CLAIMS_SCAN, str(f))
        assert out.returncode == 1, f"claim not caught: {sample}"
        assert "claims.md" in out.stdout


def test_claims_scan_clean_copy_passes(tmp_path: Path) -> None:
    f = tmp_path / "claims.md"
    f.write_text("Randevudan önce yakınmalarınızı sesli olarak anlatırsınız.\n", encoding="utf-8")
    assert run_script(CLAIMS_SCAN, str(f)).returncode == 0


def test_claims_scan_catches_turkish_performance_claims(tmp_path: Path) -> None:
    """Invariant 20 in the product's FIRST language.

    An English-only pattern set left the gate unenforced for exactly the copy
    that matters most: a Turkish regulatory or legal file says `duyarlılık`,
    not `sensitivity`. Consonant softening (k -> ğ) is part of the word, so
    `duyarlılığı` has to be caught as surely as `duyarlılık`.
    """
    for sample in (
        "%94 duyarlılık",
        "Duyarlılık %94",
        "testin duyarlılığı %94 olarak ölçüldü",
        "Özgüllük oranı %88",
        "özgüllüğü %88 bulundu",
        "Kesinlik %92",
        "İsabet oranı %95",
        "duyarlılık 0,94",
    ):
        f = tmp_path / "claims.md"
        f.write_text(f"Ürün {sample} sağlar.\n", encoding="utf-8")
        out = run_script(CLAIMS_SCAN, str(f))
        assert out.returncode == 1, f"Turkish claim not caught: {sample}"


def test_claims_scan_allows_ordinary_turkish_prose(tmp_path: Path) -> None:
    """The near-miss control: the same nouns are ordinary Turkish legal words.

    `bilgilerin doğruluğu` and `kültürel duyarlılık` are not performance
    claims, and a gate that failed on them would be turned off within a week.
    A claim is the vocabulary NEXT TO A FIGURE — the invariant's own noun.
    """
    for sample in (
        "Bilgilerinizin doğruluğundan siz sorumlusunuz.",
        "Kültürel duyarlılık ilkelerimiz arasındadır.",
        "Verilerin doğruluğu KVKK 4. maddede düzenlenir.",
        "Randevunuz 14:30 olarak ayarlandı.",
    ):
        f = tmp_path / "claims.md"
        f.write_text(sample + "\n", encoding="utf-8")
        out = run_script(CLAIMS_SCAN, str(f))
        assert out.returncode == 0, f"false positive on ordinary Turkish prose: {sample}"


def test_claims_scan_copy_tier_allows_clinical_symptom_vocabulary(tmp_path: Path) -> None:
    """Patient copy has to be able to ask about photophobia.

    `intake.opt.lightSensitivity` / "Işığa hassasiyet" is a SYMPTOM name, not a
    claim about the product. Scanning the i18n catalogues at strict tier failed
    on those labels, which is why the copy tier scores term-plus-figure only.
    """
    f = tmp_path / "app-en.json"
    f.write_text(
        '{"intake.opt.lightSensitivity": "Sensitivity to light",\n'
        ' "intake.opt.soundSensitivity": "Sensitivity to sound"}\n',
        encoding="utf-8",
    )
    out = run_script(CLAIMS_SCAN, "--copy", str(f))
    assert out.returncode == 0, f"symptom vocabulary must not read as a claim:\n{out.stdout}"


def test_claims_scan_copy_tier_still_catches_a_figure_claim(tmp_path: Path) -> None:
    """…but the copy tier is a tier, not an exemption."""
    for sample in (
        '{"marketing.blurb": "Our triage has 94% sensitivity"}',
        '{"marketing.tr": "Triyajımız %94 duyarlılık sağlar"}',
        '{"marketing.auroc": "AUROC 0.94"}',
    ):
        f = tmp_path / "app.json"
        f.write_text(sample + "\n", encoding="utf-8")
        out = run_script(CLAIMS_SCAN, "--copy", str(f))
        assert out.returncode == 1, f"copy-tier claim not caught: {sample}"


def test_claims_scan_strict_tier_catches_bare_english_terms(tmp_path: Path) -> None:
    """docs/regulatory and docs/legal are where claims get MADE.

    "high sensitivity" carries no figure but is still a property claim about
    the product, which invariant 20's last sentence forbids just as firmly.
    """
    f = tmp_path / "claims.md"
    f.write_text("The system offers high sensitivity in triage.\n", encoding="utf-8")
    out = run_script(CLAIMS_SCAN, str(f))
    assert out.returncode == 1, "a bare property claim must fail at strict tier"


def test_claims_scan_passes_the_real_trees() -> None:
    out = run_script(CLAIMS_SCAN)
    assert out.returncode == 0, f"performance claims in scanned trees:\n{out.stdout}{out.stderr}"


def test_claims_scan_covers_patient_and_clinician_copy() -> None:
    """Invariant 20 names "patient or clinician copy" alongside the regulatory
    and legal trees. Those catalogues landed on main after this gate was first
    written, so the default target set has to reach them or the invariant is
    only enforced where no copy lives."""
    trees = [p for p in (REPO / "apps").glob("*/src/locales") if p.is_dir()]
    trees += [p for p in (REPO / "apps").glob("*/src/lib/i18n") if p.is_dir()]
    assert trees, "no i18n catalogue found — update the claims-scan target set"
    body = CLAIMS_SCAN.read_text(encoding="utf-8")
    assert "COPY_GLOBS" in body and "src/locales" in body and "src/lib/i18n" in body, (
        "claims_scan.sh does not scan the patient/clinician copy catalogues"
    )


# --- trivy ignore file: scoped, and actually loaded ----------------------------


TRIVYIGNORE = REPO / ".trivyignore.yaml"


def test_trivyignore_rows_are_purl_scoped() -> None:
    """No row may mute an advisory tree-wide.

    A bare `id:` row suppresses the CVE for every package forever, including a
    real dependency that acquires it later. Every row must name the exact
    package it is about, and say why.
    """
    rows = yaml.safe_load(TRIVYIGNORE.read_text(encoding="utf-8"))["vulnerabilities"]
    assert rows, "an empty ignore file should be deleted, not kept"
    for row in rows:
        assert row.get("purls"), f"{row.get('id')} has no purls — that is a tree-wide mute"
        assert all(p.startswith("pkg:") for p in row["purls"]), row["purls"]
        assert len(str(row.get("statement", "")).split()) >= 30, (
            f"{row.get('id')} needs a statement a reviewer can disagree with"
        )


def test_the_node_forge_exception_is_scoped_and_expires() -> None:
    """INT-429: the one owner-approved, time-boxed row (2 Oct 2026).

    node-forge 1.4.0 has no fixed release for CVE-2026-85393. The row names
    exactly that package version. It states how the package is reached and
    what the evidence is, and it expires within 30 days of the decision. After
    that date trivy reports the finding again and the gate turns red.
    """
    rows = yaml.safe_load(TRIVYIGNORE.read_text(encoding="utf-8"))["vulnerabilities"]
    forge = [r for r in rows if r.get("id") == "CVE-2026-85393"]
    assert len(forge) == 1
    row = forge[0]
    assert row["purls"] == ["pkg:npm/node-forge@1.4.0"], "scoped to the one version, nothing wider"
    expiry = row.get("expired_at")
    assert isinstance(expiry, datetime.date), "the exception must carry trivy's expired_at"
    assert datetime.date(2026, 10, 2) < expiry <= datetime.date(2026, 11, 1), (
        "30 days from the decision, no more"
    )
    statement = " ".join(str(row.get("statement", "")).split())
    for must in ("owner", "expo export", "@expo/cli", "docs/evidence/INT-429.md"):
        assert must in statement, f"the statement must say {must!r}"


def test_the_osv_exception_names_one_advisory_and_expires() -> None:
    """INT-429: osv-scanner's view of the same node-forge advisory, same terms."""
    config = tomllib.loads((REPO / "osv-scanner.toml").read_text(encoding="utf-8"))
    assert set(config) == {"IgnoredVulns"}, "no package-wide override, no other mute form"
    (entry,) = [e for e in config["IgnoredVulns"] if e["id"] == "GHSA-86w9-cpqp-85rv"]
    until = entry.get("ignoreUntil")
    assert isinstance(until, datetime.datetime), "the exception must carry ignoreUntil"
    assert datetime.date(2026, 10, 2) < until.date() <= datetime.date(2026, 11, 1), (
        "30 days, no more"
    )
    reason = " ".join(str(entry.get("reason", "")).split())
    for must in ("owner", "node-forge 1.4.0", "expo export", "docs/evidence/INT-429.md"):
        assert must in reason, f"the reason must say {must!r}"


# INT-426 follow-up: the two advisories OSV reissued on 2 Oct with no fix.
OSV_NO_FIX_ROWS = {
    "GHSA-vfj7-8cjw-p6xm": ("braces 3.0.3", "micromatch 4.0.8", "metro-file-map"),
    "GHSA-ch52-4w7c-c8xp": ("http-cache-semantics 4.2.0", "@expo/ngrok", "--tunnel"),
}

# INT-378: the one OSV record keycloak-services 26.7.4 still matches. Its range is open,
# and its GitHub source ends below 26.5.5 (docs/evidence/INT-390.md, INT-378.md). The
# entry sits beside the provider's pom, the only config osv-scanner applies to it.
OSV_SAML_BROKER_ROW = "GHSA-794g-x443-36f7"
OSV_KEYCLOAK_CONFIG = REPO / "infra/keycloak/providers/webauthn-session-notes/osv-scanner.toml"


def test_the_osv_no_fix_exceptions_are_named_reasoned_and_expire() -> None:
    """Each entry names one advisory of one package, says how it is reached,
    and expires within 30 days of 3 Oct 2026, after which the gate turns red."""
    config = tomllib.loads((REPO / "osv-scanner.toml").read_text(encoding="utf-8"))
    entries = {e["id"]: e for e in config["IgnoredVulns"]}
    assert set(entries) == {"GHSA-86w9-cpqp-85rv", *OSV_NO_FIX_ROWS}, "nothing else is muted"
    for advisory, musts in OSV_NO_FIX_ROWS.items():
        entry = entries[advisory]
        until = entry.get("ignoreUntil")
        assert isinstance(until, datetime.datetime), f"{advisory} must carry ignoreUntil"
        assert datetime.date(2026, 10, 3) < until.date() <= datetime.date(2026, 11, 2), (
            f"{advisory}: 30 days, no more"
        )
        reason = " ".join(str(entry.get("reason", "")).split())
        for must in (
            "approve for the two osv exceptions",
            "expo export",
            "docs/evidence/INT-426.md",
            *musts,
        ):
            assert must in reason, f"{advisory}: the reason must say {must!r}"


def test_the_keycloak_osv_exception_is_bounded_reasoned_and_expires() -> None:
    """One advisory of one package, beside the pom it applies to.

    The reason names the one version, why the record is not live for it (GitHub's
    bound and the fixing change), why it is unreachable, and its evidence. It
    expires within 30 days of 3 Oct 2026, after which the gate turns red again."""
    config = tomllib.loads(OSV_KEYCLOAK_CONFIG.read_text(encoding="utf-8"))
    assert set(config) == {"IgnoredVulns"}, "no package-wide override, no other mute form"
    (entry,) = config["IgnoredVulns"]
    assert entry["id"] == OSV_SAML_BROKER_ROW
    until = entry.get("ignoreUntil")
    assert isinstance(until, datetime.datetime), "the exception must carry ignoreUntil"
    assert datetime.date(2026, 10, 3) < until.date() <= datetime.date(2026, 11, 2), (
        "30 days, no more"
    )
    reason = " ".join(str(entry.get("reason", "")).split())
    for must in (
        "keycloak-services 26.7.4 only",
        "< 26.5.5",
        "keycloak/keycloak#46912",
        "provided",
        "no identity provider",
        "docs/evidence/INT-378.md",
    ):
        assert must in reason, f"the reason must say {must!r}"


def test_near_miss_the_root_config_would_not_reach_the_pom() -> None:
    """The root file names no Keycloak advisory: there it would be an unused ignore."""
    root = tomllib.loads((REPO / "osv-scanner.toml").read_text(encoding="utf-8"))
    assert OSV_SAML_BROKER_ROW not in {e["id"] for e in root["IgnoredVulns"]}
    assert OSV_KEYCLOAK_CONFIG in _tracked_suppression_files(OSV_SUPPRESSION_FILES)


def test_make_security_actually_loads_the_trivy_ignore_file() -> None:
    """trivy 0.74 auto-detects .trivyignore but NOT .trivyignore.yaml.

    Without the explicit flag the file is decoration: the gate still fails and
    the next reader assumes the suppression is what is wrong. Measured on
    trivy 0.74.0 (docs/evidence/INT-019.md) — the row was committed unproven.
    """
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    trivy_fs = [
        ln
        for ln in makefile.splitlines()
        if ln.lstrip().startswith("trivy fs")  # the command, not its @echo banner
    ]
    assert trivy_fs, "make security no longer runs trivy fs"
    for line in trivy_fs:
        assert "--ignorefile .trivyignore.yaml" in line, (
            f"trivy fs would ignore .trivyignore.yaml: {line.strip()}"
        )


# --- gitleaks: the ignore file, and where the near-miss actually lives ----------


GITLEAKSIGNORE = REPO / ".gitleaksignore"
GITLEAKS_TOML = REPO / ".gitleaks.toml"
GATE_SELFTEST = REPO / "scripts" / "ci" / "gate_selftest.sh"


def test_gitleaksignore_rows_are_fully_scoped_and_only_shrink() -> None:
    """A fingerprint must pin one finding, and the set may only shrink.

    `commit:file:rule:line` is the narrowest suppression gitleaks has — it
    exempts no file, no rule and no other line. A row missing any field, or a
    row added without a reviewer noticing, is how an ignore file turns into the
    path allowlist .gitleaks.toml deliberately refuses to be.
    """
    if not GITLEAKSIGNORE.exists():
        return  # nothing suppressed is the better state, not a failure
    rows = {
        line.strip()
        for line in GITLEAKSIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for row in rows:
        commit, _, rule, line_no = row.split(":", 3)
        assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), (
            f"{row} does not pin one commit"
        )
        assert rule and line_no.isdigit(), f"{row} does not pin one rule and line"
    pinned = {
        # INT-019: the self-test's own fixtures in the commit 9fae031 superseded.
        "a68309d5ca17b0ea3face47590d417a7488b1edd:scripts/ci/gate_selftest.sh:curl-auth-user:97",
        "a68309d5ca17b0ea3face47590d417a7488b1edd:scripts/ci/gate_selftest.sh:generic-api-key:99",
        "a68309d5ca17b0ea3face47590d417a7488b1edd:scripts/ci/gate_selftest.sh:curl-auth-user:110",
        # INT-426: owner approval, 3 Oct 2026, "ignore the two old token
        # fingerprints". A fake JWT test fixture in history ("signature-sample");
        # the full-history scan in `make security` [1/12] reports it forever.
        "2c6a5dcf299b997682602044d14f79d8f9ac35d7:apps/embed-sample-partner/src/partnerBackend.test.ts:jwt:39",
        "2c6a5dcf299b997682602044d14f79d8f9ac35d7:apps/embed-sample-partner/src/partnerBackend.test.ts:jwt:41",
    }
    assert rows <= pinned, f"gitleaks ignore file grew beyond the pinned set: {rows - pinned}"


def test_the_gitleaks_allowlist_near_miss_exists_where_it_is_claimed() -> None:
    """The allowlist rows are only trustworthy because something plants a real
    literal in the two files they name and requires it to still fail.

    That near-miss lives in scripts/ci/gate_selftest.sh, and both .gitleaks.toml
    and an INT-019 commit message once cited this pytest module for it instead —
    a justification pointing at a test that does not exist is how a gate rots.
    """
    selftest = GATE_SELFTEST.read_text(encoding="utf-8")
    assert 'expect_reject "gitleaks (literal pw in the allowlisted file)"' in selftest
    assert 'expect_reject "gitleaks (real key in the allowlisted file)"' in selftest
    assert 'expect_accept "gitleaks (env-var ref + prose are allowlisted)"' in selftest, (
        "a gate that rejects everything proves as little as one that rejects nothing"
    )
    cited = GITLEAKS_TOML.read_text(encoding="utf-8")
    assert "scripts/ci/gate_selftest.sh" in cited, (
        "the .gitleaks.toml rationale must name whatever actually plants the near-miss; "
        "it cited this pytest module for years, which never contained it"
    )


def test_gate_selftest_holds_no_allowlisted_literal() -> None:
    """The generator is the committed artefact; the violation lives only in a
    mktemp directory. Committing the allowlisted strings as literals broke that
    rule and put three findings in the history (fixed in 9fae031) — the fixtures
    are read out of the real files at run time instead.

    The strings are DERIVED here rather than named, because naming them puts
    them back in the tree — which is precisely what the first version of this
    test did: it asserted the literals were gone in a line that contained them,
    and gitleaks flagged the guard instead of the thing guarded.
    """
    selftest = GATE_SELFTEST.read_text(encoding="utf-8")

    # Every anchored allowlist row whose pattern is a plain string is a literal
    # the generator must not carry. Rows with regex metacharacters describe a
    # shape rather than a string, and are covered by the yml-derived check below.
    metachars = set("\\[](){}|+*?.")
    anchored = re.findall(r"'''\^([^'\n]+)\$'''", GITLEAKS_TOML.read_text(encoding="utf-8"))
    plain = [pat for pat in anchored if not set(pat) & metachars]
    assert plain, (
        "no anchored plain-literal allowlist row found — has .gitleaks.toml changed shape?"
    )

    # The env-var reference is a shape, not a literal, so take the actual token
    # out of the file whose row names it.
    siem = (REPO / "infra" / "docker-compose.siem.yml").read_text(encoding="utf-8")
    marker = "curl -sk -u admin:"
    siem_line = next((ln for ln in siem.splitlines() if marker in ln), None)
    assert siem_line is not None, f"{marker!r} is no longer in docker-compose.siem.yml"
    plain.append(siem_line.split(marker, 1)[1].split()[0])

    for literal in plain:
        assert literal not in selftest, (
            "an allowlisted string is back as a literal in the generator; "
            "mirror it out of its real file instead"
        )


LOCKFILE = REPO / "pnpm-lock.yaml"

# The eight advisories osv-scanner 2.5.1 reported against pnpm-lock.yaml on
# 3 Sep 2026 (docs/evidence/INT-310.md, red run), with the fixed version each
# one names. A package resolving BELOW its fixed version is the advisory
# returning; the ids are carried alongside so the suppression sweep below can
# look for them by name.
#
# INT-346 raised the vitest floor and added @vitest/mocker: GHSA-82fw-gwwq-j7x9
# (published 8 Sep 2026, during the Actions billing outage) affects both from
# 2.1.0 up to the 4.1.11 fix, so no 3.x release clears it (docs/evidence/INT-346.md).
FIXED_VERSIONS: dict[str, tuple[int, int, int]] = {
    "vitest": (4, 1, 11),  # GHSA-5xrq-8626-4rwp (3.2.6), GHSA-82fw-gwwq-j7x9 (4.1.11)
    "@vitest/mocker": (4, 1, 11),  # GHSA-82fw-gwwq-j7x9
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
    "GHSA-82fw-gwwq-j7x9",
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
#
# INT-429 raises it to 2, by owner decision on 2 Oct 2026. The second row is
# node-forge 1.4.0 (CVE-2026-85393), which has no fixed release. That row is
# PURL-scoped, carries a reachability statement and expires on 2026-11-01
# (test_the_node_forge_exception_is_scoped_and_expires below). When it goes,
# this pin goes back to 1.
#
# INT-429 also raises the osv pin from 0 to 1, under the same owner decision
# (a narrow 30-day exception for just that package). osv-scanner reports the
# same advisory as GHSA-86w9-cpqp-85rv, and its one entry is in
# osv-scanner.toml (test_the_osv_exception_names_one_advisory_and_expires).
#
# The INT-426 follow-up raises the osv pin from 1 to 3, by exactly two, on the
# owner's approval in chat on 3 Oct 2026: "approve for the two osv exceptions".
# The two are braces 3.0.3 and http-cache-semantics 4.2.0, which OSV reissued
# on 2 Oct with no fixed release
# (test_the_osv_no_fix_exceptions_are_named_reasoned_and_expire). The pin goes
# back down as each entry expires or is removed.
#
# INT-378 raises it from 3 to 4, by exactly one. That happens only through the
# owner's own commit of owner-643-keycloak-exception.patch.
# - The advisory: GHSA-794g-x443-36f7 on keycloak-services 26.7.4, whose open
#   OSV range has a GitHub source that ends below 26.5.5, so no Keycloak
#   version clears it.
# - The entry sits beside the provider's pom, because osv-scanner reads config
#   per manifest directory. The pin therefore counts every tracked osv config
#   file, not only the root's (_tracked_suppression_files).
# - It expires on 2 Nov 2026
#   (test_the_keycloak_osv_exception_is_bounded_reasoned_and_expires).
# - The trivy pin does not move, because trivy reports nothing for that pom.
MAX_OSV_SUPPRESSIONS = 4
# The INT-426 follow-up raises the trivy pin from 2 to 3 for trivy's view of
# the same braces 3.0.3 advisory (CVE-2026-93687 = GHSA-vfj7-8cjw-p6xm), on the
# owner's approval in chat on 3 Oct 2026. It expires on 2026-11-02 with the osv
# entry, and the pin goes back down when it does.
MAX_TRIVY_SUPPRESSIONS = 3

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


def _tracked_suppression_files(names: tuple[str, ...]) -> list[Path]:
    """Every TRACKED file with one of these names, at any depth.

    osv-scanner reads the config beside each manifest (INT-378's pom carries its
    own), so a pin that counted the root file alone could be passed by moving a
    suppression one directory down.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True
    ).stdout.decode("utf-8")
    return [REPO / rel for rel in listed.split("\0") if rel and Path(rel).name in names]


def _suppression_entries(path: Path) -> list[str]:
    """The suppression ROWS in a trivy/osv ignore file.

    Counted structurally, not by leading `- `. A trivy YAML row carries a
    `purls:` list whose items are themselves `- ` lines, so a line-shaped count
    reads one properly scoped row as three and reports growth that never
    happened — which is worse than under-counting, because the fix it invites is
    to raise the pin and hide a real over-count behind a bigger number.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text) or {}
        rows = loaded.get("vulnerabilities") or [] if isinstance(loaded, dict) else []
        return [str(row.get("id", row)) for row in rows]
    if path.suffix == ".toml":
        # osv-scanner: an ignored advisory, or a package override that mutes one
        loaded_toml = tomllib.loads(text)
        ignored = [str(row.get("id", row)) for row in loaded_toml.get("IgnoredVulns", [])]
        overrides = [str(row.get("name", row)) for row in loaded_toml.get("PackageOverrides", [])]
        return ignored + overrides
    # trivy's legacy plain form: one bare advisory id per line.
    return [
        stripped
        for line in text.splitlines()
        if (stripped := line.strip())
        and not stripped.startswith("#")
        and re.match(r"^(CVE|GHSA|AVD|DS)-", stripped)
    ]


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
    for path in _tracked_suppression_files(OSV_SUPPRESSION_FILES):
        total += len(_suppression_entries(path))
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
    for path in _tracked_suppression_files(TRIVY_SUPPRESSION_FILES + OSV_SUPPRESSION_FILES):
        body = path.read_text(encoding="utf-8")
        for advisory in ADVISORY_IDS:
            assert advisory not in body, (
                f"{path.relative_to(REPO)} names {advisory} — INT-310's contract is that these are "
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


def test_the_suppression_counter_counts_rows_not_list_items(tmp_path: Path) -> None:
    """The counter guards the pin, so something must guard the counter.

    Its first version matched any line starting with `- `, so one properly
    PURL-scoped row counted as three and INT-019's single justified entry
    tripped INT-310's pin of 1. The tempting fix — raise the pin — would have
    buried a real over-count under a larger number.
    """
    one_row = tmp_path / ".trivyignore.yaml"
    one_row.write_text(
        "vulnerabilities:\n"
        "  - id: CVE-2026-33310\n"
        "    purls:\n"
        '      - "pkg:pypi/intake@0.1.0"\n'
        '      - "pkg:pypi/intake@0.2.0"\n'
        "    statement: >\n"
        "      two purls, one suppression\n",
        encoding="utf-8",
    )
    assert len(_suppression_entries(one_row)) == 1, "purl list items are not suppressions"

    two_rows = tmp_path / "two.trivyignore.yaml"
    two_rows.write_text(
        "vulnerabilities:\n"
        "  - id: CVE-2026-33310\n"
        '    purls: ["pkg:pypi/intake@0.1.0"]\n'
        "  - id: CVE-2026-44421\n"
        '    purls: ["pkg:pypi/other@1.0.0"]\n',
        encoding="utf-8",
    )
    assert len(_suppression_entries(two_rows)) == 2, "a real second row must still be seen"

    legacy = tmp_path / ".trivyignore"
    legacy.write_text("# comment\n\nCVE-2026-33310\nGHSA-aaaa-bbbb-cccc\n", encoding="utf-8")
    assert len(_suppression_entries(legacy)) == 2, "the legacy plain form still counts"

    assert _suppression_entries(tmp_path / "absent.yaml") == []


def test_the_suppression_counter_reads_osv_toml(tmp_path: Path) -> None:
    """INT-429: osv-scanner's config is TOML, and both of its mute forms count.

    Before INT-429 the counter sent `.toml` down the legacy plain-text branch,
    where `id = "GHSA-..."` never starts with an advisory prefix, so an osv
    suppression counted as zero and the osv pin could not see one.
    """
    config = tmp_path / "osv-scanner.toml"
    config.write_text(
        '[[IgnoredVulns]]\nid = "GHSA-aaaa-bbbb-cccc"\nreason = "x"\n\n'
        '[[PackageOverrides]]\nname = "left-pad"\necosystem = "npm"\nvulnerability.ignore = true\n',
        encoding="utf-8",
    )
    assert _suppression_entries(config) == ["GHSA-aaaa-bbbb-cccc", "left-pad"]
