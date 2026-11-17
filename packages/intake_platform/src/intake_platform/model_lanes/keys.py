"""Hosted-provider API keys: OpenBao only, never echoed (INT-428, ADR-035).

**Where a key may exist.** In OpenBao KV v2 (invariant 14), under
``model-lanes/providers/<provider>``; while a key-set ceremony is pending, under
``model-lanes/staged/<action_id>``, from which the approval promotes it and
then destroys the staged copy. Never in the database, never in a log line,
never in an exception message, never in a response body. The console shows
``set`` / ``not set`` and the last four characters, at most.

**How that is held structurally rather than by care.** A key is a
:class:`ProviderApiKey`, whose ``repr``/``str`` are a fixed redaction, so a
stray f-string or a logged object prints nothing; the raw value leaves the
object only through :meth:`ProviderApiKey.reveal`, which the provider adapter
calls while building an ``Authorization`` header and nowhere else (a test
holds the call sites). Every failure here raises a code, never the store's own
error text, which can carry a path or a body.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol

import httpx

from intake_platform.model_lanes.model import KeyHolder, ProviderId

__all__ = [
    "KEY_PATH_PREFIX",
    "STAGED_PATH_PREFIX",
    "KeyStatus",
    "KeyVaultUnavailable",
    "KvBackend",
    "ProviderApiKey",
    "ProviderKeyMalformed",
    "ProviderKeyNotSet",
    "ProviderKeyVault",
]

KEY_PATH_PREFIX: Final = "model-lanes/providers/"
STAGED_PATH_PREFIX: Final = "model-lanes/staged/"
_KEY_SHAPE: Final = re.compile(r"^[A-Za-z0-9_.-]{20,512}$")
_ACTION_ID: Final = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_REDACTED: Final = "ProviderApiKey(redacted)"


class ProviderKeyMalformed(ValueError):
    code = "model_lanes_key_malformed"


class ProviderKeyNotSet(Exception):
    code = "hosted_key_not_set"


class KeyVaultUnavailable(Exception):
    def __init__(self, code: str = "model_lanes_key_store_unavailable") -> None:
        super().__init__(code)
        self.code = code


class ProviderApiKey:
    """A key value that will not print itself."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or _KEY_SHAPE.match(value) is None:
            # the message names the rule, never the value
            raise ProviderKeyMalformed("an API key is 20-512 characters of [A-Za-z0-9_.-]")
        self._value = value

    def reveal(self) -> str:
        """The raw value, for an ``Authorization`` header and nothing else."""
        return self._value

    @property
    def last4(self) -> str:
        return self._value[-4:]

    def __repr__(self) -> str:
        return _REDACTED

    __str__ = __repr__

    def __reduce__(self) -> tuple[Any, ...]:
        raise TypeError("a provider API key is not serialisable")


@dataclass(frozen=True)
class KeyStatus:
    """What the console may show: whether a key is set, its last four, and
    when. ``state`` is ``set`` | ``not_set`` | ``unknown`` (store unreachable)."""

    state: str
    last4: str | None = None
    set_at: str | None = None

    @property
    def is_set(self) -> bool:
        return self.state == "set"


class KvBackend(Protocol):
    """The OpenBao KV v2 calls this module needs (``SecretsProvider`` has them)."""

    def put_kv(self, path: str, data: dict[str, Any]) -> None: ...

    def get_kv(self, path: str) -> dict[str, Any]: ...

    def destroy_kv(self, path: str) -> None: ...

    def list_kv(self, path: str) -> list[str]: ...


def _require_action_id(action_id: str) -> str:
    if _ACTION_ID.match(action_id) is None:
        raise KeyVaultUnavailable("model_lanes_key_staging_malformed")
    return action_id


