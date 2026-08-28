"""INT-120 — upload pipeline integration lane: real clamd + real MinIO.

Runs under ``-m integration`` (``make check-integration``; the unit lane
never dials a network). Requires the compose ``clamav`` profile service from
infra/docker-compose.dev.yml healthy on 127.0.0.1:3310 and the ``minio``
service on 127.0.0.1:9000 (dev-only root credentials).

What only this lane can prove:

- a real clamd speaks the INSTREAM protocol our thin client implements:
  PING answers, a clean payload comes back OK, and the EICAR test file comes
  back FOUND from the image's baked-in signature database;
- the full INT-034 → INT-120 handoff: a presigned PUT lands bytes under
  ``quarantine/`` with whatever content type the uploader claimed, the
  worker sniffs/limits/scans/promotes, and the promoted object serves over a
  presigned GET with the *canonical* content type, not the uploader's claim.

The EICAR string is assembled from two halves so this source file itself
never contains the contiguous signature (desktop AV quarantining the repo is
a real failure mode). ClamAV's EICAR signature hashes the whole file, so the
verdict test feeds the scanner exactly the 68-byte payload.

Buckets are freshly named per run (``int120-*``). As in the INT-034 lane,
the WORM audit bucket cannot be drained before its 1-day retention expires;
it stays in the disposable dev volume.
"""

from __future__ import annotations

import hashlib
import os
import uuid

import httpx
import pytest
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.documents import (
    DocumentState,
    DocumentStore,
    ScanVerdict,
    as_object_storage,
)
from intake_platform.uploads import ClamAvScanner, UploadPipeline
from minio import Minio

pytestmark = pytest.mark.integration

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$" + rb"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@pytest.fixture(scope="module")
def scanner() -> ClamAvScanner:
    return ClamAvScanner(
        host=os.environ.get("INTAKE_CLAMD_HOST", "127.0.0.1"),
        port=int(os.environ.get("INTAKE_CLAMD_PORT", "3310")),
        timeout_seconds=120,  # a cold clamd can be slow on its first scans
    )


@pytest.fixture(scope="module")
def client() -> Minio:
    return Minio(
        os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=os.environ.get("MINIO_ROOT_USER", "intake-dev"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "intake-dev-only"),
        secure=False,
    )


def _fresh(kind: str) -> str:
    return f"int120-{kind}-{uuid.uuid4().hex[:12]}"


def _drain_bucket(client: Minio, bucket: str) -> None:
    for obj in client.list_objects(bucket, recursive=True):
        if obj.object_name is not None:
            client.remove_object(bucket, obj.object_name)
    client.remove_bucket(bucket)


def test_real_clamd_answers_ping(scanner: ClamAvScanner) -> None:
    assert scanner.ping() is True


def test_real_clamd_clean_verdict(scanner: ClamAvScanner) -> None:
    assert scanner.scan(PDF_BYTES) is ScanVerdict.CLEAN


def test_real_clamd_finds_eicar(scanner: ClamAvScanner) -> None:
    assert scanner.scan(EICAR) is ScanVerdict.INFECTED


def test_presigned_upload_scan_promote_serve_roundtrip(
    client: Minio, scanner: ClamAvScanner
) -> None:
    docs, worm = _fresh("docs"), _fresh("worm")
    chain = AuditChain(InMemoryAuditStore())
    store = DocumentStore(
        as_object_storage(client),
        docs,
        worm,
        chain,
        audit_retention_days=1,  # COMPLIANCE cannot be shortened later, even by root
    )
    store.ensure_buckets()
    try:
        slot = store.presigned_put(
            "tenant-int120",
            "psn-integration",
            consent_scope_ref="consent:document-upload:v1",
        )
        # The uploader claims octet-stream; promotion must rewrite it.
        upload = httpx.put(
            slot.url,
            content=PDF_BYTES,
            headers={"content-type": "application/octet-stream"},
        )
        assert upload.status_code == 200

        pipeline = UploadPipeline(store, scanner)
        outcome = pipeline.process(
            "tenant-int120",
            "psn-integration",
            slot.document_id,
            claimed_content_type="application/pdf",
            consent_scope_ref="consent:document-upload:v1",
        )
        assert outcome.state is DocumentState.CLEAN
        ref = outcome.ref
        assert ref is not None
        assert ref.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()

        # Idempotency against a real store: a second pass is a no-op.
        second = pipeline.process(
            "tenant-int120",
            "psn-integration",
            slot.document_id,
            claimed_content_type="application/pdf",
            consent_scope_ref="consent:document-upload:v1",
        )
        assert second.already_processed is True

        url = store.presigned_get(ref, consent_scope_ref="consent:document-share:v1")
        served = httpx.get(url)
        assert served.status_code == 200
        assert served.content == PDF_BYTES
        assert served.headers["content-type"] == "application/pdf"  # canonical, not claimed

        actions = [entry.action for entry in chain._store.entries()]  # type: ignore[attr-defined]
        assert actions == [
            "document.presigned",  # the upload slot
            "document.scan_read",  # the worker's read for the verdict
            "document.released",  # promotion
            "document.presigned",  # the share
        ]
        assert chain.verify().ok
    finally:
        _drain_bucket(client, docs)
        # The worm bucket holds COMPLIANCE-locked audit copies for 1 day; by
        # design it cannot be drained here (same posture as the INT-034 lane).
