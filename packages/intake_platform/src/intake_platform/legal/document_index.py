"""INT-210 — the loader over ``docs/legal/documents.yaml``, fail closed.

The declarations live in :mod:`intake_platform.legal.documents`; this module is
the half that reads bytes and refuses. Four refusals, in the order they are
checked, because the order is the difference between a gate and a suggestion:

1. **no index, or no row** → :class:`~intake_platform.legal.documents.LegalDocumentMissingError`.
   The set is declared before it is authored, so an absent document is an
   absence the code already knows the shape of.
2. **no counsel sign-off** →
   :class:`~intake_platform.legal.documents.LegalDocumentUnsignedError`, checked
   *before* the bytes are read: a document nobody signed does not become
   servable by having a correct hash.
3. **bytes that do not hash to the signed value** →
   :class:`~intake_platform.legal.documents.LegalDocumentHashMismatchError`,
   for the document and for its plain-language summary alike.
4. **a performance claim** →
   :class:`~intake_platform.legal.documents.LegalDocumentInvalidError`.
   Invariant 20's CI gate scans this tree between merges; this one refuses at
   render, so a claim cannot reach a patient in the window between the two.

Nothing is cached. That is the acceptance's "rendered in-app from source"
clause made structural rather than promised: every lookup re-reads the file, so
a document edited under a live process stops rendering rather than serving
bytes nobody approved.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

import yaml

from intake_platform.audit import AuditChain
from intake_platform.consent.registry import CHANNELS
from intake_platform.legal.claims import SCANNED_TREES, scan_text
from intake_platform.legal.documents import (
    ACCEPTANCE_ACTION,
    ACCEPTANCE_BASIS_REF,
    COUNSEL_EVIDENCE_PATH,
    LEGAL_INDEX_FILENAME,
    CounselSignoff,
    IndexRow,
    LegalAcceptance,
    LegalDocument,
    LegalDocumentError,
    LegalDocumentHashMismatchError,
    LegalDocumentInvalidError,
    LegalDocumentMissingError,
    LegalDocumentUnsignedError,
    UnknownLegalDocumentError,
    document_ids,
    required_document,
)

__all__ = ["LegalDocumentSet", "record_acceptance"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: Invariant 20's pattern groups for this tree, read from the one declaration
#: rather than copied — ``claims.py`` exists because a second copy makes the
#: gate a habit instead of a rule.
_CLAIM_GROUPS: Final[tuple[str, ...]] = next(
    tree.groups for tree in SCANNED_TREES if tree.path == "docs/legal"
)


def _text(row: Mapping[str, Any], key: str, *, where: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LegalDocumentInvalidError(f"{where}: {key!r} must be a non-empty string")
    return value.strip()


def _signoff(raw: object, *, where: str) -> CounselSignoff | None:
    """A sign-off is three facts or it is not one. A partial block returns
    ``None`` rather than raising, so the caller can raise the error that says
    what is actually wrong: nobody signed this. A sign-off pointing at the
    wrong file is different — it is a claim of a record that is not there, so
    it refuses here and by name."""
    if not isinstance(raw, Mapping):
        return None
    signed_by = raw.get("signed_by")
    signed_on = raw.get("signed_on")
    evidence = raw.get("evidence")
    if not isinstance(signed_by, str) or not signed_by.strip():
        return None
    if not isinstance(signed_on, date) or isinstance(signed_on, datetime):
        return None
    if not isinstance(evidence, str) or not evidence.strip():
        return None
    if not evidence.strip().startswith(COUNSEL_EVIDENCE_PATH):
        raise LegalDocumentUnsignedError(
            f"{where}: counsel evidence must point at {COUNSEL_EVIDENCE_PATH} — the "
            "acceptance says the sign-off is recorded in the evidence file"
        )
    return CounselSignoff(signed_by.strip(), signed_on, evidence.strip())


def _parse_row(raw: object, *, where: str) -> IndexRow:
    if not isinstance(raw, Mapping):
        raise LegalDocumentInvalidError(f"{where}: every documents entry must be a mapping")
    document_id = _text(raw, "id", where=where)
    try:
        required = required_document(document_id)
    except UnknownLegalDocumentError as exc:
        # An id the set does not contain is a defect in the INDEX, not a
        # document somebody meant to add: the set is closed, and a row for
        # something outside it would sign bytes nothing ever renders.
        raise LegalDocumentInvalidError(f"{where}: {exc}") from exc
    version = _text(raw, "version", where=where)
    if not _VERSION.match(version):
        raise LegalDocumentInvalidError(f"{where}: {document_id!r} has a malformed version")
    digest = _text(raw, "sha256", where=where)
    if not _SHA256.match(digest):
        raise LegalDocumentInvalidError(f"{where}: {document_id!r} sha256 is not a SHA-256 hex")
    summary_digest: str | None = None
    if required.summary_path is not None:
        summary_digest = _text(raw, "summary_sha256", where=where)
        if not _SHA256.match(summary_digest):
            raise LegalDocumentInvalidError(
                f"{where}: {document_id!r} summary_sha256 is not a SHA-256 hex"
            )
    return IndexRow(
        id=document_id,
        version=version,
        sha256=digest,
        summary_sha256=summary_digest,
        counsel=_signoff(raw.get("counsel"), where=f"{where}:{document_id}"),
    )


def _read(path: Path, *, document_id: str, what: str) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise LegalDocumentMissingError(
            f"no {what} for {document_id!r} at {path} — the INT-210 document set is "
            "authored by counsel; nothing renders without it"
        ) from exc
    try:
        return raw, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LegalDocumentInvalidError(f"{path}: not valid UTF-8") from exc


def _check_claims(text: str, *, document_id: str, what: str) -> None:
    hits = scan_text(text, groups=_CLAIM_GROUPS, path=document_id)
    if hits:
        raise LegalDocumentInvalidError(
            f"{document_id}: the {what} carries a performance claim "
            f"({hits[0].pattern}, line {hits[0].line_no}) — invariant 20 forbids one "
            "anywhere under docs/legal"
        )


class LegalDocumentSet:
    """Reads ``documents.yaml`` and the bytes it binds, fresh on every lookup."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def index_path(self) -> Path:
        return self._root / LEGAL_INDEX_FILENAME

    def index(self) -> Mapping[str, IndexRow]:
        """Every declared row, keyed by id, or a fail-closed error."""
        path = self.index_path
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise LegalDocumentMissingError(
                f"no legal document index at {path} — the INT-210 set is declared there "
                "and nothing under docs/legal renders until a row is signed"
            ) from exc
        try:
            loaded = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise LegalDocumentInvalidError(f"{path}: not valid YAML") from exc
        if not isinstance(loaded, Mapping):
            raise LegalDocumentInvalidError(f"{path}: the index must be a mapping")
        version = loaded.get("legal_index_version")
        if not isinstance(version, str) or not _VERSION.match(version.strip()):
            raise LegalDocumentInvalidError(
                f"{path}: no legal_index_version — the SET is versioned, not only its files"
            )
        documents = loaded.get("documents") or []
        if not isinstance(documents, Sequence) or isinstance(documents, str | bytes):
            raise LegalDocumentInvalidError(f"{path}: 'documents' must be a list")
        rows: dict[str, IndexRow] = {}
        for entry in documents:
            row = _parse_row(entry, where=str(path))
            if row.id in rows:
                raise LegalDocumentInvalidError(
                    f"{path}: {row.id!r} is declared twice — two hashes for one document "
                    "is two answers to the question of which bytes were signed"
                )
            rows[row.id] = row
        return rows

    def entry(self, document_id: str) -> LegalDocument:
        """The servable document, or the one error that says why not."""
        required = required_document(document_id)
        row = self.index().get(document_id)
        if row is None:
            raise LegalDocumentMissingError(
                f"{document_id!r} is not declared in {self.index_path} — it is owed by "
                "counsel (docs/evidence/INT-210.md §7) and nothing renders until it is"
            )
        if row.counsel is None:
            raise LegalDocumentUnsignedError(
                f"{document_id!r} carries no counsel sign-off (signed_by, signed_on and "
                f"evidence in {self.index_path}) — an unsigned legal document is "
                "unservable, not provisional"
            )

        path = self._root / required.relative_path
        raw, text = _read(path, document_id=document_id, what="legal document")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row.sha256:
            raise LegalDocumentHashMismatchError(
                f"{path}: the bytes hash to {digest} but {self.index_path} signed "
                f"{row.sha256} — re-sign rather than serve what nobody approved"
            )
        if not text.strip():
            raise LegalDocumentInvalidError(f"{path}: the document is empty")
        _check_claims(text, document_id=document_id, what="document")

        summary, summary_hash = self._summary(required.summary_path, row, document_id)
        return LegalDocument(
            id=document_id,
            kind=required.kind,
            version=row.version,
            text_hash=digest,
            summary_hash=summary_hash,
            path=path,
            body=text,
            summary=summary,
            counsel=row.counsel,
        )

    def _summary(
        self, summary_path: str | None, row: IndexRow, document_id: str
    ) -> tuple[str | None, str | None]:
        if summary_path is None:
            return None, None
        path = self._root / summary_path
        raw, text = _read(path, document_id=document_id, what="plain-language summary")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row.summary_sha256:
            raise LegalDocumentHashMismatchError(
                f"{path}: the plain-language summary hashes to {digest} but "
                f"{self.index_path} signed {row.summary_sha256} — a summary that drifted "
                "from its document is the failure this clause exists to prevent"
            )
        if not text.strip():
            raise LegalDocumentInvalidError(f"{path}: the summary is empty")
        _check_claims(text, document_id=document_id, what="plain-language summary")
        return text, digest

    def render(self, document_id: str) -> LegalDocument:
        """What a surface shows. Identical to :meth:`entry` by construction —
        there is no second path that could serve a cached or unsigned copy."""
        return self.entry(document_id)

    def available(self) -> tuple[str, ...]:
        """The ids that resolve right now, in registry order. Empty today."""
        try:
            declared = self.index()
        except LegalDocumentMissingError:
            return ()
        out: list[str] = []
        for document_id in document_ids():
            if document_id not in declared:
                continue
            try:
                self.entry(document_id)
            except LegalDocumentError:
                continue
            out.append(document_id)
        return tuple(out)


