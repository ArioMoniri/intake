"""INT-016 — the verifier job against a real object-locked bucket.

Runs under ``-m integration`` (``make check-integration``); the unit lane never
dials a network. Requires the compose ``minio`` service from
infra/docker-compose.dev.yml healthy on 127.0.0.1:9000.

The unit lane proves the job's *decisions* — which of the five tamper cases it
detects, and that it refuses to report green without an anchor. Only this lane
can answer the question the acceptance actually asks: **what enforces
write-once?** The answer is the S3 Object Lock the server applies, not
anything in our code, and the assertions below take it from the server:

- the bundle the verifier copied is byte-identical in the bucket and still
  self-verifies when read back with no store and no chain object at hand;
- the object version cannot be deleted before its retention expires — the
  server refuses, and that refusal is the whole WORM guarantee;
- a run whose chain is broken copies **nothing**, so a forged history is never
  written into a bucket it could not be removed from for ten years.

What this lane does *not* prove, and no lane in this repo does: that a
production deployment has such a bucket at all. files/08 §6 records the MinIO
vs Garage decision as open — Garage implements no S3 Object Lock and would
void this guarantee silently — and it is an open human decision
(files/HUMAN_BLOCKERS.md HB-I9).
"""

from __future__ import annotations

import dataclasses
import os
import uuid
from pathlib import Path

import pytest
from intake_platform.audit import AuditChain, AuditStore, InMemoryAuditStore, verify_worm_export
from intake_platform.audit_verifier import VerifierOutcome, run_daily_verification
from intake_platform.documents import DocumentStore, as_object_storage
from minio import Minio
from minio.error import S3Error

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client() -> Minio:
    return Minio(
        os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=os.environ.get("MINIO_ROOT_USER", "intake-dev"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "intake-dev-only"),
        secure=False,
    )


def _fresh(kind: str) -> str:
    return f"int016-{kind}-{uuid.uuid4().hex[:12]}"


def _sink(client: Minio, docs: str, worm: str, store: AuditStore) -> DocumentStore:
    """The archive side holds a chain writer on purpose: the WORM copy is
    itself an audited event (invariant 4). The verifier does not — it reads."""
    sink = DocumentStore(
        as_object_storage(client),
        docs,
        worm,
        AuditChain(store),
        audit_retention_days=1,  # COMPLIANCE cannot be shortened later, even by root
    )
    sink.ensure_buckets()
    return sink


def _stock(store: AuditStore, count: int) -> str:
    chain = AuditChain(store)
    for i in range(1, count + 1):
        chain.append(
            actor="svc-api",
            action="api.note.read",
            resource_ref=f"note:{i:04d}",
            consent_scope_ref="consent:visit-notes:v1",
        )
    return chain.head


class _Anchor:
    def __init__(self, head: str) -> None:
        self._head = head

    def anchored_head(self) -> str:
        return self._head


def test_the_verified_bundle_lands_in_the_locked_bucket_and_cannot_be_deleted(
    client: Minio,
) -> None:
    docs, worm = _fresh("docs"), _fresh("worm")
    store = InMemoryAuditStore()
    head = _stock(store, 4)
    sink = _sink(client, docs, worm, store)

    report = run_daily_verification(store, anchor=_Anchor(head), worm_sink=sink)
    assert report.outcome is VerifierOutcome.INTACT
    assert report.worm_key is not None

    response = client.get_object(worm, report.worm_key)
    try:
        stored = response.read()
    finally:
        response.close()
        response.release_conn()

    # Self-verifying from the bucket's own bytes: no store, no chain object.
    assert verify_worm_export(stored).ok

    stat = client.stat_object(worm, report.worm_key)
    assert stat.version_id is not None  # object-lock buckets are versioned
    with pytest.raises(S3Error):
        # This refusal, from the server, is what "write-once" means here.
        client.remove_object(worm, report.worm_key, version_id=stat.version_id)


def test_the_cli_archives_only_under_worm_copy_and_the_object_verifies(
    client: Minio, tmp_path: Path
) -> None:
    """``make audit-verify ANCHOR=... WORM=1`` end to end over a real DB store
    and a real locked bucket. The sink is injected so the bucket can carry a
    1-day retention: the CLI's own env constructor builds a 3650-day COMPLIANCE
    bucket (files/10 §3), which is correct in production and unremovable in a
    test volume — those four lines are exercised by the make target, not here."""
    from intake_platform.audit_verifier.cli import EXIT_OK, main
    from intake_platform.db.audit_store import AuditChainRow, SqlAlchemyAuditStore
    from intake_platform.db.models import Base
    from sqlalchemy import create_engine

    docs, worm = _fresh("docs"), _fresh("worm")
    url = f"sqlite+pysqlite:///{tmp_path / 'audit.sqlite3'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[AuditChainRow.__table__])
    db_store = SqlAlchemyAuditStore(engine)
    head = _stock(db_store, 3)
    sink = _sink(client, docs, worm, db_store)
    env = {"INTAKE_DATABASE_URL": url}

    # Without the flag nothing is archived, even with a sink in hand.
    assert main(["--anchor-head", head], env=env, worm_sink=sink) == EXIT_OK
    assert list(client.list_objects(worm, recursive=True)) == []

    assert main(["--anchor-head", head, "--worm-copy"], env=env, worm_sink=sink) == EXIT_OK
    (archived,) = list(client.list_objects(worm, recursive=True))
    assert archived.object_name is not None
    response = client.get_object(worm, archived.object_name)
    try:
        assert verify_worm_export(response.read()).ok
    finally:
        response.close()
        response.release_conn()
    engine.dispose()


def test_a_broken_chain_writes_nothing_into_a_bucket_it_could_never_be_removed_from(
    client: Minio,
) -> None:
    docs, worm = _fresh("docs"), _fresh("worm")
    store = InMemoryAuditStore()
    head = _stock(store, 4)
    sink = _sink(client, docs, worm, store)
    store._entries[1] = dataclasses.replace(  # noqa: SLF001
        store._entries[1], resource_ref="note:9999"
    )

    report = run_daily_verification(store, anchor=_Anchor(head), worm_sink=sink)

    assert report.outcome is VerifierOutcome.CHAIN_BROKEN
    assert report.first_bad_seq == 2
    assert report.worm_key is None
    assert list(client.list_objects(worm, recursive=True)) == []
