"""Feature-flag facade (INT-023; CLAUDE.md inv. 12/18/19; files/10 §5).

OpenFeature-shaped without the dependency: the ``openfeature-sdk`` package is
pure Python (Apache-2.0) but drags a full evaluation-API surface (clients,
hooks, evaluation details) that nothing here needs — the provider shape below
(``get_bool`` + swappable provider) is the part of the contract we use, so it
is implemented directly with zero new dependencies (httpx is already a
platform dependency).

Posture:

- :class:`InMemoryProvider` is the DEFAULT. No environment, no network.
- :class:`UnleashProvider` exists only when ``INTAKE_UNLEASH_URL`` is set
  (:func:`default_provider`), speaks the Unleash client API over httpx with a
  200 ms budget, and falls CLOSED to the in-memory defaults on *any* failure:
  a flag backend outage must never take a service down or open a gate.
- The four safety flags are pre-declared False and outrank the call-site
  default in both providers; only a payload that explicitly carries a boolean
  ``enabled`` can decide them. The authority for flipping them in production
  is the gated-capability service of files/10 §0b (inv. 34/48) — Unleash is
  rollout plumbing, not the safety authority.
- Flag reads are logged as ``flag_read flag=... value=... provider=...``.
  The evaluation ``ctx`` is accepted for provider-interface compatibility but
  is never logged and never transmitted (inv. 6 — nothing session-scoped
  leaves through the flag path).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from types import MappingProxyType, TracebackType
from typing import Final, Protocol

import httpx

__all__ = [
    "SAFETY_FLAG_DEFAULTS",
    "UNLEASH_TIMEOUT_SECONDS",
    "FlagProvider",
    "InMemoryProvider",
    "UnleashProvider",
    "default_provider",
]

logger = logging.getLogger(__name__)

UNLEASH_TIMEOUT_SECONDS: Final[float] = 0.2

#: Safety flags stay False until their gate opens for a tenant:
#: - device_functions — inv. 18: off without a recorded CE certificate or
#:   clinical-investigation approval id (gate test INT-117);
#: - s2s — inv. 19: the profile does not exist; the flag exists to assert it;
#: - learning_apply — inv. 12: learning is proposal-only, never auto-apply;
#: - satisfaction_prompts — İYS posture (inv. 18): no prompt without consent;
#: - guardian_link — INT-223: persisting a guardian↔minor relationship is a
#:   new personal-data category (CLAUDE.md stop-and-ask), so the linkage
#:   store stays unwritable AND unreadable until counsel assigns a basis.
SAFETY_FLAG_DEFAULTS: Final[Mapping[str, bool]] = MappingProxyType(
    {
        "device_functions": False,
        "s2s": False,
        "learning_apply": False,
        "satisfaction_prompts": False,
        "guardian_link": False,
    }
)


def _log_flag_read(flag: str, value: bool, provider: str) -> None:
    # name/value/provider only — ctx never reaches a log line (inv. 6).
    logger.info("flag_read flag=%s value=%s provider=%s", flag, value, provider)


class FlagProvider(Protocol):
    """The provider contract: a boolean evaluation with a caller default."""

    name: str

    def get_bool(self, flag: str, default: bool, ctx: Mapping[str, str] | None = None) -> bool: ...


class InMemoryProvider:
    """Dict-seeded provider — the default. Safety flags are always present,
    so a caller default can never open one; an explicit seed can."""

    name = "in_memory"

    def __init__(self, seed: Mapping[str, bool] | None = None) -> None:
        flags: dict[str, bool] = dict(SAFETY_FLAG_DEFAULTS)
        flags.update(seed or {})
        self._flags = flags

    def get_bool(self, flag: str, default: bool, ctx: Mapping[str, str] | None = None) -> bool:
        value = self._flags.get(flag, default)
        _log_flag_read(flag, value, self.name)
        return value


class UnleashProvider:
    """Unleash client-API provider. Fail-closed by construction: any error,
    timeout, non-200 or non-boolean payload delegates to the in-memory
    defaults — only an explicit boolean ``enabled`` decides a flag."""

    name = "unleash"

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        fallback: InMemoryProvider | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = UNLEASH_TIMEOUT_SECONDS
        self._fallback = fallback if fallback is not None else InMemoryProvider()
        headers = {"Authorization": token} if token else {}
        self._client = httpx.Client(
            base_url=url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(UNLEASH_TIMEOUT_SECONDS),
            transport=transport,
        )

    def get_bool(self, flag: str, default: bool, ctx: Mapping[str, str] | None = None) -> bool:
        # ctx is deliberately NOT sent: no query params, no body — nothing
        # session-scoped leaves the service through the flag path.
        try:
            response = self._client.get(f"/api/client/features/{flag}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # class name only — never the error text, which can quote the
            # request (inv. 6). Flags never take a service down: fall closed.
            logger.warning(
                "unleash unavailable (%s); flag %s falls closed to in-memory defaults",
                type(exc).__name__,
                flag,
            )
            return self._fallback.get_bool(flag, default, ctx)
        enabled = payload.get("enabled") if isinstance(payload, dict) else None
        if isinstance(enabled, bool):
            _log_flag_read(flag, enabled, self.name)
            return enabled
        # payload did not explicitly decide → the safe default decides.
        return self._fallback.get_bool(flag, default, ctx)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> UnleashProvider:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def default_provider() -> FlagProvider:
    """In-memory unless ``INTAKE_UNLEASH_URL`` is set — the Unleash provider
    is constructed only behind that config, never by default."""
    url = os.environ.get("INTAKE_UNLEASH_URL")
    if url:
        return UnleashProvider(url, token=os.environ.get("INTAKE_UNLEASH_TOKEN"))
    return InMemoryProvider()
