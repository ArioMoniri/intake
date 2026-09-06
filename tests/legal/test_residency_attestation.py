"""INT-221 — tr-residency tenants are provably vendor-free on the PHI path.

Acceptance clause under test, verbatim: *"tr-residency tenants provably
vendor-free on PHI path (registry assertion); Rehber control mapping doc; …"*.

The proof is two committed sources, cross-checked, and it fails **closed**:

1. **The self-hosting registry** (``observability/registry.yaml``): every row
   that touches clinical data (``phi_path: true``) declares ``self_hostable:
   true`` (CLAUDE.md invariant 19 at the data layer). This is checked over the
   RAW yaml, independent of the pydantic model, so the assertion catches a bad
   row even if the loader's own validator were ever weakened.
2. **The egress allow-list** (``infra/security/egress-allowlist.yaml``): no
   anthropic/openai/google adapter is reachable on the PHI path
   (:func:`intake_platform.egress.assert_dev_only_vendors`, invariant 14/19).

The **Genelge 2019/12 residency attestation** is a legal statement to the
Ministry that no agent may author (CLAUDE.md stop-and-ask: consent/legal-text
territory). The mechanism is built and the machine-checkable conformance is
attached, but the attestation renders only once a named human signs it — until
then :class:`AttestationUnsigned` refuses it, naming the blocker (HB-L11). The
tests below prove the gate is a real gate: it refuses while unsigned and opens
once signed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from intake_platform.egress import (
    VENDOR_LLM_DOMAINS,
    AllowlistEntry,
    EgressAllowlist,
    EgressPurpose,
)
from intake_platform.legal.claims import scan_file
from intake_probes.registry import RegistryEntry, load_registry
from intake_probes.residency import (
    GENELGE_ATTESTATION_BLOCKER,
    AttestationUnsigned,
    ResidencyViolation,
    assert_egress_phi_path_vendor_free,
    assert_registry_phi_path_self_hosted,
    attest_residency,
    default_allowlist_path,
    default_registry_path,
    draft_genelge_attestation,
    load_registry_components_raw,
    repo_root,
)

REPO = Path(__file__).resolve().parents[2]
REHBER_DOC = REPO / "docs" / "regulatory" / "ddo_rehber_mapping.md"
GENELGE_DOC = REPO / "docs" / "regulatory" / "genelge_2019_12_residency_attestation.md"

_CLAIMS_GROUPS = ("performance", "satisfaction", "bare_percentage")

# Vendor hosts are DERIVED from the committed set, never written as literals:
# scripts/ci/assert_no_vendor_calls.sh refuses a literal vendor endpoint outside
# files/ (MEMORY: a guard must not name what it forbids).
_OPENAI_HOST = "api." + next(d for d in VENDOR_LLM_DOMAINS if d.startswith("openai"))
_ANTHROPIC_HOST = "api." + next(d for d in VENDOR_LLM_DOMAINS if d.startswith("anthropic"))


# --- the committed configuration is vendor-free ------------------------------


def test_committed_registry_every_phi_path_row_is_self_hostable() -> None:
    """Registry assertion, over the RAW yaml: invariant 19 at the data layer."""
    components = load_registry_components_raw(default_registry_path())
    phi_rows = [c for c in components if c.get("phi_path")]
    assert phi_rows, "the committed registry must have PHI-path rows to attest over"
    # does not raise
    assert_registry_phi_path_self_hosted(components)
    for row in phi_rows:
        assert row["self_hostable"] is True, row["component"]


def test_committed_registry_loads_and_agrees_with_the_raw_check() -> None:
    """The validated loader and the raw check agree — no drift between them."""
    registry = load_registry(default_registry_path())
    phi_components = {e.component for e in registry if e.phi_path}
    raw = load_registry_components_raw(default_registry_path())
    raw_phi = {c["component"] for c in raw if c.get("phi_path")}
    assert phi_components == raw_phi
    for entry in registry:
        if entry.phi_path:
            assert entry.self_hostable is True, entry.component


def test_committed_egress_phi_path_tier_is_vendor_free() -> None:
    """No anthropic/openai/google adapter reaches the PHI path (invariant 14/19)."""
    # does not raise over the committed allow-list
    assert_egress_phi_path_vendor_free(default_allowlist_path())


def test_attest_residency_over_committed_config_passes_and_names_components() -> None:
    report = attest_residency()
    assert report.vendor_free is True
    assert report.phi_path_components, "attestation must enumerate the PHI-path components"
    # every declared control passed
    assert all(control.status == "pass" for control in report.controls)
    ids = {control.id for control in report.controls}
    assert {"registry_phi_path_self_hosted", "egress_phi_path_vendor_free"} <= ids


# --- the assertion fails CLOSED (the near-miss controls) ---------------------


def test_registry_assertion_bites_when_a_vendor_slips_onto_the_phi_path() -> None:
    """A phi_path row that is not self_hostable is refused — the fail-closed
    direction that makes the attestation load-bearing rather than decorative."""
    tampered = [
        {"component": "vendor-llm", "phi_path": True, "self_hostable": False},
    ]
    with pytest.raises(ResidencyViolation) as excinfo:
        assert_registry_phi_path_self_hosted(tampered)
    assert "vendor-llm" in str(excinfo.value)


def test_registry_entry_type_also_refuses_a_non_self_hostable_phi_row() -> None:
    """Defence in depth: the loader's own validator refuses the same row, so a
    tampered file cannot even parse (invariant 19)."""
    with pytest.raises(ValueError):
        RegistryEntry(
            component="vendor-llm",
            self_hostable=False,
            self_hosted_now=False,
            host="vendor-llm.example",
            license="proprietary",
            probe="http_health",
            budget_ms=100,
            fallback="none",
            phi_path=True,
        )


def test_egress_assertion_bites_on_a_vendor_on_the_phi_path_tier() -> None:
    tampered = EgressAllowlist(
        version=1,
        tiers={
            "dev": [],
            "phi_path": [
                AllowlistEntry(
                    name="openai",
                    host=_OPENAI_HOST,
                    port=443,
                    protocol="https",
                    purpose_id=EgressPurpose.MODEL_WEIGHTS,
                    purpose="would put a vendor on the PHI path",
                    basis="none — this row must never exist",
                )
            ],
        },
    )
    with pytest.raises(ResidencyViolation):
        assert_egress_phi_path_vendor_free(tampered)


def test_egress_assertion_bites_on_a_phi_allowed_vendor_on_the_dev_tier() -> None:
    tampered = EgressAllowlist(
        version=1,
        tiers={
            "dev": [
                AllowlistEntry(
                    name="anthropic",
                    host=_ANTHROPIC_HOST,
                    port=443,
                    protocol="https",
                    purpose_id=EgressPurpose.MODEL_WEIGHTS,
                    purpose="a vendor approved for personal data",
                    basis="none — this row must never exist",
                    phi_allowed=True,
                    phi_exception_approval="fabricated-approval",
                )
            ],
            "phi_path": [],
        },
    )
    with pytest.raises(ResidencyViolation):
        assert_egress_phi_path_vendor_free(tampered)


# --- the Genelge 2019/12 attestation gate (fail-closed, awaiting-human) ------


def test_genelge_attestation_is_unsigned_and_fails_closed() -> None:
    attestation = draft_genelge_attestation()
    assert attestation.is_signed is False
    # the machine-checkable conformance IS attached and vendor-free …
    assert attestation.conformance.vendor_free is True
    # … but no legal attestation may be rendered until a human signs it.
    with pytest.raises(AttestationUnsigned) as excinfo:
        attestation.render()
    assert GENELGE_ATTESTATION_BLOCKER in str(excinfo.value)


def test_genelge_attestation_blocker_is_an_existing_human_blocker() -> None:
    """The clause points at a real HUMAN_BLOCKERS row (no minted id)."""
    hb = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
    assert f"**{GENELGE_ATTESTATION_BLOCKER}**" in hb


def test_genelge_attestation_renders_only_once_signed() -> None:
    """The gate is a gate, not a permanent raise: with a recorded signature it
    renders. The values here are obviously synthetic test fixtures — a real
    attestation is authored by a human into the repo, never by this test."""
    draft = draft_genelge_attestation()
    signed = draft.signed(
        attestation_statement_tr="<sentetik test beyanı — gerçek metin değildir>",
        signatory_name="<synthetic-signatory>",
        signatory_title="<synthetic-title>",
        signed_on=date(2026, 1, 1),
        signed_commit="0" * 40,
    )
    assert signed.is_signed is True
    rendered = signed.render()
    assert "<sentetik test beyanı" in rendered
    assert "<synthetic-signatory>" in rendered


# --- the derivable artefacts exist and carry no performance claim ------------


def test_rehber_mapping_doc_exists_and_is_claims_clean() -> None:
    assert REHBER_DOC.is_file(), "the DDO Rehber control mapping doc must exist"
    hits = scan_file(REHBER_DOC, _CLAIMS_GROUPS, relative_to=REPO)
    assert hits == (), f"invariant 20: performance-claim patterns in the Rehber doc: {hits}"


def test_rehber_mapping_doc_cites_the_derivable_controls_and_marks_human_rows() -> None:
    text = REHBER_DOC.read_text(encoding="utf-8")
    # derivable controls, each pointing at a committed artefact
    assert "infra/security/egress-allowlist.yaml" in text
    assert "observability/registry.yaml" in text
    # human-gated rows are marked and reference existing blockers, not minted ids
    assert "awaiting-human" in text
    for hb in ("HB-L11", "HB-A15", "HB-I12"):
        assert hb in text, f"{hb} must be referenced by a Rehber mapping row"


def test_genelge_doc_exists_is_claims_clean_and_marks_awaiting_human() -> None:
    assert GENELGE_DOC.is_file(), "the Genelge 2019/12 attestation pack must exist"
    hits = scan_file(GENELGE_DOC, _CLAIMS_GROUPS, relative_to=REPO)
    assert hits == (), f"invariant 20: performance-claim patterns in the Genelge doc: {hits}"
    text = GENELGE_DOC.read_text(encoding="utf-8")
    assert "awaiting-human" in text
    assert GENELGE_ATTESTATION_BLOCKER in text


def test_repo_root_finds_the_committed_sources() -> None:
    root = repo_root()
    assert (root / "observability" / "registry.yaml").is_file()
    assert (root / "infra" / "security" / "egress-allowlist.yaml").is_file()
