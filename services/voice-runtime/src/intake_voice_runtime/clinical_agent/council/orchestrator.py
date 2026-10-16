"""Convening the members: concurrent draws, one deadline, stragglers abstain.

Every draw of a verification runs as its own task on the Backend's event loop
and the round ends at the first of *all draws finished* or *the deadline*,
measured on the injected :class:`~intake_voice_runtime.ports.Clock` — so a
fake clock can prove a 30 s stall costs the Talker nothing. A draw still
running at the deadline is cancelled and recorded ``timed_out``; it does not
hold the round open, and it does not count as agreement.

**One outcome class for refusal, truncation and empty output** (AI/ML
review): each is ``abstained``. A member that refused to read a self-harm
transcript, ran out of tokens, or returned nothing has said nothing, and
"nothing" is never a negative — the asymmetric adjudication cannot clear a
slot on silence.

**Spans are the closed field set.** Each draw emits one
:class:`~intake_platform.observability.spans.LlmSpan` of kind
``verification`` through :func:`~intake_platform.observability.spans.
emit_llm_span`, whose field tuple *is* the span-attribute allow-list; the
transcript, the quotes and the numbers have no field to occupy.
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
from dataclasses import dataclass
from typing import Any

from intake_platform.observability.spans import (
    LlmSpan,
    SpanKind,
    SpanOutcome,
    SpanSink,
    emit_llm_span,
)

from intake_voice_runtime.clinical_agent.council.lanes import SessionPins
from intake_voice_runtime.clinical_agent.council.policy import VerifierPolicy
from intake_voice_runtime.clinical_agent.council.readings import (
    VERIFIER_PROMPT_VERSION,
    VERIFIER_SCHEMA_ID,
    DropReason,
    MemberOutputRefused,
    MemberReading,
    build_verifier_instructions,
    parse_member_output,
    verifier_output_schema,
)
from intake_voice_runtime.clinical_agent.council.scope import VerifierScope
from intake_voice_runtime.clinical_agent.council.transport import (
    FinishReason,
    MemberCall,
    MemberCompletion,
    MemberTransport,
)
from intake_voice_runtime.extraction.boundary import PatientData
from intake_voice_runtime.metrics import (
    COUNCIL_MEMBER_LATENCY_MS,
    COUNCIL_MEMBER_TOKENS_TOTAL,
    COUNCIL_READINGS_DROPPED_TOTAL,
)
from intake_voice_runtime.ports import Clock

__all__ = ["MemberOutcome", "MemberResult", "VerificationRound", "VerifierOrchestrator"]


class MemberOutcome(enum.StrEnum):
    OK = "ok"
    ABSTAINED = "abstained"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


_SPAN_OUTCOME = {
    MemberOutcome.OK: SpanOutcome.OK,
    MemberOutcome.ABSTAINED: SpanOutcome.SCHEMA_INVALID,
    MemberOutcome.TIMED_OUT: SpanOutcome.TIMEOUT,
    MemberOutcome.FAILED: SpanOutcome.ERROR,
}


@dataclass(frozen=True, slots=True)
class MemberResult:
    """One draw's receipt. Readings are present only when ``outcome`` is OK."""

    member_id: str
    sample: int
    outcome: MemberOutcome
    readings: tuple[MemberReading, ...] = ()
    dropped: tuple[DropReason, ...] = ()
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class VerificationRound:
    """Every draw of one verification, sorted by ``(member_id, sample)``."""

    results: tuple[MemberResult, ...]

    @property
    def readings(self) -> tuple[tuple[str, MemberReading], ...]:
        return tuple(
            (result.member_id, reading)
            for result in self.results
            if result.outcome is MemberOutcome.OK
            for reading in result.readings
        )


@dataclass(frozen=True, slots=True)
class SpanContext:
    """The ids a span carries. All of them are ids or digests."""

    work_id: str
    session_id: str
    tenant_id: str
    protocol_hash: str

    @property
    def session_id_hash(self) -> str:
        return hashlib.sha256(self.session_id.encode("utf-8")).hexdigest()


