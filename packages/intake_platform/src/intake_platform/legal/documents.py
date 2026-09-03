"""INT-210 — the docs/legal document SET: what it contains, and what a row is.

CLAUDE.md invariant 18: *"consent and legal texts render only from
``docs/legal/`` with hash binding; the fixed strings in
``docs/legal/strings.yaml`` are verbatim."*

INT-038 bound one consent text at a time (:mod:`intake_platform.consent.texts`)
and INT-037 bound the fixed strings (:mod:`intake_platform.legal.strings`).
Neither can express the three things this issue's acceptance asks for, because
none of them is a property of a single file:

``docs/legal/ versioned with hashes``
    A **set** has a version. ``documents.yaml`` is that version: one row per
    document carrying ``{version, sha256}``, and the loader refuses a row whose
    hash no longer matches the bytes on disk. A document outside the closed
    required set below is a defect in the index, not an extra document.
``plain-language summaries``
    A summary is a second file bound to the first. Binding them separately
    would let the two drift, which is precisely the failure the clause exists
    to prevent, so a document whose summary is absent or has moved does not
    serve at all.
``counsel sign-off recorded in evidence file before merge``
    The gate. A document with no ``counsel:`` block — or one missing any of its
    three facts, or pointing anywhere but ``docs/evidence/INT-210.md`` — is
    **unservable**, the way ``instrument_licence_gate`` makes a non-``GO``
    instrument uncompilable. Sign-off is not metadata about a document; it is
    the condition of the document existing at all.

**This module authors no legal copy and never will.** The five aydınlatma
metinleri, the eleven açık rıza texts, the gizlilik policy, the kullanım
koşulları, the KVKK başvuru formu, the çerez policy and the files/06 §7 fixed
strings are human legal work. ``docs/legal/documents.yaml`` ships with
``documents: []``, every required id refuses today, and that empty-but-gated
state is the deliverable — a plausible draft would load, hash, bind to real
acceptances and become indistinguishable from counsel's own words once merged
(CLAUDE.md invariant 17; the same reasoning ``dsar/strings.py`` records for the
fixed strings, and ``docs/legal/COUNSEL_BRIEF.md`` §5 for the consent texts).

Two lists this module deliberately does not own. The five aydınlatma channels
come from :data:`intake_platform.consent.registry.CHANNELS` (files/06 §1's
KVKK-10 row: app, kiosk, clinician, admin, web) and the eleven açık rıza rows
from :func:`~intake_platform.consent.registry.purpose_ids` with
:func:`~intake_platform.consent.texts.text_filename` — so a purpose added to
files/06 §2 gains a required legal document without anyone remembering to add
it here, and a text can never be signed in the index while absent from the
loader the consent guard actually reads.

The loader over these declarations is :mod:`intake_platform.legal.document_index`.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

from intake_platform.consent.registry import CHANNELS, purpose_ids
from intake_platform.consent.texts import text_filename

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
    "LegalDocumentUnsignedError",
    "RequiredDocument",
    "UnknownLegalDocumentError",
    "document_ids",
    "required_document",
]

#: The signed index, beside the documents it binds.
LEGAL_INDEX_FILENAME: Final[str] = "documents.yaml"

#: The acceptance clause names one file and only one. A sign-off recorded
#: anywhere else is not "recorded in evidence file".
COUNSEL_EVIDENCE_PATH: Final[str] = "docs/evidence/INT-210.md"

#: files/06 §1, KVKK-10 + AYD-2018. Showing an aydınlatma metni discharges an
#: obligation; it is not a patient consent scope — the same shape
#: ``admin.audit.ADMIN_BASIS_REF`` uses for KVKK-12.
ACCEPTANCE_BASIS_REF: Final[str] = "basis:KVKK-10"
ACCEPTANCE_ACTION: Final[str] = "legal_document.accepted"


class DocumentKind(enum.StrEnum):
    """The closed kinds of INT-210's set. ``lane:acoustic`` has no kind and
    never will: files/06 §2.4 makes it an investigational-device ICF under
    TCKAY — a different artefact with its own required content list and its
    own approval chain, not a ``{version, text_hash}`` row."""

    AYDINLATMA = "aydinlatma"
    ACIK_RIZA = "acik_riza"
    GIZLILIK = "gizlilik"
    KULLANIM_KOSULLARI = "kullanim_kosullari"
    KVKK_BASVURU = "kvkk_basvuru"
    CEREZ = "cerez"
    FIXED_STRINGS = "fixed_strings"


class LegalDocumentError(Exception):
    """Base for document-set failures. Messages carry paths and ids only —
    never the copy (invariant 6)."""


class UnknownLegalDocumentError(LegalDocumentError, LookupError):
    """An id outside the closed required set."""


class LegalDocumentMissingError(LegalDocumentError):
    """No index, no row, or no file yet. Fail closed: nothing renders."""


class LegalDocumentInvalidError(LegalDocumentError):
    """The index or a document exists but breaks the contract."""


class LegalDocumentHashMismatchError(LegalDocumentError):
    """The bytes are not the bytes that were signed."""


class LegalDocumentUnsignedError(LegalDocumentError):
    """No counsel sign-off. The document exists and still does not serve."""


@dataclass(frozen=True)
class RequiredDocument:
    """One row of the closed set. ``summary_path`` is ``None`` only for the
    fixed strings, which are the verbatim sentences other documents embed
    rather than a document a patient reads end to end — summarising copy that
    may not be paraphrased would defeat the point of it being fixed."""

    id: str
    kind: DocumentKind
    relative_path: str
    summary_path: str | None
    source: str


@dataclass(frozen=True)
class CounselSignoff:
    """Three facts or it is not a sign-off: who, when, and where it is
    recorded. ``evidence`` must be inside :data:`COUNSEL_EVIDENCE_PATH`."""

    signed_by: str
    signed_on: date
    evidence: str


@dataclass(frozen=True)
class IndexRow:
    """One parsed row of ``documents.yaml``, before the bytes are read."""

    id: str
    version: str
    sha256: str
    summary_sha256: str | None
    counsel: CounselSignoff | None


@dataclass(frozen=True)
class LegalDocument:
    """One servable document: signed, hash-bound, summarised."""

    id: str
    kind: DocumentKind
    version: str
    text_hash: str
    summary_hash: str | None
    path: Path
    body: str
    summary: str | None
    counsel: CounselSignoff


@dataclass(frozen=True)
class LegalAcceptance:
    """The evidence a document was shown, bound to the exact bytes shown."""

    document_id: str
    version: str
    text_hash: str
    summary_hash: str | None
    actor: str
    channel: str
    accepted_at: datetime
    audit_seq: int


def _summary_path(document_id: str) -> str:
    return f"summaries/{document_id}.tr.md"


def _standalone() -> tuple[tuple[str, DocumentKind, str, str], ...]:
    return (
        ("gizlilik", DocumentKind.GIZLILIK, "gizlilik.tr.md", "INT-210 title"),
        (
            "kullanim_kosullari",
            DocumentKind.KULLANIM_KOSULLARI,
            "kullanim-kosullari.tr.md",
            "INT-210 title",
        ),
        (
            "kvkk_basvuru_formu",
            DocumentKind.KVKK_BASVURU,
            "kvkk-basvuru-formu.tr.md",
            "INT-210 title; KVKK m.11/m.13 (INT-037 answers the request itself)",
        ),
        ("cerez", DocumentKind.CEREZ, "cerez.tr.md", "INT-210 title"),
    )


def _build_required() -> tuple[RequiredDocument, ...]:
    rows: list[RequiredDocument] = [
        RequiredDocument(
            id=f"aydinlatma.{channel}",
            kind=DocumentKind.AYDINLATMA,
            relative_path=f"aydinlatma/{channel}.tr.md",
            summary_path=_summary_path(f"aydinlatma.{channel}"),
            source="files/06 §1 (KVKK-10 + AYD-2018): layered aydınlatma per channel",
        )
        for channel in CHANNELS
    ]
    rows += [
        RequiredDocument(
            id="acik_riza." + purpose.replace(":", "."),
            kind=DocumentKind.ACIK_RIZA,
            relative_path=f"consents/{text_filename(purpose)}",
            summary_path=_summary_path("acik_riza." + purpose.replace(":", ".")),
            source="files/06 §2: one açık rıza text per purpose (INT-038 loads the same file)",
        )
        for purpose in purpose_ids()
    ]
    rows += [
        RequiredDocument(
            id=document_id,
            kind=kind,
            relative_path=filename,
            summary_path=_summary_path(document_id),
            source=source,
        )
        for document_id, kind, filename, source in _standalone()
    ]
    rows.append(
        RequiredDocument(
            id="strings",
            kind=DocumentKind.FIXED_STRINGS,
            relative_path="strings.yaml",
            summary_path=None,
            source="files/06 §7 + invariant 18's second sentence: verbatim fixed copy",
        )
    )
    return tuple(rows)


REQUIRED_DOCUMENTS: Final[tuple[RequiredDocument, ...]] = _build_required()
_BY_ID: Final[Mapping[str, RequiredDocument]] = {row.id: row for row in REQUIRED_DOCUMENTS}


def document_ids() -> tuple[str, ...]:
    """The closed set, in registry order."""
    return tuple(_BY_ID)


def required_document(document_id: str) -> RequiredDocument:
    """The declaration for ``document_id``, or a refusal. An id outside the set
    is never treated as an extra document somebody meant to add."""
    try:
        return _BY_ID[document_id]
    except KeyError as exc:
        raise UnknownLegalDocumentError(
            f"{document_id!r} is not a document of the INT-210 set; the set is closed "
            "(files/06 §1 channels, files/06 §2 purposes, the four standalone documents "
            "and the files/06 §7 fixed strings)"
        ) from exc
