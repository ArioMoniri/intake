"""Where Safety inbox entries live between the RED path and the console (INT-406).

The RED is determined in the voice runtime; the queue is read and answered in
the API's console. The store is the one place both already reach: Redis — the
INT-182 voice-control store's precedent, and for the same reason. No hospital
connector is on this path, which is what "regardless of connector presence"
(files/02 §8.2, §2b) needs: an entry exists whether or not a tenant has any
connector at all.

**Keys** (all under :data:`KEY_PREFIX`):

- ``entry:<tenant>:<entry_id>`` — the entry, as its JSON model;
- ``open`` — sorted set of ``<tenant>:<entry_id>`` for every unacknowledged
  entry, scored by ``created_at`` (the sweep's one read);
- ``tenant:<tenant>`` — sorted set of every entry id of one tenant (the
  console's read);
- ``visit:<tenant>:<visit_id>`` — set of the RED entry ids of one visit
  (files/02 §2b's "is this a RED visit?").

A tenant id never contains ``:`` and an entry id is ``sx_<hex>``, so every
member splits one way.

**Writes are transactions.** ``add`` is ``WATCH``/``MULTI``: an entry already
there is returned as it is (first write wins, so a replayed RED keeps its
first clock), otherwise the record and its three indexes are written in one
``EXEC``. ``acknowledge`` is the same compare-and-set, so two people pressing
the button at once record one acknowledgement and the second is told so.

**Reads fail closed and loudly.** An unreachable server, a record that is not
JSON, one that fails the model, or one filed under another entry's key is
:class:`SafetyInboxUnavailable` with a machine code — never a skipped row. A
queue with a silently missing entry is a RED that nobody is shown.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Final, Protocol

import redis
from pydantic import ValidationError

from intake_platform.safety_inbox.model import (
    AlreadyAcknowledged,
    EntryKind,
    InboxEntry,
    require_id,
    require_subject,
    require_tenant_id,
)

__all__ = [
    "ENV_SAFETY_INBOX_REDIS_URL",
    "KEY_PREFIX",
    "EntryNotFound",
    "RedisSafetyInboxStore",
    "SafetyInboxStore",
    "SafetyInboxUnavailable",
    "safety_inbox_store_from_env",
]

#: Set to the SAME Redis in the API and in the voice runtime. Unset, the
#: console's Safety queue answers 503 and the runtime is not ready.
ENV_SAFETY_INBOX_REDIS_URL: Final = "INTAKE_SAFETY_INBOX_REDIS_URL"
KEY_PREFIX: Final = "intake:safety-inbox:v1:"
_OPEN: Final = f"{KEY_PREFIX}open"
#: A concurrent writer moved the entry between the read and the write; re-read.
_ATTEMPTS: Final = 3


class SafetyInboxUnavailable(Exception):
    """The inbox could not be read or written. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EntryNotFound(LookupError):
    """No such entry in this tenant. Another tenant's entry is not found too."""

    code = "safety_entry_not_found"


class SafetyInboxStore(Protocol):
    def add(self, entry: InboxEntry) -> InboxEntry:
        """Store the entry, or return the one already stored under its id."""
        ...

    def get(self, tenant_id: str, entry_id: str) -> InboxEntry | None: ...

    def acknowledge(self, tenant_id: str, entry_id: str, *, by: str, at: datetime) -> InboxEntry:
        """Record the acknowledgement once; :class:`AlreadyAcknowledged` after."""
        ...

    def open_entries(self) -> tuple[InboxEntry, ...]:
        """Every unacknowledged entry of every tenant, oldest first."""
        ...

    def tenant_entries(self, tenant_id: str) -> tuple[InboxEntry, ...]:
        """Every entry of one tenant, oldest first."""
        ...

    def red_entries_for_visit(self, tenant_id: str, visit_id: str) -> tuple[InboxEntry, ...]: ...

    def tenants(self) -> tuple[str, ...]:
        """Every tenant with at least one entry, sorted."""
        ...


def _text(raw: object) -> str:
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


