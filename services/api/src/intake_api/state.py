"""Per-app dependency container (INT-197): the wired engine, audit writer
and envelope cipher, reachable from any route via ``Depends(get_state)`` —
tests inject their own, the env path builds the real ones (app.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request
from intake_platform.consent import ConsentTextCatalog
from intake_platform.envelope import EnvelopeCipher
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.age_context import AgeContextSource, NoAgeRecordSource
from intake_api.audit import AuditWriter
from intake_api.settings import ApiSettings

if TYPE_CHECKING:
    from intake_api.documents import DocumentsGateway
    from intake_api.otp import OtpAuthService

__all__ = ["ApiState", "State", "get_state"]


def _catalog_from_settings(settings: ApiSettings) -> ConsentTextCatalog:
    return ConsentTextCatalog(settings.legal_root)


@dataclass
class ApiState:
    settings: ApiSettings
    engine: AsyncEngine
    audit: AuditWriter
    cipher: EnvelopeCipher
    documents: DocumentsGateway | None = None
    # INT-131: the OTP/DPoP tier; None = unconfigured (auth routes 503,
    # DPoP-scheme requests refused) while dev-bearer keeps working
    auth: OtpAuthService | None = None
    # INT-223: where ensure_consent gets the subject's age context. The
    # default reports "no date of birth is recorded" truthfully; a source
    # that reads a verified DOB replaces it when onboarding has one, and
    # every guarded route inherits the change with no route edit.
    age_context: AgeContextSource = field(default_factory=NoAgeRecordSource)
    # INT-038: the docs/legal consent-text catalog the guard binds against;
    # defaults from settings.legal_root in __post_init__ so every state has
    # one (an absent legal tree is an EMPTY catalog — grants fail closed).
    consent_catalog: ConsentTextCatalog = field(init=False)

    def __post_init__(self) -> None:
        self.consent_catalog = _catalog_from_settings(self.settings)


def get_state(request: Request) -> ApiState:
    return cast(ApiState, request.app.state.api)


State = Annotated[ApiState, Depends(get_state)]
