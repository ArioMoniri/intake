"""Upload pipeline: sniff → limits → ClamAV → promote (INT-120; files/10 §4 +
§9 `records`; invariants 4, 6, 14; KVKK-12).

Shape of the flow. A presigned PUT (INT-034) lands bytes under
``quarantine/`` where nothing can serve them. This module is the worker that
earns the promotion: it checks where the document currently sits (re-running
on an already-promoted or rejected object is a no-op), enforces the size
limit from a HEAD before a single byte is fetched, normalises the claimed
content type, sniffs the magic bytes, refuses claim/content mismatches, runs
the ClamAV verdict, and only then promotes through the documents.py path.
Every rejection is a typed error carried as a reason *code* — content never
reaches an error message, an audit entry or a log (invariant 6).

The clamd client is deliberately our own ~80 lines over the INSTREAM wire
protocol (null-terminated command, 4-byte big-endian length-prefixed chunks,
one verdict line) instead of pyclamd: the protocol is three frames, pyclamd
is unmaintained and untyped, and a dependency we cannot read is a heavier
liability than a socket loop we test against a fake and a real clamd both.
Configuration comes from env and there is NO default endpoint — an
unconfigured scanner refuses at construction, and an unreachable, silent or
garbage-talking clamd is a *scan failure* (the document stays quarantined,
retryable), never a verdict (invariant 14: fail closed).

OCR is a seam, not an engine: picking the engine and its sandbox (files/10
§4 demands seccomp-isolated parsing) is an architecture decision that needs
an ADR, so :class:`NoOcr` — the fail-closed default — parses nothing and
marks every promoted document ``ocr_pending``. A future engine implements
:class:`OcrExtractor` and plugs into :class:`UploadPipeline` without a
caller changing.

`services/workers` does not exist yet; :func:`process_quarantined_document`
is the plain callable the workers issue will wrap into a Celery task.
"""

from __future__ import annotations

import enum
import os
import socket
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from prometheus_client import Counter, disable_created_metrics

from intake_platform.documents import (
    ALLOWED_CONTENT_TYPES,
    MAX_DOCUMENT_BYTES,
    DocumentRef,
    DocumentState,
    DocumentStore,
    DocumentStoreError,
    QuarantineMissingError,
    Scanner,
    ScanVerdict,
)

__all__ = [
    "CLAMD_HOST_ENV",
    "CLAMD_PORT_ENV",
    "CLAMD_TIMEOUT_ENV",
    "CLAMD_UNIX_SOCKET_ENV",
    "PROMOTABLE_TYPES",
    "SNIFFABLE_TYPES",
    "UPLOAD_MAX_BYTES_ENV",
    "ClamAvScanner",
    "ClamdNotConfiguredError",
    "NoOcr",
    "OcrExtractor",
    "OcrOutcome",
    "OcrStatus",
    "RejectReason",
    "ScanFailedError",
    "UploadConfigError",
    "UploadLimits",
    "UploadOutcome",
    "UploadPipeline",
    "UploadPipelineError",
    "UploadRejectedError",
    "normalise_claimed_type",
    "process_quarantined_document",
    "sniff_media_type",
]

CLAMD_HOST_ENV = "INTAKE_CLAMD_HOST"
CLAMD_PORT_ENV = "INTAKE_CLAMD_PORT"
CLAMD_UNIX_SOCKET_ENV = "INTAKE_CLAMD_UNIX_SOCKET"
CLAMD_TIMEOUT_ENV = "INTAKE_CLAMD_TIMEOUT_SECONDS"
UPLOAD_MAX_BYTES_ENV = "INTAKE_UPLOAD_MAX_BYTES"

# clamd's IANA-registered port. A default *port* does not skip scanning —
# a missing endpoint altogether still refuses at construction.
_CLAMD_DEFAULT_PORT = 3310
_CLAMD_DEFAULT_TIMEOUT_SECONDS = 30.0
# INSTREAM chunk size. Any value under clamd's StreamMaxLength works; 32 KiB
# keeps frames small without a syscall per page.
_INSTREAM_CHUNK = 32 * 1024
_REPLY_CAP = 4096

