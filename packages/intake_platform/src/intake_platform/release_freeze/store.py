"""Where the deploy freeze lives between the console and the deploy path (INT-187).

The freeze stops a deploy only if the deploy path reads it from somewhere the
console writes while both keep running. That somewhere is the deployment's own
Redis — already a dependency of the API, append-only-file persisted in the
staging tier — and **not** the generic flag store: Unleash API tokens flip
flags with no audit row and CI runners hold them (files/08 §3, §6; invariant
34), so a freeze kept there could be lifted by the very pipeline it holds. The
only writer is ``services/api/admin`` behind the ``DangerousAction`` registry
and the write-ahead audit; the reader is ``intake_api.admin.release_gate``,
which ``infra/staging/deploy.sh`` runs before it touches the host.

**Reads fail closed and loudly.** An unreachable server, a record that is not
JSON, or one that fails the model is :class:`ReleaseFreezeUnavailable` with a
machine code — never "not frozen". The one legitimate default is a store with
**no** record, which reads as :meth:`DeployFreeze.unconfigured`.

**Writes are compare-and-set on the revision** (``WATCH``/``MULTI``), so a lift
approval binds to the revision its brief showed and a freeze that moved in
between refuses the approval instead of being silently undone.

**The URL carries the Redis password.** Nothing here ever echoes it: a
malformed value is refused by its variable's name, and a connection failure is
a code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

import redis
from pydantic import ValidationError

from intake_platform.release_freeze.model import DeployFreeze

__all__ = [
    "ENV_RELEASE_FREEZE_REDIS_URL",
    "FREEZE_KEY",
    "RedisReleaseFreezeStore",
    "ReleaseFreezeConflict",
    "ReleaseFreezeStore",
    "ReleaseFreezeUnavailable",
    "release_freeze_store_from_env",
]

#: Set on the API. Unset, the freeze controls answer 503, the console's freeze
#: tile reads unknown and the deploy gate refuses: a deploy path that cannot
#: see the freeze does not get to assume there is none.
ENV_RELEASE_FREEZE_REDIS_URL: Final = "INTAKE_RELEASE_FREEZE_REDIS_URL"
FREEZE_KEY: Final = "intake:release-freeze:v1"


class ReleaseFreezeUnavailable(Exception):
    """The freeze could not be read or written. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ReleaseFreezeConflict(Exception):
    """The record moved since the revision the writer expected."""

    code = "release_freeze_changed"


class ReleaseFreezeStore(Protocol):
    """The freeze, read now, and a compare-and-set write."""

    def read(self) -> DeployFreeze: ...

    def write(self, freeze: DeployFreeze, *, expected_revision: int) -> DeployFreeze: ...


def _parse(raw: object) -> DeployFreeze:
    if raw is None:
        return DeployFreeze.unconfigured()
    if not isinstance(raw, bytes | str):
        raise ReleaseFreezeUnavailable("release_freeze_malformed")
    try:
        return DeployFreeze.model_validate_json(raw)
    except ValidationError:
        # hide_input_in_errors keeps the bytes out of the message; the message
        # itself is dropped here too — a code is all that leaves
        raise ReleaseFreezeUnavailable("release_freeze_malformed") from None


class RedisReleaseFreezeStore:
    """One JSON record under :data:`FREEZE_KEY`."""

    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    def read(self) -> DeployFreeze:
        try:
            raw: object = self._r.get(FREEZE_KEY)
        except redis.RedisError:
            raise ReleaseFreezeUnavailable("release_freeze_unreachable") from None
        return _parse(raw)

    def write(self, freeze: DeployFreeze, *, expected_revision: int) -> DeployFreeze:
        if freeze.revision != expected_revision + 1:
            raise ValueError("a write moves the revision by exactly one")
        payload = freeze.model_dump_json()
        try:
            with self._r.pipeline() as pipe:
                pipe.watch(FREEZE_KEY)  # type: ignore[no-untyped-call]  # redis-py leaves watch unannotated
                current = _parse(pipe.get(FREEZE_KEY))
                if current.revision != expected_revision:
                    raise ReleaseFreezeConflict("the freeze moved since it was read")
                pipe.multi()
                pipe.set(FREEZE_KEY, payload)
                pipe.execute()
        except redis.WatchError:
            raise ReleaseFreezeConflict("the freeze moved while it was written") from None
        except redis.RedisError:
            raise ReleaseFreezeUnavailable("release_freeze_unreachable") from None
        return freeze


def release_freeze_store_from_env(env: Mapping[str, str]) -> RedisReleaseFreezeStore | None:
    """The configured store, or ``None`` — never a default address. A value
    that is not a ``redis://``/``rediss://`` URL raises, naming the variable
    and never the value (it carries a password)."""
    raw = env.get(ENV_RELEASE_FREEZE_REDIS_URL, "").strip()
    if not raw:
        return None
    if not raw.startswith(("redis://", "rediss://")):
        raise ValueError(f"{ENV_RELEASE_FREEZE_REDIS_URL} must be a redis:// or rediss:// URL")
    # short timeouts: the deploy gate must answer "unreachable", not hang
    return RedisReleaseFreezeStore(
        redis.Redis.from_url(raw, socket_connect_timeout=5.0, socket_timeout=5.0)
    )
