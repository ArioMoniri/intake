"""SMART backend services: a signed assertion, a second host, one token.

INT-160 gave ``auth_mode`` a single member and said the second would arrive
with this issue "never as a relaxation of this one". This module is the second
member, and the shape of it is why it had to be one rather than a widening.

``mtls`` authenticates the **channel** with material OpenBao already holds, so
a push is one request to one host. SMART authenticates the **client**: we mint
a JWT assertion, sign it with a key the hospital has registered, exchange it
at the hospital's *authorization server* for a short-lived access token, and
present that token on the FHIR request. Two requests, two hosts, and the
second host is the part with security consequences — see
:meth:`~intake_connectors.destinations.ConnectorDestination.authorization_egress_entry`
for why it gets its own allow-list entry and its own purpose.

Four decisions worth stating, because each had a cheaper alternative:

**No discovery.** SMART defines ``/.well-known/smart-configuration``, and this
module never reads it. Discovery lets the receiver nominate the URL our client
credential is sent to — a redirect to an unchecked host wearing a standard's
name. The token endpoint and the assertion's ``aud`` both come from the
registry row.

**No token cache.** One push, one assertion, one token. A cached token is a
credential that outlives the consent check that authorised it, and INT-160
already refused to cache the consent verdict for that exact reason. The cost
is one extra round trip on a path that is not hot.

**The algorithm is derived from the key, not configured.** SMART permits RS384
and ES384. Reading the algorithm from the credential document would add a knob
whose only use is to be set wrong; the key's own type decides, and a key that
is neither (a P-256 key is fine crypto and is still not one of the two) fails
closed rather than being signed with the nearest available curve.

**The token response body *is* read, and the error body is not.** This is the
one deliberate exception to INT-160's never-read rule, and it is narrow. A
successful token response is a credential *we asked for*: it contains an
access token and a scope, no patient ever appears in it, and not reading it
would mean not having the token. It is read under a byte cap, parsed as JSON,
and accepted only as ``{access_token, token_type, scope?}`` with everything
else discarded. A **failing** token response is read not at all — the status
already separates our assertion (400) from our client identity (401) from
their outage (5xx), and an error document is free text we do not need.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

__all__ = [
    "ASSERTION_TYPE",
    "AccessToken",
    "SmartAuthorizationFailed",
    "build_client_assertion",
    "request_access_token",
    "scope_covers",
]

#: RFC 7523 / SMART backend services.
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

#: The ceiling on an assertion's life. SMART permits five minutes; sixty
#: seconds is enough for one exchange and nothing needs the other four.
_ASSERTION_CEILING = timedelta(seconds=60)

#: A token response is a small JSON document. Anything larger is not one, and
#: reading it to find that out is how a receiver chooses our memory usage.
_MAX_TOKEN_BODY_BYTES = 8192

#: An access token is an opaque string on the wire. Bounded and printable, so
#: it cannot smuggle a newline into a header or a megabyte into a process.
_MAX_TOKEN_CHARS = 4096

#: SMART v2 permission letters, and the v1 words that mean the same thing.
_V1_PERMISSIONS = {"read": frozenset("rs"), "write": frozenset("cud"), "*": frozenset("cruds")}
_V2_LETTERS = frozenset("cruds")


class SmartAuthorizationFailed(Exception):
    """No access token, and an id-shaped reason that came from us.

    ``code`` is the whole payload on purpose: it is drawn from this module's
    own closed set, never from a receiver's prose, so it is safe to put into
    a receipt, a metric label and an audit entry (invariant 6).
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, repr=False)
class AccessToken:
    """A bearer token with no representation containing itself.

    Same treatment as :class:`~intake_connectors.credentials.TlsMaterial`, and
    for the same reason: a credential leaks because a dataclass grew a default
    ``__repr__``, not because someone logged it deliberately. ``__str__`` is
    overridden alongside ``__repr__`` because overriding only the first leaves
    ``f"{token}"`` printing the secret.
    """

    value: str

    def __repr__(self) -> str:
        return "AccessToken(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def header(self) -> str:
        return f"Bearer {self.value}"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _segment(payload: dict[str, object]) -> str:
    return _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _signer(private_key_pem: str) -> tuple[str, Callable[[bytes], bytes]]:
    """Load the key once and let its own type name the algorithm.

    SMART permits RS384 and ES384. Reading the algorithm from the credential
    document instead would add a knob whose only use is to be set wrong, so
    the key decides — and a key that is neither (a P-256 key is perfectly good
    crypto and is still not one of the two) fails closed rather than being
    signed with the nearest available curve.

    Failures are raised as :class:`SmartAuthorizationFailed` rather than as
    the crypto exception: a traceback from ``load_pem_private_key`` can quote
    the material it was handed, and this failure has to be safe to record.
    """
    try:
        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    except Exception:  # noqa: BLE001 - the cause can quote the key bytes
        raise SmartAuthorizationFailed("key_unusable") from None
    if isinstance(key, rsa.RSAPrivateKey):
        rsa_key = key

        def sign_rs384(signing_input: bytes) -> bytes:
            return rsa_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA384())

        return "RS384", sign_rs384
    if isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name == "secp384r1":
        ec_key = key

        def sign_es384(signing_input: bytes) -> bytes:
            r, s = decode_dss_signature(ec_key.sign(signing_input, ec.ECDSA(hashes.SHA384())))
            # JOSE wants the raw R||S pair at fixed width. Handing over the
            # DER blob is the classic ES384 bug, and it fails at the receiver
            # rather than here, which is the worst place for it to fail.
            return r.to_bytes(48, "big") + s.to_bytes(48, "big")

        return "ES384", sign_es384
    raise SmartAuthorizationFailed("key_unsupported")


