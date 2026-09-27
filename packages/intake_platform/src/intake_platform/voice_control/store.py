"""Where the voice control lives between the admin API and the runtime (INT-182).

The kill switch works "without a deploy" (files/02 §375) only if the runtime
reads the control from somewhere the console can write while both keep
running. That somewhere is Redis — already a platform dependency, already
reached by both services' dependency tree — and **not** the generic flag
store: files/08 §3 and §6 put the kill switch outside Unleash, whose API
tokens flip flags with no audit row (invariant 34, §0b F1). The only writer
of this store is ``services/api/admin``, behind the ``DangerousAction``
registry and the write-ahead audit.

**Reads fail closed and loudly.** An unreachable server, a record that is not
JSON, or one that fails the model is :class:`VoiceControlUnavailable` with a
machine code — never a silent default. The runtime turns that into a
``typed`` session start; the console turns it into an unknown tile. The one
legitimate default is a tenant with **no** record, which reads as
:meth:`TenantVoiceControl.unconfigured` — typed — so a store that lost its keys
falls every tenant to the safer transport too.

**Writes are compare-and-set on the revision** (``WATCH``/``MULTI``). A
four-eyes approval binds to the revision its brief showed, so a control that
moved in between — say, the kill switch pulled after a profile switch was
requested — refuses the approval instead of applying it over the new state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

import redis
from pydantic import ValidationError

from intake_platform.voice_control.model import TenantVoiceControl, require_tenant_id

__all__ = [
    "ENV_VOICE_CONTROL_REDIS_URL",
    "KEY_PREFIX",
    "RedisVoiceControlStore",
    "VoiceControlConflict",
    "VoiceControlReader",
    "VoiceControlStore",
    "VoiceControlUnavailable",
    "voice_control_store_from_env",
]

#: Set to the SAME Redis in the API and in the voice runtime. Unset, the API's
#: voice mutations answer 503 and the runtime's speech worker is not ready.
ENV_VOICE_CONTROL_REDIS_URL: Final = "INTAKE_VOICE_CONTROL_REDIS_URL"
KEY_PREFIX: Final = "intake:voice-control:v1:"


class VoiceControlUnavailable(Exception):
    """The control could not be read or written. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VoiceControlConflict(Exception):
    """The record moved since the revision the writer expected."""

    code = "voice_control_changed"


class VoiceControlReader(Protocol):
    """What the runtime needs: one tenant's control, read now."""

    def read(self, tenant_id: str) -> TenantVoiceControl: ...


class VoiceControlStore(VoiceControlReader, Protocol):
    """What the console needs on top: a compare-and-set write and a listing."""

    def write(
        self, control: TenantVoiceControl, *, expected_revision: int
    ) -> TenantVoiceControl: ...

    def tenants(self) -> tuple[TenantVoiceControl, ...]: ...


def _parse(raw: object, tenant_id: str) -> TenantVoiceControl:
    if raw is None:
        return TenantVoiceControl.unconfigured(tenant_id)
    if not isinstance(raw, bytes | str):
        raise VoiceControlUnavailable("voice_control_malformed")
    try:
        control = TenantVoiceControl.model_validate_json(raw)
    except ValidationError:
        # hide_input_in_errors keeps the bytes out of the message; the message
        # itself is dropped here too — a code is all that leaves
        raise VoiceControlUnavailable("voice_control_malformed") from None
    if control.tenant_id != tenant_id:
        raise VoiceControlUnavailable("voice_control_malformed")
    return control


class RedisVoiceControlStore:
    """One JSON record per tenant under :data:`KEY_PREFIX`."""

    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    @staticmethod
    def key(tenant_id: str) -> str:
        return f"{KEY_PREFIX}{require_tenant_id(tenant_id)}"

    def read(self, tenant_id: str) -> TenantVoiceControl:
        key = self.key(tenant_id)
        try:
            raw: object = self._r.get(key)
        except redis.RedisError:
            raise VoiceControlUnavailable("voice_control_unreachable") from None
        return _parse(raw, tenant_id)

    def write(self, control: TenantVoiceControl, *, expected_revision: int) -> TenantVoiceControl:
        if control.revision != expected_revision + 1:
            raise ValueError("a write moves the revision by exactly one")
        key = self.key(control.tenant_id)
        payload = control.model_dump_json()
        try:
            with self._r.pipeline() as pipe:
                pipe.watch(key)  # type: ignore[no-untyped-call]  # redis-py leaves watch unannotated
                current = _parse(pipe.get(key), control.tenant_id)
                if current.revision != expected_revision:
                    raise VoiceControlConflict("the control moved since it was read")
                pipe.multi()
                pipe.set(key, payload)
                pipe.execute()
        except redis.WatchError:
            raise VoiceControlConflict("the control moved while it was written") from None
        except redis.RedisError:
            raise VoiceControlUnavailable("voice_control_unreachable") from None
        return control

    def tenants(self) -> tuple[TenantVoiceControl, ...]:
        """Every configured tenant, sorted by id."""
        try:
            keys = sorted(
                key.decode("utf-8") if isinstance(key, bytes) else str(key)
                for key in self._r.scan_iter(match=f"{KEY_PREFIX}*")
            )
        except redis.RedisError:
            raise VoiceControlUnavailable("voice_control_unreachable") from None
        controls: list[TenantVoiceControl] = []
        for key in keys:
            tenant_id = key.removeprefix(KEY_PREFIX)
            try:
                require_tenant_id(tenant_id)
            except ValueError:
                raise VoiceControlUnavailable("voice_control_malformed") from None
            controls.append(self.read(tenant_id))
        return tuple(controls)


def voice_control_store_from_env(env: Mapping[str, str]) -> RedisVoiceControlStore | None:
    """The configured store, or ``None`` — never a default address. A value
    that is not a ``redis://``/``rediss://`` URL raises: a guessed store is
    worse than none, because the runtime would read a kill switch nobody can
    reach."""
    raw = env.get(ENV_VOICE_CONTROL_REDIS_URL, "").strip()
    if not raw:
        return None
    if not raw.startswith(("redis://", "rediss://")):
        raise ValueError(f"{ENV_VOICE_CONTROL_REDIS_URL} must be a redis:// or rediss:// URL")
    return RedisVoiceControlStore(redis.Redis.from_url(raw))
