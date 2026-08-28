"""INT-120 — upload pipeline unit lane: ClamAV client, sniffing, limits,
promotion worker, OCR seam (files/10 §4 + §9 `records`; invariants 4, 6, 14).

What these tests pin:

- ``ClamAvScanner`` speaks clamd's INSTREAM protocol against an in-test fake
  clamd socket server (TCP and unix); ``from_env`` with nothing configured is
  a typed refusal — there is NO default endpoint that would skip scanning;
  an unreachable, silent, erroring or garbage-talking clamd is a scan
  *failure*, never a verdict, and the document stays quarantined (fail
  closed, invariant 14);
- magic-byte sniffing recognises pdf/jpeg/png (promotable) plus heic/dicom
  (detected so the refusal is precise, not promotable until their sandboxed
  parsers land — the INT-034 allow-list posture); claimed content types and
  bare extensions normalise to canonical MIME; unknown values are refused
  without being echoed (invariant 6);
- the promotion worker takes a quarantined object and runs
  state-check → limit → claimed-type → sniff → mismatch → scan → promote;
  every rejection is a reason-coded audit entry (never content), promotion
  goes through the existing documents.py path (``document.released``), and
  re-running on an already-promoted/rejected object is a no-op;
- malformed/fuzzed PDFs never crash the pipeline: sniffing reads magic bytes
  only and the fail-closed ``NoOcr`` default parses nothing, marking every
  document ``ocr_pending`` until the OCR engine + sandbox ADR lands.

Out of scope here (tests/records/test_upload_pipeline_integration.py): a real
clamd from the compose ``clamav`` profile, EICAR verdicts, and the presigned
PUT → worker promotion roundtrip against real MinIO.
"""

from __future__ import annotations

import hashlib
import inspect
import shutil
import socket
import struct
import tempfile
import threading
import time
from typing import BinaryIO

import pytest
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.documents import (
    ALLOWED_CONTENT_TYPES,
    MAX_DOCUMENT_BYTES,
    ContentTypeNotAllowedError,
    DocumentState,
    DocumentStore,
    QuarantineMissingError,
    ScanVerdict,
)
from intake_platform.uploads import (
    CLAMD_HOST_ENV,
    CLAMD_PORT_ENV,
    CLAMD_TIMEOUT_ENV,
    CLAMD_UNIX_SOCKET_ENV,
    UPLOAD_MAX_BYTES_ENV,
    ClamAvScanner,
    ClamdNotConfiguredError,
    NoOcr,
    OcrOutcome,
    OcrStatus,
    RejectReason,
    ScanFailedError,
    UploadConfigError,
    UploadLimits,
    UploadPipeline,
    UploadRejectedError,
    normalise_claimed_type,
    process_quarantined_document,
    sniff_media_type,
)
from minio.error import S3Error

DOCS_BUCKET = "intake-docs"
AUDIT_BUCKET = "intake-audit-worm"
TENANT = "tenant-ankara"
PSN = "psn-7f3a"
DOC_ID = "0f0e0d0c0b0a09080706050403020100"
CONSENT = "consent:document-upload:v1"

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 32 + b"\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32
HEIC_BYTES = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 16
DICOM_BYTES = b"\x00" * 128 + b"DICM\x02\x00\x00\x00UL\x04\x00" + b"\x00" * 32

# The fake server flags any payload containing this marker as FOUND. It is a
# test-lane token, deliberately NOT the real EICAR string (that one belongs to
# the integration lane where a real clamd recognises it).
FOUND_MARKER = b"INT120-FAKE-SIGNATURE"


def _s3_error(code: str, message: str) -> S3Error:
    # minio's S3Error wants a live HTTP response first; the fake has none and
    # S3Error.__init__ never touches it, so None stands in.
    return S3Error(None, code, message, "resource", "req-1", "host-1")  # type: ignore[arg-type]


# --- fakes: object storage with get/stat (the INT-120 additions) --------------------


class _Payload:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True


class _Stat:
    def __init__(self, size: int) -> None:
        self.size = size


