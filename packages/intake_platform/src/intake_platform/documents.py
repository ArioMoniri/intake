"""MinIO document store: signed URLs, AV hook, WORM audit bucket (INT-034;
files/10 §2 + §4 + §9 `documents`; invariants 4, 6, 14; KVKK-12).

Shape of the flow. Uploaded bytes land under ``quarantine/`` and are not
reachable from anywhere: ``presigned_get`` signs only keys under ``clean/``,
and the only way a key gets there is a malware verdict. The scanner is an
injected callback slot — INT-120's ClamAV plugs into it — and the *default*
slot raises :class:`NoScanConfiguredError`, so a service that forgot to wire
a scanner cannot silently serve unscanned files. The one escape hatch for the
dev tier, :class:`DevNullScanner`, is unconstructible unless
``INTAKE_DEV_ALLOW_UNSCANNED=explicit-yes`` and never in prod.

Object keys are ``<prefix>/<tenant_id>/<patient_pseudonym>/<uuid4hex>``.
There is deliberately no filename parameter: patient-supplied filenames are
the classic PHI carrier ("MR-raporu-Ayşe-Yılmaz.pdf"), and a parameter that
does not exist cannot leak (invariant 6). The pseudonym comes from the
tokenization service (INT-013) and is the only patient-adjacent token a key
may carry. The declared sha256 is recomputed server-side — the client's claim
is data, not truth (invariant 14 posture).

The audit bucket is WORM: created with S3 object-lock and a default
COMPLIANCE retention, it holds the hash-chain exports from
:meth:`intake_platform.audit.AuditChain.export_worm` (files/10 §2: audit
copies with object lock, 10-year hospital-tenant retention). MinIO enables
object-lock **only at bucket creation**, so a pre-existing bucket without the
lock is a typed :class:`WormMisconfiguredError` — recreate the bucket; there
is no honest way to upgrade it in place, and pretending otherwise is exactly
the silent degradation invariant 14 forbids.

Every mutating operation appends exactly one entry to the injected
:class:`~intake_platform.audit.AuditChain` (invariant 4: every share is
audited). Entries carry the object key and the consent scope — never the
bytes, the digest, the content type or the signed URL, because the audit
log's closed field set is how PHI stays out of it (invariant 6).

Dev-tier honesty: this module rides the compose MinIO. Production residency
(in-country object storage, KES-backed SSE — the ``sse`` slot is already
plumbed through to ``put_object``) lands with the infra issues; the files/10
§2 note that Garage lacks object-lock is why the store pins MinIO semantics.
"""

from __future__ import annotations

import enum
import hashlib
import io
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import BinaryIO, Protocol

from minio import Minio
from minio.commonconfig import COMPLIANCE, CopySource
from minio.error import S3Error
from minio.objectlockconfig import DAYS, ObjectLockConfig
from minio.sse import Sse

from intake_platform.audit import AuditChain

__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "DEFAULT_PRESIGN_TTL",
    "MAX_DOCUMENT_BYTES",
    "PRESIGN_TTL_CAP",
    "ContentTypeNotAllowedError",
    "DevNullScanner",
    "DevScannerForbiddenError",
    "DigestMismatchError",
    "DocumentNotFetchableError",
    "DocumentRef",
    "DocumentRejectedError",
    "DocumentState",
    "DocumentStore",
    "DocumentStoreError",
    "InvalidKeySegmentError",
    "NoScanConfiguredError",
    "ObjectPayload",
    "ObjectStat",
    "ObjectStorageClient",
    "PresignTtlError",
    "PresignedUpload",
    "QuarantineMissingError",
    "ScanVerdict",
    "Scanner",
    "WormMisconfiguredError",
    "as_object_storage",
]

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
# pdf + jpeg + png to start; heic and dicom join once their sandboxed parsers
# land (files/10 §4: file-type sniffing, sandboxed OCR — the parser side).
ALLOWED_CONTENT_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})
DEFAULT_PRESIGN_TTL = timedelta(seconds=300)
PRESIGN_TTL_CAP = timedelta(minutes=15)