# Magic-byte signatures. Sniffing is deliberately *only* this: no parsing of
# untrusted structure happens in this process (that is the sandboxed OCR
# worker's job, engine pending its ADR).
_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# ISO BMFF brands that mean HEIF/HEIC still images (not generic mp4 video).
_HEIC_BRANDS = frozenset({b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"})

# What the sniffer can recognise; promotion is gated by the *store* allow-list
# (single source of truth: documents.ALLOWED_CONTENT_TYPES). HEIC and DICOM
# are sniffed so their refusal is precise (`type-not-allowed`, not "unknown
# magic") but stay unpromotable until their sandboxed parsers land — the
# INT-034 posture.
SNIFFABLE_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/heic", "application/dicom"}
)
PROMOTABLE_TYPES = ALLOWED_CONTENT_TYPES

# Claimed content types and bare extensions → canonical MIME. Anything absent
# is `type-unrecognised`; the caller-supplied value is never echoed
# (invariant 6: a "content type" field can carry arbitrary free text).
_CLAIMED_ALIASES: Mapping[str, str] = {
    "application/pdf": "application/pdf",
    "application/x-pdf": "application/pdf",
    "pdf": "application/pdf",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/x-png": "image/png",
    "png": "image/png",
    "image/heic": "image/heic",
    "image/heif": "image/heic",
    "heic": "image/heic",
    "heif": "image/heic",
    "application/dicom": "application/dicom",
    "dicom": "application/dicom",
    "dcm": "application/dicom",
}

disable_created_metrics()  # type: ignore[no-untyped-call]  # upstream def has no annotations

# files/10 §9 `records` signals: upload scan results, by outcome and reason
# code. Catalogued in observability/metrics_catalog.yaml (invariant 13);
# label values are closed enumerations, never free text (invariant 6).
UPLOAD_PIPELINE_OUTCOMES = Counter(
    "document_upload_pipeline",
    "Upload pipeline outcomes by result and reason code (INT-120).",
    ["outcome", "reason"],
)

_NO_REASON = "none"


class UploadPipelineError(DocumentStoreError):
    """Base for every typed refusal this module raises."""


class ClamdNotConfiguredError(UploadPipelineError):
    """No clamd endpoint is configured. There is deliberately no default
    host: an unconfigured scanner must refuse at construction, never turn
    into a scan that silently did not happen."""


class UploadConfigError(UploadPipelineError):
    """Malformed configuration: an unparsable port/limit, or both a TCP and a
    unix endpoint at once. Refused, not guessed."""


class ScanFailedError(UploadPipelineError):
    """The scan could not produce a verdict — clamd unreachable, timed out,
    answered ERROR or spoke garbage. Never treated as clean OR infected: the
    document stays quarantined and the worker retries (invariant 14)."""


class RejectReason(enum.Enum):
    """Closed set of rejection reason codes. These strings are what reaches
    the audit chain (``document.rejected.<code>``) and the outcome metric —
    reason codes only, never content (invariant 6)."""

    EMPTY = "empty"
    TOO_LARGE = "too-large"
    TYPE_UNRECOGNISED = "type-unrecognised"
    TYPE_NOT_ALLOWED = "type-not-allowed"
    MAGIC_UNRECOGNISED = "magic-unrecognised"
    TYPE_MISMATCH = "type-mismatch"
    MALWARE = "malware"


class UploadRejectedError(UploadPipelineError):
    """A validation step refused the document. Carries the reason code; the
    message never echoes caller-supplied values."""

    def __init__(self, reason: RejectReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


# --- sniffing + normalisation ---------------------------------------------------------


def sniff_media_type(data: bytes) -> str | None:
    """Canonical MIME type from magic bytes, or ``None``. Reads signatures
    only — deliberately no structural parsing of untrusted bytes here."""
    if data.startswith(_PDF_MAGIC):
        return "application/pdf"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
        return "image/heic"
    if len(data) >= 132 and data[128:132] == b"DICM":
        return "application/dicom"
    return None


def normalise_claimed_type(claimed: str) -> str:
    """Normalise a claimed content type or bare file extension to canonical
    MIME. Unknown values are a typed refusal — and are not echoed, because a
    caller-supplied "content type" is free text until proven otherwise."""
    value = claimed.split(";", 1)[0].strip().lower().lstrip(".")
    canonical = _CLAIMED_ALIASES.get(value)
    if canonical is None:
        raise UploadRejectedError(
            RejectReason.TYPE_UNRECOGNISED,
            "claimed content type is not one this pipeline recognises; the offered "
            "value is not echoed here (invariant 6)",
        )
    return canonical


# --- limits ----------------------------------------------------------------------------


@dataclass(frozen=True)
class UploadLimits:
    """Size cap for the presigned-upload path. Defaults to the store cap so
    the two ingestion paths agree; env-overridable. Note clamd's own
    ``StreamMaxLength`` (25 MB by default) still bounds what a scan can pass
    — a cap raised past it turns into scan failures, which fail closed."""

    max_bytes: int = MAX_DOCUMENT_BYTES

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> UploadLimits:
        raw = environ.get(UPLOAD_MAX_BYTES_ENV)
        if raw is None:
            return cls()
        try:
            value = int(raw)
        except ValueError as err:
            raise UploadConfigError(
                f"{UPLOAD_MAX_BYTES_ENV} must be a positive integer byte count"
            ) from err
        if value <= 0:
            raise UploadConfigError(f"{UPLOAD_MAX_BYTES_ENV} must be a positive integer byte count")
        return cls(max_bytes=value)


# --- the ClamAV scanner ------------------------------------------------------------------


class ClamAvScanner:
    """:class:`~intake_platform.documents.Scanner` over clamd's INSTREAM
    protocol, TCP or unix socket. Every failure mode — refused connection,
    timeout, ERROR reply, unrecognised reply, mid-stream close (clamd's
    stream size limit) — raises :class:`ScanFailedError`; the only verdicts
    are clamd's own OK and FOUND."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        unix_socket: str | None = None,
        timeout_seconds: float = _CLAMD_DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if unix_socket is not None and host is not None:
            raise UploadConfigError(
                "both a TCP endpoint and a unix socket are configured for clamd; "
                "refusing to pick one silently"
            )
        if unix_socket is None and host is None:
            raise ClamdNotConfiguredError(
                f"no clamd endpoint configured: set {CLAMD_HOST_ENV} (+ optional "
                f"{CLAMD_PORT_ENV}) or {CLAMD_UNIX_SOCKET_ENV}; there is no default "
                "endpoint because a guessed scanner is a scan that did not happen"
            )
        resolved_port = port if port is not None else _CLAMD_DEFAULT_PORT
        if host is not None and not 0 < resolved_port < 65536:
            raise UploadConfigError("clamd port must be in 1..65535")
        if timeout_seconds <= 0:
            raise UploadConfigError("clamd timeout must be positive seconds")
        self._host = host
        self._port = resolved_port
        self._unix_socket = unix_socket
        self._timeout = timeout_seconds

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> ClamAvScanner:
        host = environ.get(CLAMD_HOST_ENV)
        unix_socket = environ.get(CLAMD_UNIX_SOCKET_ENV)
        port: int | None = None
        raw_port = environ.get(CLAMD_PORT_ENV)
        if raw_port is not None:
            try:
                port = int(raw_port)
            except ValueError as err:
                raise UploadConfigError(f"{CLAMD_PORT_ENV} must be an integer port") from err
        timeout = _CLAMD_DEFAULT_TIMEOUT_SECONDS
        raw_timeout = environ.get(CLAMD_TIMEOUT_ENV)
        if raw_timeout is not None:
            try:
                timeout = float(raw_timeout)
            except ValueError as err:
                raise UploadConfigError(f"{CLAMD_TIMEOUT_ENV} must be a number of seconds") from err
        return cls(host=host, port=port, unix_socket=unix_socket, timeout_seconds=timeout)

    def _connect(self) -> socket.socket:
        if self._unix_socket is not None:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(self._timeout)
            conn.connect(self._unix_socket)
            return conn
        assert self._host is not None  # noqa: S101 - pinned by the constructor refusals
        return socket.create_connection((self._host, self._port), timeout=self._timeout)

    def ping(self) -> bool:
        """One PING/PONG roundtrip — probe/readiness material, never a
        substitute for a scan verdict."""
        try:
            with self._connect() as conn:
                conn.sendall(b"zPING\0")
                return self._read_reply(conn) == b"PONG"
        except OSError:
            return False

    def scan(self, data: bytes) -> ScanVerdict:
        try:
            with self._connect() as conn:
                conn.sendall(b"zINSTREAM\0")
                view = memoryview(data)
                for offset in range(0, len(view), _INSTREAM_CHUNK):
                    chunk = view[offset : offset + _INSTREAM_CHUNK]
                    conn.sendall(struct.pack(">I", len(chunk)))
                    conn.sendall(chunk)
                conn.sendall(struct.pack(">I", 0))
                reply = self._read_reply(conn)
        except OSError as err:
            raise ScanFailedError(
                "clamd is unreachable or the connection failed mid-scan; no verdict "
                "was produced, so the document stays quarantined (fail closed)"
            ) from err
        return self._verdict(reply)

    def _read_reply(self, conn: socket.socket) -> bytes:
        reply = bytearray()
        while len(reply) < _REPLY_CAP:
            chunk = conn.recv(1024)
            if not chunk:
                break
            reply += chunk
            if reply.endswith(b"\0"):
                break
        return bytes(reply).rstrip(b"\0").strip()

    @staticmethod
    def _verdict(reply: bytes) -> ScanVerdict:
        if reply == b"stream: OK":
            return ScanVerdict.CLEAN
        if reply.startswith(b"stream:") and reply.endswith(b"FOUND"):
            return ScanVerdict.INFECTED
        # ERROR, an empty reply, or anything unrecognised. The raw reply is
        # withheld from the message: this exception reaches logs and the
        # reply line can name attacker-influenced content (invariant 6).
        raise ScanFailedError(
            "clamd answered with an error or an unrecognised reply instead of a "
            "verdict; the document stays quarantined (fail closed) and the raw "
            "reply is not echoed here"
        )


# --- OCR seam ------------------------------------------------------------------------------


class OcrStatus(enum.Enum):
    PENDING = "ocr_pending"
    EXTRACTED = "extracted"


@dataclass(frozen=True)
class OcrOutcome:
    """``PENDING`` + ``None`` until a real engine runs; an engine returns
    ``EXTRACTED`` with the text (which is PHI — it goes to the extraction
    flow, INT-121, never to a log)."""

    status: OcrStatus
    text: str | None


class OcrExtractor(Protocol):
    """The OCR seam. The engine and its sandbox (files/10 §4: seccomp-
    isolated parsing) are an ADR-level decision still open; implementations
    plug in here without any pipeline change."""

    def extract(self, data: bytes, content_type: str) -> OcrOutcome: ...


class NoOcr:
    """Fail-closed default while the OCR engine + sandbox ADR is open: parses
    nothing (untrusted bytes never meet a parser in this process) and marks
    every promoted document ``ocr_pending``."""

    def extract(self, data: bytes, content_type: str) -> OcrOutcome:
        return OcrOutcome(status=OcrStatus.PENDING, text=None)


# --- the promotion worker ---------------------------------------------------------------------


@dataclass(frozen=True)
class UploadOutcome:
    """What one worker pass concluded. ``already_processed`` marks the
    idempotent no-op; ``ref`` is set only when this pass promoted; ``ocr`` is
    set only for promoted documents."""

    document_id: str
    state: DocumentState
    already_processed: bool
    reason: RejectReason | None
    content_type: str | None
    ref: DocumentRef | None
    ocr: OcrOutcome | None


class UploadPipeline:
    """state-check → limit → claimed-type → sniff → mismatch → scan →
    promote/reject, over an injected :class:`DocumentStore`.

    ``scanner`` has no default on purpose: scanning is never optional, and a
    pipeline nobody wired a scanner into must not construct. The size check
    runs on a HEAD before any byte is fetched, and is re-checked after the
    read (a presigned PUT can be replayed within its TTL, growing the object
    between the two).
    """

    def __init__(
        self,
        store: DocumentStore,
        scanner: Scanner,
        *,
        limits: UploadLimits | None = None,
        ocr: OcrExtractor | None = None,
    ) -> None:
        self._store = store
        self._scanner = scanner
        self._limits = limits if limits is not None else UploadLimits.from_env()
        self._ocr: OcrExtractor = ocr if ocr is not None else NoOcr()

    def process(
        self,
        tenant_id: str,
        patient_pseudonym: str,
        document_id: str,
        *,
        claimed_content_type: str,
        consent_scope_ref: str,
    ) -> UploadOutcome:
        state = self._store.document_state(tenant_id, patient_pseudonym, document_id)
        if state is None:
            raise QuarantineMissingError(
                "the addressed document resolves to no prefix at all; ids only, nothing is echoed"
            )
        if state is not DocumentState.QUARANTINED:
            UPLOAD_PIPELINE_OUTCOMES.labels(outcome="already-processed", reason=_NO_REASON).inc()
            return UploadOutcome(
                document_id=document_id,
                state=state,
                already_processed=True,
                reason=None,
                content_type=None,
                ref=None,
                ocr=None,
            )
        try:
            data, canonical = self._validate(
                tenant_id, patient_pseudonym, document_id, claimed_content_type, consent_scope_ref
            )
        except UploadRejectedError as rejection:
            return self._reject(
                tenant_id,
                patient_pseudonym,
                document_id,
                reason=rejection.reason,
                consent_scope_ref=consent_scope_ref,
            )
        try:
            verdict = self._scanner.scan(data)
        except DocumentStoreError:
            # ScanFailedError, NoScanConfiguredError: no verdict exists, so
            # nothing moves — the object stays quarantined for a retry.
            UPLOAD_PIPELINE_OUTCOMES.labels(outcome="scan-unavailable", reason=_NO_REASON).inc()
            raise
        if verdict is ScanVerdict.INFECTED:
            return self._reject(
                tenant_id,
                patient_pseudonym,
                document_id,
                reason=RejectReason.MALWARE,
                consent_scope_ref=consent_scope_ref,
            )
        ref = self._store.release_quarantined(
            tenant_id,
            patient_pseudonym,
            document_id,
            data,
            content_type=canonical,
            consent_scope_ref=consent_scope_ref,
        )
        ocr = self._ocr.extract(data, canonical)
        UPLOAD_PIPELINE_OUTCOMES.labels(outcome="promoted", reason=_NO_REASON).inc()
        return UploadOutcome(
            document_id=document_id,
            state=DocumentState.CLEAN,
            already_processed=False,
            reason=None,
            content_type=canonical,
            ref=ref,
            ocr=ocr,
        )

    def _validate(
        self,
        tenant_id: str,
        patient_pseudonym: str,
        document_id: str,
        claimed_content_type: str,
        consent_scope_ref: str,
    ) -> tuple[bytes, str]:
        """Everything that must pass BEFORE the scan (files/10 §4: sniffing
        and limits ahead of processing). Raises :class:`UploadRejectedError`
        with a reason code; never echoes content."""
        size = self._store.quarantined_size(tenant_id, patient_pseudonym, document_id)
        if size == 0:
            raise UploadRejectedError(RejectReason.EMPTY, "the uploaded object is empty")
        if size > self._limits.max_bytes:
            raise UploadRejectedError(
                RejectReason.TOO_LARGE,
                f"the uploaded object exceeds the {self._limits.max_bytes}-byte cap",
            )
        canonical = normalise_claimed_type(claimed_content_type)
        if canonical not in PROMOTABLE_TYPES:
            raise UploadRejectedError(
                RejectReason.TYPE_NOT_ALLOWED,
                "the claimed type is recognised but not promotable (its sandboxed "
                "parser has not landed)",
            )
        data = self._store.read_quarantined(
            tenant_id, patient_pseudonym, document_id, consent_scope_ref=consent_scope_ref
        )
        if len(data) > self._limits.max_bytes:
            # The object grew between the HEAD and the read — a presigned PUT
            # replayed inside its TTL. Same refusal, no exception carve-out.
            raise UploadRejectedError(
                RejectReason.TOO_LARGE,
                f"the uploaded object exceeds the {self._limits.max_bytes}-byte cap",
            )
        sniffed = sniff_media_type(data)
        if sniffed is None:
            raise UploadRejectedError(
                RejectReason.MAGIC_UNRECOGNISED,
                "the uploaded bytes match no allow-listed signature",
            )
        if sniffed != canonical:
            raise UploadRejectedError(
                RejectReason.TYPE_MISMATCH,
                "the sniffed type disagrees with the claimed type; neither is echoed",
            )
        return data, canonical

    def _reject(
        self,
        tenant_id: str,
        patient_pseudonym: str,
        document_id: str,
        *,
        reason: RejectReason,
        consent_scope_ref: str,
    ) -> UploadOutcome:
        self._store.reject_quarantined(
            tenant_id,
            patient_pseudonym,
            document_id,
            reason_code=reason.value,
            malware=reason is RejectReason.MALWARE,
            consent_scope_ref=consent_scope_ref,
        )
        UPLOAD_PIPELINE_OUTCOMES.labels(outcome="rejected", reason=reason.value).inc()
        return UploadOutcome(
            document_id=document_id,
            state=DocumentState.REJECTED,
            already_processed=False,
            reason=reason,
            content_type=None,
            ref=None,
            ocr=None,
        )


def process_quarantined_document(
    store: DocumentStore,
    scanner: Scanner,
    *,
    tenant_id: str,
    patient_pseudonym: str,
    document_id: str,
    claimed_content_type: str,
    consent_scope_ref: str,
    limits: UploadLimits | None = None,
    ocr: OcrExtractor | None = None,
) -> UploadOutcome:
    """Plain-callable form of the worker for one document — what the
    services/workers issue wraps into a Celery task (the package does not
    exist on main yet, so there is nothing to register a task against)."""
    pipeline = UploadPipeline(store, scanner, limits=limits, ocr=ocr)
    return pipeline.process(
        tenant_id,
        patient_pseudonym,
        document_id,
        claimed_content_type=claimed_content_type,
        consent_scope_ref=consent_scope_ref,
    )