class FakeObjectStorage:
    """In-memory ``ObjectStorageClient`` with the INT-120 read seams
    (``get_object``/``stat_object``). A fake, not a mock: tests assert what
    ended up in which bucket, not call scripts."""

    def __init__(self) -> None:
        # bucket -> key -> (payload, content_type)
        self.buckets: dict[str, dict[str, tuple[bytes, str]]] = {}
        self.lock_config: dict[str, object] = {}
        self.presigned: list[tuple[str, str, str]] = []

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(
        self, bucket_name: str, location: str | None = None, object_lock: bool = False
    ) -> None:
        self.buckets[bucket_name] = {}

    def get_object_lock_config(self, bucket_name: str) -> object:
        return self.lock_config[bucket_name]

    def set_object_lock_config(self, bucket_name: str, config: object) -> None:
        self.lock_config[bucket_name] = config

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        sse: object | None = None,
    ) -> object:
        payload = data.read()
        assert len(payload) == length
        self.buckets[bucket_name][object_name] = (payload, content_type)
        return object()

    def copy_object(self, bucket_name: str, object_name: str, source: object) -> object:
        src_bucket: str = source.bucket_name  # type: ignore[attr-defined]
        src_key: str = source.object_name  # type: ignore[attr-defined]
        self.buckets[bucket_name][object_name] = self.buckets[src_bucket][src_key]
        return object()

    def remove_object(
        self, bucket_name: str, object_name: str, version_id: str | None = None
    ) -> None:
        del self.buckets[bucket_name][object_name]

    def stat_object(self, bucket_name: str, object_name: str) -> _Stat:
        try:
            payload, _ = self.buckets[bucket_name][object_name]
        except KeyError:
            raise _s3_error("NoSuchKey", "object does not exist") from None
        return _Stat(len(payload))

    def get_object(self, bucket_name: str, object_name: str) -> _Payload:
        try:
            payload, _ = self.buckets[bucket_name][object_name]
        except KeyError:
            raise _s3_error("NoSuchKey", "object does not exist") from None
        return _Payload(payload)

    def presigned_get_object(
        self, bucket_name: str, object_name: str, expires: object = None
    ) -> str:
        self.presigned.append(("GET", bucket_name, object_name))
        return f"https://minio.local/{bucket_name}/{object_name}"

    def presigned_put_object(
        self, bucket_name: str, object_name: str, expires: object = None
    ) -> str:
        self.presigned.append(("PUT", bucket_name, object_name))
        return f"https://minio.local/{bucket_name}/{object_name}?verb=PUT"


class _LyingStat(FakeObjectStorage):
    """Reports every object as tiny — the TOCTOU case where the object grows
    between the stat and the read (a presigned PUT re-used inside its TTL)."""

    def stat_object(self, bucket_name: str, object_name: str) -> _Stat:
        super().stat_object(bucket_name, object_name)
        return _Stat(1)


# --- fakes: scanners -----------------------------------------------------------------


class CleanScanner:
    def __init__(self) -> None:
        self.seen: list[bytes] = []

    def scan(self, data: bytes) -> ScanVerdict:
        self.seen.append(data)
        return ScanVerdict.CLEAN


class InfectedScanner:
    def __init__(self) -> None:
        self.seen: list[bytes] = []

    def scan(self, data: bytes) -> ScanVerdict:
        self.seen.append(data)
        return ScanVerdict.INFECTED


class FailingScanner:
    def scan(self, data: bytes) -> ScanVerdict:
        raise ScanFailedError("scanner offline (test)")


class TextOcr:
    """A future OCR engine plugging into the seam — no pipeline change."""

    def extract(self, data: bytes, content_type: str) -> OcrOutcome:
        return OcrOutcome(status=OcrStatus.EXTRACTED, text="hemogram raporu")


# --- fakes: an in-test clamd speaking INSTREAM ----------------------------------------


class FakeClamd:
    """Just enough clamd: null-terminated command, then 4-byte big-endian
    length-prefixed chunks until the zero chunk, then one verdict line.

    Modes: ``verdict`` answers OK/FOUND by payload marker; ``error`` answers
    the INSTREAM size-limit error; ``garbage`` answers bytes no client should
    trust; ``flood`` answers past the client's reply cap without a
    terminator; ``silent`` reads everything and never answers (timeout).
    """

    def __init__(self, mode: str = "verdict") -> None:
        self.mode = mode
        self.payloads: list[bytes] = []
        self.commands: list[bytes] = []
        self._listener: socket.socket | None = None

    def start_tcp(self) -> tuple[str, int]:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        self._serve(listener)
        host, port = listener.getsockname()
        return str(host), int(port)

    def start_unix(self, path: str) -> str:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        self._serve(listener)
        return path

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.close()

    def _serve(self, listener: socket.socket) -> None:
        listener.listen(5)
        self._listener = listener
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()

    def _loop(self) -> None:
        assert self._listener is not None
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            with conn:
                try:
                    self._handle(conn)
                except OSError:
                    continue

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(5)
        command = self._read_until_null(conn)
        self.commands.append(command)
        if command == b"zPING":
            conn.sendall(b"PONG\0")
            return
        if command != b"zINSTREAM":
            conn.sendall(b"UNKNOWN COMMAND\0")
            return
        payload = bytearray()
        while True:
            (length,) = struct.unpack(">I", self._read_exact(conn, 4))
            if length == 0:
                break
            payload += self._read_exact(conn, length)
        self.payloads.append(bytes(payload))
        if self.mode == "silent":
            time.sleep(2)
            return
        if self.mode == "error":
            conn.sendall(b"INSTREAM size limit exceeded. ERROR\0")
            return
        if self.mode == "garbage":
            conn.sendall(b"\xff\xfenot a clamd reply")
            return
        if self.mode == "flood":
            conn.sendall(b"A" * 8192)  # never null-terminated: hits the reply cap
            return
        if FOUND_MARKER in payload:
            conn.sendall(b"stream: Int120.Fake.Signature FOUND\0")
        else:
            conn.sendall(b"stream: OK\0")

    @staticmethod
    def _read_until_null(conn: socket.socket) -> bytes:
        out = bytearray()
        while True:
            byte = conn.recv(1)
            if not byte or byte == b"\0":
                return bytes(out)
            out += byte

    @staticmethod
    def _read_exact(conn: socket.socket, count: int) -> bytes:
        out = bytearray()
        while len(out) < count:
            chunk = conn.recv(count - len(out))
            if not chunk:
                raise OSError("peer closed mid-frame")
            out += chunk
        return bytes(out)


