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

import asyncio
import contextlib
import json
import logging
import os
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from intake_platform.admin import AdminWiring, IpAllowList
from intake_platform.admin.access import ConsoleSystemsRefused, IdentityWiring
from intake_platform.admin.access.config import (
    ENV_KEYCLOAK_URL,
    IdentityUnconfigured,
    identity_from_env,
)
from intake_platform.admin.oidc import KeycloakClaimsVerifier, load_jwks
from intake_platform.audit import AuditStore
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.envelope import EnvelopeCipher, FileKekProvider, TransitKekProvider
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.model_lanes.wiring import ModelLanesWiring, model_lanes_from_env
from intake_platform.otel import JsonLogFormatter, setup_otel
from intake_platform.release_freeze import release_freeze_store_from_env
from intake_platform.safety_inbox import (
    PUMP_INTERVAL,
    SafetyInbox,
    SafetyInboxOutbox,
    mark_inbox_unreadable,
    safety_inbox_store_from_env,
    sweep_forever,
)
from intake_platform.secrets import SecretsBootError, SecretsProvider
from intake_platform.security import SecurityHeadersMiddleware
from intake_platform.voice_control import VoiceControlStore, voice_control_store_from_env
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException as StarletteHTTPException

from intake_api import (
    admin,
    consents,
    dev_voice,
    doctor_link,
    documents,
    dsar,
    embed,
    experience,
    learned,
    notes,
    notification_prefs,
    otp_routes,
    previsit_output,
    profile_routes,
    record_items,
    red_notify,
    satisfaction,
    taxonomy_routes,
    triage_hop,
    visit_lifecycle,
    visits,
    visits_acibadem,
)
from intake_api.audit import AuditWriter
from intake_api.auth import AUTH_TIER_HEADER
from intake_api.db import build_engine
from intake_api.dev_fixture import ensure_dev_fixture
from intake_api.dev_voice import GeorgeWiring, george_wiring_from_env
from intake_api.dev_voice_guard import george_route_mountable
from intake_api.doctor_link.common import NOINDEX
from intake_api.doctor_link.service import (
    DoctorLinkService,
    DoctorLinkWiring,
    FailClosedDoctorLinkDelivery,
)
from intake_api.documents import DocumentsConfig, DocumentsGateway
from intake_api.embed import EmbedService, EmbedWiring
from intake_api.otp import AuthWiring, OtpAuthService, ensure_consumer_tenant
from intake_api.settings import ENV_MINIO_PASSWORD, ENV_MINIO_USER, ApiSettings
from intake_api.state import ApiState

if TYPE_CHECKING:
    from intake_connectors.acibadem import AcibademAppointmentsClient
    from redis import Redis

    from intake_api.app_attest import AppAttestVerifier
    from intake_api.attestation import FailClosedAttestationVerifier
    from intake_api.otp_netgsm import KvSecrets

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
    # INT-180: the admin console. None = unconfigured, so every /admin route
    # answers 503 and the console authenticates nobody (fail closed).
    admin: AdminWiring | None = None
    # INT-320: the partner white-label embed handshake (ADR-028). None =
    # unconfigured, so every /embed route answers 503 (fail closed).
    embed: EmbedWiring | None = None
    # ADR-028 (on-demand variant): the DEV George clip route. None =
    # unconfigured (no dev flag / no key), so /dev/voice/george-clip answers
    # 503 and the mobile falls back to the self-hosted TTS (fail closed).
    george: GeorgeWiring | None = None
    # INT-318: the Acıbadem appointments read client, built from the one row
    # infra/connectors/sources.yaml registers for it and from nothing else.
    # None = no row (the shipped state), so /v1/visits/sync answers
    # "unavailable" (fail closed).
    acibadem: AcibademAppointmentsClient | None = None
    # INT-407: the clinic Safety inbox a RED visit's reschedule or cancel
    # raises its entry in (files/02 §2b). None = unwired: those two moves
    # answer 503 rather than happen silently.
    safety_inbox: SafetyInbox | None = None


def _cipher_from_settings(settings: ApiSettings) -> EnvelopeCipher:
    if settings.kek_mode == "file-dev":
        # process-local KEKs: notes do not survive a restart — acceptable
        # ONLY for throwaway local runs, which is why it must be asked for
        # explicitly (INTAKE_API_KEK_MODE=file-dev)
        return EnvelopeCipher(FileKekProvider())
    return EnvelopeCipher(TransitKekProvider(SecretsProvider.from_env()))


