"""INT-320 (follow-up) — resolving an embed launch's consent document set.

The launch returns a ``consent_doc_set_id``; this module turns it into the
hash-bound documents the branded intake must show before any clinical turn
(ADR-029; invariants 4 and 18). The dev set is two documents:

- ``core`` — the standard service consent, loaded from the SAME global catalog
  a later ``POST /v1/consents/grant`` binds against, so what the patient reads
  and what a grant records can never drift (files/06 §2);
- ``partner_processor`` — the partner-processor disclosure (aydınlatma, shown
  but never granted), loaded from the tenant's own ``legal_root`` so a partner's
  processing statement is per-tenant.

Fail closed like the rest of the legal flow: if EITHER document is absent the
set is empty, and the API turns an empty set into a 503 — never a launch that
shows the patient nothing. This module authors no copy; it only binds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from intake_platform.consent.texts import (
    ConsentTextCatalog,
    ConsentTextMissingError,
    bind_legal_document,
    text_filename,
)

__all__ = [
    "CORE_DOC_ID",
    "DISCLOSURE_DOC_ID",
    "EmbedConsentDocument",
    "EmbedConsentDocumentSet",
    "embed_disclosure_root",
    "resolve_embed_consent_documents",
]

#: The grantable service consent — the same ``core`` purpose the ledger records.
CORE_DOC_ID = "core"

#: The partner-processor disclosure — shown, never granted.
DISCLOSURE_DOC_ID = "partner_processor"

#: Tenant ``legal_root`` values are repo-relative under this prefix; the dev
#: base (``~/.config/intake/dev-legal``) replaces it so the same code reads the
#: committed tree in prod and the dev tree locally.
_LEGAL_PREFIX = "docs/legal/"


@dataclass(frozen=True)
class EmbedConsentDocument:
    """One document in an embed consent set — hash-bound, ready to show."""

    doc_id: str
    #: ``consent`` (a grantable açık rıza) or ``disclosure`` (aydınlatma, shown
    #: but never granted). The branded shell shows both; it may only send a
    #: grant for a ``consent`` document.
    kind: str
    #: The files/06 §2 scope a grant records against, or ``None`` for a
    #: disclosure. This is what ties the shown ``core`` text to the scope the
    #: patient later grants through Vizite's own consent flow.
    grant_scope: str | None
    version: str
    text_hash: str
    body: str


@dataclass(frozen=True)
class EmbedConsentDocumentSet:
    """The ordered documents an embed launch must show. Empty means fail
    closed: one or more required documents are unauthored."""

    doc_set_id: str
    documents: tuple[EmbedConsentDocument, ...]


def embed_disclosure_root(tenant_legal_root: str, legal_base: Path) -> Path:
    """Resolve a tenant's repo-relative ``legal_root`` under ``legal_base``.

    A tenant row records ``docs/legal/embed/<tenant>`` (where counsel-vetted
    texts live in the committed tree). In dev the same tree lives under the
    dev-legal base, so the ``docs/legal/`` prefix is swapped for it — one code
    path, two roots. A ``legal_root`` outside the prefix is joined as-is.
    """
    rel = tenant_legal_root
    if rel.startswith(_LEGAL_PREFIX):
        rel = rel[len(_LEGAL_PREFIX) :]
    return legal_base / rel


def _try_disclosure(root: Path, doc_id: str) -> tuple[str, str, str] | None:
    """(version, text_hash, body) for a disclosure, or ``None`` when its file
    is not authored yet (fail closed). An invalid file still raises — an
    unversionable text is a defect in the legal tree, not a quiet absence
    (matches ``ConsentTextCatalog.try_entry``)."""
    try:
        bound = bind_legal_document(root / text_filename(doc_id))
    except ConsentTextMissingError:
        return None
    return bound.version, bound.text_hash, bound.body


def resolve_embed_consent_documents(
    *,
    doc_set_id: str,
    consent_catalog: ConsentTextCatalog,
    disclosure_root: Path,
) -> EmbedConsentDocumentSet:
    """Bind the embed consent set, fail closed.

    ``core`` comes from ``consent_catalog`` (the global tree a grant binds
    against); the partner-processor disclosure comes from ``disclosure_root``
    (the tenant's own tree). If either is unauthored the set is empty.
    """
    core = consent_catalog.try_entry(CORE_DOC_ID)
    disclosure = _try_disclosure(disclosure_root, DISCLOSURE_DOC_ID)
    if core is None or disclosure is None:
        return EmbedConsentDocumentSet(doc_set_id=doc_set_id, documents=())
    version, text_hash, body = disclosure
    documents = (
        EmbedConsentDocument(
            doc_id=CORE_DOC_ID,
            kind="consent",
            grant_scope=CORE_DOC_ID,
            version=core.version,
            text_hash=core.text_hash,
            body=core.body,
        ),
        EmbedConsentDocument(
            doc_id=DISCLOSURE_DOC_ID,
            kind="disclosure",
            grant_scope=None,
            version=version,
            text_hash=text_hash,
            body=body,
        ),
    )
    return EmbedConsentDocumentSet(doc_set_id=doc_set_id, documents=documents)