def build_client_assertion(
    *,
    client_id: str,
    token_url: str,
    private_key_pem: str,
    key_id: str | None,
    now: datetime,
    consent_expires_at: datetime | None,
) -> str:
    """One RFC 7523 assertion, scoped by the share consent it is acting under.

    ``exp`` is the **earlier** of our own sixty-second ceiling and the share
    consent's own expiry (files/06 §2.1 ``share:{recipient, visit, sections,
    expiry}``). That is what "scoped by share consent token" can mean at this
    layer and still be enforceable: the credential we present is valid only
    inside the window the patient's consent is valid, and a stale-consent
    authorization is then refused by the **hospital's** clock as well as ours.
    """
    expires_at = now + _ASSERTION_CEILING
    if consent_expires_at is not None:
        expires_at = min(expires_at, consent_expires_at)
    if expires_at <= now:
        raise SmartAuthorizationFailed("consent_expired")
    header: dict[str, object] = {"alg": "", "typ": "JWT"}
    if key_id is not None:
        header["kid"] = key_id
    claims: dict[str, object] = {
        "iss": client_id,
        "sub": client_id,
        "aud": token_url,
        "exp": int(expires_at.timestamp()),
        # Unique per assertion: an authorization server that replays a jti is
        # supposed to refuse it, and reusing one would make our own retries
        # indistinguishable from an attacker's replay.
        "jti": uuid.uuid4().hex,
    }
    algorithm, sign = _signer(private_key_pem)
    header["alg"] = algorithm
    signing_input = f"{_segment(header)}.{_segment(claims)}".encode("ascii")
    return f"{signing_input.decode('ascii')}.{_b64url(sign(signing_input))}"


def _parse_scope(scope: str) -> tuple[str, str, frozenset[str]] | None:
    """``system/Bundle.c`` → ``("system", "Bundle", {"c"})``; else ``None``."""
    context, _, rest = scope.partition("/")
    resource, dot, permission = rest.partition(".")
    if not context or not resource or not dot:
        return None
    if permission in _V1_PERMISSIONS:
        return context, resource, _V1_PERMISSIONS[permission]
    letters = frozenset(permission)
    if not permission or not letters <= _V2_LETTERS:
        return None
    return context, resource, letters


def scope_covers(granted: str, requested: str) -> bool:
    """Does the grant include what we asked for?

    Space-delimited, per RFC 6749. A grant covers the request when some
    granted scope has the same context, names the same resource or ``*``, and
    carries at least the requested permissions. Both SMART v1 (``.read`` /
    ``.write``) and v2 (``.cruds``) spellings are understood, because real
    servers ship both and a scope we fail to parse would fail closed on a
    grant that was actually fine.
    """
    wanted = _parse_scope(requested)
    if wanted is None:
        return False
    context, resource, permissions = wanted
    for candidate in granted.split():
        parsed = _parse_scope(candidate)
        if parsed is None:
            continue
        their_context, their_resource, their_permissions = parsed
        if their_context != context:
            continue
        if their_resource not in (resource, "*"):
            continue
        if permissions <= their_permissions:
            return True
    return False


def _read_capped(response: httpx.Response) -> bytes:
    body = b""
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > _MAX_TOKEN_BODY_BYTES:
            raise SmartAuthorizationFailed("token_response_too_large")
    return body


def _token_from(body: bytes, requested_scope: str) -> AccessToken:
    try:
        document = json.loads(body)
    except ValueError:
        raise SmartAuthorizationFailed("token_response_malformed") from None
    if not isinstance(document, dict):
        raise SmartAuthorizationFailed("token_response_malformed")
    token_type = document.get("token_type")
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise SmartAuthorizationFailed("token_type_unsupported")
    value = document.get("access_token")
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _MAX_TOKEN_CHARS
        or not value.isascii()
        or any(character.isspace() for character in value)
    ):
        raise SmartAuthorizationFailed("token_malformed")
    granted = document.get("scope")
    # RFC 6749 §5.1: an omitted scope means the grant is identical to the
    # request. Treating silence as a denial would break conformant servers;
    # treating it as a wildcard would be the opposite mistake.
    if isinstance(granted, str) and not scope_covers(granted, requested_scope):
        raise SmartAuthorizationFailed("scope_not_granted")
    return AccessToken(value)


def request_access_token(
    client: httpx.Client, *, token_url: str, assertion: str, scope: str
) -> AccessToken:
    """Exchange the assertion for a token, over an already-guarded client.

    The client is built by the sender from the destination's
    ``authorization_egress_entry()``, so the allow-list, the denied-range
    refusal, the resolve-once-and-pin and the redirect refusal are the INT-018
    code and not a second implementation of it (ADR-025's "one engine").
    """
    request = client.build_request(
        "POST",
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": ASSERTION_TYPE,
            "client_assertion": assertion,
            "scope": scope,
        },
        headers={"Accept": "application/json"},
    )
    try:
        response = client.send(request, stream=True)
    except httpx.TransportError:
        # Nothing clinical was in flight, so there is no ambiguity to park:
        # the push simply has not happened.
        raise SmartAuthorizationFailed("token_unreachable") from None
    try:
        if response.status_code != 200:
            # The status is the whole diagnosis. 400 is our assertion, 401 is
            # our client identity, 403 is our registration, 5xx is theirs —
            # and an error document adds prose to a question already answered.
            raise SmartAuthorizationFailed(f"token_http_{response.status_code}")
        body = _read_capped(response)
    finally:
        response.close()
    return _token_from(body, scope)
