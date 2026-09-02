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
"""

from __future__ import annotations

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