class ProviderKeyVault:
    """Read, stage, promote and report provider keys. Reads are cached for
    ``cache_ttl_s`` so a routing decision does not cost an OpenBao round trip
    per call; a promotion invalidates the cache at once."""

    def __init__(
        self,
        kv: KvBackend,
        *,
        cache_ttl_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._kv = kv
        self._ttl = cache_ttl_s
        self._clock = clock
        self._now = now if now is not None else (lambda: datetime.now(tz=UTC))
        self._cache: dict[KeyHolder, tuple[float, ProviderApiKey | None, KeyStatus]] = {}

    # -- reads -----------------------------------------------------------------------

    def _load(self, provider: KeyHolder) -> tuple[ProviderApiKey | None, KeyStatus]:
        cached = self._cache.get(provider)
        if cached is not None and self._clock() - cached[0] < self._ttl:
            return cached[1], cached[2]
        try:
            data = self._kv.get_kv(f"{KEY_PATH_PREFIX}{provider.value}")
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 404:
                entry: tuple[ProviderApiKey | None, KeyStatus] = (None, KeyStatus("not_set"))
                self._cache[provider] = (self._clock(), *entry)
                return entry
            raise KeyVaultUnavailable() from None
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise KeyVaultUnavailable() from None
        raw = data.get("api_key")
        try:
            key = ProviderApiKey(raw if isinstance(raw, str) else "")
        except ProviderKeyMalformed:
            raise KeyVaultUnavailable("model_lanes_key_store_malformed") from None
        set_at = data.get("set_at")
        status = KeyStatus("set", key.last4, set_at if isinstance(set_at, str) else None)
        self._cache[provider] = (self._clock(), key, status)
        return key, status

    def status(self, provider: KeyHolder) -> KeyStatus:
        """Never raises: an unreachable store is the ``unknown`` state."""
        try:
            return self._load(provider)[1]
        except KeyVaultUnavailable:
            return KeyStatus("unknown")

    def is_set(self, provider: KeyHolder) -> bool:
        return self.status(provider).is_set

    def key_for_call(self, provider: KeyHolder) -> ProviderApiKey:
        key, _ = self._load(provider)
        if key is None:
            raise ProviderKeyNotSet("no key is set for this provider")
        return key

    # -- the key-set ceremony ---------------------------------------------------------

    def stage(self, action_id: str, provider: ProviderId, key: ProviderApiKey) -> KeyStatus:
        """Hold a submitted key until its approval. Returns only what the
        approver's brief may show."""
        path = f"{STAGED_PATH_PREFIX}{_require_action_id(action_id)}"
        try:
            self._kv.put_kv(path, {"provider": provider.value, "api_key": key.reveal()})
        except httpx.HTTPError:
            raise KeyVaultUnavailable() from None
        return KeyStatus("staged", key.last4)

    def promote(self, action_id: str, provider: ProviderId) -> KeyStatus:
        """Move a staged key to the provider's path, then destroy the staged copy."""
        staged_path = f"{STAGED_PATH_PREFIX}{_require_action_id(action_id)}"
        try:
            data = self._kv.get_kv(staged_path)
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 404:
                raise KeyVaultUnavailable("model_lanes_key_staging_missing") from None
            raise KeyVaultUnavailable() from None
        except httpx.HTTPError:
            raise KeyVaultUnavailable() from None
        if data.get("provider") != provider.value:
            raise KeyVaultUnavailable("model_lanes_key_staging_mismatch")
        raw = data.get("api_key")
        try:
            key = ProviderApiKey(raw if isinstance(raw, str) else "")
        except ProviderKeyMalformed:
            raise KeyVaultUnavailable("model_lanes_key_store_malformed") from None
        set_at = self._now().isoformat()
        try:
            self._kv.put_kv(
                f"{KEY_PATH_PREFIX}{provider.value}",
                {"api_key": key.reveal(), "last4": key.last4, "set_at": set_at},
            )
        except httpx.HTTPError:
            raise KeyVaultUnavailable() from None
        self.discard(action_id)
        self._cache.pop(provider, None)
        return KeyStatus("set", key.last4, set_at)

    def staged_refs(self) -> tuple[str, ...]:
        """Every staged key's reference, for reaping the ones whose ceremony
        expired. An unreachable store raises; a reap that cannot list is a
        reap that did not happen, and says so."""
        try:
            refs = self._kv.list_kv(STAGED_PATH_PREFIX)
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise KeyVaultUnavailable() from None
        return tuple(ref for ref in refs if _ACTION_ID.match(ref) is not None)

    def discard(self, action_id: str) -> None:
        """Destroy a staged key (every version). Idempotent."""
        try:
            self._kv.destroy_kv(f"{STAGED_PATH_PREFIX}{_require_action_id(action_id)}")
        except httpx.HTTPStatusError as err:
            if err.response.status_code != 404:
                raise KeyVaultUnavailable() from None
        except httpx.HTTPError:
            raise KeyVaultUnavailable() from None
