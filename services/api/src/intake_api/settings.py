"""Dev-tier settings (INT-197). Tokens have NO in-code default — with either
one unset the API refuses every /v1 request (fail closed); real OIDC auth is
INT-131. Database URLs default to the compose dev tier's least-privilege
roles (the same values migrations/0001 creates and tests/data/test_rls.py
connects with)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

__all__ = ["ApiSettings"]

# Environment KEY NAMES, not credentials: the values live only in the
# runtime environment and have no in-code default (fail closed when unset).
ENV_TOKEN_PATIENT = "INTAKE_DEV_TOKEN_PATIENT"  # noqa: S105 — env var name
ENV_TOKEN_ADMIN = "INTAKE_DEV_TOKEN_ADMIN"  # noqa: S105 — env var name
ENV_TOKENIZATION_KEY = "INTAKE_TOKENIZATION_KEY"  # noqa: S105 — env var name
ENV_TOKENIZATION_KEY_ID = "INTAKE_TOKENIZATION_KEY_ID"
ENV_REDIS_URL = "INTAKE_REDIS_URL"
#: The compose dev tier's Redis; one spelling for every consumer of it.
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
# Dev-only gates (INT-131): anything but the exact phrase is OFF (fail closed).
ENV_DEV_OTP_PEEK = "INTAKE_DEV_OTP_PEEK"
ENV_DEV_ALLOW_UNATTESTED = "INTAKE_DEV_ALLOW_UNATTESTED"
# INT-308: where the carrier/geo allocation table lives.
ENV_MSISDN_ALLOCATION = "INTAKE_MSISDN_ALLOCATION"
# INT-344 Apple App Attest. The team id is the App ID prefix from the Apple
# Developer account (HB-A3): not secret — every signed build carries it — but it
# has no default, so without it iOS attestation fails closed. The bundle id is
# the app's committed identity. The environment is production unless it says
# exactly "development" (dev-signed builds only; never on a public host).
ENV_APP_ATTEST_TEAM_ID = "INTAKE_APP_ATTEST_TEAM_ID"
ENV_APP_ATTEST_BUNDLE_ID = "INTAKE_APP_ATTEST_BUNDLE_ID"
ENV_APP_ATTEST_ENVIRONMENT = "INTAKE_APP_ATTEST_ENVIRONMENT"
IOS_BUNDLE_ID = "com.ariomoniri.intakemobile"
EXPLICIT_YES = "explicit-yes"

KekMode = Literal["transit", "file-dev"]


def _dev_db_url(user: str, password: str) -> str:
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "intake")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"


@dataclass(frozen=True)
class ApiSettings:
    """Runtime configuration; construct directly in tests, from env in dev."""

    token_patient: str | None
    token_admin: str | None
    app_db_url: str
    audit_db_url: str
    bootstrap_db_url: str
    kek_mode: KekMode
    # INT-131 OTP tier — all fail closed by default: no tokenization key
    # means no OTP auth (503), and the dev gates are off unless the env
    # carries the exact phrase "explicit-yes".
    redis_url: str = DEFAULT_REDIS_URL
    tokenization_key: str | None = None
    tokenization_key_id: str = "v1"
    dev_otp_peek: bool = False
    dev_allow_unattested: bool = False
    # Where the consent texts live (INT-038; invariant 18: texts render only
    # from docs/legal with hash binding). The default points at the repo's
    # legal tree; until INT-210 authors the texts the directory is absent and
    # the consent service fails closed on every new grant.
    legal_root: Path = field(default_factory=lambda: Path("docs/legal/consents"))
    # Where the files/06 §7 fixed strings live (INT-037 renders the DSAR
    # export document from them, hash-bound). Absent until INT-210 authors
    # them, which is why every renderer of these strings fails closed.
    legal_strings_path: Path = field(default_factory=lambda: Path("docs/legal/strings.yaml"))
    # The branch taxonomy the /v1/taxonomy feed serves (INT-134; files/09 §1
    # names this file the source of truth). Absent or invalid → the feed and
    # the branch-backed visit path answer 503, never an empty list.
    taxonomy_path: Path = field(
        default_factory=lambda: Path("packages/protocols/taxonomy/branches.yaml")
    )
    # Which hospital systems may FETCH a finished previsit (owner directive).
    # The committed file has zero rows — no DPA is executed and no reader is
    # approved — so the read-back refuses every caller until a human adds one.
    previsit_output_recipients_path: Path = field(
        default_factory=lambda: Path("infra/previsit_output/recipients.yaml")
    )
    # INT-320: the partner white-label embed handshake (ADR-028). The registry
    # of embed tenants (dev-only in the committed file); the base URL the
    # branded launch opens. Absent launch URL → the embed surface stays
    # unconfigured (503). The signing key comes from OpenBao (invariant 14) or
    # the surface fails closed — no key is ever read from the environment.
    embed_registry_path: Path = field(
        default_factory=lambda: Path("infra/tenants/embed_registry.yaml")
    )
    embed_launch_base_url: str | None = None
    # INT-308: the carrier/geo authority for the OTP request path (files/10
    # §2). Absent, unreadable or empty → the check ADMITS, which is the
    # opposite of every other fail-closed default here and is deliberate: a
    # lookup that cannot be made must not lock a patient out of their own
    # intake. See intake_api.carrier_geo.
    msisdn_allocation_path: Path = field(
        default_factory=lambda: Path("infra/security/msisdn_allocation.yaml")
    )
    # INT-344: Apple App Attest. No team id → iOS attestation fails closed
    # (app_attest_not_configured); a malformed one fails closed too.
    app_attest_team_id: str | None = None
    app_attest_bundle_id: str = IOS_BUNDLE_ID
    app_attest_environment: str | None = None

    @property
    def dev_auth_configured(self) -> bool:
        return bool(self.token_patient) and bool(self.token_admin)

    @property
    def otp_auth_configured(self) -> bool:
        """The OTP tier needs the phone-tokenization key (invariant 14:
        identifiers tokenized); without it the tier stays 503."""
        return bool(self.tokenization_key)

    @classmethod
    def from_env(cls) -> ApiSettings:
        kek_mode: KekMode = (
            "file-dev" if os.environ.get("INTAKE_API_KEK_MODE") == "file-dev" else "transit"
        )
        return cls(
            token_patient=os.environ.get(ENV_TOKEN_PATIENT) or None,
            token_admin=os.environ.get(ENV_TOKEN_ADMIN) or None,
            app_db_url=os.environ.get("INTAKE_API_DB_URL")
            or _dev_db_url("app_rw", "app-rw-dev-only"),
            audit_db_url=os.environ.get("INTAKE_API_AUDIT_DB_URL")
            or _dev_db_url("svc_audit_writer", "svc-audit-writer-dev-only"),
            bootstrap_db_url=os.environ.get("INTAKE_API_BOOTSTRAP_DB_URL")
            or _dev_db_url(
                os.environ.get("POSTGRES_USER", "intake"),
                os.environ.get("POSTGRES_PASSWORD", "intake-dev-only"),
            ),
            kek_mode=kek_mode,
            redis_url=os.environ.get(ENV_REDIS_URL) or DEFAULT_REDIS_URL,
            tokenization_key=os.environ.get(ENV_TOKENIZATION_KEY) or None,
            tokenization_key_id=os.environ.get(ENV_TOKENIZATION_KEY_ID) or "v1",
            dev_otp_peek=os.environ.get(ENV_DEV_OTP_PEEK) == EXPLICIT_YES,
            dev_allow_unattested=os.environ.get(ENV_DEV_ALLOW_UNATTESTED) == EXPLICIT_YES,
            legal_root=Path(os.environ.get("INTAKE_LEGAL_ROOT") or "docs/legal/consents"),
            legal_strings_path=Path(
                os.environ.get("INTAKE_LEGAL_STRINGS") or "docs/legal/strings.yaml"
            ),
            previsit_output_recipients_path=Path(
                os.environ.get("INTAKE_PREVISIT_OUTPUT_RECIPIENTS")
                or "infra/previsit_output/recipients.yaml"
            ),
            embed_registry_path=Path(
                os.environ.get("INTAKE_EMBED_REGISTRY") or "infra/tenants/embed_registry.yaml"
            ),
            embed_launch_base_url=os.environ.get("INTAKE_EMBED_LAUNCH_URL") or None,
            msisdn_allocation_path=Path(
                os.environ.get(ENV_MSISDN_ALLOCATION) or "infra/security/msisdn_allocation.yaml"
            ),
            app_attest_team_id=os.environ.get(ENV_APP_ATTEST_TEAM_ID) or None,
            app_attest_bundle_id=os.environ.get(ENV_APP_ATTEST_BUNDLE_ID) or IOS_BUNDLE_ID,
            app_attest_environment=os.environ.get(ENV_APP_ATTEST_ENVIRONMENT) or None,
        )