def record_acceptance(
    chain: AuditChain,
    document: LegalDocument,
    *,
    actor: str,
    channel: str,
    now: datetime | None = None,
) -> LegalAcceptance:
    """Store the evidence that ``document`` was shown, in invariant 4's log.

    The acceptance can only be built from a :class:`LegalDocument`, and a
    :class:`LegalDocument` can only come from :meth:`LegalDocumentSet.entry` —
    so an unsigned or moved document has no acceptance path at all, rather than
    a check somebody could forget at a call site.

    The audit row carries ids and digests only (invariant 6): which document,
    which version, which bytes — never a word of the copy.
    """
    if channel not in CHANNELS:
        raise LegalDocumentInvalidError(
            f"{channel!r} is not one of the files/06 §1 aydınlatma channels {CHANNELS} — "
            "an acceptance against a sixth would claim a surface that does not exist"
        )
    entry = chain.append(
        actor=actor,
        action=ACCEPTANCE_ACTION,
        resource_ref=(
            f"legal_document:{document.id}@{document.version}/sha256:{document.text_hash}"
        ),
        consent_scope_ref=ACCEPTANCE_BASIS_REF,
    )
    return LegalAcceptance(
        document_id=document.id,
        version=document.version,
        text_hash=document.text_hash,
        summary_hash=document.summary_hash,
        actor=actor,
        channel=channel,
        accepted_at=now if now is not None else datetime.now(tz=UTC),
        audit_seq=entry.seq,
    )
