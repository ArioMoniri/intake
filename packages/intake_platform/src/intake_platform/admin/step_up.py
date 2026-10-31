"""The four-eyes step-up: a fresh WebAuthn re-authentication, proven by
Keycloak, spent once (INT-563; files/08 §2.3).

files/08 §2.3: *"Step-up is a fresh, single-use WebAuthn assertion at the
moment of the action, and its credential id goes in the audit row."* Until
this module, an approval carried an ``assertion_id`` the API never checked:
any unused string passed, and the approver's "credential" was the one the
console session had logged in with hours before. The approval was therefore a
second click, not a second key.

**Who verifies the WebAuthn assertion.** Keycloak does — it holds the
registered credentials and runs the staff browser flow, whose WebAuthn step is
REQUIRED (INT-365) and records the asserted credential's AAGUID and id as
user-session notes (INT-378). The console is script-free under its CSP and
cannot run ``navigator.credentials.get`` itself; the API holds no credential
public keys. So the step-up is an OIDC re-authentication the API runs:

1. :meth:`StepUpService.begin` opens a ceremony bound to the caller (subject
   and session) and to the pending action, and returns an authorization URL
   for the public client :data:`STEP_UP_CLIENT_ID` with ``prompt=login`` and
   ``max_age=0`` (the browser flow runs again, WebAuthn included), a PKCE S256
   challenge, a ``state`` and a ``nonce``. The verifier never leaves the API.
2. Keycloak redirects the browser to the console's callback, which relays the
   ``state`` and the ``code`` here; :meth:`StepUpService.complete` redeems the
   code with the verifier and verifies the ID token — RS256 against the
   mirrored key set, issuer, audience :data:`STEP_UP_CLIENT_ID`, expiry, an
   ID token's ``typ`` and ``azp``, the ceremony's nonce, the caller's subject
   AND Keycloak session, an ``auth_time`` no older than the ceremony, ``hwk``
   in ``amr``, an id-shaped AAGUID and a well-formed credential id — and
   spends its ``jti`` for as long as the token could verify.
3. It returns a :class:`StepUpGrant`: one approval of that one action by that
   caller, inside :data:`GRANT_TTL`. The approve route redeems it once and
   builds the approver's actor block from the credential just asserted, so
   four-eyes' "different key" compares the key used *now* (files/08 §8.1).

**What proves the WebAuthn step ran *now*** (ADR-043). Keycloak's
``oidc-amr-mapper`` emits ``hwk`` from the user session's completed
authenticators while the execution's ``default.reference.maxAge`` (28800 s)
lasts, so ``amr`` alone says "within eight hours", not "in this ceremony". The
freshness is ``auth_time``: Keycloak rewrites the session's ``AUTH_TIME`` on
every non-SSO authentication, and ``prompt=login`` makes this one non-SSO. The
staff browser flow is the only flow and its WebAuthn step is REQUIRED (checked
on every deploy and smoke by ``infra/staging/keycloak/staff_flow.py``), so a
fresh authentication there is a fresh assertion; the credential notes name
which key made it.

Every refusal carries a machine code and nothing a caller submitted
(invariant 6). Storage is process-local, the same failure direction as
:class:`~intake_platform.admin.four_eyes.FourEyesService`: a restart drops
every ceremony and grant, which refuses rather than grants.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric import rsa

from intake_platform.admin.four_eyes import ActorBlock
from intake_platform.admin.oidc import CLOCK_LEEWAY, KeycloakClaimsVerifier
from intake_platform.admin.principal import ClaimsRejected, is_credential_id, is_id_shaped
from intake_platform.admin.second_factor import AMR_WEBAUTHN, authentication_methods

__all__ = [
    "AUTH_TIME_LEEWAY",
    "CEREMONY_TTL",
    "ENV_STEP_UP_REDIRECT_URI",
    "ENV_STEP_UP_EXCHANGE_URL",
    "GRANT_TTL",
    "STEP_UP_CLIENT_ID",
    "Ceremony",
    "HttpTokenExchange",
    "IdTokenVerifier",
    "StepUpConfig",
    "StepUpExchangeFailed",
    "StepUpGrant",
    "StepUpNotFresh",
    "StepUpRefused",
    "StepUpReplayed",
    "StepUpService",
    "StepUpTokenRefused",
    "StepUpUnknown",
    "StepUpWithoutWebAuthn",
    "TokenExchange",
    "step_up_config_from_env",
    "step_up_service_from_env",
]

#: The realm's public client for the re-authentication alone (dev and staging
#: realms; tests/admin/test_step_up.py holds both to it).
STEP_UP_CLIENT_ID: Final = "admin-web-stepup"
ENV_STEP_UP_REDIRECT_URI: Final = "INTAKE_ADMIN_STEP_UP_REDIRECT_URI"
ENV_STEP_UP_EXCHANGE_URL: Final = "INTAKE_ADMIN_STEP_UP_EXCHANGE_URL"
#: How long the passkey prompt may take: a ceremony not completed by then is gone.
CEREMONY_TTL: Final = timedelta(minutes=2)
#: How long the console has, after the ceremony, to send the approval.
GRANT_TTL: Final = timedelta(minutes=2)
#: Keycloak's clock against the API's. An ``auth_time`` older than the
#: ceremony by more than this is a re-used login, not a step-up.
AUTH_TIME_LEEWAY: Final = timedelta(seconds=30)
_CALLBACK_PATH: Final = "/step-up/callback"
_LOOPBACK: Final = frozenset({"localhost", "127.0.0.1", "[::1]"})
_MAX_STATE_CHARS: Final = 128
_MAX_CODE_CHARS: Final = 4096
_TIMEOUT_S: Final = 10.0
#: Keycloak's ID-token type (``TokenUtil.TOKEN_TYPE_ID``): an access token
#: minted for the same client is not an answer to this ceremony.
_KEYCLOAK_ID_TYP: Final = "ID"
#: Open ceremonies one caller may hold. A begin past it drops the oldest, so
#: an authenticated loop cannot grow the table without bound.
_MAX_LIVE_PER_CALLER: Final = 3


class StepUpRefused(Exception):
    """Base refusal. ``code`` is stable and machine-shaped (invariant 6)."""

    code = "step_up_refused"


class StepUpUnknown(StepUpRefused):
    """No live ceremony or grant for this caller: unknown, expired, spent, or
    another caller's. One code for all of them, so the answer does not say
    which."""

    code = "step_up_unknown"


class StepUpExchangeFailed(StepUpRefused):
    """Keycloak would not redeem the code, or could not be reached."""

    code = "step_up_exchange_failed"


class StepUpTokenRefused(StepUpRefused):
    """The ID token did not verify, or does not belong to this ceremony."""

    code = "step_up_token_refused"


class StepUpNotFresh(StepUpRefused):
    """The token's ``auth_time`` predates the ceremony: a remembered login."""

    code = "step_up_not_fresh"


