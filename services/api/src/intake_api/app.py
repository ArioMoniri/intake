"""App factory (INT-197) — the dev-tier API over the INT-030 schema.

EXPLICITLY the dev tier: auth is the two-account dev bearer
(:mod:`intake_api.auth`), every response carries ``X-Intake-Auth-Tier: dev``,
and real OIDC auth is INT-131. Everything else follows the platform
contracts: the four health endpoints and readiness checks come from
``intake_platform.health`` (invariant 15), request metrics from
``intake_platform.metrics`` (both families already catalogued), traces from
``intake_platform.otel.setup_otel``, security headers from
``intake_platform.security``. Logs carry ids only (invariant 6).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from intake_platform.audit import AuditStore
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.envelope import EnvelopeCipher, FileKekProvider, TransitKekProvider
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel
from intake_platform.secrets import SecretsProvider
from intake_platform.security import SecurityHeadersMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException as StarletteHTTPException

from intake_api import consents, documents, notes, otp_routes, taxonomy_routes, visits
from intake_api.audit import AuditWriter
from intake_api.auth import AUTH_TIER_HEADER
from intake_api.db import build_engine
from intake_api.dev_fixture import ensure_dev_fixture
from intake_api.documents import DocumentsConfig, DocumentsGateway
from intake_api.otp import AuthWiring, OtpAuthService, ensure_consumer_tenant
from intake_api.settings import ApiSettings
from intake_api.state import ApiState

__all__ = ["ApiWiring", "create_app", "wiring_from_env"]

logger = logging.getLogger("intake_api")

_otel_installed = False


def _setup_observability() -> None:
    """Shared OTel setup + JSON logging, once per process (invariant 15)."""
    global _otel_installed
    if _otel_installed:
        return
    setup_otel("api")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    _otel_installed = True


@dataclass
class ApiWiring:
    """Everything the app needs, injectable for tests; ``wiring_from_env``
    builds the real dev-tier stack."""

    settings: ApiSettings
    engine: AsyncEngine
    audit_store: AuditStore
    cipher: EnvelopeCipher
    bootstrap: bool = True
    bootstrap_engine: AsyncEngine | None = None
    documents: DocumentsConfig | None = None
    # INT-131: the OTP/DPoP tier; None = unconfigured (fail closed) while
    # the dev-bearer tier keeps carrying the demo
    auth: AuthWiring | None = None


def _cipher_from_settings(settings: ApiSettings) -> EnvelopeCipher:
    if settings.kek_mode == "file-dev":
        # process-local KEKs: notes do not survive a restart — acceptable
        # ONLY for throwaway local runs, which is why it must be asked for
        # explicitly (INTAKE_API_KEK_MODE=file-dev)
        return EnvelopeCipher(FileKekProvider())
    return EnvelopeCipher(TransitKekProvider(SecretsProvider.from_env()))


def _documents_from_env() -> DocumentsConfig:
    """The INT-034 seams from the compose dev tier. The scanner slot stays
    empty (ingest fails closed) unless the operator sets the INT-034 opt-in
    phrase INTAKE_DEV_ALLOW_UNSCANNED=explicit-yes; ClamAV is INT-120."""
    from intake_platform.documents import (
        DevNullScanner,
        DevScannerForbiddenError,
        Scanner,
        as_object_storage,
    )
    from minio import Minio

    scanner: Scanner | None
    try:
        scanner = DevNullScanner()
    except DevScannerForbiddenError:
        scanner = None
    client = Minio(
        os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=os.environ.get("MINIO_ROOT_USER", "intake-dev"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "intake-dev-only"),
        secure=os.environ.get("INTAKE_MINIO_SECURE", "") == "true",
    )
    return DocumentsConfig(
        client=as_object_storage(client),
        bucket_docs=os.environ.get("INTAKE_DOCS_BUCKET", "intake-docs"),
        bucket_audit=os.environ.get("INTAKE_AUDIT_BUCKET", "intake-audit-worm"),
        scanner=scanner,
    )


def _auth_from_settings(settings: ApiSettings) -> AuthWiring | None:
    """INT-131 wiring. No tokenization key → None → the OTP tier answers
    503 (fail closed) and the dev-bearer tier stays load-bearing. The
    attestation verifier is fail-closed unless the dev phrase is set, and
    the delivery adapter is the dev event logger — the SMS vendor contract
    is awaiting-human (docs/evidence/INT-131.md)."""
    if not settings.otp_auth_configured or settings.tokenization_key is None:
        return None
    from intake_platform.tokenization import Tokenizer
    from redis import Redis

    from intake_api.attestation import (
        DevStructuralAttestationVerifier,
        FailClosedAttestationVerifier,
    )
    from intake_api.otp import DevLogDeliveryAdapter

    return AuthWiring(
        redis_client=Redis.from_url(settings.redis_url),
        tokenizer=Tokenizer(
            keys={settings.tokenization_key_id: settings.tokenization_key.encode("utf-8")},
            active_key_id=settings.tokenization_key_id,
        ),
        delivery=DevLogDeliveryAdapter(),
        attestation=(
            DevStructuralAttestationVerifier()
            if settings.dev_allow_unattested
            else FailClosedAttestationVerifier()
        ),
        dev_otp_peek=settings.dev_otp_peek,
    )


def wiring_from_env() -> ApiWiring:
    settings = ApiSettings.from_env()
    return ApiWiring(
        settings=settings,
        engine=build_engine(settings.app_db_url),
        audit_store=SqlAlchemyAuditStore(create_engine(settings.audit_db_url)),
        cipher=_cipher_from_settings(settings),
        bootstrap=True,
        bootstrap_engine=build_engine(settings.bootstrap_db_url),
        documents=_documents_from_env(),
        auth=_auth_from_settings(settings),
    )


def create_app(wiring: ApiWiring | None = None) -> FastAPI:
    _setup_observability()
    w = wiring if wiring is not None else wiring_from_env()
    audit = AuditWriter(w.audit_store)
    state = ApiState(
        settings=w.settings,
        engine=w.engine,
        audit=audit,
        cipher=w.cipher,
        documents=DocumentsGateway(w.documents, audit) if w.documents is not None else None,
        auth=(OtpAuthService(w.auth, engine=w.engine, audit=audit) if w.auth is not None else None),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if w.bootstrap:
            try:
                await ensure_dev_fixture(w.engine, w.bootstrap_engine)
            except Exception:  # noqa: BLE001 — readiness reports the state; ids-only log
                logger.warning("dev fixture bootstrap deferred: database not ready")
            if w.auth is not None:
                try:
                    # INT-131: consumer tenant for real OTP accounts (tenant
                    # INSERT needs the owner engine, like the dev fixture)
                    await ensure_consumer_tenant(w.bootstrap_engine or w.engine)
                except Exception:  # noqa: BLE001 — readiness reports; ids-only log
                    logger.warning("consumer tenant bootstrap deferred: database not ready")
        yield

    app = FastAPI(title="intake-api", lifespan=lifespan)
    app.state.api = state
    app.state.settings = w.settings

    app.add_middleware(SecurityHeadersMiddleware)
    mount_http_metrics(app, "api")

    header_name, header_value = AUTH_TIER_HEADER

    @app.middleware("http")
    async def _tag_auth_tier(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        # honest tiering (INT-131): requests resolved through the OTP/DPoP
        # path set request.state.auth_tier = "otp"; everything else keeps
        # the INT-197 "dev" tag so nobody mistakes the tier they are on
        response.headers[header_name] = getattr(request.state, "auth_tier", header_value)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _machine_readable_errors(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return JSONResponse(detail, status_code=exc.status_code, headers=exc.headers)

    async def _db_ready() -> bool:
        async with w.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def _dev_auth_ready() -> bool:
        return w.settings.dev_auth_configured

    mount_health(
        app,
        readiness=[
            ReadinessCheck("db", _db_ready),
            ReadinessCheck("audit_store", state.audit.healthy),
            ReadinessCheck("dev_auth", _dev_auth_ready),
        ],
    )

    app.include_router(visits.router)
    app.include_router(notes.router)
    app.include_router(documents.router)
    app.include_router(otp_routes.router)
    app.include_router(consents.router)
    app.include_router(taxonomy_routes.router)
    return app
