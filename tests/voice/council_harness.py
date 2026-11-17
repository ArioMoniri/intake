"""Synthetic pack, recorded-shape doubles and builders for the INT-430 verifier suites.

Everything here is synthetic (files/04 §7): the slot names, the Turkish
strings and the two rules carry no clinical meaning and no clinical threshold.
No double dials anything; :class:`ScriptedTransport` returns completions from
a table and spends its latency on the virtual clock, which is how a 30 s stall
is reproduced in zero wall time.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from clinical_schemas.session import AnswerState
from intake_voice_runtime.clinical_agent.council.adjudicate import SlotView
from intake_voice_runtime.clinical_agent.council.desk import (
    AdmissionGate,
    ApplyVerdictHandler,
    ClinicianAddendum,
    RerunReason,
    VerifierDesk,
)
from intake_voice_runtime.clinical_agent.council.lanes import (
    DeploymentDataClass,
    MemberAssignment,
    SelfHostedMember,
    SessionPins,
    binding_of,
)
from intake_voice_runtime.clinical_agent.council.orchestrator import (
    MemberOutcome,
    MemberResult,
    VerificationRound,
    VerifierOrchestrator,
)
from intake_voice_runtime.clinical_agent.council.policy import (
    MemberSpec,
    VerifierMode,
    VerifierPolicy,
)
from intake_voice_runtime.clinical_agent.council.readings import (
    VERIFIER_PROMPT_VERSION,
    EvidenceSpan,
    MemberReading,
    Reading,
)
from intake_voice_runtime.clinical_agent.council.scope import VerifierScope, verifier_scope
from intake_voice_runtime.clinical_agent.council.transport import (
    FinishReason,
    MemberCall,
    MemberCompletion,
)
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import BackendAgent
from intake_voice_runtime.metering.budgets import SessionBudget, published_budgets
from intake_voice_runtime.metering.components import MeteredComponent
from intake_voice_runtime.metering.ledger import SessionLedger
from intake_voice_runtime.metering.meter import SessionMeter
from intake_voice_runtime.ports import Clock, WorkType
from protocols import EK4Level, RedFlagRule
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.types import Delivery, SlotType

NOW = datetime.datetime(2026, 10, 2, 9, 0, tzinfo=datetime.UTC)
HASH = "c" * 64
SESSION = "33333333-4444-4555-8666-777777777777"
TENANT = "sentetik-kiraci"
WEIGHTS = "d" * 64

BELIRTI = "oyku.sentetik_belirti"  # red-flag slot (rule when)
ZAMAN = "oyku.sentetik_zaman"  # tense anchor of both rules
OLCUM = "oyku.sentetik_olcum"  # numeric, not red-flag
IKINCI = "oyku.sentetik_ikinci"  # red-flag slot behind a gate on BELIRTI
KIMLIK = "kimlik.subject_role"  # gate-relevant identity slot, never verifiable
GUVENLIK = "guvenlik.sentetik_guvenlik"  # red-flag slot in a text_only section
BEKLENTI = "beklenti.metni"  # free text, out of scope

_SOURCE = {
    "guideline_id": "SYN-GUIDE-430",
    "guideline_title": "Sentetik kılavuz 430",
    "version_or_date": "sürüm bir",
    "url": "https://example.invalid/syn-guide-430",
    "retrieved_on": "2026-10-02",
    "quote": "sentetik alıntı metni",
}


def _slot(**fields: object) -> Slot:
    return Slot.model_validate(fields)


def _resolved(section_id: str, key: str, slot: Slot, delivery: Delivery) -> ResolvedSlot:
    return ResolvedSlot(
        section_id=section_id,
        key=key,
        fhir_link_id=f"{section_id}.{key}",
        slot=slot,
        delivery=delivery,
    )


def _rule(rule_id: str, when: str) -> RedFlagRule:
    return RedFlagRule.model_validate(
        {
            "id": rule_id,
            "label_tr": "Sentetik kural etiketi",
            "when": when,
            "tense": "ever",
            "tense_anchor": ZAMAN,
            "level": EK4Level.SARI_K1,
            "route": "SAME_DAY_ACIL",
            "notify_clinic": "always",
            "status": "active",
            "source": _SOURCE,
        }
    )


def protocol(*, with_rules: bool = True) -> ResolvedProtocol:
    voice = Delivery.VOICE
    kimlik = ResolvedSection(
        id="kimlik",
        delivery=voice,
        allow_paraphrase=False,
        slots=(
            _resolved(
                "kimlik",
                "subject_role",
                _slot(
                    type=SlotType.CODE,
                    valueset="vs.sentetik_rol",
                    ask_tr={"tr": "Sentetik rol sorusu."},
                    choices_tr={"tr": ("kendim", "yakınım")},
                ),
                voice,
            ),
        ),
    )
    oyku = ResolvedSection(
        id="oyku",
        delivery=voice,
        allow_paraphrase=False,
        slots=(
            _resolved(
                "oyku",
                "sentetik_belirti",
                _slot(
                    type=SlotType.BOOLEAN,
                    required=True,
                    must_ask=True,
                    ask_tr={"tr": "Sentetik belirtiniz var mı?"},
                    confirm_tr={"tr": "Sentetik belirti hâlâ var, doğru mu?"},
                    follow_up_tr={"tr": "Sentetik belirti takip sorusu."},
                ),
                voice,
            ),
            _resolved(
                "oyku",
                "sentetik_zaman",
                _slot(
                    type=SlotType.DATE,
                    ask_tr={"tr": "Sentetik zaman sorusu."},
                ),
                voice,
            ),
            _resolved(
                "oyku",
                "sentetik_olcum",
                _slot(
                    type=SlotType.INTEGER,
                    required=True,
                    ask_tr={"tr": "Sentetik ölçüm sorusu."},
                    confirm_tr={"tr": "Sentetik ölçümü doğru anladım mı?"},
                    follow_up_tr={"tr": "Sentetik ölçüm takip sorusu."},
                ),
                voice,
            ),
            _resolved(
                "oyku",
                "sentetik_ikinci",
                _slot(
                    type=SlotType.BOOLEAN,
                    ask_if="oyku.sentetik_belirti",
                    ask_tr={"tr": "Sentetik ikinci soru."},
                ),
                voice,
            ),
        ),
    )
    guvenlik = ResolvedSection(
        id="guvenlik",
        delivery=Delivery.TEXT_ONLY,
        allow_paraphrase=False,
        slots=(
            _resolved(
                "guvenlik",
                "sentetik_guvenlik",
                _slot(type=SlotType.BOOLEAN, ask_tr={"tr": "Sentetik güvenlik sorusu."}),
                Delivery.TEXT_ONLY,
            ),
        ),
    )
    beklenti = ResolvedSection(
        id="beklenti",
        delivery=voice,
        allow_paraphrase=True,
        slots=(
            _resolved(
                "beklenti",
                "metni",
                _slot(type=SlotType.STRING, ask_tr={"tr": "Sentetik beklenti sorusu."}),
                voice,
            ),
        ),
    )
    rules = (
        (
            _rule("rf.sentetik_bir", f"{BELIRTI} || {IKINCI}"),
            _rule("rf.sentetik_iki", GUVENLIK),
        )
        if with_rules
        else ()
    )
    return ResolvedProtocol(
        pack_id="base.sentetik_council",
        version="1.0.0",
        chain=("base.sentetik_council",),
        sections=(kimlik, oyku, guvenlik, beklenti),
        red_flags=rules,
        resolved_protocol_hash=HASH,
    )


def scope() -> VerifierScope:
    return verifier_scope(protocol())


def engine() -> IntakeEngine:
    return IntakeEngine(protocol=protocol(), reference_time=NOW)


def answer(engine_: IntakeEngine, step_id: str, value: Any) -> None:
    """Ask a step and bind a direct answer to it, the way the primary does."""
    engine_.mark_asked(step_id)
    engine_.apply_extraction(step_id, {step_id: value})


# --- readings ----------------------------------------------------------------------


def reading(
    ref: str, kind: Reading, transcript: str, quote: str, number: str | None = None
) -> MemberReading:
    start = transcript.index(quote)
    return MemberReading(
        ref=ref,
        reading=kind,
        number=number,
        evidence=EvidenceSpan(start=start, end=start + len(quote), quote=quote),
    )


def document(*readings: MemberReading) -> str:
    return json.dumps(
        {"readings": [item.model_dump(mode="json", exclude_none=True) for item in readings]},
        ensure_ascii=False,
    )


def ok(member_id: str, *readings: MemberReading, sample: int = 0) -> MemberResult:
    return MemberResult(
        member_id=member_id, sample=sample, outcome=MemberOutcome.OK, readings=tuple(readings)
    )


def round_of(*results: MemberResult) -> VerificationRound:
    return VerificationRound(results=tuple(sorted(results, key=lambda r: (r.member_id, r.sample))))


def view(
    ref: str,
    state: AnswerState,
    value: Any = None,
    *,
    revision: int = 2,
    gate_open: bool = True,
) -> SlotView:
    return SlotView(ref=ref, state=state, value=value, revision=revision, gate_open=gate_open)


# --- members and lanes ---------------------------------------------------------------


def member(member_id: str = "dogrulayici") -> SelfHostedMember:
    return SelfHostedMember(
        member_id=member_id,
        provider="vllm-tr",
        model_id="sentetik/verifier",
        revision="r1",
        weights_sha256=WEIGHTS,
    )


def assignment(
    role_id: str, *, route_kind: str = "self_hosted", available: bool = True, revision: str = "r1"
) -> MemberAssignment:
    return MemberAssignment(
        role_id=role_id,
        available=available,
        route_kind=route_kind,
        provider="vllm-tr",
        model_id="sentetik/verifier",
        revision=revision,
        weights_sha256=WEIGHTS,
    )


SLOT_TYPES = ("boolean", "integer")


def binding_digest(member_id: str = "dogrulayici", temperature: str = "0.7") -> str:
    return binding_of(
        member(member_id),
        prompt_version=VERIFIER_PROMPT_VERSION,
        temperature=temperature,
        slot_types=SLOT_TYPES,
    ).digest


def policy(
    *,
    samples: int = 3,
    deadline_ms: int = 4_000,
    members: tuple[str, ...] = ("dogrulayici",),
) -> VerifierPolicy:
    return VerifierPolicy(
        mode=VerifierMode.SELF_CONSISTENCY,
        members=tuple(MemberSpec(member_id=m) for m in members),
        samples=samples,
        temperature="0.7",
        deadline_ms=deadline_ms,
        bindings={m: binding_digest(m) for m in members},
    )


@dataclass
class TableResolver:
    """INT-428's router, as a table. A test may swap an answer mid-session."""

    answers: dict[str, MemberAssignment]
    asked: list[str] = field(default_factory=list)

    def resolve(self, role: str, *, tenant_id: str | None) -> MemberAssignment:
        self.asked.append(role)
        return self.answers[role]


