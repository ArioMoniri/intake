"""Where the model-lane control lives between the console and the callers.

The INT-182 shape: Redis, one JSON record, compare-and-set on the revision,
written only by ``services/api`` admin routes behind the ``DangerousAction``
registry and the write-ahead audit. A switch takes effect on the next call in
every process that reads this store — no deploy, no restart.

**Reads fail closed and loudly.** Unreachable, not JSON, or failing the model
is :class:`ModelLanesUnavailable` with a machine code, and a caller treats
that as "no hosted lane" (see :mod:`intake_platform.model_lanes.router`). The
one legitimate default is *no record at all*, which reads as
:meth:`ModelLanesControl.unconfigured` — every lane self-hosted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

import redis
from pydantic import ValidationError

from intake_platform.model_lanes.model import ModelLanesControl, require_bound_class

__all__ = [
    "CONTROL_KEY",
    "ENV_MODEL_LANES_REDIS_URL",
    "InMemoryModelLanesStore",
    "ModelLanesConflict",
    "ModelLanesReader",
    "ModelLanesStore",
    "ModelLanesUnavailable",
    "RedisModelLanesStore",
    "model_lanes_store_from_env",
]

ENV_MODEL_LANES_REDIS_URL: Final = "INTAKE_MODEL_LANES_REDIS_URL"
CONTROL_KEY: Final = "intake:model-lanes:v1:control"


class ModelLanesUnavailable(Exception):
    """The control could not be read or written. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ModelLanesConflict(Exception):
    """The record moved since the revision the writer expected."""

    code = "model_lanes_changed"


class ModelLanesReader(Protocol):
    def read(self) -> ModelLanesControl: ...


class ModelLanesStore(ModelLanesReader, Protocol):
    def write(self, control: ModelLanesControl, *, expected_revision: int) -> ModelLanesControl: ...


def _parse(raw: object) -> ModelLanesControl:
    if raw is None:
        return ModelLanesControl.unconfigured()
    if not isinstance(raw, bytes | str):
        raise ModelLanesUnavailable("model_lanes_malformed")
    try:
        return ModelLanesControl.model_validate_json(raw)
    except ValidationError:
        raise ModelLanesUnavailable("model_lanes_malformed") from None


def _require_step(control: ModelLanesControl, expected_revision: int) -> None:
    if control.revision != expected_revision + 1:
        raise ValueError("a write moves the revision by exactly one")


class RedisModelLanesStore:
    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    def read(self) -> ModelLanesControl:
        try:
            raw: object = self._r.get(CONTROL_KEY)
        except redis.RedisError:
            raise ModelLanesUnavailable("model_lanes_unreachable") from None
        return _parse(raw)

    def write(self, control: ModelLanesControl, *, expected_revision: int) -> ModelLanesControl:
        _require_step(control, expected_revision)
        payload = control.model_dump_json()
        try:
            with self._r.pipeline() as pipe:
                pipe.watch(CONTROL_KEY)  # type: ignore[no-untyped-call]  # redis-py leaves watch unannotated
                current = _parse(pipe.get(CONTROL_KEY))
                if current.revision != expected_revision:
                    raise ModelLanesConflict("the control moved since it was read")
                require_bound_class(current, control)
                pipe.multi()
                pipe.set(CONTROL_KEY, payload)
                pipe.execute()
        except redis.WatchError:
            raise ModelLanesConflict("the control moved while it was written") from None
        except redis.RedisError:
            raise ModelLanesUnavailable("model_lanes_unreachable") from None
        return control


class InMemoryModelLanesStore:
    """The same contract in one process — for a composition that has no Redis
    and for tests. Never a fallback for a configured Redis that is down."""

    def __init__(self, control: ModelLanesControl | None = None) -> None:
        self._control = control if control is not None else ModelLanesControl.unconfigured()

    def read(self) -> ModelLanesControl:
        return self._control

    def write(self, control: ModelLanesControl, *, expected_revision: int) -> ModelLanesControl:
        _require_step(control, expected_revision)
        if self._control.revision != expected_revision:
            raise ModelLanesConflict("the control moved since it was read")
        require_bound_class(self._control, control)
        self._control = control
        return control


def model_lanes_store_from_env(env: Mapping[str, str]) -> RedisModelLanesStore | None:
    """The configured store, or ``None`` — never a default address."""
    raw = env.get(ENV_MODEL_LANES_REDIS_URL, "").strip()
    if not raw:
        return None
    if not raw.startswith(("redis://", "rediss://")):
        raise ValueError(f"{ENV_MODEL_LANES_REDIS_URL} must be a redis:// or rediss:// URL")
    return RedisModelLanesStore(redis.Redis.from_url(raw))