_QUARANTINE = "quarantine"
_CLEAN = "clean"
_INFECTED = "infected"
# Policy rejections (sniff mismatch, size, unknown type — INT-120). Distinct
# from infected/ so forensics can tell malware from malformed; both are
# equally unservable (presigned_get signs clean/ only).
_REJECTED = "rejected"

# S3 error codes that mean "the object is not there" as opposed to a real
# storage failure; anything else propagates.
_MISSING_OBJECT_CODES = frozenset({"NoSuchKey", "NoSuchObject"})

# One path segment of an object key: id-shaped, no separators, bounded so the
# full key stays inside the audit log's 128-char resource_ref shape.
_SEGMENT_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")

_DEV_UNSCANNED_ENV = "INTAKE_DEV_ALLOW_UNSCANNED"
_DEV_UNSCANNED_PHRASE = "explicit-yes"
_WORM_CONSENT_SCOPE = "system.audit-worm"


class DocumentStoreError(Exception):
    """Base for every typed refusal this module raises."""


class WormMisconfiguredError(DocumentStoreError):
    """The audit bucket cannot honestly provide object-lock (WORM) — either it
    pre-exists without the lock (MinIO only enables it at creation) or the
    server refused lock-enabled creation. Never degraded silently."""


class DocumentTooLargeError(DocumentStoreError):
    """Payload exceeds the 20 MB cap."""


class ContentTypeNotAllowedError(DocumentStoreError):
    """Content type outside the allow-list. The offending value is not echoed:
    it is caller-supplied free text and this error will reach a log."""


class DigestMismatchError(DocumentStoreError):
    """The declared sha256 does not match the digest recomputed server-side."""


class InvalidKeySegmentError(DocumentStoreError):
    """tenant_id or patient_pseudonym is not id-shaped. The value is never
    echoed — a malformed pseudonym is exactly the kind of string that might be
    a real name (invariant 6)."""


class DocumentRejectedError(DocumentStoreError):
    """The malware verdict was INFECTED; the object was moved aside and will
    never be fetchable."""


class DocumentNotFetchableError(DocumentStoreError):
    """Only scanned-clean documents under ``clean/`` in the documents bucket
    ever get a URL."""


class PresignTtlError(DocumentStoreError):
    """Requested URL lifetime is zero, negative, or above the 15-minute cap.
    Refused, not clamped: silently shortening a TTL the caller relies on is a
    different bug than the one it hides."""


class NoScanConfiguredError(DocumentStoreError):
    """No malware scanner is wired. The stored object stays in quarantine and
    nothing serves it — fail closed until INT-120's ClamAV (or the explicit
    dev stand-in) is injected."""


class DevScannerForbiddenError(DocumentStoreError):
    """:class:`DevNullScanner` construction refused: the explicit dev opt-in
    env is absent, or the environment is prod."""


class QuarantineMissingError(DocumentStoreError):
    """The addressed quarantine object does not exist. The INT-120 worker
    treats an already-promoted/rejected document as a no-op *before* calling
    the promotion path, so reaching this means the id is wrong or the object
    vanished — loud, never silent."""


class DocumentState(enum.Enum):
    QUARANTINED = "quarantined"
    CLEAN = "clean"
    REJECTED = "rejected"


class ScanVerdict(enum.Enum):
    CLEAN = "clean"
    INFECTED = "infected"


class Scanner(Protocol):
    """The AV hook. INT-120 implements this over ClamAV; the unit lane uses
    fakes; the dev tier may use :class:`DevNullScanner` under its env gate."""

    def scan(self, data: bytes) -> ScanVerdict: ...


class _NoScanConfigured:
    """Default scanner slot: refuses loudly so an unwired service cannot
    serve unscanned files. Private on purpose — nothing should inject it."""

    def scan(self, data: bytes) -> ScanVerdict:
        raise NoScanConfiguredError(
            "no malware scanner is configured: the document stays in quarantine and is "
            "not fetchable; wire the ClamAV scanner (INT-120) or, in dev only, an "
            "explicit DevNullScanner"
        )


