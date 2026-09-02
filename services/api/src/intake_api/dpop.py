"""DPoP proof verification (RFC 9449 shape) — INT-131, files/10 §2.

Refresh tokens are device-bound: the client holds a P-256 key, sends a
compact-JWS proof per request, and every token we issue is bound to that
key's RFC 7638 thumbprint (``jkt``). Verification here is deliberately
self-contained over ``cryptography`` — no JOSE library, no algorithm
negotiation: the ONLY accepted header is ``{"typ": "dpop+jwt", "alg":
"ES256", "jwk": <EC P-256 public key>}``, which removes the classic JWS
``alg`` confusion surface. Every failure raises :class:`DpopError` with a
machine code (invariant 6: codes, never narrative)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

__all__ = [
    "DPOP_IAT_WINDOW_S",
    "DpopError",
    "DpopProof",
    "jwk_thumbprint",
    "verify_dpop_proof",
]

# Acceptance window for the proof's iat (client clock skew allowance).
DPOP_IAT_WINDOW_S = 300

_MAX_PROOF_BYTES = 4096
_MAX_JTI_CHARS = 128


class DpopError(Exception):
    """A refused proof; ``code`` is the machine-readable reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DpopProof:
    """The verified claims a proof carries once its signature checked out."""

    jkt: str
    jti: str
    htm: str
    htu: str
    iat: int
    ath: str | None


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + pad)
    except (binascii.Error, ValueError) as exc:
        raise DpopError("dpop_malformed") from exc


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def jwk_thumbprint(jwk: dict[str, str]) -> str:
    """RFC 7638 thumbprint of an EC JWK — the ``jkt`` tokens are bound to."""
    ordered = {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]}
    digest = hashlib.sha256(json.dumps(ordered, separators=(",", ":")).encode("utf-8")).digest()
    return _b64url(digest)


def _normalise_htu(url: str) -> str:
    """RFC 9449 §4.3: compare without query and fragment."""
    base = url.split("#", 1)[0].split("?", 1)[0]
    scheme, sep, rest = base.partition("://")
    return scheme.lower() + sep + rest


def _decode_json(segment: str) -> dict[str, object]:
    try:
        decoded = json.loads(_b64url_decode(segment))
    except ValueError as exc:
        raise DpopError("dpop_malformed") from exc
    if not isinstance(decoded, dict):
        raise DpopError("dpop_malformed")
    return dict(decoded)


def _public_key(jwk: dict[str, str]) -> ec.EllipticCurvePublicKey:
    x = _b64url_decode(jwk["x"])
    y = _b64url_decode(jwk["y"])
    if len(x) != 32 or len(y) != 32:
        raise DpopError("dpop_malformed")
    numbers = ec.EllipticCurvePublicNumbers(
        int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()
    )
    try:
        return numbers.public_key()
    except ValueError as exc:  # point not on the curve
        raise DpopError("dpop_malformed") from exc


def _require_str(claims: dict[str, object], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise DpopError("dpop_malformed")
    return value


def verify_dpop_proof(
    proof: str,
    *,
    method: str,
    url: str,
    now: int | None = None,
    access_token: str | None = None,
) -> DpopProof:
    """Verify one compact-JWS DPoP proof against the request it accompanies.

    ``access_token`` set → the proof MUST carry the matching ``ath`` claim
    (resource requests); unset → issuance/refresh, where no token exists yet.
    jti single-use is the caller's job (it needs the shared replay cache).
    """
    if len(proof) > _MAX_PROOF_BYTES:
        raise DpopError("dpop_malformed")
    parts = proof.split(".")
    if len(parts) != 3:
        raise DpopError("dpop_malformed")
    header_b64, claims_b64, signature_b64 = parts

    header = _decode_json(header_b64)
    if header.get("typ") != "dpop+jwt" or header.get("alg") != "ES256":
        raise DpopError("dpop_header")
    jwk_raw = header.get("jwk")
    if not isinstance(jwk_raw, dict):
        raise DpopError("dpop_header")
    jwk = {k: v for k, v in jwk_raw.items() if isinstance(k, str) and isinstance(v, str)}
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or "x" not in jwk or "y" not in jwk:
        raise DpopError("dpop_header")

    signature = _b64url_decode(signature_b64)
    if len(signature) != 64:
        raise DpopError("dpop_malformed")
    der = encode_dss_signature(
        int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    )
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")
    try:
        _public_key(jwk).verify(der, signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise DpopError("dpop_signature") from exc

    claims = _decode_json(claims_b64)
    jti = _require_str(claims, "jti")
    if len(jti) > _MAX_JTI_CHARS:
        raise DpopError("dpop_malformed")
    htm = _require_str(claims, "htm")
    if htm != method.upper():
        raise DpopError("dpop_htm")
    htu = _require_str(claims, "htu")
    if _normalise_htu(htu) != _normalise_htu(url):
        raise DpopError("dpop_htu")
    iat = claims.get("iat")
    if not isinstance(iat, int):
        raise DpopError("dpop_malformed")
    reference = int(now if now is not None else time.time())
    if abs(reference - iat) > DPOP_IAT_WINDOW_S:
        raise DpopError("dpop_stale")

    ath = claims.get("ath")
    if access_token is not None:
        expected = _b64url(hashlib.sha256(access_token.encode("ascii")).digest())
        if ath != expected:
            raise DpopError("dpop_ath")
    return DpopProof(
        jkt=jwk_thumbprint(jwk),
        jti=jti,
        htm=htm,
        htu=htu,
        iat=iat,
        ath=ath if isinstance(ath, str) else None,
    )
