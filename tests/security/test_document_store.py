"""INT-034 — MinIO document store, unit lane (files/10 §2 + §9 `documents`;
invariants 4, 6, 14).

What these tests pin:

- ``ensure_buckets`` gives the audit bucket object-lock (WORM) with a default
  COMPLIANCE retention, and a pre-existing bucket *without* the lock is a typed
  misconfiguration — never a silent downgrade (MinIO can only enable the lock
  at creation, so "fix it later" does not exist);
- ``put_document`` recomputes the sha256 server-side, enforces the 20 MB cap
  and the pdf+images allow-list, and builds keys as
  ``<prefix>/<tenant>/<pseudonym>/<uuid>`` — no filename parameter even exists,
  so a patient-named file can never leak its name into an object key
  (invariant 6);
- nothing is fetchable before a malware verdict: the default scanner refuses
  loudly (``NoScanConfiguredError``), an infected verdict lands the object
  under ``infected/`` and raises, and ``presigned_get`` only ever signs keys
  under ``clean/``;
- ``DevNullScanner`` — the dev-tier "mark everything clean" stand-in — is
  unconstructible unless ``INTAKE_DEV_ALLOW_UNSCANNED=explicit-yes``, and
  refuses prod outright;
- every mutating operation appends exactly one hash-chained audit entry
  (INT-016) with an id-shaped ``resource_ref`` and no payload: no digest, no
  URL, no content, no content type.

Out of scope here (the integration lane, test_document_store_integration.py):
real MinIO bucket creation, the presigned-URL HTTP roundtrip, and the WORM
delete-refusal on a locked object version. ClamAV itself is INT-120; this
module pins the wiring point it plugs into.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import re
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

import pytest
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.documents import (
    ALLOWED_CONTENT_TYPES,
    MAX_DOCUMENT_BYTES,
    ContentTypeNotAllowedError,
    DevNullScanner,
    DevScannerForbiddenError,
    DigestMismatchError,
    DocumentNotFetchableError,
    DocumentRejectedError,
    DocumentState,
    DocumentStore,
    DocumentTooLargeError,
    InvalidKeySegmentError,
    NoScanConfiguredError,
    ScanVerdict,
    WormMisconfiguredError,
    as_object_storage,
)
from minio import Minio
from minio.commonconfig import COMPLIANCE, GOVERNANCE
from minio.error import S3Error
from minio.objectlockconfig import DAYS, ObjectLockConfig

DOCS_BUCKET = "intake-docs"
AUDIT_BUCKET = "intake-audit-worm"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()
HEX32 = re.compile(r"[0-9a-f]{32}")


def _s3_error(code: str, message: str) -> S3Error:
    # minio's S3Error wants a live HTTP response object first; the fake has
    # none, and S3Error.__init__ never touches it, so None stands in.
    return S3Error(None, code, message, "resource", "req-1", "host-1")  # type: ignore[arg-type]


class _FakeBucket:
    def __init__(self, object_lock: bool) -> None:
        self.object_lock = object_lock
        self.lock_config: ObjectLockConfig | None = None
        # key -> (payload, content_type)
        self.objects: dict[str, tuple[bytes, str]] = {}


class FakeObjectStorage:
    """In-memory implementation of the ``ObjectStorageClient`` protocol.

    A fake, not a mock: it keeps real bucket/object state so the tests assert
    outcomes (what ended up where) rather than call scripts. It mirrors dev
    MinIO's one sharp edge on purpose: object-lock exists only if requested at
    bucket creation.
    """

    def __init__(self) -> None:
        self.buckets: dict[str, _FakeBucket] = {}
        self.make_bucket_calls: list[tuple[str, bool]] = []
        # (verb, bucket, key, expires)
        self.presigned: list[tuple[str, str, str, timedelta]] = []
        self.refuse_object_lock = False  # a server build without lock support

    # --- buckets ---------------------------------------------------------------

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(
        self, bucket_name: str, location: str | None = None, object_lock: bool = False
    ) -> None:
        if object_lock and self.refuse_object_lock:
            raise _s3_error("NotImplemented", "object locking is not available")
        self.make_bucket_calls.append((bucket_name, object_lock))
        self.buckets[bucket_name] = _FakeBucket(object_lock)

    def get_object_lock_config(self, bucket_name: str) -> ObjectLockConfig:
        bucket = self.buckets[bucket_name]
        if not bucket.object_lock:
            raise _s3_error(
                "ObjectLockConfigurationNotFoundError", "Object Lock configuration does not exist"
            )
        if bucket.lock_config is None:
            return ObjectLockConfig(None, None, None)
        return bucket.lock_config

    def set_object_lock_config(self, bucket_name: str, config: ObjectLockConfig) -> None:
        bucket = self.buckets[bucket_name]
        if not bucket.object_lock:
            raise _s3_error("InvalidRequest", "bucket is missing ObjectLockConfiguration")
        bucket.lock_config = config

    # --- objects ---------------------------------------------------------------

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
        self.buckets[bucket_name].objects[object_name] = (payload, content_type)
        return object()

    def copy_object(self, bucket_name: str, object_name: str, source: object) -> object:
        src_bucket: str = source.bucket_name  # type: ignore[attr-defined]
        src_key: str = source.object_name  # type: ignore[attr-defined]
        self.buckets[bucket_name].objects[object_name] = self.buckets[src_bucket].objects[src_key]
        return object()

    def remove_object(
        self, bucket_name: str, object_name: str, version_id: str | None = None
    ) -> None:
        del self.buckets[bucket_name].objects[object_name]

    def presigned_get_object(
        self, bucket_name: str, object_name: str, expires: timedelta = timedelta(days=7)
    ) -> str:
        self.presigned.append(("GET", bucket_name, object_name, expires))
        seconds = int(expires.total_seconds())
        return f"https://minio.local/{bucket_name}/{object_name}?X-Amz-Expires={seconds}"

    def presigned_put_object(
        self, bucket_name: str, object_name: str, expires: timedelta = timedelta(days=7)
    ) -> str:
        self.presigned.append(("PUT", bucket_name, object_name, expires))
        seconds = int(expires.total_seconds())
        return f"https://minio.local/{bucket_name}/{object_name}?X-Amz-Expires={seconds}&verb=PUT"


class CleanScanner:
    def __init__(self) -> None:
        self.seen: list[bytes] = []

    def scan(self, data: bytes) -> ScanVerdict:
        self.seen.append(data)
        return ScanVerdict.CLEAN


class InfectedScanner:
    def scan(self, data: bytes) -> ScanVerdict:
        return ScanVerdict.INFECTED


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 28, 9, 0, 0, tzinfo=UTC)


def _store(
    scanner: object | None = None, **kwargs: object
) -> tuple[DocumentStore, FakeObjectStorage, AuditChain]:
    fake = FakeObjectStorage()
    chain = AuditChain(InMemoryAuditStore(), clock=_fixed_clock)
    store = DocumentStore(
        fake,
        DOCS_BUCKET,
        AUDIT_BUCKET,
        chain,
        scanner=scanner,  # type: ignore[arg-type]
        clock=_fixed_clock,
        **kwargs,  # type: ignore[arg-type]
    )
    return store, fake, chain


def _put(store: DocumentStore, **overrides: object) -> object:
    kwargs: dict[str, object] = {
        "tenant_id": "tenant-ankara",
        "patient_pseudonym": "psn-7f3a",
        "file_bytes": PDF_BYTES,
        "content_type": "application/pdf",
        "sha256": PDF_SHA,
        "consent_scope_ref": "consent:document-upload:v1",
    }
    kwargs.update(overrides)
    return store.put_document(**kwargs)  # type: ignore[arg-type]


def _actions(chain: AuditChain) -> list[str]:
    return [entry.action for entry in chain._store.entries()]  # type: ignore[attr-defined]


# --- ensure_buckets: WORM honesty --------------------------------------------------


def test_ensure_buckets_creates_docs_plain_and_audit_with_worm() -> None:
    store, fake, _ = _store()
    store.ensure_buckets()
    assert fake.make_bucket_calls == [(DOCS_BUCKET, False), (AUDIT_BUCKET, True)]
    config = fake.buckets[AUDIT_BUCKET].lock_config
    assert config is not None
    assert config.mode == COMPLIANCE
    assert config.duration == 3650  # ten years by default; hospital-tenant tier, files/10 §2


def test_ensure_buckets_retention_days_is_configurable() -> None:
    store, fake, _ = _store(audit_retention_days=30)
    store.ensure_buckets()
    config = fake.buckets[AUDIT_BUCKET].lock_config
    assert config is not None
    assert config.duration == 30


def test_ensure_buckets_is_idempotent() -> None:
    store, fake, _ = _store()
    store.ensure_buckets()
    store.ensure_buckets()
    assert len(fake.make_bucket_calls) == 2  # one per bucket, not per call


def test_audit_bucket_preexisting_without_lock_is_a_typed_misconfiguration() -> None:
    store, fake, _ = _store()
    fake.make_bucket(AUDIT_BUCKET)  # someone created it without the lock
    with pytest.raises(WormMisconfiguredError, match="object.lock|WORM"):
        store.ensure_buckets()


def test_server_refusing_object_lock_fails_closed_not_degraded() -> None:
    store, fake, _ = _store()
    fake.refuse_object_lock = True
    with pytest.raises(WormMisconfiguredError) as excinfo:
        store.ensure_buckets()
    assert isinstance(excinfo.value.__cause__, S3Error)
    assert AUDIT_BUCKET not in fake.buckets  # nothing half-created


def test_lock_enabled_but_no_default_retention_is_tightened_to_compliance() -> None:
    store, fake, _ = _store()
    fake.make_bucket(AUDIT_BUCKET, object_lock=True)  # lock on, no default retention
    store.ensure_buckets()
    config = fake.buckets[AUDIT_BUCKET].lock_config
    assert config is not None
    assert config.mode == COMPLIANCE


def test_governance_default_is_tightened_to_compliance() -> None:
    store, fake, _ = _store()
    fake.make_bucket(AUDIT_BUCKET, object_lock=True)
    fake.buckets[AUDIT_BUCKET].lock_config = ObjectLockConfig(GOVERNANCE, 7, DAYS)
    store.ensure_buckets()
    config = fake.buckets[AUDIT_BUCKET].lock_config
    assert config is not None
    assert config.mode == COMPLIANCE


def test_existing_compliance_retention_is_left_alone() -> None:
    store, fake, _ = _store()
    fake.make_bucket(AUDIT_BUCKET, object_lock=True)
    fake.buckets[AUDIT_BUCKET].lock_config = ObjectLockConfig(COMPLIANCE, 7300, DAYS)
    store.ensure_buckets()
    config = fake.buckets[AUDIT_BUCKET].lock_config
    assert config is not None
    assert config.duration == 7300  # an operator's stricter setting is never loosened


# --- put_document: validation ------------------------------------------------------


def test_put_document_clean_flow_promotes_quarantine_to_clean() -> None:
    scanner = CleanScanner()
    store, fake, chain = _store(scanner=scanner)
    store.ensure_buckets()
    ref = _put(store)
    assert ref.state is DocumentState.CLEAN  # type: ignore[attr-defined]
    key: str = ref.key  # type: ignore[attr-defined]
    assert key.startswith("clean/tenant-ankara/psn-7f3a/")
    assert key in fake.buckets[DOCS_BUCKET].objects
    payload, content_type = fake.buckets[DOCS_BUCKET].objects[key]
    assert payload == PDF_BYTES
    assert content_type == "application/pdf"
    assert scanner.seen == [PDF_BYTES]
    # quarantine copy is gone; nothing ever landed in the audit bucket
    assert not any(k.startswith("quarantine/") for k in fake.buckets[DOCS_BUCKET].objects)
    assert fake.buckets[AUDIT_BUCKET].objects == {}
    assert _actions(chain) == ["document.stored", "document.released"]
    assert chain.verify().ok


def test_object_key_is_tenant_pseudonym_uuid_and_nothing_else() -> None:
    store, _, _ = _store(scanner=CleanScanner())
    store.ensure_buckets()
    ref = _put(store)
    prefix, tenant, pseudonym, document_id = ref.key.split("/")  # type: ignore[attr-defined]
    assert prefix == "clean"
    assert tenant == "tenant-ankara"
    assert pseudonym == "psn-7f3a"
    assert HEX32.fullmatch(document_id)
    # No filename can leak into a key because no filename parameter exists.
    assert "filename" not in inspect.signature(DocumentStore.put_document).parameters


def test_oversized_document_is_refused_before_anything_is_stored() -> None:
    store, fake, chain = _store(scanner=CleanScanner())
    store.ensure_buckets()
    with pytest.raises(DocumentTooLargeError, match="20"):
        _put(store, file_bytes=b"\0" * (MAX_DOCUMENT_BYTES + 1), sha256="0" * 64)
    assert fake.buckets[DOCS_BUCKET].objects == {}
    assert _actions(chain) == []


def test_document_at_exactly_the_cap_is_accepted() -> None:
    store, _, _ = _store(scanner=CleanScanner())
    store.ensure_buckets()
    blob = b"\0" * MAX_DOCUMENT_BYTES
    ref = _put(store, file_bytes=blob, sha256=hashlib.sha256(blob).hexdigest())
    assert ref.size_bytes == MAX_DOCUMENT_BYTES  # type: ignore[attr-defined]


@pytest.mark.parametrize("bad_type", ["text/html", "application/zip", "image/svg+xml", ""])
def test_content_type_outside_the_allow_list_is_refused(bad_type: str) -> None:
    store, fake, chain = _store(scanner=CleanScanner())
    store.ensure_buckets()
    with pytest.raises(ContentTypeNotAllowedError) as excinfo:
        _put(store, content_type=bad_type)
    # The caller-supplied string is data, not something to echo into an error
    # that will reach a log (invariant 6 discipline).
    if bad_type:
        assert bad_type not in str(excinfo.value)
    assert fake.buckets[DOCS_BUCKET].objects == {}
    assert _actions(chain) == []


def test_allow_list_is_pdf_and_images_only_for_now() -> None:
    assert ALLOWED_CONTENT_TYPES == frozenset({"application/pdf", "image/jpeg", "image/png"})


def test_sha256_is_recomputed_server_side_and_mismatch_is_refused() -> None:
    store, fake, chain = _store(scanner=CleanScanner())
    store.ensure_buckets()
    wrong = hashlib.sha256(b"some other bytes").hexdigest()
    with pytest.raises(DigestMismatchError) as excinfo:
        _put(store, sha256=wrong)
    message = str(excinfo.value)
    assert wrong not in message and PDF_SHA not in message
    assert fake.buckets[DOCS_BUCKET].objects == {}
    assert _actions(chain) == []


def test_declared_sha256_is_case_insensitive() -> None:
    store, _, _ = _store(scanner=CleanScanner())
    store.ensure_buckets()
    ref = _put(store, sha256=PDF_SHA.upper())
    assert ref.sha256 == PDF_SHA  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "bad_segment",
    ["", "has/slash", "has space", "hasta-adı", "-leading", "x" * 41],
)
def test_key_segments_must_be_id_shaped(bad_segment: str) -> None:
    store, _, chain = _store(scanner=CleanScanner())
    store.ensure_buckets()
    for field in ("tenant_id", "patient_pseudonym"):
        with pytest.raises(InvalidKeySegmentError) as excinfo:
            _put(store, **{field: bad_segment})
        assert field in str(excinfo.value)
        if bad_segment:
            assert bad_segment not in str(excinfo.value)  # never echo the value
    assert _actions(chain) == []


# --- the AV hook: nothing serves unscanned ------------------------------------------


def test_default_scanner_refuses_and_the_object_stays_quarantined() -> None:
    store, fake, chain = _store()  # no scanner injected
    store.ensure_buckets()
    with pytest.raises(NoScanConfiguredError):
        _put(store)
    quarantined = [k for k in fake.buckets[DOCS_BUCKET].objects if k.startswith("quarantine/")]
    assert len(quarantined) == 1
    assert not any(k.startswith("clean/") for k in fake.buckets[DOCS_BUCKET].objects)
    assert _actions(chain) == ["document.stored"]


def test_infected_document_is_moved_aside_and_the_put_raises() -> None:
    store, fake, chain = _store(scanner=InfectedScanner())
    store.ensure_buckets()
    with pytest.raises(DocumentRejectedError):
        _put(store)
    keys = list(fake.buckets[DOCS_BUCKET].objects)
    assert len(keys) == 1 and keys[0].startswith("infected/")
    assert _actions(chain) == ["document.stored", "document.rejected"]
    entries = chain._store.entries()  # type: ignore[attr-defined]
    assert entries[-1].resource_ref.startswith("infected/")


def test_infected_and_quarantined_objects_never_get_a_url() -> None:
    store, fake, chain = _store(scanner=CleanScanner())
    store.ensure_buckets()
    ref = _put(store)
    # A ref whose key was tampered toward quarantine/infected is refused even
    # if its state field lies (defence in depth: prefix and state both gate).
    for prefix in ("quarantine", "infected"):
        lying = dataclasses.replace(ref, key=ref.key.replace("clean/", f"{prefix}/", 1))  # type: ignore[type-var]
        with pytest.raises(DocumentNotFetchableError):
            store.presigned_get(lying, consent_scope_ref="consent:document-share:v1")  # type: ignore[arg-type]
    honest_state = dataclasses.replace(ref, state=DocumentState.QUARANTINED)  # type: ignore[type-var]
    with pytest.raises(DocumentNotFetchableError):
        store.presigned_get(honest_state, consent_scope_ref="consent:document-share:v1")  # type: ignore[arg-type]
    assert [(verb, key) for verb, _, key, _ in fake.presigned] == []


def test_wrong_bucket_ref_is_refused() -> None:
    store, _, _ = _store(scanner=CleanScanner())
    store.ensure_buckets()
    ref = _put(store)
    foreign = dataclasses.replace(ref, bucket="somebody-elses-bucket")  # type: ignore[type-var]
    with pytest.raises(DocumentNotFetchableError):
        store.presigned_get(foreign, consent_scope_ref="consent:document-share:v1")  # type: ignore[arg-type]


def test_docs_and_audit_may_never_be_the_same_bucket() -> None:
    # WORM retention on patient documents would make KVKK-7 erasure impossible,
    # so the constructor refuses the aliasing outright.
    chain = AuditChain(InMemoryAuditStore(), clock=_fixed_clock)
    with pytest.raises(WormMisconfiguredError, match="separate"):
        DocumentStore(FakeObjectStorage(), "one-bucket", "one-bucket", chain)


def test_the_default_clock_stamps_worm_bundle_keys_in_utc() -> None:
    fake = FakeObjectStorage()
    chain = AuditChain(InMemoryAuditStore(), clock=_fixed_clock)
    store = DocumentStore(fake, DOCS_BUCKET, AUDIT_BUCKET, chain)  # no clock injected
    store.ensure_buckets()
    key = store.put_audit_bundle(chain.export_worm())
    stamp = key.removeprefix("audit/").split("-")[0]
    parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    assert abs((parsed - datetime.now(tz=UTC)).total_seconds()) < 300


# --- DevNullScanner: dev-tier honesty ----------------------------------------------


def test_dev_null_scanner_is_unconstructible_without_the_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INTAKE_DEV_ALLOW_UNSCANNED", raising=False)
    with pytest.raises(DevScannerForbiddenError):
        DevNullScanner()


@pytest.mark.parametrize("half_hearted", ["yes", "true", "1", "explicit_yes", "EXPLICIT-YES"])
def test_dev_null_scanner_rejects_anything_but_the_exact_phrase(
    monkeypatch: pytest.MonkeyPatch, half_hearted: str
) -> None:
    monkeypatch.setenv("INTAKE_DEV_ALLOW_UNSCANNED", half_hearted)
    with pytest.raises(DevScannerForbiddenError):
        DevNullScanner()


def test_dev_null_scanner_refuses_prod_even_with_the_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTAKE_DEV_ALLOW_UNSCANNED", "explicit-yes")
    monkeypatch.setenv("INTAKE_ENV", "prod")
    with pytest.raises(DevScannerForbiddenError, match="prod"):
        DevNullScanner()


def test_dev_null_scanner_marks_clean_when_explicitly_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTAKE_DEV_ALLOW_UNSCANNED", "explicit-yes")
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    scanner = DevNullScanner()
    assert scanner.scan(PDF_BYTES) is ScanVerdict.CLEAN
    store, _, _ = _store(scanner=scanner)
    store.ensure_buckets()
    ref = _put(store)
    assert ref.state is DocumentState.CLEAN  # type: ignore[attr-defined]


# --- WORM export upload + audit accounting ------------------------------------------


def test_put_audit_bundle_lands_in_the_worm_bucket() -> None:
    store, fake, chain = _store()
    store.ensure_buckets()
    bundle = chain.export_worm()
    key = store.put_audit_bundle(bundle)
    assert re.fullmatch(r"audit/\d{8}T\d{6}Z-[0-9a-f]{32}\.jsonl", key)
    payload, content_type = fake.buckets[AUDIT_BUCKET].objects[key]
    assert payload == bundle
    assert content_type == "application/x-ndjson"
    assert _actions(chain) == ["audit.worm_copied"]


def test_every_mutating_op_appends_exactly_one_entry_with_no_payload() -> None:
    store, fake, chain = _store(scanner=CleanScanner())
    store.ensure_buckets()
    ref = _put(store)
    store.presigned_get(ref, consent_scope_ref="consent:document-share:v1")  # type: ignore[arg-type]
    store.presigned_put("tenant-ankara", "psn-7f3a", consent_scope_ref="consent:document-upload:v1")
    store.put_audit_bundle(chain.export_worm())
    assert _actions(chain) == [
        "document.stored",  # put: quarantine write
        "document.released",  # put: clean promotion after the verdict
        "document.presigned",  # GET share
        "document.presigned",  # PUT upload slot
        "audit.worm_copied",  # WORM copy of the chain itself
    ]
    entries = chain._store.entries()  # type: ignore[attr-defined]
    for entry in entries:
        for value in dataclasses.asdict(entry).values():
            text = str(value)
            assert PDF_SHA not in text  # no digest
            assert "http" not in text and "X-Amz" not in text  # no URL, no signature
            assert "application/pdf" not in text  # no payload metadata
    assert chain.verify().ok
    assert store.presigned_get(
        ref,
        consent_scope_ref="consent:document-share:v1",  # type: ignore[arg-type]
    ).startswith("https://")


def test_the_real_minio_client_satisfies_the_protocol() -> None:
    # Constructing a Minio client makes no network call; the point is that
    # `as_object_storage` type-checks under mypy --strict, pinning that the
    # protocol stays call-compatible with the real client.
    client = Minio("127.0.0.1:9000", access_key="unit", secret_key="unit-only", secure=False)
    assert as_object_storage(client) is client