class DevNullScanner:
    """Dev-tier stand-in that marks everything clean — honestly gated.

    Constructible only when ``INTAKE_DEV_ALLOW_UNSCANNED`` equals the exact
    phrase ``explicit-yes`` (no truthy shortcuts) and ``INTAKE_ENV`` is not
    prod. The gate lives in the constructor so a misconfigured service fails
    at boot, not at first upload.
    """

    def __init__(self) -> None:
        if os.environ.get("INTAKE_ENV", "dev").lower().startswith("prod"):
            raise DevScannerForbiddenError(
                "DevNullScanner is refused in prod outright: unscanned documents never "
                "serve in production, whatever the env flags say"
            )
        if os.environ.get(_DEV_UNSCANNED_ENV) != _DEV_UNSCANNED_PHRASE:
            raise DevScannerForbiddenError(
                f"DevNullScanner requires {_DEV_UNSCANNED_ENV}={_DEV_UNSCANNED_PHRASE!r} "
                "(the exact phrase): serving unscanned files is a decision, not a default"
            )

    def scan(self, data: bytes) -> ScanVerdict:
        return ScanVerdict.CLEAN


class ObjectPayload(Protocol):
    """What a fetched object hands back: the bytes, and a way to let the
    connection go. urllib3's response object satisfies this; unit-lane fakes
    carry the bytes directly."""

    def read(self) -> bytes: ...

    def close(self) -> None: ...


class ObjectStat(Protocol):
    """The one field the store needs from a HEAD: the size, so the INT-120
    limit check runs *before* any byte is pulled into memory."""

    @property
    def size(self) -> int | None: ...


class ObjectStorageClient(Protocol):
    """The narrow slice of the S3 client the store uses, call-compatible with
    :class:`minio.Minio` (pinned by :func:`as_object_storage` under mypy).
    Unit tests inject in-memory fakes; nothing here ever dials a network in
    the unit lane."""

    def bucket_exists(self, bucket_name: str) -> bool: ...

    def make_bucket(
        self, bucket_name: str, location: str | None = ..., object_lock: bool = ...
    ) -> None: ...

    def get_object_lock_config(self, bucket_name: str) -> ObjectLockConfig: ...

    def set_object_lock_config(self, bucket_name: str, config: ObjectLockConfig) -> None: ...

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = ...,
        *,
        sse: Sse | None = ...,
    ) -> object: ...

    def copy_object(self, bucket_name: str, object_name: str, source: CopySource) -> object: ...

    def remove_object(
        self, bucket_name: str, object_name: str, version_id: str | None = ...
    ) -> None: ...

    def stat_object(self, bucket_name: str, object_name: str) -> ObjectStat: ...

    def get_object(self, bucket_name: str, object_name: str) -> ObjectPayload: ...

    def presigned_get_object(
        self, bucket_name: str, object_name: str, expires: timedelta = ...
    ) -> str: ...

    def presigned_put_object(
        self, bucket_name: str, object_name: str, expires: timedelta = ...
    ) -> str: ...


def as_object_storage(client: Minio) -> ObjectStorageClient:
    """Identity at runtime; at type-check time this is the proof that the real
    MinIO client still satisfies :class:`ObjectStorageClient`."""
    return client


@dataclass(frozen=True)
class DocumentRef:
    """Handle to a stored document. ``key`` is the object's current location;
    only ``state == CLEAN`` (and a ``clean/`` key) is ever fetchable."""

    tenant_id: str
    patient_pseudonym: str
    document_id: str
    bucket: str
    key: str
    content_type: str
    size_bytes: int
    sha256: str
    state: DocumentState


@dataclass(frozen=True)
class PresignedUpload:
    """A minted upload slot: the object lands under ``quarantine/`` and stays
    unservable until a scan pass (INT-120) promotes it."""

    document_id: str
    key: str
    url: str
    expires: timedelta


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _require_segment(field_name: str, value: str) -> None:
    if not _SEGMENT_SHAPE.fullmatch(value):
        raise InvalidKeySegmentError(
            f"{field_name} must be id-shaped ([A-Za-z0-9._-], ≤40 chars, no separators); "
            "the refused value is not echoed because a malformed identifier may be "
            "patient-identifying free text (invariant 6)"
        )