def _documents_from_env() -> DocumentsConfig:
    """The INT-034 seams from the compose dev tier.

    Scanner precedence, strongest first (INT-238): the INT-120 ClamAV client
    whenever a clamd endpoint is configured, then the INT-034 dev stub behind
    its opt-in phrase INTAKE_DEV_ALLOW_UNSCANNED=explicit-yes, then nothing —
    and nothing means ingest fails closed. The real scanner is checked FIRST
    so the dev stub can never shadow a live clamd and quietly turn a verdict
    into an assumption. Before this order existed the slot only ever held the
    stub, so on the documented dev stack — which starts a healthy ClamAV on
    3310 — every upload answered 503 scan_not_configured.
    """
    from intake_platform.documents import (
        DevNullScanner,
        DevScannerForbiddenError,
        Scanner,
        as_object_storage,
    )
    from intake_platform.uploads import ClamAvScanner, ClamdNotConfiguredError
    from minio import Minio

    scanner: Scanner | None
    try:
        scanner = ClamAvScanner.from_env()
    except ClamdNotConfiguredError:
        try:
            scanner = DevNullScanner()
        except DevScannerForbiddenError:
            scanner = None
    # the dev defaults below never apply outside dev: ApiSettings.from_env
    # has already refused a non-dev boot with either variable absent (INT-325)
    client = Minio(
        os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=os.environ.get(ENV_MINIO_USER, "intake-dev"),
        secret_key=os.environ.get(ENV_MINIO_PASSWORD, "intake-dev-only"),
        secure=os.environ.get("INTAKE_MINIO_SECURE", "") == "true",
    )
    return DocumentsConfig(
        client=as_object_storage(client),
        bucket_docs=os.environ.get("INTAKE_DOCS_BUCKET", "intake-docs"),
        bucket_audit=os.environ.get("INTAKE_AUDIT_BUCKET", "intake-audit-worm"),
        scanner=scanner,
    )


def _app_attest_from_settings(
    settings: ApiSettings, redis_client: Redis
) -> AppAttestVerifier | FailClosedAttestationVerifier:
    """INT-344. No team id → fail closed, typed. A malformed team id, bundle id
    or environment word — or a trust anchor that is not the pinned Apple root —
    also fails closed, with its own reason and one log line naming no value."""
    from intake_api.app_attest import AppAttestConfig, AppAttestConfigError, AppAttestVerifier
    from intake_api.app_attest_store import RedisAppAttestKeyStore
    from intake_api.attestation import AttestationReason, FailClosedAttestationVerifier

    if settings.app_attest_team_id is None:
        return FailClosedAttestationVerifier(AttestationReason.APP_ATTEST_NOT_CONFIGURED)
    try:
        config = AppAttestConfig.parse(
            settings.app_attest_team_id,
            settings.app_attest_bundle_id,
            settings.app_attest_environment,
        )
        return AppAttestVerifier(config, RedisAppAttestKeyStore(redis_client))
    except AppAttestConfigError:
        logger.warning("app attest configuration refused; iOS attestation fails closed")
        return FailClosedAttestationVerifier(AttestationReason.APP_ATTEST_CONFIG_INVALID)


