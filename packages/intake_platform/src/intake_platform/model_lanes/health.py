"""Self-hosted lane health by identity, not address (INT-428, ADR-035).

:class:`SelfHostedHealth` does not call a lane healthy because something
answers at its URL — a loopback tunnel answers from anywhere. It asks the
endpoint who it is (``GET /identity`` → ``{model_id, revision,
weights_manifest_sha256}``) and the lane is healthy only when that identity is
the attested registry model the role resolved to. A call-time failure or a
per-call identity mismatch quarantines the lane for a cooldown.

The two errors every routed call can end in live here too, so the resolver
and the dispatcher share them without importing each other.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final

import httpx

from intake_platform.model_lanes.model import LANES, Lane
from intake_platform.model_lanes.models import ModelRef

__all__ = [
    "IDENTITY_PATH",
    "LaneIdentityMismatch",
    "LaneRefused",
    "SelfHostedHealth",
    "ServedIdentity",
    "self_hosted_endpoints_from_env",
]

IDENTITY_PATH: Final = "/identity"
_ENV_SELF_HOSTED: Final[Mapping[Lane, str]] = {
    lane: f"INTAKE_LANE_{lane.value.upper()}_SELF_HOSTED_URL" for lane in LANES
}


class LaneRefused(Exception):
    """The lane could not serve this call. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class LaneIdentityMismatch(Exception):
    """A backend answered as a model other than the one it was asked for."""

    code = "model_identity_mismatch"


def self_hosted_endpoints_from_env(env: Mapping[str, str]) -> dict[Lane, str | None]:
    """Each lane's self-hosted base URL, or ``None`` — never a default host.
    An address is only where to ask; who answers is the identity probe's."""
    return {lane: (env.get(name, "").strip() or None) for lane, name in _ENV_SELF_HOSTED.items()}


@dataclass(frozen=True)
class ServedIdentity:
    """What a self-hosted endpoint says it serves."""

    model_id: str
    revision: str
    weights_manifest_sha256: str

    def is_(self, ref: ModelRef) -> bool:
        return (
            ref.source == "self_hosted"
            and self.model_id == ref.model_id
            and self.revision == ref.version
            and self.weights_manifest_sha256 == ref.sha256
        )


def _identity_probe(url: str) -> ServedIdentity | None:
    try:
        response = httpx.get(f"{url.rstrip('/')}{IDENTITY_PATH}", timeout=2.0)
        body = response.json() if 200 <= response.status_code < 300 else None
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    fields = (body.get("model_id"), body.get("revision"), body.get("weights_manifest_sha256"))
    if not all(isinstance(value, str) and value for value in fields):
        return None
    model_id, revision, manifest = (str(value) for value in fields)
    return ServedIdentity(model_id, revision, manifest)


@dataclass
class SelfHostedHealth:
    """Cached identity per lane, with a quarantine cooldown on failure."""

    endpoints: Mapping[Lane, str | None]
    probe: Callable[[str], ServedIdentity | None] = _identity_probe
    ttl_s: float = 15.0
    cooldown_s: float = 30.0
    clock: Callable[[], float] = time.monotonic
    _seen: dict[Lane, tuple[float, ServedIdentity | None]] = field(default_factory=dict)
    _failed_at: dict[Lane, float] = field(default_factory=dict)

    def identity(self, lane: Lane, *, fresh: bool = False) -> ServedIdentity | None:
        url = self.endpoints.get(lane)
        if url is None:
            return None
        now = self.clock()
        failed = self._failed_at.get(lane)
        if failed is not None and now - failed < self.cooldown_s and not fresh:
            return None
        seen = self._seen.get(lane)
        if seen is None or fresh or now - seen[0] >= self.ttl_s:
            seen = (now, self.probe(url))
            self._seen[lane] = seen
            if seen[1] is not None:
                self._failed_at.pop(lane, None)
        return seen[1]

    def state(self, lane: Lane, expected: ModelRef | None, *, fresh: bool = False) -> str:
        """``healthy`` | ``unconfigured`` | ``unattested`` (no attested model to
        expect) | ``quarantined`` | ``unreachable`` | ``identity_mismatch``."""
        if self.endpoints.get(lane) is None:
            return "unconfigured"
        if expected is None:
            return "unattested"
        failed = self._failed_at.get(lane)
        if failed is not None and self.clock() - failed < self.cooldown_s and not fresh:
            return "quarantined"
        served = self.identity(lane, fresh=fresh)
        if served is None:
            return "unreachable"
        return "healthy" if served.is_(expected) else "identity_mismatch"

    def healthy(self, lane: Lane, expected: ModelRef | None, *, fresh: bool = False) -> bool:
        return self.state(lane, expected, fresh=fresh) == "healthy"

    def report_failure(self, lane: Lane) -> None:
        self._failed_at[lane] = self.clock()