class StepUpWithoutWebAuthn(StepUpRefused):
    """The re-authentication completed without the WebAuthn step."""

    code = "step_up_without_webauthn"


class StepUpReplayed(StepUpRefused):
    """That ID token was already spent on a step-up."""

    code = "step_up_replayed"


@dataclass(frozen=True)
class StepUpConfig:
    authorize_endpoint: str
    token_endpoint: str
    redirect_uri: str
    client_id: str = STEP_UP_CLIENT_ID


def _url(value: str, what: str, *, path_suffix: str | None = None) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError(f"{what} is not an absolute http(s) URL")
    if parts.scheme == "http" and parts.hostname not in _LOOPBACK and "." in parts.hostname:
        # a plain-http public host carries the code in the clear; only a
        # loopback address (dev) or a compose service name (the backchannel)
        raise ValueError(f"{what} is plain http to a public host")
    if parts.query or parts.fragment:
        raise ValueError(f"{what} carries a query or a fragment")
    if path_suffix is not None and not parts.path.endswith(path_suffix):
        raise ValueError(f"{what} is not the console's {path_suffix}")
    return value


def step_up_config_from_env(env: Mapping[str, str], *, issuer: str) -> StepUpConfig | None:
    """Both variables, or neither: neither leaves the step-up unconfigured and
    every approval refused (fail closed); one without the other raises."""
    redirect = env.get(ENV_STEP_UP_REDIRECT_URI, "").strip()
    token = env.get(ENV_STEP_UP_EXCHANGE_URL, "").strip()
    if not redirect and not token:
        return None
    if not redirect or not token:
        raise ValueError(f"{ENV_STEP_UP_REDIRECT_URI} and {ENV_STEP_UP_EXCHANGE_URL} go together")
    return StepUpConfig(
        authorize_endpoint=_url(issuer, "the issuer").rstrip("/") + "/protocol/openid-connect/auth",
        token_endpoint=_url(token, ENV_STEP_UP_EXCHANGE_URL),
        redirect_uri=_url(redirect, ENV_STEP_UP_REDIRECT_URI, path_suffix=_CALLBACK_PATH),
    )