def _auth_from_settings(
    settings: ApiSettings, secrets: KvSecrets | None = None
) -> AuthWiring | None:
    """INT-131 wiring. No tokenization key → None → the OTP tier answers
    503 (fail closed) and the dev-bearer tier stays load-bearing. Attestation
    routes by mode (INT-344): App Attest when the Apple team id is configured,
    Play Integrity never until HB-A3 supplies a decoder, the dev tier only
    under the dev phrase — every unconfigured piece fails closed with a typed
    reason. Delivery (INT-329, INT-528): the dev logger in dev; outside dev
    Netgsm or nothing, never the dev logger (INT-325) — see otp_netgsm. ``secrets`` is
    the OpenBao reader, injectable for tests. The pepper (INT-578): OpenBao
    ``secret/api/otp``, read after the delivery adapter so a tier that cannot
    send pulls no key; only dev under file-dev KEKs takes a process-local one."""
    if not settings.otp_auth_configured or settings.tokenization_key is None:
        return None
    from intake_api.otp_netgsm import NetgsmSmsDeliveryAdapter, otp_delivery_from_settings
    from intake_api.sms_recipients import ADMIT_ALL

    if (delivery := otp_delivery_from_settings(settings, secrets)) is None:
        return None
    from intake_api.otp_pepper import OtpPepper, otp_pepper_from_vault

    if settings.kek_mode == "file-dev" and settings.dev_tier_expected:
        # the no-OpenBao dev escape, refused at boot outside dev (INT-325):
        # process-local, like the file-dev KEKs
        pepper: OtpPepper | None = OtpPepper.ephemeral()
    else:
        pepper = otp_pepper_from_vault(secrets)
    if pepper is None:
        return None
    # INT-528: the synthetic host's test allow-list gates the login as well as
    # the send, so a number off it never has a code minted
    recipients = (
        delivery.recipients if isinstance(delivery, NetgsmSmsDeliveryAdapter) else ADMIT_ALL
    )
    from intake_platform.tokenization import Tokenizer
    from redis import Redis

    from intake_api.attestation import (
        AttestationReason,
        DevStructuralAttestationVerifier,
        FailClosedAttestationVerifier,
        PlatformAttestationVerifier,
    )
    from intake_api.carrier_geo import carrier_geo_from_path

    redis_client = Redis.from_url(settings.redis_url)
    app_attest = _app_attest_from_settings(settings, redis_client)
    return AuthWiring(
        redis_client=redis_client,
        tokenizer=Tokenizer(
            keys={settings.tokenization_key_id: settings.tokenization_key.encode("utf-8")},
            active_key_id=settings.tokenization_key_id,
        ),
        delivery=delivery,
        attestation=PlatformAttestationVerifier(
            app_attest=app_attest,
            # HB-A3: no decoder exists until the Play Console organisation account
            # and its service account do (intake_api.play_integrity)
            play_integrity=FailClosedAttestationVerifier(
                AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED
            ),
            dev=DevStructuralAttestationVerifier() if settings.dev_allow_unattested else None,
        ),
        key_attestation=app_attest,
        dev_otp_peek=settings.dev_otp_peek,
        # INT-308: files/10 §2's carrier/geo check. The committed table
        # declares no prefixes, so this admits every request and says so in
        # one log line at wiring time.
        carrier_geo=carrier_geo_from_path(settings.msisdn_allocation_path),
        recipients=recipients,
        pepper=pepper,
    )


def _doctor_link_service(auth: AuthWiring | None) -> DoctorLinkService | None:
    """INT-150. The Doctor Link tier rides the OTP tier's Redis, because it
    rides the OTP tier's GATE — one abuse budget, one code store, one place to
    fix. No Redis (``auth is None``) means the whole surface answers 503 rather
    than issuing links whose opening code nobody could check.

    The delivery adapter is the fail-closed one: files/10 §2 sends the code to
    the phone or e-mail the patient chose, this repo records no such
    destination and no vendor is contracted, and a stub that returned a receipt
    would be a mock standing in for a control (invariant 17).
    """
    if auth is None:
        return None
    return DoctorLinkService(
        DoctorLinkWiring(
            redis_client=auth.redis_client,
            delivery=FailClosedDoctorLinkDelivery(),
            dev_otp_peek=auth.dev_otp_peek,
            now_fn=auth.now_fn,
        )
    )