@pytest.fixture
def clamd(request: pytest.FixtureRequest) -> FakeClamd:
    server = FakeClamd()
    request.addfinalizer(server.stop)
    return server


def _dead_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


# --- harness ---------------------------------------------------------------------------


def _store(fake: FakeObjectStorage | None = None) -> tuple[DocumentStore, FakeObjectStorage]:
    storage = fake if fake is not None else FakeObjectStorage()
    chain = AuditChain(InMemoryAuditStore())
    store = DocumentStore(storage, DOCS_BUCKET, AUDIT_BUCKET, chain)
    storage.buckets.setdefault(DOCS_BUCKET, {})
    storage.buckets.setdefault(AUDIT_BUCKET, {})
    return store, storage


def _quarantine(storage: FakeObjectStorage, data: bytes, document_id: str = DOC_ID) -> str:
    key = f"quarantine/{TENANT}/{PSN}/{document_id}"
    storage.buckets[DOCS_BUCKET][key] = (data, "application/octet-stream")
    return key


def _actions(store: DocumentStore) -> list[str]:
    chain: AuditChain = store._audit_chain  # noqa: SLF001  # type: ignore[attr-defined]
    return [entry.action for entry in chain._store.entries()]  # type: ignore[attr-defined]


def _process(
    pipeline: UploadPipeline,
    *,
    document_id: str = DOC_ID,
    claimed: str = "application/pdf",
) -> object:
    return pipeline.process(
        TENANT,
        PSN,
        document_id,
        claimed_content_type=claimed,
        consent_scope_ref=CONSENT,
    )


# --- sniffing ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PDF_BYTES, "application/pdf"),
        (JPEG_BYTES, "image/jpeg"),
        (PNG_BYTES, "image/png"),
        (HEIC_BYTES, "image/heic"),
        (DICOM_BYTES, "application/dicom"),
    ],
)
def test_sniff_recognises_the_allow_listed_magics(data: bytes, expected: str) -> None:
    assert sniff_media_type(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\0",
        b"MZ\x90\x00" + b"\x00" * 64,  # PE executable
        b"PK\x03\x04" + b"\x00" * 64,  # zip (docx/apk/jar carrier)
        b"<html><script>alert(1)</script>",
        b"GIF89a" + b"\x00" * 16,
        b"%PDF",  # truncated before the version dash
        b"\x00" * 127 + b"DICM",  # DICM but not at offset 128
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16,  # mp4 brand, not heic
    ],
)
def test_sniff_returns_none_for_anything_else(data: bytes) -> None:
    assert sniff_media_type(data) is None


@pytest.mark.parametrize(
    ("claimed", "expected"),
    [
        ("application/pdf", "application/pdf"),
        ("Application/PDF; charset=UTF-8", "application/pdf"),
        ("application/x-pdf", "application/pdf"),
        (".pdf", "application/pdf"),
        ("pdf", "application/pdf"),
        ("image/jpg", "image/jpeg"),
        ("image/pjpeg", "image/jpeg"),
        (".JPG", "image/jpeg"),
        ("jpeg", "image/jpeg"),
        ("image/x-png", "image/png"),
        ("png", "image/png"),
        ("image/heif", "image/heic"),
        ("heic", "image/heic"),
        ("dcm", "application/dicom"),
        ("application/dicom", "application/dicom"),
    ],
)
def test_claimed_types_and_extensions_normalise_to_canonical_mime(
    claimed: str, expected: str
) -> None:
    assert normalise_claimed_type(claimed) == expected


@pytest.mark.parametrize("claimed", ["text/html", "application/zip", "", "exe", "image/svg+xml"])
def test_unknown_claimed_type_is_a_typed_refusal_and_never_echoed(claimed: str) -> None:
    with pytest.raises(UploadRejectedError) as excinfo:
        normalise_claimed_type(claimed)
    assert excinfo.value.reason is RejectReason.TYPE_UNRECOGNISED
    if claimed:
        assert claimed not in str(excinfo.value)  # caller free text never reaches a log


# --- limits ------------------------------------------------------------------------------


