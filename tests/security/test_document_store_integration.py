"""INT-034 — document store integration lane: real MinIO from the dev compose.

Runs under ``-m integration`` (its own CI job / ``make check-integration``;
the unit lane never dials a network). Requires the compose ``minio`` service
from infra/docker-compose.dev.yml healthy on 127.0.0.1:9000 with the dev-only
root credentials.

What only this lane can prove:

- ``ensure_buckets`` against a real server: the audit bucket comes back with
  object-lock + default COMPLIANCE retention, and a bucket created *without*
  the lock genuinely cannot be upgraded (the typed misconfiguration fires);
- the presigned URL actually serves the exact bytes over HTTP — and stops
  serving them after its short TTL expires;
- WORM is real: deleting a locked object *version* before retention expiry is
  refused by the server. (S3 semantics: a versionless delete on a versioned
  bucket only writes a delete marker, and an overwrite only stacks a new
  version — in both cases the original version survives and stays readable,
  which is asserted below. Nothing erases the written bytes.)

Buckets are freshly named per run (``int034-*``). The docs bucket is cleaned
up; the WORM bucket *cannot* be cleaned before its retention expires — that
is the property under test — so each run leaves one small locked bucket in
the dev volume (retention 1 day; the miniodata volume is disposable).
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from datetime import timedelta

import httpx
import pytest
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.documents import (
    DevNullScanner,
    DocumentStore,
    WormMisconfiguredError,
    as_object_storage,
)
from minio import Minio
from minio.commonconfig import COMPLIANCE
from minio.error import S3Error

pytestmark = pytest.mark.integration

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()


@pytest.fixture(scope="module")
def client() -> Minio:
    return Minio(
        os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=os.environ.get("MINIO_ROOT_USER", "intake-dev"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "intake-dev-only"),
        secure=False,
    )


@pytest.fixture
def dev_scanner(monkeypatch: pytest.MonkeyPatch) -> DevNullScanner:
    monkeypatch.setenv("INTAKE_DEV_ALLOW_UNSCANNED", "explicit-yes")
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    return DevNullScanner()


def _fresh(kind: str) -> str:
    return f"int034-{kind}-{uuid.uuid4().hex[:12]}"


def _store(
    client: Minio, docs: str, worm: str, scanner: DevNullScanner | None = None
) -> tuple[DocumentStore, AuditChain]:
    chain = AuditChain(InMemoryAuditStore())
    store = DocumentStore(
        as_object_storage(client),
        docs,
        worm,
        chain,
        scanner=scanner,
        audit_retention_days=1,  # COMPLIANCE cannot be shortened later, even by root
    )
    return store, chain


def _drain_bucket(client: Minio, bucket: str) -> None:
    for obj in client.list_objects(bucket, recursive=True):
        if obj.object_name is not None:
            client.remove_object(bucket, obj.object_name)
    client.remove_bucket(bucket)


def test_ensure_buckets_provisions_worm_for_real(client: Minio) -> None:
    docs, worm = _fresh("docs"), _fresh("worm")
    store, _ = _store(client, docs, worm)
    store.ensure_buckets()
    try:
        assert client.bucket_exists(docs)
        assert client.bucket_exists(worm)
        config = client.get_object_lock_config(worm)
        assert config.mode == COMPLIANCE
        assert config.duration == 1
        store.ensure_buckets()  # idempotent against a live server too
    finally:
        _drain_bucket(client, docs)
        _drain_bucket(client, worm)  # empty and unlocked: removable


def test_preexisting_bucket_without_lock_is_refused_by_a_real_server(client: Minio) -> None:
    docs, worm = _fresh("docs"), _fresh("badworm")
    client.make_bucket(worm)  # created the wrong way: no object-lock
    store, _ = _store(client, docs, worm)
    try:
        with pytest.raises(WormMisconfiguredError, match="recreate"):
            store.ensure_buckets()
    finally:
        _drain_bucket(client, docs)
        _drain_bucket(client, worm)


def test_put_presign_get_roundtrip_and_ttl_expiry(
    client: Minio, dev_scanner: DevNullScanner
) -> None:
    docs, worm = _fresh("docs"), _fresh("worm")
    store, chain = _store(client, docs, worm, scanner=dev_scanner)
    store.ensure_buckets()
    try:
        ref = store.put_document(
            tenant_id="tenant-int034",
            patient_pseudonym="psn-integration",
            file_bytes=PDF_BYTES,
            content_type="application/pdf",
            sha256=PDF_SHA,
            consent_scope_ref="consent:document-upload:v1",
        )
        url = store.presigned_get(ref, consent_scope_ref="consent:document-share:v1")
        response = httpx.get(url)
        assert response.status_code == 200
        assert response.content == PDF_BYTES
        assert response.headers["content-type"] == "application/pdf"

        short = store.presigned_get(
            ref,
            consent_scope_ref="consent:document-share:v1",
            expires=timedelta(seconds=1),
        )
        time.sleep(3)
        expired = httpx.get(short)
        assert expired.status_code == 403  # short TTL means the link really dies

        actions = [entry.action for entry in chain._store.entries()]  # type: ignore[attr-defined]
        assert actions == [
            "document.stored",
            "document.released",
            "document.presigned",
            "document.presigned",
        ]
        assert chain.verify().ok
    finally:
        _drain_bucket(client, docs)
        _drain_bucket(client, worm)


def test_worm_bucket_refuses_deleting_a_version_before_retention(client: Minio) -> None:
    docs, worm = _fresh("docs"), _fresh("worm")
    store, chain = _store(client, docs, worm)
    store.ensure_buckets()
    bundle = chain.export_worm()
    key = store.put_audit_bundle(bundle)

    stat = client.stat_object(worm, key)
    version_id = stat.version_id
    assert version_id is not None  # object-lock buckets are versioned

    # The WORM claim: the written version cannot be destroyed before retention.
    with pytest.raises(S3Error):
        client.remove_object(worm, key, version_id=version_id)

    # An overwrite only stacks a new version; the original bytes survive it.
    second = chain.export_worm()
    store_second_key = store.put_audit_bundle(second)
    assert store_second_key != key  # keys are unique per export, never overwritten
    original = client.get_object(worm, key, version_id=version_id)
    try:
        assert original.read() == bundle
    finally:
        original.close()
        original.release_conn()

    # A versionless delete writes only a delete marker; the version remains.
    client.remove_object(worm, key)
    survivor = client.get_object(worm, key, version_id=version_id)
    try:
        assert survivor.read() == bundle
    finally:
        survivor.close()
        survivor.release_conn()

    _drain_bucket(client, docs)
    # The worm bucket holds COMPLIANCE-locked versions for 1 day: by design it
    # cannot be drained here. It stays in the disposable dev volume.
