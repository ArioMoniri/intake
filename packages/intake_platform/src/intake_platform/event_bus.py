"""Redis-streams event bus: typed producers/consumers, retries, DLQ (INT-035).

Acceptance, verbatim: "typed producers/consumers with retries, DLQ,
exactly-once handlers via idempotency keys; consumer lag metric".

Shape of the bus, pinned by tests/platform/test_event_bus.py:

- **Typed edges.** ``Producer[E]`` / ``Consumer[E]`` bind to one pydantic
  event model (the INT-031 set in ``clinical_schemas.events``). ``publish``
  re-validates the serialised payload through the model, so a value that
  fails its schema — including a ``model_construct`` validation bypass —
  never reaches the stream, and the refusal names field paths only, never
  values (invariant 6). The consumer re-validates on receipt; a payload
  failing the schema dead-letters immediately, because a deterministic
  failure gains nothing from retries.
- **At-least-once transport, exactly-once side effects.** XREADGROUP/XACK
  delivers at least once; XAUTOCLAIM recovers deliveries a crashed consumer
  never acked. The handler runs behind ``HandlerIdempotency`` — the INT-176
  replay-suppression scheme (``intake_platform.security.idempotency``)
  re-scoped from (principal, route, key) to (event id, handler name):
  sha256-scoped key, NX in-flight claim with a short TTL, done-marker on
  success, release on failure. A redelivery of an already-handled event
  skips the side effect and just acknowledges.
- **Retries are group-local.** A failed delivery is requeued onto
  ``<stream>.retry.<group>`` with ``attempts`` and ``not_before_ms``
  (exponential backoff, capped) carried in the message itself; the injected
  millisecond clock decides readiness, so tests never sleep. A re-add onto
  the source stream would double-deliver to every other consumer group.
- **DLQ per source stream.** ``<stream>.dlq`` receives the typed payload
  plus a closed ``reason`` code — never exception text, which could carry
  PHI (invariant 6).
- **Metrics** (declared in observability/metrics_catalog.yaml, inv. 13):
  ``event_bus_consumer_lag`` (undelivered + pending across the source and
  retry streams), ``event_bus_retried_total``,
  ``event_bus_dead_lettered_total``.

Redis ≥ 7 semantics are assumed (the compose pin is redis:7.4): XAUTOCLAIM
drops trimmed entries from the PEL itself, so claimed messages always carry
fields. Clients are binary (no ``decode_responses``), like the rest of the
platform.
"""

from __future__ import annotations

import enum
import hashlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

import redis
from prometheus_client import Counter, Gauge, disable_created_metrics
from pydantic import BaseModel, ValidationError

# The wire shapes redis-py hands back for stream replies (binary client, no
# decode_responses). The library's own annotations are loose unions, so the
# call sites below narrow through these via ``cast``.
_RawFields = dict[bytes | str, bytes | str]
_RawEntries = list[tuple[bytes | str, _RawFields]]

__all__ = [
    "EVENT_BUS_CONSUMER_LAG",
    "EVENT_BUS_DEAD_LETTERED_TOTAL",
    "EVENT_BUS_RETRIED_TOTAL",
    "ClaimOutcome",
    "Clock",
    "Consumer",
    "DeadLetterReason",
    "EventSchemaError",
    "HandlerIdempotency",
    "PollResult",
    "Producer",
    "dlq_stream",
    "retry_stream",
]

# Same rationale as intake_platform.metrics: the `_created` companion series
# would be served without appearing in the catalogue (inv. 13).
disable_created_metrics()  # type: ignore[no-untyped-call]  # upstream def has no annotations

EVENT_BUS_CONSUMER_LAG = Gauge(
    "event_bus_consumer_lag",
    "Unprocessed messages for one consumer group: undelivered plus pending "
    "entries across the source stream and its group-local retry stream.",
    ["stream", "group"],
)

EVENT_BUS_RETRIED_TOTAL = Counter(
    "event_bus_retried_total",
    "Event deliveries requeued for retry after a handler failure, by source "
    "stream and consumer group.",
    ["stream", "group"],
)

EVENT_BUS_DEAD_LETTERED_TOTAL = Counter(
    "event_bus_dead_lettered_total",
    "Events moved to the per-stream dead-letter stream, by source stream, "
    "consumer group and closed reason code.",
    ["stream", "group", "reason"],
)

#: Milliseconds-now provider. Wall clock in production (``not_before_ms``
#: must survive a process restart); injected as a fake in tests.
Clock = Callable[[], int]