def _admin_from_env() -> AdminWiring | None:
    """INT-180. All three of issuer, audience and a mirrored JWKS, or nothing.

    The JWKS is read from a FILE rather than fetched from Keycloak's
    well-known endpoint on purpose: the most privileged surface in the system
    should not answer 503 because an identity provider is briefly unreachable,
    key rotation should be a deploy with a diff, and CI must never dial a live
    service. Any of the three absent, or a key set that carries no usable
    signing key, leaves the console unconfigured — every /admin route answers
    503 rather than admitting anyone.

    The IP allow-list (files/08 §2.3) ships EMPTY, which admits nobody. No
    file in this repository names an office range, a VPN egress or a bastion,
    and a plausible address here would look configured while being wrong
    (invariant 17).
    """
    issuer = os.environ.get("INTAKE_ADMIN_OIDC_ISSUER", "")
    audience = os.environ.get("INTAKE_ADMIN_OIDC_AUDIENCE", "")
    jwks_path = os.environ.get("INTAKE_ADMIN_OIDC_JWKS_PATH", "")
    if not (issuer and audience and jwks_path):
        return None
    try:
        keys = load_jwks(json.loads(Path(jwks_path).read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError):
        # ids only, and never the path's contents (invariant 6)
        logger.warning("admin console unconfigured: the JWKS mirror is absent or unusable")
        return None
    try:
        # INT-182: the store the voice runtime reads the kill switch from.
        # Unset, the voice controls answer 503 rather than writing somewhere
        # the runtime is not reading; a malformed URL is the same, loudly.
        voice_controls = voice_control_store_from_env(os.environ)
    except ValueError:
        logger.warning("voice controls unconfigured: the store URL is not a redis URL")
        voice_controls = None
    try:
        # INT-187: the deployment's deploy-freeze record, which deploy.sh's
        # release gate reads too. Unset or malformed, the freeze controls
        # answer 503 and the console shows the gate refusing — never "open".
        release_freeze = release_freeze_store_from_env(os.environ)
    except ValueError:
        logger.warning("deploy freeze unconfigured: the store URL is not a redis URL")
        release_freeze = None
    return AdminWiring(
        claims=KeycloakClaimsVerifier(issuer=issuer, audience=audience, keys=keys),
        ip_allowlist=IpAllowList.from_spec(os.environ.get("INTAKE_ADMIN_IP_ALLOWLIST", "")),
        voice_controls=voice_controls,
        release_freeze=release_freeze,
        identity=_identity_from_env(),
        safety_inbox=_safety_inbox_from_env(),
        model_lanes=_model_lanes_from_env(voice_controls),
    )


def _safety_inbox_from_env() -> SafetyInbox | None:
    """INT-406: the clinic Safety inbox, from the store the voice runtime
    writes. Unset or malformed, the Safety queue answers 503 and the inbox is
    reported unreadable at boot, which pages (fail closed, never a default
    address). The SLA is files/02 §8.2's default; no tenant SLA is set here."""
    try:
        store = safety_inbox_store_from_env(os.environ)
    except ValueError:
        logger.warning("safety inbox unconfigured: the store URL is not a redis URL")
        return None
    return SafetyInbox(store=store) if store is not None else None


def _model_lanes_from_env(voice_controls: VoiceControlStore | None) -> ModelLanesWiring | None:
    """INT-428 (ADR-035): the model-lane control store, the router and the
    hosted adapters. No ``INTAKE_MODEL_LANES_REDIS_URL`` leaves the module
    unconfigured — its mutations answer 503 and its tiles read unknown. The
    INT-182 voice kill switch, when wired, disables hosted lanes for its
    tenant; an unreadable one reads as engaged (fail closed). A policy file
    that does not load (the allow-list, the provider catalogue, the transfer
    bases) leaves the module unconfigured rather than half-built."""
    kill_switch = None
    if voice_controls is not None:
        store = voice_controls

        def kill_switch(tenant_id: str) -> bool:
            return store.read(tenant_id).kill_switch

    try:
        return model_lanes_from_env(
            os.environ, kv=SecretsProvider.from_env, kill_switch=kill_switch
        )
    except (OSError, ValueError) as err:
        # the class name says what failed; no path or value is logged
        logger.warning("model lanes unconfigured: %s", type(err).__name__)
        return None


def _identity_from_env() -> IdentityWiring | None:
    """INT-366: Keycloak and OpenBao admin access for the access review and
    offboarding. Any fact absent — the Keycloak origin or realm, the OpenBao
    auth mount, the admin client in OpenBao KV, or a loadable console-systems
    file — leaves both answering 503 (fail closed). The §2.7 read-only
    downgrade does not depend on this: it reads the audit chain."""
    if not os.environ.get(ENV_KEYCLOAK_URL):
        return None
    try:
        return identity_from_env(os.environ, SecretsProvider.from_env())
    except (SecretsBootError, IdentityUnconfigured, ConsoleSystemsRefused, httpx.HTTPError) as err:
        # the exception class names what is missing; no value is logged
        logger.warning("access review unconfigured: %s", type(err).__name__)
        return None


def _embed_from_settings(settings: ApiSettings) -> EmbedWiring | None:
    """INT-320 (ADR-028). The embed handshake needs a registry, a launch base
    URL and an OpenBao-backed signing-key resolver. Any of the three absent —
    no launch URL, an unloadable registry, or secrets not configured — leaves
    the surface unconfigured: every /embed route answers 503 rather than
    minting a ticket nobody could verify. The signing key is read from OpenBao
    only (invariant 14); it is never defaulted or read from the environment.
    """
    if not settings.embed_launch_base_url:
        return None
    from intake_platform.consent.texts import ConsentTextCatalog
    from intake_platform.embed import InMemoryNonceStore, TenantEmbedRegistry

    from intake_api.embed import OpenBaoSigningKeys

    try:
        registry = TenantEmbedRegistry.from_yaml(settings.embed_registry_path)
        secrets = SecretsProvider.from_env()
    except Exception:  # noqa: BLE001 — ids-only log; fail closed on any config gap
        logger.warning("embed unconfigured: registry absent/invalid or secrets not configured")
        return None
    return EmbedWiring(
        registry=registry,
        signing_keys=OpenBaoSigningKeys(secrets),
        launch_base_url=settings.embed_launch_base_url,
        # dev/single-replica store; a shared store (Redis) is required for
        # multi-replica single-use and is awaiting-human, not stubbed here
        nonce_store=InMemoryNonceStore(),
        # INT-320 (follow-up): the consent render reads ``core`` from the SAME
        # global tree the grant binds against (settings.legal_root), and each
        # tenant's partner-processor disclosure from its own ``legal_root``
        # under the legal base (the parent of the global consents dir — in dev
        # the ~/.config/intake/dev-legal tree, in prod docs/legal).
        consent_catalog=ConsentTextCatalog(settings.legal_root),
        legal_base=settings.legal_root.parent,
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
        admin=_admin_from_env(),
        embed=_embed_from_settings(settings),
        # INT-443: on the synthetic host the vendor key comes from OpenBao
        george=george_wiring_from_env(redis_url=settings.redis_url, kv=SecretsProvider.from_env),
        acibadem=visits_acibadem.acibadem_client_from_registry(settings.clinical_sources_path),
        # INT-407: the same store the console's queue reads and the voice
        # runtime writes (INTAKE_SAFETY_INBOX_REDIS_URL)
        safety_inbox=_safety_inbox_from_env(),
    )


@dataclass(frozen=True)
class _RedPump:
    """INT-475: the thread writing the RED path's outbox into the shared store."""

    outbox: SafetyInboxOutbox
    thread: threading.Thread

    @classmethod
    def start(cls, state: ApiState) -> _RedPump | None:
        """No inbox, no pump: a hop RED then counts a route failure, which pages."""
        if state.red_outbox is None or state.safety_inbox is None:
            return None
        thread = threading.Thread(
            target=state.red_outbox.pump,
            args=(state.safety_inbox.store,),
            name="safety-inbox-pump",
            daemon=True,
        )
        thread.start()
        return cls(outbox=state.red_outbox, thread=thread)

    def stop(self) -> None:
        """One last pass; what the store still refuses is counted, never named."""
        self.outbox.stop()
        self.thread.join(timeout=PUMP_INTERVAL.total_seconds() * 5)
        left = len(self.outbox.pending())
        if left:
            # a count only (invariant 6); the entries' age already pages
            logger.error("safety inbox entries unwritten at stop", extra={"count": left})


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
        doctor_link=_doctor_link_service(w.auth),
        embed=EmbedService(w.embed, audit) if w.embed is not None else None,
        acibadem=w.acibadem,
        safety_inbox=w.safety_inbox,
        # INT-475: the RED path's outbox, wired exactly when the inbox is
        red_outbox=SafetyInboxOutbox() if w.safety_inbox is not None else None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if w.bootstrap:
            # INT-421 (owner, 27 Sep 2026: "in production don't include deneme
            # hastası"): the synthetic dev tenant, patient and consents are the
            # dev environment's only. Anywhere else nothing is seeded, and what
            # earlier boots left is removed by intake_api.dev_fixture_retire.
            if w.settings.dev_tier_expected:
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
        if w.admin is not None:
            # INT-366: read the review state off the chain at start, so the
            # review-age gauge is not +Inf until the first admin request.
            try:
                await w.admin.review_ledger.refresh(audit)
            except Exception:  # noqa: BLE001 — the gauge stays +Inf and pages; ids-only log
                logger.warning("access review ledger deferred: audit chain not readable")
        # INT-406, invariant 49: the scheduled checker. Wired, it recomputes
        # the unacknowledged-RED gauge every sweep interval for as long as the
        # API serves; unwired, nothing can say whether a RED is waiting, so the
        # inbox is reported unreadable — which pages — until it is wired.
        inbox = w.admin.safety_inbox if w.admin is not None else None
        sweeper: asyncio.Task[None] | None = None
        if inbox is None:
            mark_inbox_unreadable()
        else:
            sweeper = asyncio.create_task(sweep_forever(inbox, clock=lambda: datetime.now(UTC)))
        # INT-475: the outbox pump — the triage hop's RED and the on-site staff
        # notification are put in-process and written to the shared store here,
        # as the voice runtime's are (INT-406).
        pump = _RedPump.start(state)
        try:
            yield
        finally:
            if sweeper is not None:
                sweeper.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sweeper
            if pump is not None:
                pump.stop()

    app = FastAPI(title="intake-api", lifespan=lifespan)
    app.state.api = state
    app.state.settings = w.settings
    app.state.admin = w.admin
    # ADR-028 (on-demand): dev George clip route reads this; None = fail closed.
    app.state.george = w.george

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
        # INT-150 / files/10 §9 `doctor-link` row: "no indexing". Set on EVERY
        # response, including the ones an exception handler builds — a header
        # attached by a route dependency is lost the moment a route raises, and
        # a refusal page for a Doctor Link is exactly the page that must not be
        # crawled. This API serves nothing indexable at all, so the widest form
        # is also the correct one.
        response.headers.setdefault("X-Robots-Tag", NOINDEX)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _machine_readable_errors(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return JSONResponse(detail, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_errors_without_the_input(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """FastAPI's default 422 body echoes the rejected value back — for a
        note line or a DSAR correction that is patient free text leaving the
        boundary into every access log and trace (invariant 6). Keep the
        machine-readable part (type + field) and drop ``input``/``ctx``, which
        are the only members that can carry content."""
        return JSONResponse(
            {
                "error": "validation_error",
                "detail": [
                    {"type": item.get("type", ""), "loc": [str(p) for p in item.get("loc", ())]}
                    for item in exc.errors()
                ],
            },
            status_code=422,
        )

    async def _db_ready() -> bool:
        async with w.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def _dev_auth_ready() -> bool:
        return w.settings.dev_auth_configured

    readiness = [
        ReadinessCheck("db", _db_ready),
        ReadinessCheck("audit_store", state.audit.healthy),
    ]
    if w.settings.dev_tier_expected:
        # INT-197 dev tier: not ready until both dev bearers are set. Only the
        # dev environment expects them (INT-325): every other environment,
        # staging included, refuses them at boot, so anywhere else this check
        # would hold the API not-ready forever.
        readiness.append(ReadinessCheck("dev_auth", _dev_auth_ready))
    mount_health(app, readiness=readiness)

    app.include_router(visits.router)
    app.include_router(visit_lifecycle.router)
    app.include_router(visits_acibadem.router)
    app.include_router(notes.router)
    app.include_router(previsit_output.router)
    app.include_router(doctor_link.router)
    app.include_router(doctor_link.public_router)
    app.include_router(documents.router)
    app.include_router(record_items.router)
    app.include_router(otp_routes.router)
    app.include_router(consents.router)
    app.include_router(profile_routes.router)
    app.include_router(taxonomy_routes.router)
    app.include_router(triage_hop.router)
    app.include_router(red_notify.router)
    app.include_router(dsar.router)
    app.include_router(satisfaction.router)
    app.include_router(notification_prefs.router)
    app.include_router(experience.router)
    app.include_router(learned.router)
    app.include_router(admin.router)
    app.include_router(embed.router)
    # INT-326: the dev George route reaches a paid US vendor, so in production
    # it is not mounted at all (404) — whatever the dev flags or wiring say.
    # INT-443: outside dev, only the synthetic deployment that declares its
    # hosted clip lane mounts it; a PHI deployment never does.
    if george_route_mountable(os.environ):
        app.include_router(dev_voice.router)
    return app