@dataclass
class VerifierOrchestrator:
    """Runs the draws of one verification. Reads nothing but its arguments."""

    transport: MemberTransport
    policy: VerifierPolicy
    pins: SessionPins
    clock: Clock
    spans: SpanSink | None = None

    async def convene(
        self,
        *,
        data: PatientData,
        scope: VerifierScope,
        cache_salt: str,
        context: SpanContext,
    ) -> VerificationRound:
        schema = verifier_output_schema(scope.ordered)
        instructions = build_verifier_instructions(schema)
        calls = [
            MemberCall(
                member=self.pins.members[member_id],
                sample=sample,
                instructions=instructions,
                data=data,
                json_schema=schema,
                temperature=self.policy.temperature,
                cache_salt=cache_salt,
            )
            for member_id, sample in self.policy.draws
        ]
        started = self.clock.now_ms()
        tasks = {
            asyncio.ensure_future(self._draw(call, data=data, scope=scope)): call for call in calls
        }
        deadline = asyncio.ensure_future(self.clock.sleep(self.policy.deadline_ms / 1000.0))
        try:
            while not deadline.done() and not all(task.done() for task in tasks):
                waiters: set[asyncio.Future[Any]] = {
                    *(task for task in tasks if not task.done()),
                    deadline,
                }
                await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            deadline.cancel()
            pending = {task for task in tasks if not task.done()}
            for task in pending:
                task.cancel()
        results: list[MemberResult] = []
        for task, call in tasks.items():
            if task in pending or task.cancelled():
                result = MemberResult(
                    member_id=call.member.member_id,
                    sample=call.sample,
                    outcome=MemberOutcome.TIMED_OUT,
                    latency_ms=self.clock.now_ms() - started,
                )
            else:
                result = task.result()
            self._observe(result, call=call, context=context)
            results.append(result)
        results.sort(key=lambda item: (item.member_id, item.sample))
        return VerificationRound(results=tuple(results))

    async def _draw(
        self, call: MemberCall, *, data: PatientData, scope: VerifierScope
    ) -> MemberResult:
        started = self.clock.now_ms()
        member_id, sample = call.member.member_id, call.sample
        try:
            completion = await self.transport.complete(call)
        except asyncio.CancelledError:
            raise
        except Exception:  # a transport fault is a receipt, never a crashed round
            return MemberResult(
                member_id=member_id,
                sample=sample,
                outcome=MemberOutcome.FAILED,
                latency_ms=self.clock.now_ms() - started,
            )
        elapsed = self.clock.now_ms() - started
        return self._judge(completion, call=call, data=data, scope=scope, elapsed=elapsed)

    @staticmethod
    def _judge(
        completion: MemberCompletion,
        *,
        call: MemberCall,
        data: PatientData,
        scope: VerifierScope,
        elapsed: float,
    ) -> MemberResult:
        def receipt(
            outcome: MemberOutcome,
            readings: tuple[MemberReading, ...] = (),
            dropped: tuple[DropReason, ...] = (),
        ) -> MemberResult:
            return MemberResult(
                member_id=call.member.member_id,
                sample=call.sample,
                outcome=outcome,
                readings=readings,
                dropped=dropped,
                latency_ms=elapsed,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
            )

        if completion.finish is not FinishReason.STOP or not completion.text.strip():
            return receipt(MemberOutcome.ABSTAINED)
        try:
            parsed = parse_member_output(completion.text, transcript=data, scope=scope)
        except MemberOutputRefused:
            return receipt(MemberOutcome.ABSTAINED)
        return receipt(MemberOutcome.OK, parsed.readings, parsed.dropped)

    def _observe(self, result: MemberResult, *, call: MemberCall, context: SpanContext) -> None:
        member = result.member_id
        COUNCIL_MEMBER_LATENCY_MS.labels(member=member, outcome=result.outcome.value).observe(
            result.latency_ms
        )
        COUNCIL_MEMBER_TOKENS_TOTAL.labels(member=member, direction="input").inc(
            result.input_tokens
        )
        COUNCIL_MEMBER_TOKENS_TOTAL.labels(member=member, direction="output").inc(
            result.output_tokens
        )
        for reason in result.dropped:
            COUNCIL_READINGS_DROPPED_TOTAL.labels(reason=reason.value).inc()
        if self.spans is None:
            return
        emit_llm_span(
            LlmSpan(
                work_id=context.work_id,
                session_id_hash=context.session_id_hash,
                tenant_id=context.tenant_id,
                prompt_version=VERIFIER_PROMPT_VERSION,
                protocol_hash=context.protocol_hash,
                model_id=call.member.model_id,
                model_revision=call.member.revision,
                kind=SpanKind.VERIFICATION,
                outcome=_SPAN_OUTCOME[result.outcome],
                latency_ms=round(result.latency_ms),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                input_chars=len(call.data.text),
                output_chars=0,
                candidate_flag_count=0,
                schema_id=VERIFIER_SCHEMA_ID,
            ),
            self.spans,
        )
