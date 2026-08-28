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
    # Where the consent texts live (INT-038; invariant 18: texts render only
    # from docs/legal with hash binding). The default points at the repo's
    # legal tree; until INT-210 authors the texts the directory is absent and
    # the consent service fails closed on every new grant.
    legal_root: Path = field(default_factory=lambda: Path("docs/legal/consents"))

    @property
    def dev_auth_configured(self) -> bool:
        return bool(self.token_patient) and bool(self.token_admin)

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
            legal_root=Path(os.environ.get("INTAKE_LEGAL_ROOT") or "docs/legal/consents"),
        )
