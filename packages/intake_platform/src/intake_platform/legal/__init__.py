"""Legal-text binding (invariant 18): docs/legal is the only source, and the
hash proves which bytes were shown.

Three loaders, one contract. :mod:`intake_platform.consent.texts` binds a
single açık rıza text for the consent guard (INT-038); :mod:`.strings` binds
the files/06 §7 fixed copy for the documents that embed it (INT-037); and
:mod:`.documents` with :mod:`.document_index` binds the SET (INT-210) — the
version of docs/legal as a whole, the plain-language summary beside each
document, and the counsel sign-off without which a document is unservable.
"""

from __future__ import annotations

from intake_platform.legal.document_index import LegalDocumentSet, record_acceptance
from intake_platform.legal.documents import (
    ACCEPTANCE_ACTION,
    ACCEPTANCE_BASIS_REF,
    COUNSEL_EVIDENCE_PATH,
    LEGAL_INDEX_FILENAME,
    REQUIRED_DOCUMENTS,
    CounselSignoff,
    DocumentKind,
    IndexRow,
    LegalAcceptance,
    LegalDocument,
    LegalDocumentError,
    LegalDocumentHashMismatchError,
    LegalDocumentInvalidError,
    LegalDocumentMissingError,
    LegalDocumentUnsignedError,
    RequiredDocument,
    UnknownLegalDocumentError,
    document_ids,
    required_document,
)
from intake_platform.legal.strings import (
    LegalStrings,
    LegalStringsCatalog,
    LegalStringsChangedError,
    LegalStringsError,
    LegalStringsInvalidError,
    LegalStringsMissingError,
)

__all__ = [
    "ACCEPTANCE_ACTION",
    "ACCEPTANCE_BASIS_REF",
    "COUNSEL_EVIDENCE_PATH",
    "LEGAL_INDEX_FILENAME",
    "REQUIRED_DOCUMENTS",
    "CounselSignoff",
    "DocumentKind",
    "IndexRow",
    "LegalAcceptance",
    "LegalDocument",
    "LegalDocumentError",
    "LegalDocumentHashMismatchError",
    "LegalDocumentInvalidError",
    "LegalDocumentMissingError",
    "LegalDocumentSet",
    "LegalDocumentUnsignedError",
    "LegalStrings",
    "LegalStringsCatalog",
    "LegalStringsChangedError",
    "LegalStringsError",
    "LegalStringsInvalidError",
    "LegalStringsMissingError",
    "RequiredDocument",
    "UnknownLegalDocumentError",
    "document_ids",
    "record_acceptance",
    "required_document",
]
