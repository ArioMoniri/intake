"""tr-residency vendor-free conformance + the Genelge 2019/12 attestation gate (INT-221).

files/00_STATE.md §0b and CLAUDE.md invariants 14/19: the PHI path is
self-hosted end to end, and the anthropic/openai/google adapters are the
mock/dev path only, blocked on the PHI path by the egress allow-list. A
public-hospital (``tr-residency``) tenant must be able to *prove* that, not
assert it — so this module cross-checks two committed sources and fails closed:

- **the self-hosting registry** (``observability/registry.yaml``) — every row
  that touches clinical data (``phi_path: true``) declares ``self_hostable:
  true``. Checked over the RAW yaml, independent of the pydantic model, so the
  assertion catches a bad row even if the loader's own validator were ever
  weakened (defence in depth);
- **the egress allow-list** (``infra/security/egress-allowlist.yaml``) — no
  vendor-LLM domain is reachable on the PHI path
  (:func:`intake_platform.egress.assert_dev_only_vendors`).

Those two are exactly the acceptance's *"every model & service on the PHI path
declares self_hostable=true AND no vendor adapter is reachable on that path"*.

The **Genelge 2019/12 residency attestation** is different in kind. A formal
attestation to the Ministry that health data resides in-country and reaches no
vendor is a *legal statement* — CLAUDE.md makes consent/legal-text a
stop-and-ask, and no agent may author one (files/HUMAN_BLOCKERS.md Rule 1). So
:class:`GenelgeResidencyAttestation` carries the machine-checkable conformance
this module derives, but its legal statement and signatory are empty and it
**refuses to render** until a named human signs it
(:class:`AttestationUnsigned`, naming HB-L11). The mechanism ships; the content
is left empty and fails closed, exactly as INT-210's ``LegalDocumentUnsigned``
and INT-298's ``pack_signoff`` do.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from intake_platform.egress import (
    EgressAllowlist,
    EgressConfigError,
    assert_dev_only_vendors,
    load_allowlist,
)

from intake_probes.registry import Registry, load_registry

__all__ = [
    "GENELGE_ATTESTATION_BLOCKER",
    "AttestationUnsigned",
    "GenelgeResidencyAttestation",
    "ResidencyControl",
    "ResidencyReport",
    "ResidencyViolation",
    "assert_egress_phi_path_vendor_free",
    "assert_registry_phi_path_self_hosted",
    "attest_residency",
    "default_allowlist_path",
    "default_registry_path",
    "draft_genelge_attestation",
    "load_registry_components_raw",
    "repo_root",
]

#: The existing HUMAN_BLOCKERS row that gates the Genelge 2019/12 attestation:
#: whether the residency claim is legally attestable at all is HB-L11's counsel
#: question (KVKK Art. 9 / in-country processing). No new id is minted here; the
#: signature regime a signed attestation would ride is HB-L27 (docs/legal).
GENELGE_ATTESTATION_BLOCKER = "HB-L11"

_REGISTRY_RELPATH = Path("observability") / "registry.yaml"
_ALLOWLIST_RELPATH = Path("infra") / "security" / "egress-allowlist.yaml"


class ResidencyViolation(Exception):
    """The committed configuration is not provably vendor-free on the PHI path.

    Raised — never returned as a soft flag — because a residency claim that
    cannot be proven must stop, not degrade: an unprovable claim rendered to a
    Ministry is the failure this module exists to prevent.
    """


class AttestationUnsigned(Exception):
    """A Genelge 2019/12 attestation was asked to render before a human signed it."""


def repo_root() -> Path:
    """Walk up from this file to the checkout root (the dir holding the registry)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / _REGISTRY_RELPATH).is_file():
            return parent
    raise FileNotFoundError(
        f"could not locate {_REGISTRY_RELPATH} above {__file__} — is this a full checkout?"
    )


def default_registry_path() -> Path:
    return repo_root() / _REGISTRY_RELPATH


