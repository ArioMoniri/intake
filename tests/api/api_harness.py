"""Unit-lane harness for services/api (INT-197 — owner-directive dev-tier slice).

The API is exercised through FastAPI's TestClient over the real INT-030
models. SQLite carries the schema for the unit lane the same way
tests/data/test_audit_store.py already carries ``audit_chain`` on SQLite:
the postgres-only surface (JSONB, ``gen_random_uuid()``/``now()`` server
defaults, BigInteger identity) is swapped for dialect-neutral equivalents in
a **DDL clone only** — the ORM statements the service issues are identical,
and the live DDL + RLS remain proven by the integration lane
(tests/api/test_api_postgres.py, tests/data/test_rls.py). The object store
is the INT-034 unit-lane fake; nothing here dials a network.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, create_app
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID, ensure_dev_fixture
from intake_api.documents import DocumentsConfig
from intake_api.settings import ApiSettings
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.db.models import (
    Base,
    Consent,
    IntakeSession,
    KvkkRole,
    Patient,
    SessionStatus,
    Slot,
    SlotSensitivity,
    Tenant,
)
from intake_platform.documents import ScanVerdict
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.uploads import ScanFailedError
from minio.commonconfig import COMPLIANCE
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    DefaultClause,
    Integer,
    MetaData,
    create_engine,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

PATIENT_TOKEN = "unit-lane-patient-token"
ADMIN_TOKEN = "unit-lane-admin-token"


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Drive an awaitable from a sync test (NullPool keeps connections
    loop-local, so mixing this with the TestClient's portal loop is safe)."""
    return asyncio.run(coro)


def sqlite_ddl_clone() -> MetaData:
    """Dialect-neutral copy of the INT-030 metadata for CREATE TABLE only."""
    clone = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(clone)
        for column in copied.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.primary_key and isinstance(column.type, BigInteger):
                column.type = Integer()
            if column.server_default is not None:
                if isinstance(column.type, DateTime):
                    column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
                else:
                    column.server_default = None
    return clone


class _LockConfig:
    mode = COMPLIANCE


class FakeObjectStorage:
    """In-memory ObjectStorageClient (mirrors the INT-034 unit-lane fake):
    real bucket/object state, so tests assert what ended up where."""

    def __init__(self) -> None:
        # bucket -> key -> (payload, content_type)
        self.buckets: dict[str, dict[str, tuple[bytes, str]]] = {}
        self.locked: set[str] = set()

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(
        self, bucket_name: str, location: str | None = None, object_lock: bool = False
    ) -> None:
        self.buckets[bucket_name] = {}
        if object_lock:
            self.locked.add(bucket_name)

    def get_object_lock_config(self, bucket_name: str) -> Any:
        assert bucket_name in self.locked, "lock config requested for an unlocked bucket"
        return _LockConfig()

    def set_object_lock_config(self, bucket_name: str, config: Any) -> None:
        self.locked.add(bucket_name)

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: Any,
        length: int,
        content_type: str = "application/octet-stream",
        sse: Any | None = None,
    ) -> object:
        self.buckets[bucket_name][object_name] = (data.read(), content_type)
        return object()

    def copy_object(self, bucket_name: str, object_name: str, source: Any) -> object:
        self.buckets[bucket_name][object_name] = self.buckets[source.bucket_name][
            source.object_name
        ]
        return object()

    def remove_object(
        self, bucket_name: str, object_name: str, version_id: str | None = None
    ) -> None:
        del self.buckets[bucket_name][object_name]

    def presigned_get_object(self, bucket_name: str, object_name: str, expires: Any = None) -> str:
        return f"https://minio.local/{bucket_name}/{object_name}?verb=GET"

    def presigned_put_object(self, bucket_name: str, object_name: str, expires: Any = None) -> str:
        return f"https://minio.local/{bucket_name}/{object_name}?verb=PUT"


class CleanScanner:
    def scan(self, data: bytes) -> ScanVerdict:
        return ScanVerdict.CLEAN


class InfectedScanner:
    def scan(self, data: bytes) -> ScanVerdict:
        return ScanVerdict.INFECTED


class UnreachableScanner:
    """A wired scanner that cannot reach clamd — the INT-120 client raises
    ScanFailedError for every no-verdict path (refused connection, timeout,
    ERROR reply, mid-stream close)."""

    def scan(self, data: bytes) -> ScanVerdict:
        raise ScanFailedError(
            "clamd is unreachable or the connection failed mid-scan; no verdict "
            "was produced, so the document stays quarantined (fail closed)"
        )


_DEFAULT_SCANNER: Any = object()


