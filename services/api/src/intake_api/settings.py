"""Dev-tier settings (INT-197). Tokens have NO in-code default — with either
one unset the API refuses every /v1 request (fail closed); real OIDC auth is
INT-131. In DEV, database URLs default to the compose dev tier's
least-privilege roles (the same values migrations/0001 creates and
tests/data/test_rls.py connects with).

OUTSIDE DEV (INT-325; audit 2026-09-26 F04/F14) ``ApiSettings.from_env``
refuses to build at all when any ``INTAKE_DEV_*`` flag is set, when the KEK
mode is ``file-dev``, or when any DB/MinIO credential variable is missing — a
dev default is never used outside dev. A public staging host is as strict as
prod. Dev is defined once, by :func:`is_dev_env`: ``INTAKE_ENV`` unset, empty
or ``dev`` (stripped, lower-cased) — the only non-prod value any test, CI job
or compose file in this repository sets; everything else is strict."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

__all__ = [
    "ApiSettings",
    "DevConfigRefusedError",
    "environment_name",
    "is_dev_env",
    "refuse_dev_config_outside_dev",
]

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
# INT-329: the egress allow-list the OTP tier's SMS vendor call is decided
# against. The same variable the compliance register reads (admin/
# compliance_source.py), so one override points both readers at one file.
ENV_EGRESS_ALLOWLIST = "INTAKE_EGRESS_ALLOWLIST_PATH"
EGRESS_ALLOWLIST_DEFAULT = "infra/security/egress-allowlist.yaml"
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
# INT-325: every dev gate lives under this prefix; outside dev ANY of them set
# is refused, so a gate added later is covered without being listed here.
DEV_FLAG_PREFIX = "INTAKE_DEV_"
ENV_KEK_MODE = "INTAKE_API_KEK_MODE"
ENV_APP_DB_URL = "INTAKE_API_DB_URL"
ENV_AUDIT_DB_URL = "INTAKE_API_AUDIT_DB_URL"
ENV_BOOTSTRAP_DB_URL = "INTAKE_API_BOOTSTRAP_DB_URL"
ENV_MINIO_USER = "MINIO_ROOT_USER"
ENV_MINIO_PASSWORD = "MINIO_ROOT_PASSWORD"  # noqa: S105 — env var name
# Each of these falls back to an in-code dev credential when absent in dev;
# outside dev an absent (or empty) one refuses the boot instead.
NON_DEV_REQUIRED_CREDENTIALS = (
    ENV_APP_DB_URL,
    ENV_AUDIT_DB_URL,
    ENV_BOOTSTRAP_DB_URL,
    ENV_MINIO_USER,
    ENV_MINIO_PASSWORD,
)

KekMode = Literal["transit", "file-dev"]


class DevConfigRefusedError(RuntimeError):
    """Raised at boot when a non-dev environment carries a dev bypass, the
    process-local KEK mode, or relies on an in-code dev credential. The
    message names the variables and never their values (invariant 6)."""


DEV_ENVIRONMENT = "dev"


def environment_name(environ: Mapping[str, str]) -> str:
    """``INTAKE_ENV`` normalised; unset or empty means dev, as in secrets.py."""
    return environ.get("INTAKE_ENV", "").strip().lower() or DEV_ENVIRONMENT


def _is_dev_name(environment: str) -> bool:
    return environment == DEV_ENVIRONMENT


def is_dev_env(environ: Mapping[str, str]) -> bool:
    """The one definition of dev (INT-325): ``INTAKE_ENV`` unset, empty or
    ``dev``. Every other value, staging included, is held to prod's rules."""
    return _is_dev_name(environment_name(environ))