def test_limit_default_matches_the_store_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(UPLOAD_MAX_BYTES_ENV, raising=False)
    assert UploadLimits.from_env().max_bytes == MAX_DOCUMENT_BYTES


def test_limit_is_env_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(UPLOAD_MAX_BYTES_ENV, "1024")
    assert UploadLimits.from_env().max_bytes == 1024


@pytest.mark.parametrize("bad", ["0", "-5", "abc", ""])
def test_malformed_limit_env_is_a_typed_refusal(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv(UPLOAD_MAX_BYTES_ENV, bad)
    with pytest.raises(UploadConfigError):
        UploadLimits.from_env()


# --- ClamAvScanner: configuration ---------------------------------------------------------


def _clear_clamd_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (CLAMD_HOST_ENV, CLAMD_PORT_ENV, CLAMD_UNIX_SOCKET_ENV, CLAMD_TIMEOUT_ENV):
        monkeypatch.delenv(name, raising=False)


def test_from_env_with_nothing_configured_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    # There is deliberately no default endpoint: an unconfigured scanner is a
    # refusal at construction, never a scan that silently did not happen.
    _clear_clamd_env(monkeypatch)
    with pytest.raises(ClamdNotConfiguredError):
        ClamAvScanner.from_env()


def test_from_env_refuses_both_endpoints_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_clamd_env(monkeypatch)
    monkeypatch.setenv(CLAMD_HOST_ENV, "127.0.0.1")
    monkeypatch.setenv(CLAMD_UNIX_SOCKET_ENV, "/run/clamd.sock")
    with pytest.raises(UploadConfigError):
        ClamAvScanner.from_env()


@pytest.mark.parametrize("bad_port", ["abc", "-1", "0", "70000"])
def test_from_env_refuses_a_malformed_port(monkeypatch: pytest.MonkeyPatch, bad_port: str) -> None:
    _clear_clamd_env(monkeypatch)
    monkeypatch.setenv(CLAMD_HOST_ENV, "127.0.0.1")
    monkeypatch.setenv(CLAMD_PORT_ENV, bad_port)
    with pytest.raises(UploadConfigError):
        ClamAvScanner.from_env()


def test_constructor_refuses_no_endpoint() -> None:
    with pytest.raises(ClamdNotConfiguredError):
        ClamAvScanner()


def test_constructor_refuses_a_non_positive_timeout() -> None:
    with pytest.raises(UploadConfigError):
        ClamAvScanner(host="127.0.0.1", port=3310, timeout_seconds=0)


def test_from_env_refuses_a_malformed_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_clamd_env(monkeypatch)
    monkeypatch.setenv(CLAMD_HOST_ENV, "127.0.0.1")
    monkeypatch.setenv(CLAMD_TIMEOUT_ENV, "soon")
    with pytest.raises(UploadConfigError):
        ClamAvScanner.from_env()


def test_from_env_honours_a_numeric_timeout(
    monkeypatch: pytest.MonkeyPatch, clamd: FakeClamd
) -> None:
    host, port = clamd.start_tcp()
    _clear_clamd_env(monkeypatch)
    monkeypatch.setenv(CLAMD_HOST_ENV, host)
    monkeypatch.setenv(CLAMD_PORT_ENV, str(port))
    monkeypatch.setenv(CLAMD_TIMEOUT_ENV, "2.5")
    assert ClamAvScanner.from_env().scan(PDF_BYTES) is ScanVerdict.CLEAN


# --- ClamAvScanner: the INSTREAM conversation -----------------------------------------------


def test_tcp_scan_clean_verdict_and_exact_payload_delivery(clamd: FakeClamd) -> None:
    host, port = clamd.start_tcp()
    scanner = ClamAvScanner(host=host, port=port, timeout_seconds=5)
    assert scanner.scan(PDF_BYTES) is ScanVerdict.CLEAN
    assert clamd.payloads == [PDF_BYTES]  # framing reassembles byte-for-byte
    assert clamd.commands == [b"zINSTREAM"]


def test_tcp_scan_infected_verdict(clamd: FakeClamd) -> None:
    host, port = clamd.start_tcp()
    scanner = ClamAvScanner(host=host, port=port, timeout_seconds=5)
    assert scanner.scan(b"%PDF-1.7 " + FOUND_MARKER) is ScanVerdict.INFECTED


def test_large_payload_is_chunked_and_reassembled(clamd: FakeClamd) -> None:
    host, port = clamd.start_tcp()
    scanner = ClamAvScanner(host=host, port=port, timeout_seconds=5)
    blob = b"%PDF-1.7\n" + b"\xab" * (200 * 1024)  # forces several chunks
    assert scanner.scan(blob) is ScanVerdict.CLEAN
    assert clamd.payloads == [blob]


def test_unix_socket_scan_works(clamd: FakeClamd) -> None:
    # Not pytest's tmp_path: AF_UNIX paths cap at 104 bytes on macOS and the
    # nested pytest tmp dir blows through it. mkdtemp stays short.
    workdir = tempfile.mkdtemp(prefix="int120-")
    try:
        path = clamd.start_unix(f"{workdir}/clamd.sock")
        scanner = ClamAvScanner(unix_socket=path, timeout_seconds=5)
        assert scanner.scan(PNG_BYTES) is ScanVerdict.CLEAN
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_from_env_tcp_roundtrip(monkeypatch: pytest.MonkeyPatch, clamd: FakeClamd) -> None:
    host, port = clamd.start_tcp()
    _clear_clamd_env(monkeypatch)
    monkeypatch.setenv(CLAMD_HOST_ENV, host)
    monkeypatch.setenv(CLAMD_PORT_ENV, str(port))
    scanner = ClamAvScanner.from_env()
    assert scanner.scan(JPEG_BYTES) is ScanVerdict.CLEAN


def test_ping_roundtrip(clamd: FakeClamd) -> None:
    host, port = clamd.start_tcp()
    scanner = ClamAvScanner(host=host, port=port, timeout_seconds=5)
    assert scanner.ping() is True


def test_ping_against_a_dead_port_is_false() -> None:
    scanner = ClamAvScanner(host="127.0.0.1", port=_dead_port(), timeout_seconds=0.5)
    assert scanner.ping() is False


def test_unreachable_clamd_is_a_scan_failure_not_a_verdict() -> None:
    scanner = ClamAvScanner(host="127.0.0.1", port=_dead_port(), timeout_seconds=0.5)
    with pytest.raises(ScanFailedError):
        scanner.scan(PDF_BYTES)


def test_clamd_error_reply_is_a_scan_failure() -> None:
    server = FakeClamd(mode="error")
    host, port = server.start_tcp()
    try:
        scanner = ClamAvScanner(host=host, port=port, timeout_seconds=5)
        with pytest.raises(ScanFailedError) as excinfo:
            scanner.scan(PDF_BYTES)
        # The raw reply is infrastructure-controlled free text; it stays out
        # of the exception because the exception reaches logs (invariant 6).
        assert "size limit" not in str(excinfo.value)
    finally:
        server.stop()


def test_garbage_reply_is_a_scan_failure() -> None:
    server = FakeClamd(mode="garbage")
    host, port = server.start_tcp()
    try:
        scanner = ClamAvScanner(host=host, port=port, timeout_seconds=5)
        with pytest.raises(ScanFailedError):
            scanner.scan(PDF_BYTES)
    finally:
        server.stop()


def test_a_flooding_reply_is_capped_and_is_a_scan_failure() -> None:
    server = FakeClamd(mode="flood")
    host, port = server.start_tcp()
    try:
        scanner = ClamAvScanner(host=host, port=port, timeout_seconds=5)
        with pytest.raises(ScanFailedError):
            scanner.scan(PDF_BYTES)
    finally:
        server.stop()


def test_silent_clamd_times_out_as_a_scan_failure() -> None:
    server = FakeClamd(mode="silent")
    host, port = server.start_tcp()
    try:
        scanner = ClamAvScanner(host=host, port=port, timeout_seconds=0.3)
        with pytest.raises(ScanFailedError):
            scanner.scan(PDF_BYTES)
    finally:
        server.stop()


# --- pipeline: promotion -----------------------------------------------------------------


def test_clean_pdf_is_promoted_via_the_documents_path() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    scanner = CleanScanner()
    pipeline = UploadPipeline(store, scanner)
    outcome = _process(pipeline)
    assert outcome.state is DocumentState.CLEAN  # type: ignore[attr-defined]
    assert outcome.already_processed is False  # type: ignore[attr-defined]
    assert outcome.content_type == "application/pdf"  # type: ignore[attr-defined]
    assert scanner.seen == [PDF_BYTES]
    clean_key = f"clean/{TENANT}/{PSN}/{DOC_ID}"
    payload, content_type = storage.buckets[DOCS_BUCKET][clean_key]
    assert payload == PDF_BYTES
    assert content_type == "application/pdf"
    assert not any(k.startswith("quarantine/") for k in storage.buckets[DOCS_BUCKET])
    assert _actions(store) == ["document.scan_read", "document.released"]
    ref = outcome.ref  # type: ignore[attr-defined]
    assert ref is not None
    assert ref.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert store.presigned_get(ref, consent_scope_ref="consent:document-share:v1").startswith(
        "https://"
    )


def test_promoted_content_type_is_the_sniffed_canonical_not_the_claimed_alias() -> None:
    store, storage = _store()
    _quarantine(storage, JPEG_BYTES)
    pipeline = UploadPipeline(store, CleanScanner())
    outcome = _process(pipeline, claimed="image/jpg")
    assert outcome.content_type == "image/jpeg"  # type: ignore[attr-defined]
    _, content_type = storage.buckets[DOCS_BUCKET][f"clean/{TENANT}/{PSN}/{DOC_ID}"]
    assert content_type == "image/jpeg"


def test_the_plain_function_wrapper_promotes_too() -> None:
    # services/workers does not exist on main yet; the workers issue wires
    # this callable into Celery without any pipeline change.
    store, storage = _store()
    _quarantine(storage, PNG_BYTES)
    outcome = process_quarantined_document(
        store,
        CleanScanner(),
        tenant_id=TENANT,
        patient_pseudonym=PSN,
        document_id=DOC_ID,
        claimed_content_type="png",
        consent_scope_ref=CONSENT,
    )
    assert outcome.state is DocumentState.CLEAN


# --- pipeline: rejections (typed, reason-coded, audited) ------------------------------------


def test_oversized_object_is_rejected_before_any_scan() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    scanner = CleanScanner()
    pipeline = UploadPipeline(store, scanner, limits=UploadLimits(max_bytes=8))
    outcome = _process(pipeline)
    assert outcome.state is DocumentState.REJECTED  # type: ignore[attr-defined]
    assert outcome.reason is RejectReason.TOO_LARGE  # type: ignore[attr-defined]
    assert scanner.seen == []  # never scanned, never even read
    assert f"rejected/{TENANT}/{PSN}/{DOC_ID}" in storage.buckets[DOCS_BUCKET]
    assert _actions(store) == ["document.rejected.too-large"]


def test_growth_between_stat_and_read_is_still_rejected() -> None:
    store, storage = _store(_LyingStat())
    _quarantine(storage, PDF_BYTES)
    scanner = CleanScanner()
    pipeline = UploadPipeline(store, scanner, limits=UploadLimits(max_bytes=8))
    outcome = _process(pipeline)
    assert outcome.reason is RejectReason.TOO_LARGE  # type: ignore[attr-defined]
    assert scanner.seen == []


def test_empty_object_is_rejected() -> None:
    store, storage = _store()
    _quarantine(storage, b"")
    pipeline = UploadPipeline(store, CleanScanner())
    outcome = _process(pipeline)
    assert outcome.reason is RejectReason.EMPTY  # type: ignore[attr-defined]
    assert _actions(store) == ["document.rejected.empty"]


def test_unrecognised_claimed_type_is_rejected_without_a_scan() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    scanner = CleanScanner()
    pipeline = UploadPipeline(store, scanner)
    outcome = _process(pipeline, claimed="application/zip")
    assert outcome.reason is RejectReason.TYPE_UNRECOGNISED  # type: ignore[attr-defined]
    assert scanner.seen == []
    assert _actions(store) == ["document.rejected.type-unrecognised"]


def test_sniffable_but_not_promotable_type_is_rejected_as_not_allowed() -> None:
    # HEIC and DICOM sniff cleanly but stay out of clean/ until their
    # sandboxed parsers land (INT-034 posture; files/10 §4).
    store, storage = _store()
    _quarantine(storage, HEIC_BYTES)
    pipeline = UploadPipeline(store, CleanScanner())
    outcome = _process(pipeline, claimed="image/heic")
    assert outcome.reason is RejectReason.TYPE_NOT_ALLOWED  # type: ignore[attr-defined]
    assert _actions(store) == ["document.rejected.type-not-allowed"]


def test_unrecognised_magic_is_rejected() -> None:
    store, storage = _store()
    _quarantine(storage, b"MZ\x90\x00" + b"\x00" * 64)
    pipeline = UploadPipeline(store, CleanScanner())
    outcome = _process(pipeline)
    assert outcome.reason is RejectReason.MAGIC_UNRECOGNISED  # type: ignore[attr-defined]
    assert _actions(store) == ["document.scan_read", "document.rejected.magic-unrecognised"]


def test_claimed_versus_sniffed_mismatch_is_rejected() -> None:
    store, storage = _store()
    _quarantine(storage, PNG_BYTES)  # bytes say png
    scanner = CleanScanner()
    pipeline = UploadPipeline(store, scanner)
    outcome = _process(pipeline, claimed="application/pdf")  # claim says pdf
    assert outcome.reason is RejectReason.TYPE_MISMATCH  # type: ignore[attr-defined]
    assert scanner.seen == []
    assert f"rejected/{TENANT}/{PSN}/{DOC_ID}" in storage.buckets[DOCS_BUCKET]
    assert _actions(store) == ["document.scan_read", "document.rejected.type-mismatch"]


def test_infected_object_lands_under_infected_for_forensics() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    pipeline = UploadPipeline(store, InfectedScanner())
    outcome = _process(pipeline)
    assert outcome.state is DocumentState.REJECTED  # type: ignore[attr-defined]
    assert outcome.reason is RejectReason.MALWARE  # type: ignore[attr-defined]
    assert f"infected/{TENANT}/{PSN}/{DOC_ID}" in storage.buckets[DOCS_BUCKET]
    assert not any(k.startswith("quarantine/") for k in storage.buckets[DOCS_BUCKET])
    assert _actions(store) == ["document.scan_read", "document.rejected.malware"]


def test_rejection_audit_entries_carry_reason_codes_never_content() -> None:
    store, storage = _store()
    _quarantine(storage, PNG_BYTES)
    pipeline = UploadPipeline(store, CleanScanner())
    _process(pipeline, claimed="application/pdf")
    chain: AuditChain = store._audit_chain  # noqa: SLF001  # type: ignore[attr-defined]
    for entry in chain._store.entries():  # type: ignore[attr-defined]
        assert "PNG" not in entry.action
        assert "http" not in entry.resource_ref
    assert chain.verify().ok


# --- pipeline: fail closed on scan failure ----------------------------------------------------


def test_scan_failure_keeps_the_object_quarantined_and_raises() -> None:
    store, storage = _store()
    key = _quarantine(storage, PDF_BYTES)
    pipeline = UploadPipeline(store, FailingScanner())
    with pytest.raises(ScanFailedError):
        _process(pipeline)
    assert key in storage.buckets[DOCS_BUCKET]  # still quarantined, retryable
    assert not any(k.startswith(("clean/", "rejected/")) for k in storage.buckets[DOCS_BUCKET])
    assert _actions(store) == ["document.scan_read"]  # no verdict, no promotion, no rejection


def test_unreachable_real_clamd_client_keeps_the_object_quarantined() -> None:
    store, storage = _store()
    key = _quarantine(storage, PDF_BYTES)
    scanner = ClamAvScanner(host="127.0.0.1", port=_dead_port(), timeout_seconds=0.5)
    pipeline = UploadPipeline(store, scanner)
    with pytest.raises(ScanFailedError):
        _process(pipeline)
    assert key in storage.buckets[DOCS_BUCKET]


def test_pipeline_scanner_parameter_has_no_default() -> None:
    parameter = inspect.signature(UploadPipeline.__init__).parameters["scanner"]
    assert parameter.default is inspect.Parameter.empty  # scanning is never optional


# --- pipeline: idempotency ---------------------------------------------------------------------


def test_rerun_on_a_promoted_object_is_a_noop() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    scanner = CleanScanner()
    pipeline = UploadPipeline(store, scanner)
    _process(pipeline)
    before = _actions(store)
    second = _process(pipeline)
    assert second.already_processed is True  # type: ignore[attr-defined]
    assert second.state is DocumentState.CLEAN  # type: ignore[attr-defined]
    assert scanner.seen == [PDF_BYTES]  # not scanned again
    assert _actions(store) == before  # no new audit entries


def test_rerun_on_a_rejected_object_is_a_noop() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    pipeline = UploadPipeline(store, InfectedScanner())
    _process(pipeline)
    before = _actions(store)
    second = _process(pipeline)
    assert second.already_processed is True  # type: ignore[attr-defined]
    assert second.state is DocumentState.REJECTED  # type: ignore[attr-defined]
    assert _actions(store) == before


def test_processing_a_missing_object_is_a_typed_error() -> None:
    store, _ = _store()
    pipeline = UploadPipeline(store, CleanScanner())
    with pytest.raises(QuarantineMissingError):
        _process(pipeline)


# --- document_state + store-level defence in depth ------------------------------------------------


def test_document_state_reports_each_prefix() -> None:
    store, storage = _store()
    assert store.document_state(TENANT, PSN, DOC_ID) is None
    key = _quarantine(storage, PDF_BYTES)
    assert store.document_state(TENANT, PSN, DOC_ID) is DocumentState.QUARANTINED
    storage.buckets[DOCS_BUCKET][f"clean/{TENANT}/{PSN}/{DOC_ID}"] = storage.buckets[DOCS_BUCKET][
        key
    ]
    del storage.buckets[DOCS_BUCKET][key]
    assert store.document_state(TENANT, PSN, DOC_ID) is DocumentState.CLEAN
    other = "1f0e0d0c0b0a09080706050403020100"
    storage.buckets[DOCS_BUCKET][f"rejected/{TENANT}/{PSN}/{other}"] = (PDF_BYTES, "x")
    assert store.document_state(TENANT, PSN, other) is DocumentState.REJECTED


def test_release_refuses_content_types_outside_the_store_allow_list() -> None:
    # Defence in depth: even a drifted pipeline cannot promote a type the
    # store does not serve.
    store, storage = _store()
    _quarantine(storage, HEIC_BYTES)
    with pytest.raises(ContentTypeNotAllowedError):
        store.release_quarantined(
            TENANT, PSN, DOC_ID, HEIC_BYTES, content_type="image/heic", consent_scope_ref=CONSENT
        )
    assert ALLOWED_CONTENT_TYPES == frozenset({"application/pdf", "image/jpeg", "image/png"})


def test_releasing_a_missing_quarantine_object_is_a_typed_error() -> None:
    store, _ = _store()
    with pytest.raises(QuarantineMissingError):
        store.release_quarantined(
            TENANT,
            PSN,
            DOC_ID,
            PDF_BYTES,
            content_type="application/pdf",
            consent_scope_ref=CONSENT,
        )


# --- OCR seam: fail-closed default, pluggable engine ---------------------------------------


def test_default_ocr_marks_documents_ocr_pending_and_parses_nothing() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    pipeline = UploadPipeline(store, CleanScanner())
    outcome = _process(pipeline)
    ocr = outcome.ocr  # type: ignore[attr-defined]
    assert ocr is not None
    assert ocr.status is OcrStatus.PENDING
    assert ocr.text is None


def test_noocr_extract_is_pending_for_any_input() -> None:
    result = NoOcr().extract(b"\x00\xff garbage that is not any format", "application/pdf")
    assert result == OcrOutcome(status=OcrStatus.PENDING, text=None)


def test_a_future_engine_plugs_into_the_seam_without_touching_callers() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    pipeline = UploadPipeline(store, CleanScanner(), ocr=TextOcr())
    outcome = _process(pipeline)
    ocr = outcome.ocr  # type: ignore[attr-defined]
    assert ocr is not None
    assert ocr.status is OcrStatus.EXTRACTED
    assert ocr.text == "hemogram raporu"


def test_rejected_documents_get_no_ocr_at_all() -> None:
    store, storage = _store()
    _quarantine(storage, b"MZ\x90\x00" + b"\x00" * 64)

    class ExplodingOcr:
        def extract(self, data: bytes, content_type: str) -> OcrOutcome:
            raise AssertionError("OCR must never see a rejected document")

    pipeline = UploadPipeline(store, CleanScanner(), ocr=ExplodingOcr())
    outcome = _process(pipeline)
    assert outcome.ocr is None  # type: ignore[attr-defined]


# --- fuzz: malformed PDFs never crash the pipeline ------------------------------------------------


def _fuzz_pdfs(count: int) -> list[bytes]:
    # Deterministic pseudo-fuzz (no RNG): hash-chained garbage behind a valid
    # header, the shape a hostile or corrupted upload actually has.
    blobs: list[bytes] = []
    for index in range(count):
        chunks = [hashlib.sha256(b"INT-120" + bytes([index, step])).digest() for step in range(64)]
        blobs.append(b"%PDF-1.4\n" + b"".join(chunks))
    return blobs


def test_fuzzed_pdfs_are_processed_without_any_parse_and_never_crash() -> None:
    for index, blob in enumerate(_fuzz_pdfs(24)):
        store, storage = _store()
        document_id = f"{index:032x}"
        _quarantine(storage, blob, document_id=document_id)
        pipeline = UploadPipeline(store, CleanScanner())
        outcome = pipeline.process(
            TENANT,
            PSN,
            document_id,
            claimed_content_type="application/pdf",
            consent_scope_ref=CONSENT,
        )
        assert outcome.state is DocumentState.CLEAN
        ocr = outcome.ocr
        assert ocr is not None and ocr.status is OcrStatus.PENDING


def test_fuzzed_headerless_garbage_is_rejected_not_crashed() -> None:
    store, storage = _store()
    blob = hashlib.sha256(b"INT-120-headerless").digest() * 100
    _quarantine(storage, blob)
    pipeline = UploadPipeline(store, CleanScanner())
    outcome = _process(pipeline)
    assert outcome.state is DocumentState.REJECTED  # type: ignore[attr-defined]
    assert outcome.reason is RejectReason.MAGIC_UNRECOGNISED  # type: ignore[attr-defined]


# --- signals (files/10 §9 records: upload scan results) ------------------------------------


def _counter(outcome: str, reason: str) -> float:
    from prometheus_client import REGISTRY

    value = REGISTRY.get_sample_value(
        "document_upload_pipeline_total", {"outcome": outcome, "reason": reason}
    )
    return value if value is not None else 0.0


def test_outcomes_are_counted_by_reason_code_only() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    before_promoted = _counter("promoted", "none")
    pipeline = UploadPipeline(store, CleanScanner())
    _process(pipeline)
    assert _counter("promoted", "none") == before_promoted + 1

    store, storage = _store()
    _quarantine(storage, PNG_BYTES)
    before_rejected = _counter("rejected", "type-mismatch")
    _process(UploadPipeline(store, CleanScanner()), claimed="application/pdf")
    assert _counter("rejected", "type-mismatch") == before_rejected + 1


def test_scan_failures_are_counted_before_the_raise() -> None:
    store, storage = _store()
    _quarantine(storage, PDF_BYTES)
    before = _counter("scan-unavailable", "none")
    with pytest.raises(ScanFailedError):
        _process(UploadPipeline(store, FailingScanner()))
    assert _counter("scan-unavailable", "none") == before + 1
