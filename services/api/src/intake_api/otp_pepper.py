"""INT-578 — the OTP pepper: the key a code is kept under, and nothing else.

INT-131 kept an OTP as ``sha256(pseudonym:code)``. A 6-digit code has 10⁶
values, so anyone holding a Redis dump and a pseudonym recovered the code with
a million hashes. Now the code is kept only as an HMAC-SHA-256 under a pepper
the API reads from OpenBao, ``secret/api/otp`` (field ``pepper``), and never
from the environment or the code (invariant 14). A dump without the pepper
holds nothing a caller can turn back into a code.

The same key derives the device binding: the App Attest key (or, in dev, the
install id) that asked for a code, kept as an HMAC as well, so the store never
holds the key id itself. The two derivations are domain-separated, and every
input is length-prefixed, so no pseudonym, request id or code can be shifted
into another field. INT-583 adds one more derivation, the key a device's push
token is sealed under at rest, separated from the others by its own domain.

**Where the pepper comes from.** Outside dev, and in dev on the OpenBao dev
server, OpenBao only: a missing or malformed document leaves the OTP tier
unconfigured (every ``/v1/auth`` route answers 503), and the log line names the
path and the field, never a value. The one exception is dev under
``INTAKE_API_KEK_MODE=file-dev`` — the sanctioned no-OpenBao escape, refused at
boot everywhere else (INT-325) — which takes a process-local random pepper,
exactly as that mode takes process-local KEKs. It is random per process, so a
code does not survive a restart there; that is the point of the mode.

**Shape.** Lower-case hex, 32 to 128 bytes. ``infra/staging/lib.sh``
(``ensure_otp_pepper``) and ``scripts/security/openbao_dev_setup.sh`` write 32
random bytes in that form.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

import httpx
from intake_platform.secrets import SecretsBootError, SecretsProvider

__all__ = [
    "OTP_PEPPER_FIELD",
    "OTP_PEPPER_KV_PATH",
    "OtpPepper",
    "OtpPepperError",
    "otp_pepper_from_vault",
]

logger = logging.getLogger("intake_api.otp_pepper")

#: KV v2 path under ``secret/``, inside the ``intake-api`` policy's grant.
OTP_PEPPER_KV_PATH: Final = "api/otp"
OTP_PEPPER_FIELD: Final = "pepper"
#: 32 to 128 bytes as lower-case hex.
_PEPPER_SHAPE = re.compile(r"(?:[0-9a-f]{2}){32,128}")
_CODE_DOMAIN: Final = b"intake.otp.code.v1"
_DEVICE_DOMAIN: Final = b"intake.otp.device.v1"
_RATE_DOMAIN: Final = b"intake.otp.rate.v1"
_PUSH_TOKEN_DOMAIN: Final = b"intake.push.token.v1"


class OtpPepperError(ValueError):
    """The pepper document is missing its value or holds a malformed one. The
    message names the path and the field, never the value."""


class KvSecrets(Protocol):
    """The slice of :class:`intake_platform.secrets.SecretsProvider` read here."""

    def get_kv(self, path: str) -> dict[str, Any]: ...


def _framed(domain: bytes, *parts: str) -> bytes:
    """``domain`` then each part as length || bytes: no part can bleed into
    the next, whatever characters it carries."""
    out = bytearray(domain)
    for part in parts:
        raw = part.encode("utf-8")
        out += len(raw).to_bytes(4, "big") + raw
    return bytes(out)


@dataclass(frozen=True)
class OtpPepper:
    """The key, held only in memory. ``repr`` and ``str`` show neither the key
    nor any part of it."""

    _key: bytes = field(repr=False)

    def __str__(self) -> str:
        return "OtpPepper(<held>)"

    @classmethod
    def parse(cls, document: Mapping[str, object]) -> OtpPepper:
        raw = document.get(OTP_PEPPER_FIELD)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raise OtpPepperError(
                f"OpenBao secret/{OTP_PEPPER_KV_PATH} is missing {OTP_PEPPER_FIELD}"
            )
        if not isinstance(raw, str) or not _PEPPER_SHAPE.fullmatch(raw):
            raise OtpPepperError(
                f"OpenBao secret/{OTP_PEPPER_KV_PATH} has a malformed {OTP_PEPPER_FIELD} "
                "(32 to 128 bytes of lower-case hex)"
            )
        return cls(bytes.fromhex(raw))

    @classmethod
    def ephemeral(cls) -> OtpPepper:
        """A process-local random pepper: dev under file-dev KEKs, and the test
        harnesses. Never a literal, never shared between processes."""
        return cls(secrets.token_bytes(32))

    def code_digest(self, pseudonym: str, request_id: str, code: str) -> str:
        """What the store keeps for a code: bound to the number's pseudonym and
        to the request that minted it, so the right digits under another
        request id are a different digest."""
        message = _framed(_CODE_DOMAIN, pseudonym, request_id, code)
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def device_binding(self, device: str) -> str:
        """What the store keeps for the device a code was minted for."""
        return hmac.new(self._key, _framed(_DEVICE_DOMAIN, device), hashlib.sha256).hexdigest()

    def rate_key(self, dimension: str, value: str) -> str:
        """INT-577: the identifier a request budget is counted under, for a
        value that must not sit in a Redis key in clear (a caller's address,
        a device). Keyed, because an IPv4 address has 2³² values and a plain
        hash of one is reversed by enumeration."""
        message = _framed(_RATE_DOMAIN, dimension, value)
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def push_token_key(self) -> bytes:
        """INT-583: the AES-256-GCM key a device's push token is sealed under in
        Redis (``intake_api.device_sessions``), derived and domain-separated
        like the derivations above. A store dump without the pepper holds no
        push token in clear."""
        return hmac.new(self._key, _framed(_PUSH_TOKEN_DOMAIN), hashlib.sha256).digest()


def otp_pepper_from_vault(secrets_reader: KvSecrets | None = None) -> OtpPepper | None:
    """The pepper from OpenBao, or None, which leaves the OTP tier at 503."""
    try:
        vault = secrets_reader if secrets_reader is not None else SecretsProvider.from_env()
        document = vault.get_kv(OTP_PEPPER_KV_PATH)
    except (SecretsBootError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "otp tier unconfigured: the OTP pepper is not readable from OpenBao secret/%s (%s)",
            OTP_PEPPER_KV_PATH,
            type(exc).__name__,
        )
        return None
    try:
        return OtpPepper.parse(document)
    except OtpPepperError as exc:
        logger.warning("otp tier unconfigured: %s", exc)
        return None
