"""INT-035 — Redis streams event bus + consumer framework + DLQ.

Acceptance, verbatim: "typed producers/consumers with retries, DLQ,
exactly-once handlers via idempotency keys; consumer lag metric".

The unit lane runs entirely on fakeredis (2.37.1 implements XADD, XREADGROUP,
XACK, XPENDING, XAUTOCLAIM and XINFO GROUPS with ``lag`` — verified before
these tests were written, so nothing here needs the compose redis). Time is
an injected millisecond clock; no test sleeps.

Delivery semantics pinned here: Redis streams give at-least-once delivery;
retries are requeued onto a group-local retry stream (a re-add onto the
source stream would double-deliver to every other consumer group); the
handler wrapper keyed on (event id, handler name) — the INT-176 pattern —
makes side effects exactly-once across redeliveries.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import fakeredis
import redis
from clinical_schemas.events import (
    CsatReason,
    CsatV1,
    NpsV1,
    SecurityEventCategory,
    SecurityV1,
)
from intake_platform.event_bus import (
    Consumer,
    DeadLetterReason,
    EventSchemaError,
    HandlerIdempotency,
    Producer,
    dlq_stream,
    retry_stream,
)
from prometheus_client import REGISTRY
from pydantic import BaseModel


def _csat(text: str | None = None) -> CsatV1:
    return CsatV1(
        tenant_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        score=4,
        reason=CsatReason.HELPFUL,
        text=text,
    )


def _security() -> SecurityV1:
    return SecurityV1(
        category=SecurityEventCategory.FAILED_LOGIN,
        correlation_id="corr-1",
    )


def _names(tag: str) -> tuple[str, str]:
    """Unique stream/group per test: metric label sets never collide."""
    suffix = uuid.uuid4().hex[:8]
    return f"events.{tag}.{suffix}", f"g-{suffix}"


def _fields(entry: tuple[bytes, dict[bytes, bytes]]) -> dict[str, str]:
    return {key.decode(): value.decode() for key, value in entry[1].items()}


class FakeClock:
    def __init__(self, now_ms: int = 0) -> None:
        self.now_ms = now_ms

    def __call__(self) -> int:
        return self.now_ms


def _consumer[E: BaseModel](
    client: redis.Redis,
    stream: str,
    group: str,
    event_type: type[E],
    handler: Callable[[E], None],
    *,
    handler_name: str = "h.default",
    consumer_name: str = "c-1",
    clock: FakeClock | None = None,
    max_attempts: int = 3,
    backoff_base_ms: int = 1000,
) -> Consumer[E]:
    return Consumer(
        client,
        stream=stream,
        group=group,
        consumer_name=consumer_name,
        event_type=event_type,
        handler=handler,
        handler_name=handler_name,
        clock=clock or FakeClock(),
        max_attempts=max_attempts,
        backoff_base_ms=backoff_base_ms,
        claim_min_idle_ms=0,
    )


def _sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def _no_pending(client: redis.Redis, stream: str, group: str) -> bool:
    return client.xpending_range(stream, group, min="-", max="+", count=10) == []


# --- typed produce / consume round-trip --------------------------------------------


def test_round_trip_delivers_the_typed_event_and_acks() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    event = _csat()
    seen: list[CsatV1] = []

    Producer(client, stream=stream, event_type=CsatV1).publish(event)
    consumer = _consumer(client, stream, group, CsatV1, seen.append)
    result = consumer.poll()

    assert seen == [event], "the handler must receive the validated typed event"
    assert result.handled == 1
    assert _no_pending(client, stream, group), "a handled message must be acknowledged"


def test_round_trip_binds_to_other_int031_models_too() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("security")
    event = _security()
    seen: list[SecurityV1] = []

    Producer(client, stream=stream, event_type=SecurityV1).publish(event)
    _consumer(client, stream, group, SecurityV1, seen.append).poll()

    assert seen == [event]


def test_publish_returns_a_unique_event_id() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, _ = _names("csat")
    producer = Producer(client, stream=stream, event_type=CsatV1)
    first = producer.publish(_csat())
    second = producer.publish(_csat())
    assert first != second
    assert client.xlen(stream) == 2


# --- schema enforcement at the publish boundary ------------------------------------


def test_publish_refuses_an_event_of_the_wrong_schema() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, _ = _names("csat")
    producer = Producer(client, stream=stream, event_type=CsatV1)
    nps = NpsV1(tenant_id=uuid.uuid4(), score=9)

    try:
        producer.publish(nps)  # type: ignore[arg-type]  # the runtime gate is the point
        raise AssertionError("publish must refuse a payload that fails its schema")
    except EventSchemaError:
        assert client.xlen(stream) == 0, "nothing may land on the stream"


def test_publish_refuses_a_validation_bypass_and_leaks_no_values() -> None:
    """``model_construct`` skips validation; the bus re-validates on the wire
    and the refusal carries field paths only — never values (invariant 6)."""
    client = fakeredis.FakeStrictRedis()
    stream, _ = _names("csat")
    producer = Producer(client, stream=stream, event_type=CsatV1)
    bad = CsatV1.model_construct(
        tenant_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        score=99,
        reason=CsatReason.HELPFUL,
        text="hasta çok kızgındı",
    )

    try:
        producer.publish(bad)
        raise AssertionError("publish must refuse a validation bypass")
    except EventSchemaError as exc:
        message = str(exc)
        assert "score" in message, "the field path locates the defect"
        assert "99" not in message, "field values never appear in the error"
        assert "hasta" not in message, "free text never appears in the error"
    assert client.xlen(stream) == 0


# --- retries with backoff bookkeeping in the message --------------------------------


def test_failed_handler_requeues_with_attempts_and_backoff_in_the_message() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    clock = FakeClock(10_000)
    calls = {"n": 0}

    def flaky(_: CsatV1) -> None:
        calls["n"] += 1
        raise RuntimeError("boom")

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    consumer = _consumer(client, stream, group, CsatV1, flaky, clock=clock, backoff_base_ms=1000)
    result = consumer.poll()

    assert calls["n"] == 1
    assert result.retried == 1
    assert _no_pending(client, stream, group), "the failed delivery is acked on the source"
    requeued = client.xrange(retry_stream(stream, group), min="-", max="+")
    assert len(requeued) == 1, "the retry lives on the group-local retry stream"
    fields = _fields(requeued[0])
    assert fields["attempts"] == "1"
    assert fields["not_before_ms"] == str(10_000 + 1000), "backoff = base * 2^(attempts-1)"
    assert _sample("event_bus_retried_total", {"stream": stream, "group": group}) == 1.0


def test_retries_are_group_local_so_other_groups_see_no_duplicate_delivery() -> None:
    """A retry re-added onto the source stream would fan out to every other
    consumer group; the group-local retry stream keeps the failure private."""
    client = fakeredis.FakeStrictRedis()
    stream, group_flaky = _names("csat")
    _, group_clean = _names("csat-clean")
    clean_calls = {"n": 0}

    def clean(_: CsatV1) -> None:
        clean_calls["n"] += 1

    def flaky(_: CsatV1) -> None:
        raise RuntimeError("boom")

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    _consumer(client, stream, group_flaky, CsatV1, flaky, handler_name="h.flaky").poll()

    clean_consumer = _consumer(client, stream, group_clean, CsatV1, clean, handler_name="h.clean")
    clean_consumer.poll()
    clean_consumer.poll()

    assert clean_calls["n"] == 1, "the other group must see the event exactly once"
    assert client.xlen(stream) == 1, "the source stream carries no requeued copy"


def test_backoff_defers_redelivery_until_the_injected_clock_passes_it() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    clock = FakeClock(0)
    calls = {"n": 0}
    fail_first = {"armed": True}

    def flaky(_: CsatV1) -> None:
        calls["n"] += 1
        if fail_first["armed"]:
            fail_first["armed"] = False
            raise RuntimeError("boom")

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    consumer = _consumer(client, stream, group, CsatV1, flaky, clock=clock, backoff_base_ms=5000)

    assert consumer.poll().retried == 1

    clock.now_ms = 1000
    early = consumer.poll()
    assert early.deferred == 1
    assert calls["n"] == 1, "before not_before_ms the handler must not run"

    clock.now_ms = 5001
    late = consumer.poll()
    assert late.handled == 1
    assert calls["n"] == 2, "past the backoff the retry executes"


def test_backoff_doubles_per_attempt_and_caps() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    clock = FakeClock(0)

    def always_fail(_: CsatV1) -> None:
        raise RuntimeError("boom")

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    consumer = Consumer(
        client,
        stream=stream,
        group=group,
        consumer_name="c-1",
        event_type=CsatV1,
        handler=always_fail,
        handler_name="h.fail",
        clock=clock,
        max_attempts=10,
        backoff_base_ms=1000,
        backoff_cap_ms=3000,
        claim_min_idle_ms=0,
    )

    consumer.poll()  # attempt 1 fails → not_before 0 + 1000
    clock.now_ms = 1001
    consumer.poll()  # attempt 2 fails → not_before 1001 + 2000
    clock.now_ms = 3002
    consumer.poll()  # attempt 3 fails → not_before 3002 + 3000 (capped)

    entries = client.xrange(retry_stream(stream, group), min="-", max="+")
    fields = _fields(entries[-1])
    assert fields["attempts"] == "3"
    assert fields["not_before_ms"] == str(3002 + 3000), "the cap bounds the exponential"


# --- DLQ ---------------------------------------------------------------------------


def test_retry_cap_moves_the_message_to_the_dlq_with_a_reason_code() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    clock = FakeClock(0)
    calls = {"n": 0}

    def always_fail(_: CsatV1) -> None:
        calls["n"] += 1
        raise RuntimeError("boom")

    event = _csat(text="metin")
    Producer(client, stream=stream, event_type=CsatV1).publish(event)
    consumer = _consumer(client, stream, group, CsatV1, always_fail, clock=clock, max_attempts=3)

    consumer.poll()
    clock.now_ms = 10_000
    consumer.poll()
    clock.now_ms = 20_000
    result = consumer.poll()

    assert calls["n"] == 3, "max_attempts bounds total handler invocations"
    assert result.dead_lettered == 1
    assert _no_pending(client, stream, group)
    assert _no_pending(client, retry_stream(stream, group), group)

    dead = client.xrange(dlq_stream(stream), min="-", max="+")
    assert len(dead) == 1
    fields = _fields(dead[0])
    assert fields["reason"] == DeadLetterReason.HANDLER_ERROR
    assert fields["group"] == group
    assert fields["attempts"] == "3"
    assert CsatV1.model_validate_json(fields["payload"]) == event, (
        "the DLQ carries the typed payload for replay"
    )
    assert (
        _sample(
            "event_bus_dead_lettered_total",
            {"stream": stream, "group": group, "reason": "handler_error"},
        )
        == 1.0
    )


def test_dlq_entry_carries_no_exception_text() -> None:
    """Invariant 6: the failure reason is a closed code; exception messages
    (which can carry PHI) never reach the DLQ entry."""
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    secret = "hasta Ayşe Yılmaz 05321234567"

    def always_fail(_: CsatV1) -> None:
        raise RuntimeError(secret)

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    _consumer(client, stream, group, CsatV1, always_fail, max_attempts=1).poll()

    dead = client.xrange(dlq_stream(stream), min="-", max="+")
    assert len(dead) == 1
    for key, value in dead[0][1].items():
        assert secret not in key.decode(errors="replace")
        assert secret not in value.decode(errors="replace")
        assert "Ayşe" not in value.decode(errors="replace")


def test_schema_invalid_payload_dead_letters_without_invoking_the_handler() -> None:
    """A poison entry (written past the Producer, failing the schema) goes
    straight to the DLQ — deterministic failures are not retried."""
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    calls = {"n": 0}

    def handler(_: CsatV1) -> None:
        calls["n"] += 1

    client.xadd(
        stream,
        {"event_id": "ev-poison", "payload": '{"nonsense": true}', "attempts": "0"},
    )
    result = _consumer(client, stream, group, CsatV1, handler).poll()

    assert calls["n"] == 0, "the handler never sees a payload that fails its schema"
    assert result.dead_lettered == 1
    dead = client.xrange(dlq_stream(stream), min="-", max="+")
    fields = _fields(dead[0])
    assert fields["reason"] == DeadLetterReason.SCHEMA_INVALID
    assert _no_pending(client, stream, group)


# --- exactly-once handlers via idempotency keys -------------------------------------


def test_redelivery_after_crash_between_handle_and_ack_does_not_reexecute() -> None:
    """The INT-176 pattern applied to the bus: the handler's side effect is
    keyed on (event id, handler name); a crash after handling but before XACK
    redelivers the message, and the second consumer skips the side effect."""
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    calls = {"n": 0}

    class CrashOnFirstAck:
        """Client wrapper: the first XACK dies, as a process crash would."""

        def __init__(self, inner: redis.Redis) -> None:
            self._inner = inner
            self.crashed = False

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

        def xack(self, *args: object, **kwargs: object) -> object:
            if not self.crashed:
                self.crashed = True
                raise ConnectionError("simulated crash between handle and XACK")
            return self._inner.xack(*args, **kwargs)

    def count(_: CsatV1) -> None:
        calls["n"] += 1

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())

    crashing = CrashOnFirstAck(client)
    first = _consumer(
        crashing,  # type: ignore[arg-type]  # duck-typed wrapper, xack only
        stream,
        group,
        CsatV1,
        count,
        handler_name="h.count",
        consumer_name="c-a",
    )
    try:
        first.poll()
        raise AssertionError("the simulated crash must propagate")
    except ConnectionError:
        assert calls["n"] == 1, "the handler ran before the crash"

    second = _consumer(
        client, stream, group, CsatV1, count, handler_name="h.count", consumer_name="c-b"
    )
    result = second.poll()

    assert calls["n"] == 1, "the redelivered message must not re-execute the side effect"
    assert result.duplicates == 1
    assert _no_pending(client, stream, group), (
        "the duplicate is acknowledged so it never redelivers again"
    )


def test_idempotency_key_scopes_by_handler_name_not_just_event_id() -> None:
    """Two different handlers (two groups) each run once for the same event."""
    client = fakeredis.FakeStrictRedis()
    stream, group_a = _names("csat")
    _, group_b = _names("csat-second")
    calls = {"a": 0, "b": 0}

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())

    def handler_a(_: CsatV1) -> None:
        calls["a"] += 1

    def handler_b(_: CsatV1) -> None:
        calls["b"] += 1

    _consumer(client, stream, group_a, CsatV1, handler_a, handler_name="h.a").poll()
    _consumer(client, stream, group_b, CsatV1, handler_b, handler_name="h.b").poll()

    assert calls == {"a": 1, "b": 1}


def test_a_failed_handler_releases_the_idempotency_key_for_the_retry() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    clock = FakeClock(0)
    calls = {"n": 0}
    fail_first = {"armed": True}

    def flaky(_: CsatV1) -> None:
        calls["n"] += 1
        if fail_first["armed"]:
            fail_first["armed"] = False
            raise RuntimeError("boom")

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    consumer = _consumer(client, stream, group, CsatV1, flaky, clock=clock, backoff_base_ms=10)
    consumer.poll()
    clock.now_ms = 11
    consumer.poll()

    assert calls["n"] == 2, "a failed attempt must stay retryable (INT-176 release-on-failure)"


def test_an_in_flight_key_leaves_the_message_pending_for_a_later_poll() -> None:
    """A concurrent consumer mid-handle holds the in-flight marker: the
    message is neither executed nor acked, and redelivers later."""
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    calls = {"n": 0}

    producer = Producer(client, stream=stream, event_type=CsatV1)
    event_id = producer.publish(_csat())

    store = HandlerIdempotency(client)
    assert store.claim(event_id=event_id, handler_name="h.count") == "claimed"

    def count(_: CsatV1) -> None:
        calls["n"] += 1

    consumer = _consumer(client, stream, group, CsatV1, count, handler_name="h.count")
    result = consumer.poll()

    assert calls["n"] == 0
    assert result.in_flight == 1
    pending = client.xpending_range(stream, group, min="-", max="+", count=10)
    assert len(pending) == 1, "the message stays pending until the holder finishes"

    store.release(event_id=event_id, handler_name="h.count")
    redelivered = consumer.poll()
    assert redelivered.handled == 1
    assert calls["n"] == 1


# --- consumer lag metric -------------------------------------------------------------


def test_consumer_lag_counts_undelivered_and_pending_and_drains_to_zero() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    producer = Producer(client, stream=stream, event_type=CsatV1)
    consumer = _consumer(client, stream, group, CsatV1, lambda _: None)

    for _ in range(3):
        producer.publish(_csat())

    assert consumer.record_lag() == 3
    assert _sample("event_bus_consumer_lag", {"stream": stream, "group": group}) == 3.0

    consumer.poll()
    assert consumer.record_lag() == 0
    assert _sample("event_bus_consumer_lag", {"stream": stream, "group": group}) == 0.0


def test_consumer_lag_includes_delivered_but_unacked_messages() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    consumer = _consumer(client, stream, group, CsatV1, lambda _: None)

    # deliver without acking, as a crashed consumer would leave it
    client.xreadgroup(group, "c-dead", {stream: ">"}, count=10)
    assert consumer.record_lag() == 1


def test_consumer_lag_counts_waiting_retries() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    clock = FakeClock(0)

    def always_fail(_: CsatV1) -> None:
        raise RuntimeError("boom")

    Producer(client, stream=stream, event_type=CsatV1).publish(_csat())
    consumer = _consumer(client, stream, group, CsatV1, always_fail, clock=clock)
    consumer.poll()

    assert consumer.record_lag() == 1, "a requeued retry is still unprocessed work"


def test_consumer_lag_counts_only_deliverable_entries_after_trimming() -> None:
    """XINFO GROUPS reports ``lag`` as nil after XDEL/trimming; the bus counts
    entries past last-delivered-id directly instead, so trimmed entries —
    which can never be delivered — are not reported as backlog."""
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    producer = Producer(client, stream=stream, event_type=CsatV1)
    consumer = _consumer(client, stream, group, CsatV1, lambda _: None)
    for _ in range(3):
        producer.publish(_csat())

    first_id, second_id = (entry[0] for entry in client.xrange(stream, min="-", max="+")[:2])
    client.xdel(stream, first_id, second_id)

    assert consumer.record_lag() == 1


def test_consumer_lag_reports_full_backlog_when_the_group_was_destroyed() -> None:
    """A group destroyed out from under the consumer means nothing was
    processed: every entry in the stream is backlog."""
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    producer = Producer(client, stream=stream, event_type=CsatV1)
    consumer = _consumer(client, stream, group, CsatV1, lambda _: None)
    producer.publish(_csat())
    producer.publish(_csat())

    client.xgroup_destroy(stream, group)
    assert consumer.record_lag() == 2


# --- consumer group plumbing ---------------------------------------------------------


def test_group_creation_is_idempotent_across_consumers() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    _consumer(client, stream, group, CsatV1, lambda _: None, consumer_name="c-1")
    _consumer(client, stream, group, CsatV1, lambda _: None, consumer_name="c-2")
    assert len(client.xinfo_groups(stream)) == 1


def test_group_creation_on_a_non_stream_key_raises() -> None:
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    client.set(stream, "not-a-stream")
    try:
        _consumer(client, stream, group, CsatV1, lambda _: None)
        raise AssertionError("WRONGTYPE must propagate; only BUSYGROUP is swallowed")
    except redis.exceptions.ResponseError:
        assert client.xlen(retry_stream(stream, group)) == 0


def test_stale_pending_messages_are_claimed_from_a_dead_consumer() -> None:
    """XAUTOCLAIM recovers messages a crashed consumer never acked."""
    client = fakeredis.FakeStrictRedis()
    stream, group = _names("csat")
    seen: list[CsatV1] = []
    event = _csat()

    Producer(client, stream=stream, event_type=CsatV1).publish(event)
    consumer = _consumer(client, stream, group, CsatV1, seen.append, consumer_name="c-live")
    # a dead consumer took delivery and vanished before acking
    client.xreadgroup(group, "c-dead", {stream: ">"}, count=10)
    assert seen == []

    result = consumer.poll()
    assert seen == [event]
    assert result.handled == 1
    assert _no_pending(client, stream, group)
