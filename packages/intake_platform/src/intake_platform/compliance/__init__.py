"""Compliance-console building blocks (INT-189; files/08 §4 "Compliance").

Pure projections behind the admin console's Compliance module: the KVKK
vendor-transfer register auto-filled from the egress feed, an ids-only audit
search, and the auditor's evidence-export bundle. None of these holds a
database session or an app — they take facts in and return the shape the
console renders, so they are unit-tested without either (the same division the
INT-183 models module draws).
"""

from __future__ import annotations

from intake_platform.compliance.audit_search import (
    AuditSearchContentRefused,
    AuditSearchQuery,
    AuditSearchRow,
    search_audit,
)
from intake_platform.compliance.evidence import (
    LEGAL_REFS,
    AuditChainStatus,
    ConsentCoverageRow,
    DsarSlaRow,
    EvidenceBundle,
    EvidenceSection,
    build_evidence_bundle,
)
from intake_platform.compliance.register import (
    NOTIFICATION_WINDOW_BUSINESS_DAYS,
    MissingLawfulBasis,
    VendorRegisterRow,
    add_business_days,
    build_register,
)

__all__ = [
    "LEGAL_REFS",
    "NOTIFICATION_WINDOW_BUSINESS_DAYS",
    "AuditChainStatus",
    "AuditSearchContentRefused",
    "AuditSearchQuery",
    "AuditSearchRow",
    "ConsentCoverageRow",
    "DsarSlaRow",
    "EvidenceBundle",
    "EvidenceSection",
    "MissingLawfulBasis",
    "VendorRegisterRow",
    "add_business_days",
    "build_evidence_bundle",
    "build_register",
    "search_audit",
]
