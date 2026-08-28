"""INT-034 — signed-URL contract (the backlog row's named test path).

Acceptance, verbatim: "short-TTL signed URLs; server-side encryption;
object-lock on audit bucket; bucket policies least-privilege".

This file pins the *signed URL* half of that sentence — the TTL ceiling, the
short default, that every issued URL is an audited share (invariant 4), and
that no URL is ever issued for anything outside ``clean/``. The bucket/WORM/AV
halves live in tests/security/test_document_store.py and the integration lane.

The fake here is deliberately smaller than the one in test_document_store.py:
presigning never touches bucket administration, so this fake implements only
the object-facing slice of the protocol and the tests prove presigning needs
nothing more.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

import pytest
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.documents import (
    DEFAULT_PRESIGN_TTL,
    PRESIGN_TTL_CAP,
    DocumentStore,
    PresignTtlError,
    ScanVerdict,
)

DOCS_BUCKET = "intake-docs"
AUDIT_BUCKET = "intake-audit-worm"
PNG_BYTES = b"\x89PNG\r\n\x1a\n-unit-lane-pixels"
PNG_SHA = hashlib.sha256(PNG_BYTES).hexdigest()
SHARE_SCOPE = "consent:document-share:v1"
UPLOAD_SCOPE = "consent:document-upload:v1"


class PresignOnlyFake:
    """Object-facing slice of the storage protocol: put/copy/remove/presign."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.presigned: list[tuple[str, str, str, timedelta]] = []

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        sse: object | None = None,
    ) -> object:
        self.objects[(bucket_name, object_name)] = data.read()
        return object()

    def copy_object(self, bucket_name: str, object_name: str, source: object) -> object:
        src = (source.bucket_name, source.object_name)  # type: ignore[attr-defined]
        self.objects[(bucket_name, object_name)] = self.objects[src]
        return object()

    def remove_object(
        self, bucket_name: str, object_name: str, version_id: str | None = None
    ) -> None:
        del self.objects[(bucket_name, object_name)]

    def presigned_get_object(
        self, bucket_name: str, object_name: str, expires: timedelta = timedelta(days=7)
    ) -> str:
        self.presigned.append(("GET", bucket_name, object_name, expires))
        return f"https://minio.local/{bucket_name}/{object_name}?X-Amz-Expires={int(expires.total_seconds())}"

    def presigned_put_object(
        self, bucket_name: str, object_name: str, expires: timedelta = timedelta(days=7)
    ) -> str:
        self.presigned.append(("PUT", bucket_name, object_name, expires))
        return f"https://minio.local/{bucket_name}/{object_name}?upload&X-Amz-Expires={int(expires.total_seconds())}"


class AlwaysClean:
    def scan(self, data: bytes) -> ScanVerdict:
        return ScanVerdict.CLEAN


def _clock() -> datetime:
    return datetime(2026, 8, 28, 9, 0, 0, tzinfo=UTC)


def _store() -> tuple[DocumentStore, PresignOnlyFake, AuditChain]:
    fake = PresignOnlyFake()
    chain = AuditChain(InMemoryAuditStore(), clock=_clock)
    store = DocumentStore(
        fake,  # type: ignore[arg-type]
        DOCS_BUCKET,
        AUDIT_BUCKET,
        chain,
        scanner=AlwaysClean(),
        clock=_clock,
    )
    return store, fake, chain


def _clean_ref(store: DocumentStore) -> object:
    return store.put_document(
        tenant_id="tenant-izmir",
        patient_pseudonym="psn-11aa",
        file_bytes=PNG_BYTES,
        content_type="image/png",
        sha256=PNG_SHA,
        consent_scope_ref=UPLOAD_SCOPE,
    )


# --- TTL contract ------------------------------------------------------------------