class RedisSafetyInboxStore:
    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    @staticmethod
    def _entry_key(tenant_id: str, entry_id: str) -> str:
        return f"{KEY_PREFIX}entry:{require_tenant_id(tenant_id)}:{entry_id}"

    @staticmethod
    def _tenant_key(tenant_id: str) -> str:
        return f"{KEY_PREFIX}tenant:{require_tenant_id(tenant_id)}"

    @staticmethod
    def _visit_key(tenant_id: str, visit_id: str) -> str:
        return f"{KEY_PREFIX}visit:{require_tenant_id(tenant_id)}:{require_id(visit_id)}"

    @staticmethod
    def _parse(raw: object, tenant_id: str, entry_id: str) -> InboxEntry:
        if not isinstance(raw, bytes | str):
            raise SafetyInboxUnavailable("safety_inbox_malformed")
        try:
            entry = InboxEntry.model_validate_json(raw)
        except ValidationError:
            # hide_input_in_errors keeps the bytes out; only a code leaves
            raise SafetyInboxUnavailable("safety_inbox_malformed") from None
        if entry.tenant_id != tenant_id or entry.entry_id != entry_id:
            raise SafetyInboxUnavailable("safety_inbox_malformed")
        return entry

    # --- writes ------------------------------------------------------------------------

    def add(self, entry: InboxEntry) -> InboxEntry:
        key = self._entry_key(entry.tenant_id, entry.entry_id)
        score = entry.created_at.timestamp()
        for _ in range(_ATTEMPTS):
            try:
                with self._r.pipeline() as pipe:
                    pipe.watch(key)  # type: ignore[no-untyped-call]  # redis-py leaves watch unannotated
                    existing = pipe.get(key)
                    if existing is not None:
                        return self._parse(existing, entry.tenant_id, entry.entry_id)
                    pipe.multi()
                    pipe.set(key, entry.model_dump_json())
                    pipe.zadd(self._tenant_key(entry.tenant_id), {entry.entry_id: score})
                    if entry.is_open:
                        pipe.zadd(_OPEN, {f"{entry.tenant_id}:{entry.entry_id}": score})
                    if entry.kind is EntryKind.RED:
                        pipe.sadd(self._visit_key(entry.tenant_id, entry.visit_id), entry.entry_id)
                    pipe.execute()
                    return entry
            except redis.WatchError:
                continue
            except redis.RedisError:
                raise SafetyInboxUnavailable("safety_inbox_unreachable") from None
        raise SafetyInboxUnavailable("safety_inbox_contended")

    def acknowledge(self, tenant_id: str, entry_id: str, *, by: str, at: datetime) -> InboxEntry:
        require_subject(by)
        key = self._entry_key(tenant_id, entry_id)
        for _ in range(_ATTEMPTS):
            try:
                with self._r.pipeline() as pipe:
                    pipe.watch(key)  # type: ignore[no-untyped-call]  # redis-py leaves watch unannotated
                    raw = pipe.get(key)
                    if raw is None:
                        raise EntryNotFound("no such entry in this tenant")
                    current = self._parse(raw, tenant_id, entry_id)
                    if not current.is_open:
                        raise AlreadyAcknowledged("the entry was already acknowledged")
                    acked = current.acknowledge(by=by, at=at)
                    pipe.multi()
                    pipe.set(key, acked.model_dump_json())
                    pipe.zrem(_OPEN, f"{tenant_id}:{entry_id}")
                    pipe.execute()
                    return acked
            except redis.WatchError:
                continue
            except redis.RedisError:
                raise SafetyInboxUnavailable("safety_inbox_unreachable") from None
        raise SafetyInboxUnavailable("safety_inbox_contended")

    # --- reads -------------------------------------------------------------------------

    def get(self, tenant_id: str, entry_id: str) -> InboxEntry | None:
        key = self._entry_key(tenant_id, entry_id)
        try:
            raw = self._r.get(key)
        except redis.RedisError:
            raise SafetyInboxUnavailable("safety_inbox_unreachable") from None
        if raw is None:
            return None
        return self._parse(raw, tenant_id, entry_id)

    def _load(self, pairs: Iterable[tuple[str, str]]) -> tuple[InboxEntry, ...]:
        wanted = list(pairs)
        if not wanted:
            return ()
        try:
            raws = self._r.mget([self._entry_key(tenant, entry) for tenant, entry in wanted])
        except redis.RedisError:
            raise SafetyInboxUnavailable("safety_inbox_unreachable") from None
        entries: list[InboxEntry] = []
        for (tenant_id, entry_id), raw in zip(wanted, raws, strict=True):
            if raw is None:
                # an index names an entry whose record is gone: never skipped
                raise SafetyInboxUnavailable("safety_inbox_malformed")
            entries.append(self._parse(raw, tenant_id, entry_id))
        return tuple(entries)

    def _members(self, key: str, *, ordered: bool) -> list[str]:
        try:
            raw: Any = self._r.zrange(key, 0, -1) if ordered else self._r.smembers(key)
        except redis.RedisError:
            raise SafetyInboxUnavailable("safety_inbox_unreachable") from None
        members = [_text(member) for member in raw]
        return members if ordered else sorted(members)

    def open_entries(self) -> tuple[InboxEntry, ...]:
        pairs: list[tuple[str, str]] = []
        for member in self._members(_OPEN, ordered=True):
            tenant_id, sep, entry_id = member.partition(":")
            if not sep:
                raise SafetyInboxUnavailable("safety_inbox_malformed")
            pairs.append((tenant_id, entry_id))
        try:
            return self._load(pairs)
        except ValueError:
            raise SafetyInboxUnavailable("safety_inbox_malformed") from None

    def tenant_entries(self, tenant_id: str) -> tuple[InboxEntry, ...]:
        members = self._members(self._tenant_key(tenant_id), ordered=True)
        return self._load((tenant_id, member) for member in members)

    def red_entries_for_visit(self, tenant_id: str, visit_id: str) -> tuple[InboxEntry, ...]:
        members = self._members(self._visit_key(tenant_id, visit_id), ordered=False)
        entries = self._load((tenant_id, member) for member in members)
        return tuple(sorted(entries, key=lambda entry: entry.created_at))

    def tenants(self) -> tuple[str, ...]:
        """Every tenant with at least one entry, sorted."""
        try:
            keys = [_text(key) for key in self._r.scan_iter(match=f"{KEY_PREFIX}tenant:*")]
        except redis.RedisError:
            raise SafetyInboxUnavailable("safety_inbox_unreachable") from None
        return tuple(sorted(key.removeprefix(f"{KEY_PREFIX}tenant:") for key in keys))


def safety_inbox_store_from_env(env: Mapping[str, str]) -> RedisSafetyInboxStore | None:
    """The configured store, or ``None`` — never a default address. A value
    that is not a ``redis://``/``rediss://`` URL raises: a guessed store is an
    inbox nobody reads."""
    raw = env.get(ENV_SAFETY_INBOX_REDIS_URL, "").strip()
    if not raw:
        return None
    if not raw.startswith(("redis://", "rediss://")):
        raise ValueError(f"{ENV_SAFETY_INBOX_REDIS_URL} must be a redis:// or rediss:// URL")
    return RedisSafetyInboxStore(redis.Redis.from_url(raw))