def _require_ttl(expires: timedelta) -> None:
    if expires <= timedelta(0) or expires > PRESIGN_TTL_CAP:
        raise PresignTtlError(
            f"signed-URL lifetime must be positive and at most 15 minutes, got "
            f"{expires.total_seconds():.0f}s — refused, not clamped (files/10 §4: short TTL)"
        )


class DocumentStore:
    """Typed document store over an injected S3 client + audit chain.

    Construction wires the four seams: the object-storage client (real MinIO
    in dev/prod, a fake in the unit lane), the private documents bucket, the
    WORM audit bucket, and the INT-016 hash chain that records every mutation
    and share. ``scanner`` is the AV hook; the default refuses to pass
    anything (see :class:`_NoScanConfigured`).
    """

    def __init__(
        self,
        client: ObjectStorageClient,
        bucket_docs: str,
        bucket_audit: str,
        audit_chain: AuditChain,
        *,
        scanner: Scanner | None = None,
        actor: str = "svc-documents",
        audit_retention_days: int = 3650,
        sse: Sse | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        _require_segment("bucket_docs", bucket_docs)
        _require_segment("bucket_audit", bucket_audit)
        if bucket_docs == bucket_audit:
            raise WormMisconfiguredError(
                "documents and audit must be separate buckets: WORM retention on "
                "patient documents would make KVKK-7 erasure impossible"
            )
        self._client = client
        self._bucket_docs = bucket_docs
        self._bucket_audit = bucket_audit
        self._audit_chain = audit_chain
        self._scanner: Scanner = scanner if scanner is not None else _NoScanConfigured()
        self._actor = actor
        self._audit_retention_days = audit_retention_days
        self._sse = sse
        self._clock = clock if clock is not None else _utc_now

    # --- buckets ----------------------------------------------------------------

    def ensure_buckets(self) -> None:
        """Create (or verify) both buckets. The documents bucket is private —
        MinIO buckets deny anonymous access unless a policy grants it, and
        this store never sets one (least privilege by absence). The audit
        bucket must be WORM; anything less raises, never degrades."""
        if not self._client.bucket_exists(self._bucket_docs):
            self._client.make_bucket(self._bucket_docs)
        if not self._client.bucket_exists(self._bucket_audit):
            try:
                self._client.make_bucket(self._bucket_audit, object_lock=True)
            except S3Error as err:
                raise WormMisconfiguredError(
                    f"the server refused object-lock creation for bucket "
                    f"{self._bucket_audit!r}: WORM cannot be provided honestly, so the "
                    "store fails closed instead of writing an erasable audit copy "
                    "(invariant 14)"
                ) from err
            self._set_compliance_retention()
            return
        try:
            config = self._client.get_object_lock_config(self._bucket_audit)
        except S3Error as err:
            raise WormMisconfiguredError(
                f"audit bucket {self._bucket_audit!r} pre-exists without object-lock; "
                "MinIO enables the lock only at bucket creation, so recreate the bucket "
                "— there is no honest in-place upgrade (invariant 14: never silently "
                "degrade WORM)"
            ) from err
        if config.mode != COMPLIANCE:
            # Lock enabled but default retention absent or GOVERNANCE: tighten
            # to COMPLIANCE. The reverse direction (loosening) never happens —
            # an operator's stricter setting is left alone above.
            self._set_compliance_retention()

    def _set_compliance_retention(self) -> None:
        self._client.set_object_lock_config(
            self._bucket_audit,
            ObjectLockConfig(COMPLIANCE, self._audit_retention_days, DAYS),
        )

    # --- documents --------------------------------------------------------------

    def put_document(
        self,
        tenant_id: str,
        patient_pseudonym: str,
        file_bytes: bytes,
        content_type: str,
        sha256: str,
        *,
        consent_scope_ref: str,
    ) -> DocumentRef:
        """Store one document: validate, quarantine, scan, promote.

        Raises :class:`NoScanConfiguredError` (object stays quarantined,
        unservable) when no scanner is wired, :class:`DocumentRejectedError`
        on an INFECTED verdict (object moved under ``infected/`` for
        forensics, never fetchable), and returns a CLEAN ref otherwise.
        """
        _require_segment("tenant_id", tenant_id)
        _require_segment("patient_pseudonym", patient_pseudonym)
        if len(file_bytes) > MAX_DOCUMENT_BYTES:
            raise DocumentTooLargeError(
                f"document is {len(file_bytes)} bytes; the cap is {MAX_DOCUMENT_BYTES} (20 MB)"
            )
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ContentTypeNotAllowedError(
                "content type is outside the allow-list "
                f"({', '.join(sorted(ALLOWED_CONTENT_TYPES))}); the offered value is "
                "not echoed here"
            )
        digest = hashlib.sha256(file_bytes).hexdigest()
        if digest != sha256.lower():
            raise DigestMismatchError(
                "declared sha256 does not match the digest recomputed server-side; "
                "the client's integrity claim is data, not truth (neither digest is "
                "echoed here)"
            )
        document_id = uuid.uuid4().hex
        quarantine_key = f"{_QUARANTINE}/{tenant_id}/{patient_pseudonym}/{document_id}"
        self._client.put_object(
            self._bucket_docs,
            quarantine_key,
            io.BytesIO(file_bytes),
            len(file_bytes),
            content_type=content_type,
            sse=self._sse,
        )
        self._audit("document.stored", quarantine_key, consent_scope_ref)
        verdict = self._scanner.scan(file_bytes)
        if verdict is ScanVerdict.INFECTED:
            infected_key = f"{_INFECTED}/{tenant_id}/{patient_pseudonym}/{document_id}"
            self._move(quarantine_key, infected_key)
            self._audit("document.rejected", infected_key, consent_scope_ref)
            raise DocumentRejectedError(
                f"document {document_id} failed the malware scan; it was retained under "
                "the infected/ prefix for forensics and will never be fetchable"
            )
        clean_key = f"{_CLEAN}/{tenant_id}/{patient_pseudonym}/{document_id}"
        self._move(quarantine_key, clean_key)
        self._audit("document.released", clean_key, consent_scope_ref)
        return DocumentRef(
            tenant_id=tenant_id,
            patient_pseudonym=patient_pseudonym,
            document_id=document_id,
            bucket=self._bucket_docs,
            key=clean_key,
            content_type=content_type,
            size_bytes=len(file_bytes),
            sha256=digest,
            state=DocumentState.CLEAN,
        )

    def _move(self, src_key: str, dst_key: str) -> None:
        self._client.copy_object(self._bucket_docs, dst_key, CopySource(self._bucket_docs, src_key))
        self._client.remove_object(self._bucket_docs, src_key)

    # --- quarantine promotion path (INT-120) --------------------------------------

    def _document_key(
        self, prefix: str, tenant_id: str, patient_pseudonym: str, document_id: str
    ) -> str:
        _require_segment("tenant_id", tenant_id)
        _require_segment("patient_pseudonym", patient_pseudonym)
        _require_segment("document_id", document_id)
        return f"{prefix}/{tenant_id}/{patient_pseudonym}/{document_id}"

    def _object_exists(self, key: str) -> bool:
        try:
            self._client.stat_object(self._bucket_docs, key)
        except S3Error as err:
            if err.code in _MISSING_OBJECT_CODES:
                return False
            raise
        return True

    def document_state(
        self, tenant_id: str, patient_pseudonym: str, document_id: str
    ) -> DocumentState | None:
        """Where a document currently sits, by prefix — the INT-120 worker's
        idempotency check. ``None`` means the id resolves nowhere."""
        for prefix, state in (
            (_CLEAN, DocumentState.CLEAN),
            (_INFECTED, DocumentState.REJECTED),
            (_REJECTED, DocumentState.REJECTED),
            (_QUARANTINE, DocumentState.QUARANTINED),
        ):
            if self._object_exists(
                self._document_key(prefix, tenant_id, patient_pseudonym, document_id)
            ):
                return state
        return None

    def quarantined_size(self, tenant_id: str, patient_pseudonym: str, document_id: str) -> int:
        """Size of a quarantined object from a HEAD — the limit check runs on
        this *before* any byte is pulled into memory (files/10 §4)."""
        key = self._document_key(_QUARANTINE, tenant_id, patient_pseudonym, document_id)
        try:
            stat = self._client.stat_object(self._bucket_docs, key)
        except S3Error as err:
            if err.code in _MISSING_OBJECT_CODES:
                raise QuarantineMissingError(
                    "the addressed quarantine object does not exist; ids only, the key "
                    "is not echoed"
                ) from err
            raise
        size = stat.size
        if size is None:
            raise DocumentStoreError(
                "object store returned no size for an object it just described"
            )
        return size

    def read_quarantined(
        self, tenant_id: str, patient_pseudonym: str, document_id: str, *, consent_scope_ref: str
    ) -> bytes:
        """Fetch quarantined bytes for the scan pass. A read of clinical data,
        so it carries a consent scope and lands in the audit chain
        (invariant 4); the entry holds the key, never the bytes."""
        key = self._document_key(_QUARANTINE, tenant_id, patient_pseudonym, document_id)
        try:
            payload = self._client.get_object(self._bucket_docs, key)
        except S3Error as err:
            if err.code in _MISSING_OBJECT_CODES:
                raise QuarantineMissingError(
                    "the addressed quarantine object does not exist; ids only, the key "
                    "is not echoed"
                ) from err
            raise
        try:
            data = payload.read()
        finally:
            payload.close()
            release = getattr(payload, "release_conn", None)
            if callable(release):
                release()
        self._audit("document.scan_read", key, consent_scope_ref)
        return data

    def release_quarantined(
        self,
        tenant_id: str,
        patient_pseudonym: str,
        document_id: str,
        file_bytes: bytes,
        *,
        content_type: str,
        consent_scope_ref: str,
    ) -> DocumentRef:
        """Promote a scanned-clean quarantined object under ``clean/``.

        The clean object is *rewritten* (not copied): the stored content type
        becomes the sniffed canonical one, never whatever the presigned PUT
        claimed — a payload served with an attacker-chosen content type is a
        browser-side gadget. Defence in depth: the canonical type must still
        be on the store allow-list, so a drifted pipeline cannot widen what
        ``presigned_get`` will ever serve.
        """
        quarantine_key = self._document_key(_QUARANTINE, tenant_id, patient_pseudonym, document_id)
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ContentTypeNotAllowedError(
                "content type is outside the allow-list "
                f"({', '.join(sorted(ALLOWED_CONTENT_TYPES))}); the offered value is "
                "not echoed here"
            )
        if not self._object_exists(quarantine_key):
            raise QuarantineMissingError(
                "cannot promote: the addressed quarantine object does not exist"
            )
        clean_key = self._document_key(_CLEAN, tenant_id, patient_pseudonym, document_id)
        self._client.put_object(
            self._bucket_docs,
            clean_key,
            io.BytesIO(file_bytes),
            len(file_bytes),
            content_type=content_type,
            sse=self._sse,
        )
        self._client.remove_object(self._bucket_docs, quarantine_key)
        self._audit("document.released", clean_key, consent_scope_ref)
        return DocumentRef(
            tenant_id=tenant_id,
            patient_pseudonym=patient_pseudonym,
            document_id=document_id,
            bucket=self._bucket_docs,
            key=clean_key,
            content_type=content_type,
            size_bytes=len(file_bytes),
            sha256=hashlib.sha256(file_bytes).hexdigest(),
            state=DocumentState.CLEAN,
        )

    def reject_quarantined(
        self,
        tenant_id: str,
        patient_pseudonym: str,
        document_id: str,
        *,
        reason_code: str,
        malware: bool,
        consent_scope_ref: str,
    ) -> str:
        """Move a quarantined object aside as rejected — ``infected/`` for a
        malware verdict (forensics parity with :meth:`put_document`),
        ``rejected/`` for policy refusals. The audit entry carries the reason
        *code* only (invariant 6): ``document.rejected.<reason_code>``."""
        _require_segment("reason_code", reason_code)
        quarantine_key = self._document_key(_QUARANTINE, tenant_id, patient_pseudonym, document_id)
        if not self._object_exists(quarantine_key):
            raise QuarantineMissingError(
                "cannot reject: the addressed quarantine object does not exist"
            )
        prefix = _INFECTED if malware else _REJECTED
        dst_key = self._document_key(prefix, tenant_id, patient_pseudonym, document_id)
        self._move(quarantine_key, dst_key)
        self._audit(f"document.rejected.{reason_code}", dst_key, consent_scope_ref)
        return dst_key

    # --- signed URLs --------------------------------------------------------------

    def presigned_get(
        self,
        ref: DocumentRef,
        *,
        consent_scope_ref: str,
        expires: timedelta = DEFAULT_PRESIGN_TTL,
    ) -> str:
        """Mint a short-TTL download URL for a scanned-clean document. Every
        issued URL is an audited share (invariant 4); the URL itself never
        enters the audit log."""
        _require_ttl(expires)
        if (
            ref.bucket != self._bucket_docs
            or ref.state is not DocumentState.CLEAN
            or not ref.key.startswith(f"{_CLEAN}/")
        ):
            raise DocumentNotFetchableError(
                "only scanned-clean documents under clean/ in the documents bucket are "
                "fetchable; quarantined, infected and foreign-bucket objects never get "
                "a URL"
            )
        url = self._client.presigned_get_object(self._bucket_docs, ref.key, expires=expires)
        self._audit("document.presigned", ref.key, consent_scope_ref)
        return url

    def presigned_put(
        self,
        tenant_id: str,
        patient_pseudonym: str,
        *,
        consent_scope_ref: str,
        expires: timedelta = DEFAULT_PRESIGN_TTL,
    ) -> PresignedUpload:
        """Mint an upload slot. The object lands under ``quarantine/`` and is
        not fetchable until a scan pass promotes it — for presigned uploads
        the bytes never transit this process, so promotion belongs to the
        INT-120 scan worker, not to this method."""
        _require_segment("tenant_id", tenant_id)
        _require_segment("patient_pseudonym", patient_pseudonym)
        _require_ttl(expires)
        document_id = uuid.uuid4().hex
        key = f"{_QUARANTINE}/{tenant_id}/{patient_pseudonym}/{document_id}"
        url = self._client.presigned_put_object(self._bucket_docs, key, expires=expires)
        self._audit("document.presigned", key, consent_scope_ref)
        return PresignedUpload(document_id=document_id, key=key, url=url, expires=expires)

    # --- WORM export ---------------------------------------------------------------

    def put_audit_bundle(self, bundle: bytes) -> str:
        """Copy one hash-chain WORM export (INT-016 ``export_worm``) into the
        object-locked audit bucket; the bucket's default COMPLIANCE retention
        applies to the new object automatically."""
        stamp = self._clock().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        key = f"audit/{stamp}-{uuid.uuid4().hex}.jsonl"
        self._client.put_object(
            self._bucket_audit,
            key,
            io.BytesIO(bundle),
            len(bundle),
            content_type="application/x-ndjson",
        )
        self._audit_chain.append(
            actor=self._actor,
            action="audit.worm_copied",
            resource_ref=key,
            consent_scope_ref=_WORM_CONSENT_SCOPE,
        )
        return key

    # --- internals -------------------------------------------------------------------

    def _audit(self, action: str, resource_ref: str, consent_scope_ref: str) -> None:
        self._audit_chain.append(
            actor=self._actor,
            action=action,
            resource_ref=resource_ref,
            consent_scope_ref=consent_scope_ref,
        )