def step_up_service_from_env(
    env: Mapping[str, str], *, issuer: str, keys: Mapping[str, rsa.RSAPublicKey]
) -> StepUpService | None:
    """The step-up over the console's own mirrored key set, or ``None`` (every
    approval refused). The ID token is verified as the console's bearer is:
    RS256 against the file the deploy mirrors, never a key fetched at the
    moment of the approval."""
    config = step_up_config_from_env(env, issuer=issuer)
    if config is None:
        return None
    verifier = KeycloakClaimsVerifier(issuer=issuer, audience=config.client_id, keys=keys)
    return StepUpService(config=config, verifier=verifier, exchange=HttpTokenExchange(config))


class IdTokenVerifier(Protocol):
    """Signature, issuer, audience and expiry; :class:`KeycloakClaimsVerifier`
    with ``audience=STEP_UP_CLIENT_ID`` satisfies it."""

    def verify(self, token: str) -> Mapping[str, Any]: ...


class TokenExchange(Protocol):
    """Redeem an authorization code with its PKCE verifier; return the ID token."""

    def __call__(self, *, code: str, verifier: str) -> str: ...


@dataclass(frozen=True)
class HttpTokenExchange:
    """The code redemption at Keycloak's token endpoint, as the public client:
    no secret, the PKCE verifier is the proof (RFC 7636)."""

    config: StepUpConfig
    #: ``trust_env=False``: no ``HTTPS_PROXY`` or netrc from the api's environment
    #: decides where the code and the verifier go (INT-563 review).
    client: httpx.Client = field(
        default_factory=lambda: httpx.Client(timeout=_TIMEOUT_S, trust_env=False)
    )

    def __call__(self, *, code: str, verifier: str) -> str:
        try:
            response = self.client.post(
                self.config.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.config.client_id,
                    "code": code,
                    "redirect_uri": self.config.redirect_uri,
                    "code_verifier": verifier,
                },
                headers={"accept": "application/json"},
            )
        except httpx.HTTPError:
            raise StepUpExchangeFailed("the token endpoint could not be reached") from None
        if response.status_code != 200:
            raise StepUpExchangeFailed("the token endpoint refused the code")
        try:
            body = response.json()
        except ValueError:
            raise StepUpExchangeFailed("the token endpoint answered no JSON") from None
        id_token = body.get("id_token") if isinstance(body, dict) else None
        if not isinstance(id_token, str):
            raise StepUpExchangeFailed("the token endpoint answered no ID token")
        return id_token


@dataclass(frozen=True)
class Ceremony:
    state: str
    nonce: str
    verifier: str
    subject: str
    session_id: str
    action_id: str
    started_at: datetime