def default_allowlist_path() -> Path:
    return repo_root() / _ALLOWLIST_RELPATH


def load_registry_components_raw(path: Path) -> list[dict[str, Any]]:
    """The registry rows as raw dicts, bypassing the pydantic model.

    Checking the invariant over raw yaml keeps the attestation independent of
    the loader: it would catch a phi_path/self_hostable violation even if the
    model's own validator were ever relaxed.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or not isinstance(raw.get("components"), list):
        raise ResidencyViolation(f"{path} is not a registry with a components list")
    components: list[dict[str, Any]] = []
    for row in raw["components"]:
        if not isinstance(row, Mapping):
            raise ResidencyViolation(f"{path} holds a non-mapping component row")
        components.append(dict(row))
    return components


def assert_registry_phi_path_self_hosted(components: Sequence[Mapping[str, Any]]) -> None:
    """Invariant 19 at the data layer: every PHI-path row is self-hostable.

    Operates on raw component mappings so it can genuinely fail on a tampered
    row (the near-miss control), not only when the typed loader would.
    """
    for row in components:
        if row.get("phi_path") and not row.get("self_hostable"):
            name = row.get("component", "<unnamed>")
            raise ResidencyViolation(
                f"registry component {name!r} is on the PHI path (phi_path: true) but "
                "is not self_hostable — a tr-residency tenant's PHI path must be "
                "vendor-free end to end (CLAUDE.md invariant 19 / 00_STATE §0b)"
            )


def assert_egress_phi_path_vendor_free(source: EgressAllowlist | Path) -> None:
    """No anthropic/openai/google adapter is reachable on the PHI path.

    Accepts either a loaded allow-list or a path to one. Wraps
    :func:`intake_platform.egress.assert_dev_only_vendors` so a vendor on the
    PHI path (or PHI-enabled anywhere) becomes a :class:`ResidencyViolation`
    rather than a lower-level config error, keeping the attestation's failure
    type uniform.
    """
    allowlist = load_allowlist(source) if isinstance(source, Path) else source
    try:
        assert_dev_only_vendors(allowlist)
    except EgressConfigError as exc:
        raise ResidencyViolation(
            f"egress allow-list is not vendor-free on the PHI path: {exc}"
        ) from exc


@dataclass(frozen=True)
class ResidencyControl:
    """One conformance control and the committed evidence it was checked over."""

    id: str
    statement: str
    status: str  # "pass" — a failing control raises rather than returning here
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ResidencyReport:
    """The machine-checkable residency posture: it exists only if it passed."""

    controls: tuple[ResidencyControl, ...]
    phi_path_components: tuple[str, ...]

    @property
    def vendor_free(self) -> bool:
        # The report is constructed only after every control passed; a failure
        # raises ResidencyViolation, so a report in hand is a vendor-free one.
        return all(control.status == "pass" for control in self.controls)


def attest_residency(
    *,
    registry_path: Path | None = None,
    allowlist_path: Path | None = None,
) -> ResidencyReport:
    """Cross-check the committed registry + allow-list. Fail-closed.

    Raises :class:`ResidencyViolation` on any violation; returns a
    :class:`ResidencyReport` only when the PHI path is provably vendor-free.
    """
    reg_path = registry_path if registry_path is not None else default_registry_path()
    allow_path = allowlist_path if allowlist_path is not None else default_allowlist_path()

    raw_components = load_registry_components_raw(reg_path)
    assert_registry_phi_path_self_hosted(raw_components)
    # The typed loader re-runs the same invariant plus schema validation; a
    # committed file that parses AND passes the raw check is doubly attested.
    registry: Registry = load_registry(reg_path)
    phi_components = tuple(entry.component for entry in registry if entry.phi_path)

    assert_egress_phi_path_vendor_free(allow_path)

    controls = (
        ResidencyControl(
            id="registry_phi_path_self_hosted",
            statement=(
                "Every model and service on the PHI path declares self_hostable: true "
                "(CLAUDE.md invariant 19)."
            ),
            status="pass",
            evidence=(str(_REGISTRY_RELPATH),),
        ),
        ResidencyControl(
            id="egress_phi_path_vendor_free",
            statement=(
                "No anthropic/openai/google adapter is reachable on the PHI path per the "
                "egress allow-list (CLAUDE.md invariants 14/19)."
            ),
            status="pass",
            evidence=(str(_ALLOWLIST_RELPATH),),
        ),
    )
    return ResidencyReport(controls=controls, phi_path_components=phi_components)


@dataclass(frozen=True)
class GenelgeResidencyAttestation:
    """The Genelge 2019/12 residency attestation: mechanism built, content empty.

    The machine-derived :attr:`conformance` is filled by this module. The legal
    statement and signatory are left ``None`` because a legal attestation to the
    Ministry is human content no agent may author (CLAUDE.md stop-and-ask;
    HUMAN_BLOCKERS Rule 1). :meth:`render` refuses until they are supplied.
    """

    conformance: ResidencyReport
    attestation_statement_tr: str | None = None
    signatory_name: str | None = None
    signatory_title: str | None = None
    signed_on: date | None = None
    signed_commit: str | None = None
    blocker: str = field(default=GENELGE_ATTESTATION_BLOCKER)

    _SIGNATURE_FIELDS = (
        "attestation_statement_tr",
        "signatory_name",
        "signatory_title",
        "signed_on",
        "signed_commit",
    )

    @property
    def missing_signature_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        for name in self._SIGNATURE_FIELDS:
            value = getattr(self, name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)
        return tuple(missing)

    @property
    def is_signed(self) -> bool:
        return not self.missing_signature_fields

    def signed(
        self,
        *,
        attestation_statement_tr: str,
        signatory_name: str,
        signatory_title: str,
        signed_on: date,
        signed_commit: str,
    ) -> GenelgeResidencyAttestation:
        """Return a copy carrying a recorded signature (a human action)."""
        return replace(
            self,
            attestation_statement_tr=attestation_statement_tr,
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            signed_on=signed_on,
            signed_commit=signed_commit,
        )

    def ensure_signed(self) -> None:
        if not self.is_signed:
            raise AttestationUnsigned(
                "the Genelge 2019/12 residency attestation cannot be rendered: its legal "
                f"statement and signatory are unset ({', '.join(self.missing_signature_fields)}). "
                "A legal attestation to the Ministry is human content no agent may author "
                f"(awaiting-human: {self.blocker}). The machine-checkable conformance is "
                "attached and vendor-free; the signature is not."
            )

    def render(self) -> str:
        """The signed attestation body. Refuses while unsigned (fail-closed)."""
        self.ensure_signed()
        # ensure_signed guarantees these are set; the `or ""` keeps mypy happy
        # without an assert (S101) on this production path.
        signed_on_iso = self.signed_on.isoformat() if self.signed_on else ""
        lines = [
            "GENELGE 2019/12 — RESIDENCY ATTESTATION",
            "",
            self.attestation_statement_tr or "",
            "",
            "Machine-checkable conformance (derived, not attested):",
        ]
        for control in self.conformance.controls:
            lines.append(f"  - [{control.status}] {control.id}: {control.statement}")
        lines.extend(
            [
                "",
                f"Signatory: {self.signatory_name} ({self.signatory_title})",
                f"Signed on: {signed_on_iso}",
                f"Signed commit: {self.signed_commit}",
            ]
        )
        return "\n".join(lines)


def draft_genelge_attestation(
    *,
    registry_path: Path | None = None,
    allowlist_path: Path | None = None,
) -> GenelgeResidencyAttestation:
    """Build the attestation with conformance derived and the legal content empty.

    Fails closed twice over: :func:`attest_residency` raises if the PHI path is
    not provably vendor-free, and the returned attestation refuses to render
    until a human signs it.
    """
    conformance = attest_residency(registry_path=registry_path, allowlist_path=allowlist_path)
    return GenelgeResidencyAttestation(conformance=conformance)