def pins(policy_: VerifierPolicy) -> SessionPins:
    resolver = TableResolver({spec.role_id: assignment(spec.role_id) for spec in policy_.members})
    return SessionPins.capture(
        policy_,
        resolver,
        tenant_id=TENANT,
        deployment=DeploymentDataClass.REAL_PHI,
        prompt_version=VERIFIER_PROMPT_VERSION,
        slot_types=SLOT_TYPES,
    )


@dataclass
class ScriptedTransport:
    """Completions from a table keyed by sample, latency spent on a virtual clock."""

    clock: Clock
    texts: Mapping[int, str]
    stall_s: float = 0.0
    finish: FinishReason = FinishReason.STOP
    calls: list[MemberCall] = field(default_factory=list)

    async def complete(self, call: MemberCall) -> MemberCompletion:
        self.calls.append(call)
        if self.stall_s:
            await self.clock.sleep(self.stall_s)
        return MemberCompletion(
            text=self.texts.get(call.sample, self.texts.get(-1, "")),
            finish=self.finish,
            input_tokens=11,
            output_tokens=7,
        )


@dataclass
class RecordingTriage:
    reasons: list[RerunReason] = field(default_factory=list)

    def rerun(self, reason: RerunReason) -> None:
        self.reasons.append(reason)


