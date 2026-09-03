"""Keycloak access-token verification (INT-180; files/08 §2, ADR-017).

Self-contained over ``cryptography``, exactly as :mod:`intake_api.dpop` does
for DPoP proofs, and for the same reason: **no algorithm negotiation.** The
only accepted header algorithm is ``RS256``, so the classic JWS ``alg``
confusion surface — ``none``, or an HMAC verified against a public key — does
not exist here rather than being defended against. A JOSE library would bring
negotiation back by default.

**No network.** The verifier is handed a key set; it never fetches one.
Keycloak publishes its JWKS at a well-known URL, and mirroring that document
onto disk (``INTAKE_ADMIN_OIDC_JWKS_PATH``) keeps the most privileged surface
in the system free of a runtime dependency on an identity provider being
reachable, keeps CI free of a live call, and makes key rotation a deploy with
a diff rather than an invisible refresh. An unknown ``kid`` is refused.

**Every check is mandatory.** Issuer, audience, expiry and not-before are all
verified; none is optional and none has a permissive default. The refusal
carries a machine code and never the token, the claim value, or the reason in
prose (invariant 6).
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from intake_platform.admin.principal import ClaimsRejected

__all__ = ["KeycloakClaimsVerifier", "load_jwks"]

#: Clock skew allowance, matching the DPoP tier's window (INT-131).
_LEEWAY_S = 300
#: A Keycloak access token is well under this; the cap bounds the parse.
_MAX_TOKEN_BYTES = 8192
_REQUIRED_ALG = "RS256"


def _b64url(segment: str) -> bytes:
    padding_needed = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding_needed)
    except (binascii.Error, ValueError):
        raise ClaimsRejected("token segment is not base64url") from None


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ClaimsRejected("token segment is not JSON") from None
    if not isinstance(parsed, dict):
        raise ClaimsRejected("token segment is not a JSON object")
    return parsed


def load_jwks(document: Mapping[str, Any]) -> dict[str, rsa.RSAPublicKey]:
    """Parse a JWKS into ``kid -> RSA public key``.

    Only RSA signing keys usable with RS256 are loaded. A key the verifier
    would refuse to use anyway is dropped here rather than at verification
    time, so an operator can see from the loaded count that a rotation
    landed. An empty result raises: a key set with nothing in it would make
    every token fail with an unknown-``kid`` code that hides the real fault.
    """
    keys: dict[str, rsa.RSAPublicKey] = {}
    for entry in document.get("keys", ()):
        if not isinstance(entry, Mapping):
            continue
        kid, kty = entry.get("kid"), entry.get("kty")
        if not isinstance(kid, str) or kty != "RSA":
            continue
        if entry.get("use") not in (None, "sig"):
            continue
        if entry.get("alg") not in (None, _REQUIRED_ALG):
            continue
        modulus, exponent = entry.get("n"), entry.get("e")
        if not isinstance(modulus, str) or not isinstance(exponent, str):
            continue
        numbers = rsa.RSAPublicNumbers(
            e=int.from_bytes(_b64url(exponent), "big"),
            n=int.from_bytes(_b64url(modulus), "big"),
        )
        keys[kid] = numbers.public_key()
    if not keys:
        raise ValueError(
            "the JWKS document carries no RS256-usable RSA signing key; the console "
            "would refuse every token with an unknown-kid code that hides this fault"
        )
    return keys


def _utc_epoch() -> int:
    return int(datetime.now(tz=UTC).timestamp())


@dataclass(frozen=True)
class KeycloakClaimsVerifier:
    """Verify a Keycloak access token and return its claims.

    Satisfies :class:`~intake_platform.admin.principal.AdminClaimsVerifier`
    structurally; the console holds it behind that Protocol and never reaches
    for a key or a signature itself.
    """

    issuer: str
    audience: str
    keys: Mapping[str, rsa.RSAPublicKey]
    clock: Callable[[], int] = _utc_epoch

    def verify(self, token: str) -> Mapping[str, Any]:
        if len(token.encode("utf-8")) > _MAX_TOKEN_BYTES:
            raise ClaimsRejected("token exceeds the accepted size")
        parts = token.split(".")
        if len(parts) != 3:
            raise ClaimsRejected("token is not a three-part compact JWS")
        header_segment, payload_segment, signature_segment = parts
        header = _json_object(_b64url(header_segment))
        if header.get("alg") != _REQUIRED_ALG:
            # the whole alg-confusion family — 'none', HS256 against a public
            # key, a downgraded curve — dies on this one line
            raise ClaimsRejected("unsupported signature algorithm")
        kid = header.get("kid")
        if not isinstance(kid, str):
            raise ClaimsRejected("token header names no key id")
        key = self.keys.get(kid)
        if key is None:
            raise ClaimsRejected("token was signed by an unknown key")
        try:
            key.verify(
                _b64url(signature_segment),
                f"{header_segment}.{payload_segment}".encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            raise ClaimsRejected("signature does not verify") from None
        claims = _json_object(_b64url(payload_segment))
        self._check_claims(claims)
        return claims

    def _check_claims(self, claims: Mapping[str, Any]) -> None:
        if claims.get("iss") != self.issuer:
            raise ClaimsRejected("token was issued by another issuer")
        audience = claims.get("aud")
        accepted = (audience,) if isinstance(audience, str) else tuple(audience or ())
        if self.audience not in accepted:
            raise ClaimsRejected("token was not issued for this audience")
        now = self.clock()
        expiry = claims.get("exp")
        if not isinstance(expiry, int) or isinstance(expiry, bool):
            raise ClaimsRejected("token carries no integer expiry")
        if now > expiry + _LEEWAY_S:
            raise ClaimsRejected("token has expired")
        not_before = claims.get("nbf")
        if isinstance(not_before, int) and not isinstance(not_before, bool):
            if now + _LEEWAY_S < not_before:
                raise ClaimsRejected("token is not yet valid")
