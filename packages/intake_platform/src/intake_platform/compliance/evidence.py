"""The auditor's evidence-export bundle (INT-189).

Acceptance: *"evidence export bundles for audits"*. `legal: KVKK-9,
TRANSFER-2024`; `sec_row: compliance-evidence`.

An evidence bundle is a text-typed tabular artefact an ``auditor`` or
``compliance_officer`` hands a KVKK inspector, a notified body or counsel. Two
rules shape it:

- **Every cell is neutralised.** files/08 §0c F13 / invariant 47: the export is
  opened in a spreadsheet, and a value someone else wrote must not evaluate
  there. Every cell goes through the one shared guard,
  :func:`intake_platform.export_safety.sanitise_cell` — the same function the
  DSAR export uses, so there is no second copy to drift.
- **Ids, counts and dates only** (invariant 6). The bundle carries the vendor
  register, consent coverage, the DSAR SLA and the audit-chain *status* — never
  a chain head or hash (HB-I12), never patient content.

The bundle carries a SHA-256 over its sanitised content so an inspector can
tell two exports apart and detect a later edit.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from intake_platform.compliance.register import VendorRegisterRow
from intake_platform.export_safety import sanitise_cell

__all__ = [
    "LEGAL_REFS",
    "AuditChainStatus",
    "ConsentCoverageRow",
    "DsarSlaRow",
    "EvidenceBundle",
    "EvidenceSection",
    "build_evidence_bundle",
    "seal_bundle",
]

#: The obligations this bundle is evidence for (INT-189 issue `legal:` field).
LEGAL_REFS: Final = ("KVKK-9", "TRANSFER-2024")


@dataclass(frozen=True)
class ConsentCoverageRow:
    """Consent coverage for one (scope, version): counts only (invariant 6)."""

    scope: str
    version: str
    granted: int
    withdrawn: int


@dataclass(frozen=True)
class DsarSlaRow:
    """DSAR queue depth by status, with the oldest KVKK m.13 due-date."""

    status: str
    count: int
    oldest_due: str | None


@dataclass(frozen=True)
class AuditChainStatus:
    """The daily verifier's verdict — a boolean and a date, not the chain.

    Fail-closed: an unknown status is ``verified=False``, so a missing verifier
    result reads as "not shown to be intact" rather than a silent green.
    """

    verified: bool
    checked_at: str | None


@dataclass(frozen=True)
class EvidenceSection:
    """One table in the bundle. Every cell is already sanitised."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class EvidenceBundle:
    generated_at: str
    legal_refs: tuple[str, ...]
    sections: tuple[EvidenceSection, ...]
    #: ``base64url(sha256(canonical))`` over the sanitised content. Base64
    #: rather than hex on purpose: a 64-hex string is the shape of an audit
    #: chain hash, and the console must not hand one back (HB-I12) — the
    #: `no_admin_response_carries_a_chain_hash` guard rejects any 64-hex. This
    #: is a content digest, not chain material, so it wears a different shape.
    digest: str


def _row(*values: object) -> tuple[str, ...]:
    return tuple(sanitise_cell(str(value)) for value in values)


def _register_section(register: Sequence[VendorRegisterRow]) -> EvidenceSection:
    columns = (
        "host",
        "purpose",
        "category",
        "basis",
        "retention",
        "recipients",
        "data_class",
        "first_seen",
        "last_seen",
        "transfers",
        "bytes_out",
        "notification_due",
        "window_open",
    )
    rows = tuple(
        _row(
            r.host,
            r.purpose,
            r.category,
            r.basis,
            r.retention,
            r.recipients,
            r.data_class.value,
            r.first_seen.isoformat(),
            r.last_seen.isoformat(),
            r.transfer_count,
            r.bytes_out,
            r.notification_due.isoformat(),
            "open" if r.notification_window_open else "elapsed",
        )
        for r in register
    )
    return EvidenceSection("vendor_transfer_register", columns, rows)


def _consent_section(coverage: Sequence[ConsentCoverageRow]) -> EvidenceSection:
    columns = ("scope", "version", "granted", "withdrawn")
    rows = tuple(_row(c.scope, c.version, c.granted, c.withdrawn) for c in coverage)
    return EvidenceSection("consent_coverage", columns, rows)


def _dsar_section(sla: Sequence[DsarSlaRow]) -> EvidenceSection:
    columns = ("status", "count", "oldest_due")
    rows = tuple(
        _row(d.status, d.count, d.oldest_due if d.oldest_due is not None else "-") for d in sla
    )
    return EvidenceSection("dsar_sla", columns, rows)


def _audit_section(status: AuditChainStatus) -> EvidenceSection:
    columns = ("verified", "checked_at")
    rows = (_row(str(status.verified).lower(), status.checked_at if status.checked_at else "-"),)
    return EvidenceSection("audit_chain", columns, rows)


def _digest(
    generated_at: str, legal_refs: tuple[str, ...], sections: tuple[EvidenceSection, ...]
) -> str:
    payload = {
        "generated_at": generated_at,
        "legal_refs": list(legal_refs),
        "sections": [
            {"title": s.title, "columns": list(s.columns), "rows": [list(row) for row in s.rows]}
            for s in sections
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    raw = hashlib.sha256(canonical.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def seal_bundle(
    *, generated_at: str, legal_refs: tuple[str, ...], sections: tuple[EvidenceSection, ...]
) -> EvidenceBundle:
    """Bind already-sanitised sections into a bundle with its content digest.

    The one sealing step every auditor export shares (INT-189's bundle and
    INT-215's 2018/10 packet), so the digest rule has a single copy.
    """
    return EvidenceBundle(
        generated_at=generated_at,
        legal_refs=legal_refs,
        sections=sections,
        digest=_digest(generated_at, legal_refs, sections),
    )


def build_evidence_bundle(
    *,
    generated_at: str,
    register: Sequence[VendorRegisterRow],
    consent_coverage: Sequence[ConsentCoverageRow],
    dsar_sla: Sequence[DsarSlaRow],
    audit_chain: AuditChainStatus,
) -> EvidenceBundle:
    """Assemble the four-section bundle and bind it with a content digest."""
    sections = (
        _register_section(register),
        _consent_section(consent_coverage),
        _dsar_section(dsar_sla),
        _audit_section(audit_chain),
    )
    return seal_bundle(generated_at=generated_at, legal_refs=LEGAL_REFS, sections=sections)