@dataclass
class RecordingInbox:
    addenda: list[ClinicianAddendum] = field(default_factory=list)

    def append(self, addendum: ClinicianAddendum) -> None:
        self.addenda.append(addendum)


def meter(*, cap: float | None = 1_000_000.0) -> SessionMeter:
    """A meter whose extraction cap is declared — a *test* fixture, as in
    ``test_budgets.py``. ``cap=None`` is the shipped state: HB-O8 open."""
    published = dict(published_budgets())
    extraction = published[MeteredComponent.LLM_EXTRACTION]
    published[MeteredComponent.LLM_EXTRACTION] = SessionBudget(
        component=extraction.component,
        unit=extraction.unit,
        kind=extraction.kind,
        limit=cap,
        source="tests/voice/council_harness.py fixture",
        open_reason=None if cap is not None else extraction.open_reason,
    )
    return SessionMeter(ledger=SessionLedger(SESSION, budgets=published))


@dataclass
class DeskRig:
    engine: IntakeEngine
    agent: BackendAgent
    desk: VerifierDesk
    transport: ScriptedTransport
    triage: RecordingTriage
    inbox: RecordingInbox
    handler: ApplyVerdictHandler


def desk_rig(
    clock: Clock,
    *,
    texts: Mapping[int, str],
    stall_s: float = 0.0,
    gate: AdmissionGate | None = None,
    meter_: SessionMeter | None = None,
    policy_: VerifierPolicy | None = None,
    agent_: BackendAgent | None = None,
    scope_: VerifierScope | None = None,
) -> DeskRig:
    the_policy = policy_ or policy()
    agent = agent_ or BackendAgent(session_id=SESSION, engine=engine(), clock=clock)
    the_engine = agent.engine
    transport = ScriptedTransport(clock=clock, texts=texts, stall_s=stall_s)
    triage, inbox = RecordingTriage(), RecordingInbox()
    desk = VerifierDesk(
        session_id=SESSION,
        tenant_id=TENANT,
        agent=agent,
        orchestrator=VerifierOrchestrator(
            transport=transport,
            policy=the_policy,
            pins=pins(the_policy),
            clock=clock,
        ),
        scope=scope_ or scope(),
        meter=meter_ or meter(),
        gate=gate or AdmissionGate(max_in_flight=4),
        triage=triage,
        addenda=inbox,
        clock=clock,
    )
    handler = ApplyVerdictHandler(vault=desk.vault, ledger=desk.ledger, triage=triage)
    agent.register_state(WorkType.PLAN_FOLLOW_UPS, handler)
    return DeskRig(the_engine, agent, desk, transport, triage, inbox, handler)