def refuse_dev_config_outside_dev(environ: Mapping[str, str]) -> None:
    """Fail closed at boot (INT-325). A no-op in dev, so dev is unchanged."""
    if is_dev_env(environ):
        return
    offences: list[str] = []
    dev_flags = sorted(
        name for name, value in environ.items() if name.startswith(DEV_FLAG_PREFIX) and value
    )
    if dev_flags:
        offences.append("dev flag(s) set: " + ", ".join(dev_flags))
    if environ.get(ENV_KEK_MODE) == "file-dev":
        offences.append(f"{ENV_KEK_MODE} is file-dev (process-local KEKs)")
    missing = [name for name in NON_DEV_REQUIRED_CREDENTIALS if not environ.get(name)]
    if missing:
        offences.append("credential variable(s) missing: " + ", ".join(missing))
    if offences:
        raise DevConfigRefusedError(
            f"INTAKE_ENV={environment_name(environ)} is not dev and the API refuses to boot "
            "with dev configuration (no dev default is used outside dev): " + "; ".join(offences)
        )


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
    # INT-329: the egress allow-list (INT-018) the SMS vendor call must clear.
    # Absent or unreadable → the OTP tier stays unconfigured outside dev.
    egress_allowlist_path: Path = field(default_factory=lambda: Path(EGRESS_ALLOWLIST_DEFAULT))
    # INT-318: the clinical READ-source registry (intake_connectors.sources).
    # It ships with zero rows, so /v1/visits/sync answers "unavailable"; a row
    # is registered there by a human (HB-A15, HB-A5, HB-L27) and never built
    # in code. Absent, invalid or ambiguous → nothing is wired (fail closed).
    clinical_sources_path: Path = field(
        default_factory=lambda: Path("infra/connectors/sources.yaml")
    )
    # INT-317: which hospital systems may FETCH a finished previsit. The
    # committed file has zero rows (no DPA is executed and no reader is
    # approved), so the read-back refuses every caller until a human adds one.
    previsit_output_recipients_path: Path = field(
        default_factory=lambda: Path("infra/previsit_output/recipients.yaml")
    )
    # INT-446: the served life-threat rule set the rules-engine hop evaluates
    # (packages/protocols/triage). None — the shipped state while every rule is
    # draft_needs_source (HB-C1) — makes /v1/triage answer 503, never GREEN.
    triage_rules_path: Path | None = None
    # INT-453: the generic RED escalation document. The committed one is
    # draft_needs_source until CD-24 lands, so it refuses and nothing is served.
    triage_generic_red_path: Path | None = field(
        default_factory=lambda: Path("packages/protocols/generic/generic_red.yaml")
    )
    # INT-325: the normalised INTAKE_ENV, set by from_env. The single source
    # for `dev_tier_expected`, which gates every dev-only collaborator (the
    # dev-bearer readiness check, the OTP dev delivery logger).
    environment: str = DEV_ENVIRONMENT

    @property
    def dev_tier_expected(self) -> bool:
        """Dev bearers and dev collaborators belong to the dev environment
        only; every other environment refuses them at boot (INT-325)."""
        return _is_dev_name(self.environment)

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
        # INT-325: outside dev, refuse before any dev default below can apply
        refuse_dev_config_outside_dev(os.environ)
        kek_mode: KekMode = "file-dev" if os.environ.get(ENV_KEK_MODE) == "file-dev" else "transit"
        return cls(
            token_patient=os.environ.get(ENV_TOKEN_PATIENT) or None,
            token_admin=os.environ.get(ENV_TOKEN_ADMIN) or None,
            app_db_url=os.environ.get(ENV_APP_DB_URL) or _dev_db_url("app_rw", "app-rw-dev-only"),
            audit_db_url=os.environ.get(ENV_AUDIT_DB_URL)
            or _dev_db_url("svc_audit_writer", "svc-audit-writer-dev-only"),
            bootstrap_db_url=os.environ.get(ENV_BOOTSTRAP_DB_URL)
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
            egress_allowlist_path=Path(
                os.environ.get(ENV_EGRESS_ALLOWLIST) or EGRESS_ALLOWLIST_DEFAULT
            ),
            clinical_sources_path=Path(
                os.environ.get("INTAKE_CLINICAL_SOURCES") or "infra/connectors/sources.yaml"
            ),
            previsit_output_recipients_path=Path(
                os.environ.get("INTAKE_PREVISIT_OUTPUT_RECIPIENTS")
                or "infra/previsit_output/recipients.yaml"
            ),
            triage_rules_path=(
                Path(os.environ["INTAKE_API_TRIAGE_RULES"])
                if os.environ.get("INTAKE_API_TRIAGE_RULES")
                else None
            ),
            triage_generic_red_path=Path(
                os.environ.get("INTAKE_API_TRIAGE_GENERIC_RED")
                or "packages/protocols/generic/generic_red.yaml"
            ),
            environment=environment_name(os.environ),
        )