ClaimOutcome = Literal["claimed", "done", "in_flight"]

# TTLs mirror intake_platform.security.idempotency (INT-176): a day for the
# done marker, and a short in-flight TTL so a crash mid-handle poisons the
# key for at most a minute before the delivery becomes retryable again.
_DONE_TTL_S = 24 * 3600
_IN_FLIGHT_TTL_S = 60
_IN_FLIGHT = b"__in_flight__"
_DONE = b"__done__"

_FIELD_EVENT_ID = "event_id"
_FIELD_PAYLOAD = "payload"
_FIELD_ATTEMPTS = "attempts"
_FIELD_NOT_BEFORE_MS = "not_before_ms"


def _now_ms() -> int:
    return int(time.time() * 1000)


def dlq_stream(stream: str) -> str:
    """The dead-letter stream for a source stream (one DLQ per source)."""
    return f"{stream}.dlq"


def retry_stream(stream: str, group: str) -> str:
    """The group-local retry stream: failures never fan out to other groups."""
    return f"{stream}.retry.{group}"


class DeadLetterReason(enum.StrEnum):
    """Closed reason codes for DLQ entries — codes only, never exception
    text, which could carry PHI (invariant 6)."""

    HANDLER_ERROR = "handler_error"
    SCHEMA_INVALID = "schema_invalid"


class EventSchemaError(ValueError):
    """Raised when a payload fails its event schema at the publish boundary.

    The message carries the model name and offending field paths only —
    field values (which may be patient-authored) never appear (invariant 6).
    """


def _schema_error_message(event_type: type[BaseModel], exc: ValidationError) -> str:
    paths = sorted(
        {
            ".".join(str(part) for part in error["loc"]) or "<root>"
            for error in exc.errors(include_url=False, include_input=False)
        }
    )
    return f"payload failed the {event_type.__name__} schema at: {', '.join(paths)}"


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _decode_fields(raw: _RawFields) -> dict[str, str]:
    return {_decode(key): _decode(value) for key, value in raw.items()}


def _xadd(client: redis.Redis, stream: str, fields: dict[str, str]) -> None:
    # redis-py's xadd parameter is invariant in its dict key/value unions, so
    # a plain str→str mapping — which is what actually goes over the wire —
    # does not unify with it; the cast is the whole point of this helper.
    client.xadd(stream, cast("dict[Any, Any]", fields))


class Producer[E: BaseModel]:
    """Typed producer for one stream: only payloads that pass ``event_type``'s
    schema ever reach Redis."""

    def __init__(self, redis_client: redis.Redis, *, stream: str, event_type: type[E]) -> None:
        self._redis = redis_client
        self._stream = stream
        self._event_type = event_type

    def publish(self, event: E) -> str:
        """Validate, enqueue, and return the bus-assigned event id.

        The serialised payload is re-validated through the event model: a
        wrong-model instance or a ``model_construct`` bypass raises
        ``EventSchemaError`` (``from None`` — the pydantic original embeds
        input values, which must not travel; invariant 6).
        """
        payload = event.model_dump_json()
        try:
            self._event_type.model_validate_json(payload)
        except ValidationError as exc:
            raise EventSchemaError(_schema_error_message(self._event_type, exc)) from None
        event_id = str(uuid.uuid4())
        _xadd(
            self._redis,
            self._stream,
            {_FIELD_EVENT_ID: event_id, _FIELD_PAYLOAD: payload, _FIELD_ATTEMPTS: "0"},
        )
        return event_id


class HandlerIdempotency:
    """INT-176's replay-suppression scheme, re-scoped to the bus.

    ``intake_platform.security.idempotency`` suppresses HTTP replays with a
    sha256-scoped key, an NX in-flight claim under a short TTL, and release
    on failure so a failed first attempt stays retryable. This class is the
    same scheme keyed on (event id, handler name): the unit of exactly-once
    is one handler's side effect for one event, so two different handlers
    each run once for the same event.
    """

    def __init__(self, redis_client: redis.Redis, *, key_prefix: str = "event_bus:idem") -> None:
        self._redis = redis_client
        self._prefix = key_prefix

    def _key(self, *, event_id: str, handler_name: str) -> str:
        digest = hashlib.sha256("\x1f".join([handler_name, event_id]).encode()).hexdigest()
        return f"{self._prefix}:{digest}"

    def claim(self, *, event_id: str, handler_name: str) -> ClaimOutcome:
        """Try to claim the right to execute. ``done`` means the side effect
        already happened (skip and ack); ``in_flight`` means another consumer
        holds it (leave the delivery pending for a later poll)."""
        key = self._key(event_id=event_id, handler_name=handler_name)
        if self._redis.set(key, _IN_FLIGHT, nx=True, ex=_IN_FLIGHT_TTL_S):
            return "claimed"
        return "done" if self._redis.get(key) == _DONE else "in_flight"

    def mark_done(self, *, event_id: str, handler_name: str) -> None:
        key = self._key(event_id=event_id, handler_name=handler_name)
        self._redis.set(key, _DONE, ex=_DONE_TTL_S)

    def release(self, *, event_id: str, handler_name: str) -> None:
        """A failed attempt must stay retryable (INT-176 release-on-failure)."""
        self._redis.delete(self._key(event_id=event_id, handler_name=handler_name))