def test_the_default_ttl_is_five_minutes() -> None:
    assert DEFAULT_PRESIGN_TTL == timedelta(seconds=300)
    store, fake, _ = _store()
    ref = _clean_ref(store)
    url = store.presigned_get(ref, consent_scope_ref=SHARE_SCOPE)  # type: ignore[arg-type]
    verb, _, _, expires = fake.presigned[-1]
    assert verb == "GET"
    assert expires == timedelta(seconds=300)
    assert "X-Amz-Expires=300" in url


def test_the_ceiling_is_fifteen_minutes_inclusive() -> None:
    assert PRESIGN_TTL_CAP == timedelta(minutes=15)
    store, fake, _ = _store()
    ref = _clean_ref(store)
    url = store.presigned_get(
        ref,
        consent_scope_ref=SHARE_SCOPE,
        expires=timedelta(minutes=15),  # type: ignore[arg-type]
    )
    assert "X-Amz-Expires=900" in url
    assert fake.presigned[-1][3] == timedelta(minutes=15)


@pytest.mark.parametrize(
    "too_long",
    [timedelta(minutes=15, seconds=1), timedelta(hours=1), timedelta(days=7)],
)
def test_a_ttl_above_the_ceiling_is_refused_not_clamped(too_long: timedelta) -> None:
    store, fake, chain = _store()
    ref = _clean_ref(store)
    presigns_before = len(fake.presigned)
    entries_before = len(chain._store.entries())  # type: ignore[attr-defined]
    with pytest.raises(PresignTtlError, match="15"):
        store.presigned_get(ref, consent_scope_ref=SHARE_SCOPE, expires=too_long)  # type: ignore[arg-type]
    with pytest.raises(PresignTtlError):
        store.presigned_put(
            "tenant-izmir", "psn-11aa", consent_scope_ref=UPLOAD_SCOPE, expires=too_long
        )
    # refused means refused: no URL was minted and no share was recorded
    assert len(fake.presigned) == presigns_before
    assert len(chain._store.entries()) == entries_before  # type: ignore[attr-defined]


@pytest.mark.parametrize("degenerate", [timedelta(0), timedelta(seconds=-30)])
def test_zero_or_negative_ttls_are_refused(degenerate: timedelta) -> None:
    store, _, _ = _store()
    ref = _clean_ref(store)
    with pytest.raises(PresignTtlError):
        store.presigned_get(ref, consent_scope_ref=SHARE_SCOPE, expires=degenerate)  # type: ignore[arg-type]


# --- every URL is an audited share ---------------------------------------------------


def test_each_issued_url_appends_one_share_entry_naming_key_not_url() -> None:
    store, _, chain = _store()
    ref = _clean_ref(store)
    store.presigned_get(ref, consent_scope_ref=SHARE_SCOPE)  # type: ignore[arg-type]
    store.presigned_get(ref, consent_scope_ref=SHARE_SCOPE)  # type: ignore[arg-type]
    entries = chain._store.entries()  # type: ignore[attr-defined]
    shares = [e for e in entries if e.action == "document.presigned"]
    assert len(shares) == 2
    for entry in shares:
        assert entry.resource_ref == ref.key  # type: ignore[attr-defined]
        assert entry.consent_scope_ref == SHARE_SCOPE
    assert chain.verify().ok


def test_presigned_put_mints_an_upload_slot_in_quarantine() -> None:
    store, fake, chain = _store()
    upload = store.presigned_put("tenant-izmir", "psn-11aa", consent_scope_ref=UPLOAD_SCOPE)
    assert upload.key.startswith("quarantine/tenant-izmir/psn-11aa/")
    verb, bucket, key, expires = fake.presigned[-1]
    assert (verb, bucket, key) == ("PUT", DOCS_BUCKET, upload.key)
    assert expires == DEFAULT_PRESIGN_TTL
    assert upload.url.startswith("https://")
    entries = chain._store.entries()  # type: ignore[attr-defined]
    assert entries[-1].action == "document.presigned"
    assert entries[-1].resource_ref == upload.key
