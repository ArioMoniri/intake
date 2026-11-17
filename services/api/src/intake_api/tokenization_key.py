"""INT-584 (owner decision D38) — the phone-tokenization key, from OpenBao only.

Every keyed pseudonym the API derives — a phone number in the OTP tier, a
hospital patient number in the previsit read-back, a device's foreign id on the
RED path — is an HMAC under one key (:class:`intake_platform.tokenization.Tokenizer`).
Until INT-584 the synthetic host kept that key in its root-only env file and
``ApiSettings.from_env`` read it from ``INTAKE_TOKENIZATION_KEY``. D38 (28 Oct
2026) moves it into OpenBao at ``secret/api/tokenization`` (field ``key``),
carrying the same key material across so that no pseudonym changes; the
synthetic host's ``infra/staging/tokenization_key.sh`` does the move and proves
it. The API now reads the key there and nowhere else (invariant 14):

- **No environment variable is read**, in any environment, and a key left in
  the environment is never a fallback. One is named (never shown) in a warning.
- **The key is the hex text's UTF-8 bytes**, exactly as the env path used it.
  It is never hex-decoded: decoding would change every pseudonym on the host.
  Its shape is what every writer produces: 64 to 256 lower-case hex characters.
- **Absent, unreadable and malformed are told apart.** Each leaves the OTP
  tier and the previsit read-back at 503 with ``tokenization_key_<state>`` as
  the typed reason; the log line names the path and the state, never a value.
- **Dev** reads the OpenBao dev server like every environment
  (``scripts/security/openbao_dev_setup.sh`` makes a random key there, once).
  The one exception is dev under ``INTAKE_API_KEK_MODE=file-dev``, the
  sanctioned no-OpenBao escape refused at boot everywhere else (INT-325): it
  takes a process-local random key, as that mode takes process-local KEKs, so
  its pseudonyms do not survive a restart.
- The document's ``origin`` (``env_file`` for a key carried across by D38,
  ``generated`` for one made in OpenBao) and the state reach
  ``tokenization_key_state{state,origin}``, a closed vocabulary of ids.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Protocol

import httpx
from intake_platform.secrets import SecretsBootError, SecretsProvider
from prometheus_client import Gauge

if TYPE_CHECKING:
    from intake_api.settings import ApiSettings

__all__ = [
    "KEY_FIELD",
    "KEY_SHAPE",
    "ORIGIN_FIELD",
    "TOKENIZATION_KEY_STATE",
    "TOKENIZATION_KV_PATH",
    "KvSecrets",
    "TokenizationKeyOrigin",
    "TokenizationKeyResolution",
    "TokenizationKeyState",
    "parse_tokenization_document",
    "resolve_tokenization_key",
    "with_tokenization_key",
]

logger = logging.getLogger("intake_api.tokenization_key")

#: KV v2 path under ``secret/``, inside the ``intake-api`` policy's read grant.
TOKENIZATION_KV_PATH: Final = "api/tokenization"
KEY_FIELD: Final = "key"
ORIGIN_FIELD: Final = "origin"
#: The shape lib.sh's gen_secret and the dev setup write: lower-case hex TEXT.
KEY_SHAPE: Final = re.compile(r"[0-9a-f]{64,256}")
#: The variable the env path read. Named in a warning when set, never read.
_RETIRED_ENV_KEY: Final = "INTAKE_TOKENIZATION_KEY"  # noqa: S105 — a name, not a value


class TokenizationKeyState(StrEnum):
    """Where the key resolution ended. ``tokenization_key_<value>`` is the
    typed 503 reason of every tier that needs the key."""

    LOADED = "loaded"
    #: OpenBao answered and holds no key at the path
    ABSENT = "absent"
    #: OpenBao unconfigured, unreachable, sealed, or refusing the API's token
    UNREADABLE = "unreadable"
    #: a value is there, and it is not a key the API accepts
    MALFORMED = "malformed"


class TokenizationKeyOrigin(StrEnum):
    """Where a loaded key came from; ``none`` when no key loaded."""

    #: carried across from the synthetic host's env file (D38)
    ENV_FILE = "env_file"
    #: made in OpenBao (init.sh on a new host, the dev setup)
    GENERATED = "generated"
    #: dev under file-dev KEKs only
    PROCESS_LOCAL = "process_local"
    #: a document that names no origin this module knows
    UNRECORDED = "unrecorded"
    NONE = "none"


#: The origins a document may record; ``process_local`` is never one.
_DOCUMENT_ORIGINS: Final = {
    TokenizationKeyOrigin.ENV_FILE.value: TokenizationKeyOrigin.ENV_FILE,
    TokenizationKeyOrigin.GENERATED.value: TokenizationKeyOrigin.GENERATED,
}

TOKENIZATION_KEY_STATE: Final = Gauge(
    "tokenization_key_state",
    "Where the API's phone-tokenization key came from (INT-584): 1 on the "
    "current state and origin, set at wiring.",
    ("state", "origin"),
)


class KvSecrets(Protocol):
    """The slice of :class:`intake_platform.secrets.SecretsProvider` read here."""

    def get_kv(self, path: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class TokenizationKeyResolution:
    """The outcome of one resolution. ``key`` never reaches ``repr``;
    ``cause`` says why a resolution has no key, in words that carry no value."""

    state: TokenizationKeyState
    origin: TokenizationKeyOrigin
    key: str | None = field(default=None, repr=False)
    cause: str = ""

    def __post_init__(self) -> None:
        if (self.key is not None) != (self.state is TokenizationKeyState.LOADED):
            raise ValueError("a resolution carries a key exactly when it is loaded")

    @property
    def refusal(self) -> str | None:
        """The typed 503 reason, or ``None`` when a key loaded."""
        if self.state is TokenizationKeyState.LOADED:
            return None
        return f"tokenization_key_{self.state.value}"


def _without_key(state: TokenizationKeyState, cause: str) -> TokenizationKeyResolution:
    return TokenizationKeyResolution(state=state, origin=TokenizationKeyOrigin.NONE, cause=cause)


def parse_tokenization_document(document: Mapping[str, object]) -> TokenizationKeyResolution:
    """The resolution a KV document makes. A missing or blank key is absent; a
    key of any other shape is malformed. Nothing about the value is echoed."""
    raw = document.get(KEY_FIELD)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return _without_key(TokenizationKeyState.ABSENT, f"the document has no {KEY_FIELD}")
    if not isinstance(raw, str) or not KEY_SHAPE.fullmatch(raw):
        return _without_key(
            TokenizationKeyState.MALFORMED, "not 64 to 256 lower-case hex characters"
        )
    recorded = document.get(ORIGIN_FIELD)
    origin = (
        _DOCUMENT_ORIGINS.get(recorded, TokenizationKeyOrigin.UNRECORDED)
        if isinstance(recorded, str)
        else TokenizationKeyOrigin.UNRECORDED
    )
    return TokenizationKeyResolution(state=TokenizationKeyState.LOADED, origin=origin, key=raw)


def _read(secrets_reader: KvSecrets | None) -> Mapping[str, object] | TokenizationKeyResolution:
    """The document, or the keyless resolution that stopped the read. Only the
    exception's class (and an HTTP status) is kept: never its message."""
    try:
        vault = secrets_reader if secrets_reader is not None else SecretsProvider.from_env()
        return vault.get_kv(TOKENIZATION_KV_PATH)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        state = TokenizationKeyState.ABSENT if status == 404 else TokenizationKeyState.UNREADABLE
        cause = f"{type(exc).__name__} {status}"
    except (SecretsBootError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        state = TokenizationKeyState.UNREADABLE
        cause = type(exc).__name__
    return _without_key(state, cause)


def resolve_tokenization_key(
    settings: ApiSettings, secrets_reader: KvSecrets | None = None
) -> TokenizationKeyResolution:
    """The key from OpenBao, or why there is none. Dev under file-dev KEKs
    alone takes a process-local random key and reads no vault."""
    if settings.kek_mode == "file-dev" and settings.dev_tier_expected:
        return TokenizationKeyResolution(
            state=TokenizationKeyState.LOADED,
            origin=TokenizationKeyOrigin.PROCESS_LOCAL,
            key=secrets.token_hex(32),
        )
    document = _read(secrets_reader)
    if isinstance(document, TokenizationKeyResolution):
        return document
    return parse_tokenization_document(document)


def _record(resolution: TokenizationKeyResolution) -> None:
    TOKENIZATION_KEY_STATE.clear()
    TOKENIZATION_KEY_STATE.labels(state=resolution.state.value, origin=resolution.origin.value).set(
        1
    )


def with_tokenization_key(
    settings: ApiSettings, secrets_reader: KvSecrets | None = None
) -> ApiSettings:
    """``settings`` with the key resolved in, or with the typed reason it is
    not. The wiring calls this once, at start; the OTP tier, the previsit
    read-back and the RED path read the result."""
    if os.environ.get(_RETIRED_ENV_KEY):
        logger.warning(
            "%s is set in this process's environment and is ignored: the key is read "
            "from OpenBao secret/%s only (INT-584)",
            _RETIRED_ENV_KEY,
            TOKENIZATION_KV_PATH,
        )
    resolution = resolve_tokenization_key(settings, secrets_reader)
    _record(resolution)
    if resolution.state is TokenizationKeyState.LOADED:
        source = (
            "a process-local source"
            if resolution.origin is TokenizationKeyOrigin.PROCESS_LOCAL
            else f"OpenBao secret/{TOKENIZATION_KV_PATH}"
        )
        logger.info("phone-tokenization key loaded from %s (%s)", source, resolution.origin.value)
    else:
        logger.warning(
            "phone-tokenization key %s at OpenBao secret/%s (%s): the OTP tier and the "
            "previsit read-back answer 503 %s",
            resolution.state.value,
            TOKENIZATION_KV_PATH,
            resolution.cause,
            resolution.refusal,
        )
    return replace(
        settings,
        tokenization_key=resolution.key,
        tokenization_key_refusal=resolution.refusal,
    )