@dataclass(frozen=True)
class StepUpGrant:
    """One approval of one action by one caller, with the key just asserted."""

    grant_id: str
    subject: str
    session_id: str
    action_id: str
    credential_id: str
    aaguid: str
    #: What four-eyes spends as the assertion id: the ID token's ``jti``,
    #: hashed, so the chain names the assertion without carrying the token.
    assertion_ref: str
    expires_at: datetime

    def approver(self, block: ActorBlock) -> ActorBlock:
        """The caller's actor block with the credential just asserted."""
        return replace(block, credential_id=self.credential_id, authenticator_aaguid=self.aaguid)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass
class StepUpService:
    config: StepUpConfig
    verifier: IdTokenVerifier
    exchange: TokenExchange
    clock: Callable[[], datetime] = _utc_now
    _ceremonies: dict[str, Ceremony] = field(default_factory=dict)
    _grants: dict[str, StepUpGrant] = field(default_factory=dict)
    #: assertion ref -> when its token stops verifying (exp plus the verifier's
    #: clock leeway); kept until then, so a replay is refused for as long as the
    #: token itself would pass
    _spent: dict[str, datetime] = field(default_factory=dict)

    def _sweep(self, now: datetime) -> None:
        # pop, not del: two requests sweeping at once must not raise on the same key
        for state, ceremony in list(self._ceremonies.items()):
            if now > ceremony.started_at + CEREMONY_TTL:
                self._ceremonies.pop(state, None)
        for grant_id, grant in list(self._grants.items()):
            if now > grant.expires_at:
                self._grants.pop(grant_id, None)
        for ref, until in list(self._spent.items()):
            if now > until:
                self._spent.pop(ref, None)

    def _cap(self, subject: str, session_id: str) -> None:
        caller = (subject, session_id)
        mine = sorted(
            (c for c in self._ceremonies.values() if (c.subject, c.session_id) == caller),
            key=lambda c: c.started_at,
        )
        for ceremony in mine[: max(0, len(mine) - _MAX_LIVE_PER_CALLER + 1)]:
            self._ceremonies.pop(ceremony.state, None)

    def begin(self, *, subject: str, session_id: str, action_id: str) -> tuple[Ceremony, str]:
        now = self.clock()
        self._sweep(now)
        self._cap(subject, session_id)
        ceremony = Ceremony(
            state=secrets.token_urlsafe(24),
            nonce=secrets.token_urlsafe(24),
            verifier=secrets.token_urlsafe(48),
            subject=subject,
            session_id=session_id,
            action_id=action_id,
            started_at=now,
        )
        self._ceremonies[ceremony.state] = ceremony
        query = urlencode(
            {
                "client_id": self.config.client_id,
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": self.config.redirect_uri,
                "state": ceremony.state,
                "nonce": ceremony.nonce,
                "code_challenge": _challenge(ceremony.verifier),
                "code_challenge_method": "S256",
                # the browser flow runs again, WebAuthn included: no SSO cookie
                # and no "remember this device" stands in for the assertion
                "prompt": "login",
                "max_age": "0",
            }
        )
        return ceremony, f"{self.config.authorize_endpoint}?{query}"

    def complete(self, *, subject: str, session_id: str, state: str, code: str) -> StepUpGrant:
        now = self.clock()
        self._sweep(now)
        if not (0 < len(state) <= _MAX_STATE_CHARS) or not (0 < len(code) <= _MAX_CODE_CHARS):
            raise StepUpUnknown("no live ceremony for this caller")
        # spent on first use, whatever follows: a state is never tried twice
        ceremony = self._ceremonies.pop(state, None)
        if ceremony is None or (ceremony.subject, ceremony.session_id) != (subject, session_id):
            raise StepUpUnknown("no live ceremony for this caller")
        id_token = self.exchange(code=code, verifier=ceremony.verifier)
        try:
            claims = self.verifier.verify(id_token)
        except ClaimsRejected:
            raise StepUpTokenRefused("the ID token did not verify") from None
        grant = self._grant_for(ceremony, claims, now)
        self._grants[grant.grant_id] = grant
        return grant

    def _grant_for(
        self, ceremony: Ceremony, claims: Mapping[str, Any], now: datetime
    ) -> StepUpGrant:
        if claims.get("typ") != _KEYCLOAK_ID_TYP or claims.get("azp") != self.config.client_id:
            raise StepUpTokenRefused("the token is not this client's ID token")
        if claims.get("nonce") != ceremony.nonce:
            raise StepUpTokenRefused("the ID token belongs to another ceremony")
        if (claims.get("sub"), claims.get("sid")) != (ceremony.subject, ceremony.session_id):
            # another account, or this account in another Keycloak session:
            # either way not the caller who opened the ceremony
            raise StepUpTokenRefused("the ID token belongs to another session")
        auth_time = claims.get("auth_time")
        if not isinstance(auth_time, int) or isinstance(auth_time, bool):
            raise StepUpNotFresh("the ID token carries no authentication time")
        earliest = (ceremony.started_at - AUTH_TIME_LEEWAY).timestamp()
        if not earliest <= auth_time <= (now + AUTH_TIME_LEEWAY).timestamp():
            raise StepUpNotFresh("the authentication predates the ceremony")
        methods = authentication_methods(claims.get("amr"))
        if methods is None or AMR_WEBAUTHN not in methods:
            raise StepUpWithoutWebAuthn("the re-authentication shows no WebAuthn step")
        credential_id, aaguid = claims.get("credential_id"), claims.get("aaguid")
        if not isinstance(credential_id, str) or not is_credential_id(credential_id):
            raise StepUpTokenRefused("the ID token names no WebAuthn credential")
        if not isinstance(aaguid, str) or not is_id_shaped(aaguid):
            raise StepUpTokenRefused("the ID token names no authenticator")
        jti = claims.get("jti")
        if not isinstance(jti, str) or not jti:
            raise StepUpTokenRefused("the ID token carries no id")
        assertion_ref = "stepup:" + hashlib.sha256(jti.encode("utf-8")).hexdigest()[:32]
        if assertion_ref in self._spent:
            raise StepUpReplayed("that ID token was already spent")
        expiry = claims.get("exp")
        # held while the verifier would still accept the token: exp plus its own
        # clock leeway (INT-563 review), so the replay window never reopens
        until = (
            datetime.fromtimestamp(expiry, UTC) + CLOCK_LEEWAY
            if isinstance(expiry, int) and not isinstance(expiry, bool)
            else now + CEREMONY_TTL + CLOCK_LEEWAY
        )
        self._spent[assertion_ref] = max(until, now + CEREMONY_TTL)
        return StepUpGrant(
            grant_id="sug_" + secrets.token_hex(16),
            subject=ceremony.subject,
            session_id=ceremony.session_id,
            action_id=ceremony.action_id,
            credential_id=credential_id,
            aaguid=aaguid,
            assertion_ref=assertion_ref,
            expires_at=now + GRANT_TTL,
        )

    def redeem(
        self, grant_id: str, *, subject: str, session_id: str, action_id: str
    ) -> StepUpGrant:
        """Spend a grant on the one approval it was made for.

        A grant presented by anyone else, or for another action, is refused
        and left alone: only its own caller can spend it, so a guessed or
        leaked id cannot be used to burn somebody else's step-up."""
        now = self.clock()
        self._sweep(now)
        grant = self._grants.get(grant_id) if isinstance(grant_id, str) else None
        if grant is None or (grant.subject, grant.session_id, grant.action_id) != (
            subject,
            session_id,
            action_id,
        ):
            raise StepUpUnknown("no live step-up for this approval")
        del self._grants[grant_id]
        return grant