@dataclass
class ApiHarness:
    client: TestClient
    engine: AsyncEngine
    audit_store: SqlAlchemyAuditStore
    cipher: EnvelopeCipher
    settings: ApiSettings
    storage: FakeObjectStorage

    def patient(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {PATIENT_TOKEN}"}

    def admin(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    def revoke_consent(self, scope: str) -> None:
        async def _revoke() -> None:
            async with AsyncSession(self.engine) as session, session.begin():
                rows = (
                    await session.scalars(
                        select(Consent).where(
                            Consent.tenant_id == DEV_TENANT_ID,
                            Consent.patient_id == DEV_PATIENT_ID,
                            Consent.scope == scope,
                        )
                    )
                ).all()
                for row in rows:
                    row.revoked_at = datetime.now(UTC)

        run(_revoke())


def build_harness(
    tmp_path: Path,
    *,
    token_patient: str | None,
    token_admin: str | None,
    scanner: Any = _DEFAULT_SCANNER,
    legal_root: Path | None = None,
    legal_strings: Path | None = None,
    taxonomy_path: Path | None = None,
) -> Iterator[ApiHarness]:
    app_db = tmp_path / "api.db"
    audit_db = tmp_path / "audit.db"

    ddl_engine = create_engine(f"sqlite+pysqlite:///{app_db}")
    sqlite_ddl_clone().create_all(ddl_engine)
    ddl_engine.dispose()

    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    sqlite_ddl_clone().create_all(audit_engine)

    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    settings = ApiSettings(
        token_patient=token_patient,
        token_admin=token_admin,
        app_db_url=f"sqlite+aiosqlite:///{app_db}",
        audit_db_url=f"sqlite+pysqlite:///{audit_db}",
        bootstrap_db_url=f"sqlite+aiosqlite:///{app_db}",
        kek_mode="file-dev",
        # default: the pre-INT-210 state — no consent texts on disk, so the
        # catalog is empty and only the seeded (unbound) dev grants stand
        legal_root=legal_root if legal_root is not None else tmp_path / "legal-not-authored",
        # default: the pre-INT-210 state for the files/06 §7 fixed strings
        # too — everything that renders them fails closed (INT-037)
        legal_strings_path=(
            legal_strings
            if legal_strings is not None
            else tmp_path / "legal-not-authored" / "strings.yaml"
        ),
        # default: the REAL committed taxonomy (INT-134) — tests that need
        # the fail-closed path point this at a missing/broken file instead
        taxonomy_path=taxonomy_path
        if taxonomy_path is not None
        else Path(__file__).resolve().parents[2]
        / "packages"
        / "protocols"
        / "taxonomy"
        / "branches.yaml",
    )
    cipher = EnvelopeCipher(FileKekProvider())
    audit_store = SqlAlchemyAuditStore(audit_engine)
    storage = FakeObjectStorage()
    run(ensure_dev_fixture(engine))
    app = create_app(
        ApiWiring(
            settings=settings,
            engine=engine,
            audit_store=audit_store,
            cipher=cipher,
            bootstrap=False,
            documents=DocumentsConfig(
                client=storage,
                bucket_docs="intake-docs-unit",
                bucket_audit="intake-audit-unit",
                scanner=CleanScanner() if scanner is _DEFAULT_SCANNER else scanner,
            ),
        )
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield ApiHarness(
            client=client,
            engine=engine,
            audit_store=audit_store,
            cipher=cipher,
            settings=settings,
            storage=storage,
        )
    run(engine.dispose())
    audit_engine.dispose()


async def _seed_foreign_visit(engine: AsyncEngine) -> uuid.UUID:
    """A visit belonging to a DIFFERENT tenant, written straight to the DB —
    the API must never surface it (query-level isolation in the unit lane;
    RLS proves the same live in the integration lane)."""
    foreign_tenant = uuid.uuid4()
    foreign_patient = uuid.uuid4()
    session_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(
            Tenant(
                id=foreign_tenant,
                display_name="rls-foreign-unit",
                kvkk_role=KvkkRole.CONTROLLER,
            )
        )
        session.add(
            Patient(
                id=foreign_patient,
                tenant_id=foreign_tenant,
                pseudonym="dev." + uuid.uuid4().hex + uuid.uuid4().hex,
            )
        )
        session.add(
            IntakeSession(
                id=session_id,
                tenant_id=foreign_tenant,
                patient_id=foreign_patient,
                protocol_id="previsit.dev.visit",
                protocol_version="int197-dev",
                status=SessionStatus.CREATED,
                started_at=datetime.now(UTC),
            )
        )
        for slot_id, value in (
            ("visit.hospital", {"text": "Foreign Hospital"}),
            ("visit.department", {"text": "Foreign Department"}),
            ("visit.date", {"date": "2026-09-09"}),
        ):
            session.add(
                Slot(
                    tenant_id=foreign_tenant,
                    session_id=session_id,
                    slot_id=slot_id,
                    sensitivity=SlotSensitivity.PLAIN,
                    value=value,
                )
            )
    return session_id


def seed_foreign_visit(harness: ApiHarness) -> uuid.UUID:
    result: uuid.UUID = run(_seed_foreign_visit(harness.engine))
    return result
