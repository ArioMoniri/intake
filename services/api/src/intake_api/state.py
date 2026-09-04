"""Per-app dependency container (INT-197): the wired engine, audit writer
and envelope cipher, reachable from any route via ``Depends(get_state)`` —
tests inject their own, the env path builds the real ones (app.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request
from intake_platform.consent import ConsentTextCatalog
from intake_platform.envelope import EnvelopeCipher
from intake_platform.flags import FlagProvider, default_provider
from intake_platform.legal import LegalStringsCatalog
from intake_platform.previsit_output import RecipientRegistry, load_recipients
from intake_platform.tokenization import Tokenizer
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.age_context import AgeContextSource, NoAgeRecordSource
from intake_api.audit import AuditWriter
from intake_api.settings import ApiSettings
from intake_api.taxonomy_feed import LoadedTaxonomy, load_taxonomy_feed

if TYPE_CHECKING:
    from intake_api.doctor_link.service import DoctorLinkService
    from intake_api.documents import DocumentsGateway
    from intake_api.otp import OtpAuthService

__all__ = ["ApiState", "State", "get_state"]


def _catalog_from_settings(settings: ApiSettings) -> ConsentTextCatalog:
    return ConsentTextCatalog(settings.legal_root)


def _tokenizer_from_settings(settings: ApiSettings) -> Tokenizer | None:
    """The Tokenizer the previsit-output read-back resolves a hospital patient
    number with. ``None`` when no key is configured, which makes that route
    answer 503 rather than fall back to anything (invariant 14)."""
    if settings.tokenization_key is None:
        return None
    return Tokenizer(
        keys={settings.tokenization_key_id: settings.tokenization_key.encode("utf-8")},
        active_key_id=settings.tokenization_key_id,
    )


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
    # INT-150: the Doctor Link tier. It needs the same Redis the OTP tier
    # needs (one shared abuse gate, one code store), so it is wired from the
    # same AuthWiring and is None — every route 503 — without it.
    doctor_link: DoctorLinkService | None = None
    # INT-223: where ensure_consent gets the subject's age context. The
    # default reports "no date of birth is recorded" truthfully; a source
    # that reads a verified DOB replaces it when onboarding has one, and
    # every guarded route inherits the change with no route edit.
    age_context: AgeContextSource = field(default_factory=NoAgeRecordSource)
    # INT-133: the INT-023 flag facade, so a route can read a safety gate
    # (guardian_link) without reaching for the environment. The default
    # provider is in-memory unless INTAKE_UNLEASH_URL is set, and the safety
    # flags are pre-declared False in BOTH providers — a call-site default
    # cannot open one.
    flags: FlagProvider = field(default_factory=default_provider)
    # INT-038: the docs/legal consent-text catalog the guard binds against;
    # defaults from settings.legal_root in __post_init__ so every state has
    # one (an absent legal tree is an EMPTY catalog — grants fail closed).
    consent_catalog: ConsentTextCatalog = field(init=False)
    # INT-037: the files/06 §7 fixed strings the DSAR export document renders
    # from. An absent file is a fail-closed export, never a default string.
    legal_strings: LegalStringsCatalog = field(init=False)
    # INT-134: the loaded branch taxonomy, lazy so the load failure surfaces
    # as a per-request 503 (taxonomy_unconfigured), never a startup crash.
    # Owner directive: the Tokenizer the previsit-output read-back turns a
    # hospital patient number into a pseudonym with. Built from settings so it
    # is present whether or not the OTP tier is wired — they share the key but
    # not the lifecycle. None = that route answers 503 (fail closed).
    tokenizer: Tokenizer | None = field(init=False, default=None)
    _taxonomy: LoadedTaxonomy | None = field(init=False, default=None)
    _taxonomy_loaded: bool = field(init=False, default=False)
    # The approved previsit-output readers, lazy for the same reason the
    # taxonomy is: a broken or absent registry must surface as a per-request
    # 503, never as a startup crash that takes the whole API down with it.
    _recipients: RecipientRegistry | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.consent_catalog = _catalog_from_settings(self.settings)
        self.legal_strings = LegalStringsCatalog(self.settings.legal_strings_path)
        self.tokenizer = _tokenizer_from_settings(self.settings)

    def previsit_output_recipients(self) -> RecipientRegistry:
        """The approved readers, loaded once. Raises
        ``RecipientRegistryError`` on an absent or malformed file — the route
        turns that into the same 503 as "no row for this tenant", because
        serving on an unread registry is the thing this must not do."""
        if self._recipients is None:
            self._recipients = load_recipients(self.settings.previsit_output_recipients_path)
        return self._recipients

    def taxonomy(self) -> LoadedTaxonomy | None:
        """The validated taxonomy + version, loaded once from
        settings.taxonomy_path; ``None`` means fail closed (503)."""
        if not self._taxonomy_loaded:
            self._taxonomy = load_taxonomy_feed(self.settings.taxonomy_path)
            self._taxonomy_loaded = True
        return self._taxonomy


def get_state(request: Request) -> ApiState:
    return cast(ApiState, request.app.state.api)


State = Annotated[ApiState, Depends(get_state)]
