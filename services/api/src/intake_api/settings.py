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
# Dev-only gates (INT-131): anything but the exact phrase is OFF (fail closed).
ENV_DEV_OTP_PEEK = "INTAKE_DEV_OTP_PEEK"
ENV_DEV_ALLOW_UNATTESTED = "INTAKE_DEV_ALLOW_UNATTESTED"
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
    redis_url: str = "redis://127.0.0.1:6379/0"
    tokenization_key: str | None = None
    tokenization_key_id: str = "v1"
    dev_otp_peek: bool = False
    dev_allow_unattested: bool = False
    # Where the consent texts live (INT-038; invariant 18: texts render only
    # from docs/legal with hash binding). The default points at the repo's
    # legal tree; until INT-210 authors the texts the directory is absent and
    # the consent service fails closed on every new grant.
    legal_root: Path = field(default_factory=lambda: Path("docs/legal/consents"))
    # The branch taxonomy the /v1/taxonomy feed serves (INT-134; files/09 §1
    # names this file the source of truth). Absent or invalid → the feed and
    # the branch-backed visit path answer 503, never an empty list.
    taxonomy_path: Path = field(
        default_factory=lambda: Path("packages/protocols/taxonomy/branches.yaml")
    )

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
            redis_url=os.environ.get(ENV_REDIS_URL) or "redis://127.0.0.1:6379/0",
            tokenization_key=os.environ.get(ENV_TOKENIZATION_KEY) or None,
            tokenization_key_id=os.environ.get(ENV_TOKENIZATION_KEY_ID) or "v1",
            dev_otp_peek=os.environ.get(ENV_DEV_OTP_PEEK) == EXPLICIT_YES,
            dev_allow_unattested=os.environ.get(ENV_DEV_ALLOW_UNATTESTED) == EXPLICIT_YES,
            legal_root=Path(os.environ.get("INTAKE_LEGAL_ROOT") or "docs/legal/consents"),
        )