@dataclass
class PollResult:
    """What one ``Consumer.poll`` did, by outcome."""

    handled: int = 0
    retried: int = 0
    dead_lettered: int = 0
    deferred: int = 0
    duplicates: int = 0
    in_flight: int = 0


class Consumer[E: BaseModel]:
    """Typed consumer: one consumer group per handler over one source stream.

    ``poll`` claims stale pending deliveries (XAUTOCLAIM — crash recovery),
    reads new ones (XREADGROUP) from the source and the group-local retry
    stream, and drives each through validate → idempotency claim → handler →
    ack, with capped exponential-backoff retries and a per-source DLQ.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        stream: str,
        group: str,
        consumer_name: str,
        event_type: type[E],
        handler: Callable[[E], None],
        handler_name: str,
        clock: Clock = _now_ms,
        max_attempts: int = 5,
        backoff_base_ms: int = 1_000,
        backoff_cap_ms: int = 60_000,
        claim_min_idle_ms: int = 30_000,
        idempotency: HandlerIdempotency | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._redis = redis_client
        self._stream = stream
        self._group = group
        self._consumer_name = consumer_name
        self._event_type = event_type
        self._handler = handler
        self._handler_name = handler_name
        self._clock = clock
        self._max_attempts = max_attempts
        self._backoff_base_ms = backoff_base_ms
        self._backoff_cap_ms = backoff_cap_ms
        self._claim_min_idle_ms = claim_min_idle_ms
        self._idempotency = idempotency or HandlerIdempotency(redis_client)
        self._retry_stream = retry_stream(stream, group)
        self._dlq_stream = dlq_stream(stream)
        for target in (stream, self._retry_stream):
            self._create_group(target)

    # --- plumbing -------------------------------------------------------------------

    def _create_group(self, target: str) -> None:
        try:
            self._redis.xgroup_create(target, self._group, id="0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            # BUSYGROUP just means another consumer created it first.
            if "BUSYGROUP" not in str(exc):
                raise

    def _ack(self, source: str, message_id: bytes | str) -> None:
        self._redis.xack(source, self._group, message_id)

    def _deliveries(self, count: int) -> list[tuple[str, bytes | str, dict[str, str]]]:
        out: list[tuple[str, bytes | str, dict[str, str]]] = []
        for source in (self._stream, self._retry_stream):
            claimed = self._redis.xautoclaim(
                source,
                self._group,
                self._consumer_name,
                min_idle_time=self._claim_min_idle_ms,
                start_id="0-0",
                count=count,
            )
            for message_id, raw in cast("_RawEntries", claimed[1]):
                out.append((source, message_id, _decode_fields(raw)))
        fresh = self._redis.xreadgroup(
            self._group,
            self._consumer_name,
            {self._stream: ">", self._retry_stream: ">"},
            count=count,
        )
        streams = cast("list[tuple[bytes | str, _RawEntries]]", fresh or [])
        for stream_name, entries in streams:
            for message_id, raw in entries:
                out.append((_decode(stream_name), message_id, _decode_fields(raw)))
        return out

    # --- the consume loop body --------------------------------------------------------

    def poll(self, count: int = 16) -> PollResult:
        """Process up to ``count`` due deliveries per stream and return the tally."""
        result = PollResult()
        for source, message_id, fields in self._deliveries(count):
            self._process(source, message_id, fields, result)
        return result

    def _process(
        self,
        source: str,
        message_id: bytes | str,
        fields: dict[str, str],
        result: PollResult,
    ) -> None:
        if int(fields.get(_FIELD_NOT_BEFORE_MS, "0")) > self._clock():
            # Not due yet: cycle it through the retry stream unchanged. The
            # backoff bookkeeping lives in the message, so readiness needs no
            # server-side timer and tests need no sleeps.
            _xadd(self._redis, self._retry_stream, dict(fields))
            self._ack(source, message_id)
            result.deferred += 1
            return

        event_id = fields.get(_FIELD_EVENT_ID, "")
        try:
            event = self._event_type.model_validate_json(fields.get(_FIELD_PAYLOAD, ""))
        except ValidationError:
            # Deterministic failure: retrying cannot fix a payload that does
            # not parse into the schema. Straight to the DLQ.
            self._dead_letter(fields, DeadLetterReason.SCHEMA_INVALID)
            self._ack(source, message_id)
            result.dead_lettered += 1
            return

        outcome = self._idempotency.claim(event_id=event_id, handler_name=self._handler_name)
        if outcome == "done":
            # Redelivery of an already-handled event (crash between handle
            # and XACK): the side effect must not run twice.
            self._ack(source, message_id)
            result.duplicates += 1
            return
        if outcome == "in_flight":
            # Another consumer is mid-handle. Leave the delivery pending;
            # XAUTOCLAIM redelivers it once the holder finishes or expires.
            result.in_flight += 1
            return

        try:
            self._handler(event)
        except Exception:
            # Reason codes only past this point — the exception text never
            # travels (invariant 6). Release first so the retry re-executes.
            self._idempotency.release(event_id=event_id, handler_name=self._handler_name)
            self._retry_or_dead_letter(fields, result)
            self._ack(source, message_id)
            return

        self._idempotency.mark_done(event_id=event_id, handler_name=self._handler_name)
        self._ack(source, message_id)
        result.handled += 1

    def _retry_or_dead_letter(self, fields: dict[str, str], result: PollResult) -> None:
        attempts = int(fields.get(_FIELD_ATTEMPTS, "0")) + 1
        if attempts >= self._max_attempts:
            self._dead_letter(
                {**fields, _FIELD_ATTEMPTS: str(attempts)}, DeadLetterReason.HANDLER_ERROR
            )
            result.dead_lettered += 1
            return
        backoff_ms = min(self._backoff_cap_ms, self._backoff_base_ms * 2 ** (attempts - 1))
        _xadd(
            self._redis,
            self._retry_stream,
            {
                **fields,
                _FIELD_ATTEMPTS: str(attempts),
                _FIELD_NOT_BEFORE_MS: str(self._clock() + backoff_ms),
            },
        )
        EVENT_BUS_RETRIED_TOTAL.labels(stream=self._stream, group=self._group).inc()
        result.retried += 1

    def _dead_letter(self, fields: dict[str, str], reason: DeadLetterReason) -> None:
        _xadd(
            self._redis,
            self._dlq_stream,
            {
                _FIELD_EVENT_ID: fields.get(_FIELD_EVENT_ID, ""),
                _FIELD_PAYLOAD: fields.get(_FIELD_PAYLOAD, ""),
                _FIELD_ATTEMPTS: fields.get(_FIELD_ATTEMPTS, "0"),
                "group": self._group,
                "reason": reason.value,
            },
        )
        EVENT_BUS_DEAD_LETTERED_TOTAL.labels(
            stream=self._stream, group=self._group, reason=reason.value
        ).inc()

    # --- consumer lag -----------------------------------------------------------------

    def record_lag(self) -> int:
        """Set the lag gauge and return the value: undelivered plus pending
        entries for this group across the source and retry streams."""
        total = self._group_backlog(self._stream) + self._group_backlog(self._retry_stream)
        EVENT_BUS_CONSUMER_LAG.labels(stream=self._stream, group=self._group).set(total)
        return total

    def _group_backlog(self, source: str) -> int:
        for info in self._redis.xinfo_groups(source):
            if _decode(info.get("name", b"")) != self._group:
                continue
            # Undelivered is counted directly: entries past last-delivered-id
            # (exclusive XRANGE, Redis 6.2+). XINFO GROUPS' `lag` field is not
            # used — it goes nil after XDEL/trimming on real Redis (and
            # fakeredis miscounts it), while the direct count stays exact and
            # naturally excludes trimmed entries, which is right: a trimmed
            # entry can never be delivered, so it is not backlog.
            last_delivered = _decode(info.get("last-delivered-id", b"0-0"))
            past_delivery = cast(
                "_RawEntries", self._redis.xrange(source, min=f"({last_delivered}", max="+")
            )
            return len(past_delivery) + int(info.get("pending", 0))
        # The group was destroyed out from under us: everything is backlog.
        return int(self._redis.xlen(source))
