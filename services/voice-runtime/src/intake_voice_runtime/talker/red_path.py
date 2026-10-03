"""The RED preemption path: the one thing allowed to break the window.

CLAUDE.md invariant 9 says Backend speech is delivered only at a safe
insertion window. This module is the single exception, and CLAUDE.md
invariant 21 says exactly how the exception is built:

    *"The RED script is pre-positioned on the device and triggered over the
    data channel — the RED path touches no media transport."*

That sentence is the whole design. files/03 §4.6 invariant 4 explains why it
had to be rewritten: downlink p95 is *"16 ms RAN + 165 ms jitter buffer +
25 ms device output = 206 ms before the clip's first sample is even
scheduled"*, so a streamed RED script cannot hold 300 ms — and cancelling the
in-flight playback has to happen first. Bundling the script with the app and
sending a **trigger** instead replaces a media round trip with *"one downlink
one-way (~10–25 ms) plus local playback"*.

Three consequences run through everything below.

**Nothing here can speak.** The controller is handed a
:class:`PlaybackCanceller`, a :class:`RedDataChannel`, a
:class:`ClinicNotifier` and a :class:`RedScriptIndex`. There is no
synthesizer, no clip store and no ``play``. So the register table does not
need a rule saying "``SILENT`` must not speak" — no register can speak from
here, and the register travels to the device verbatim so the device renders
what the clinician authored. The one way a RED could still have been spoken
server-side is a result carrying ``speech_tr``; that is a
:attr:`RedViolation.SERVER_SIDE_SPEECH` rather than a silent drop
(CLAUDE.md invariant 17).

**The register decides delivery, from a total table with no default.**
files/02 §5.3's *"binding authoring rule"* — *"a default would be chosen once,
by an engineer, for all future rules — which is how the paediatric airway case
gets an alarm"* — applies to the delivery decision as much as to the pack.
:data:`REGISTER_DELIVERY` is total over :class:`~clinical_schemas.triage.RedRegister`
and a missing row raises.

**A missed budget fails loudly and still delivers.** The budgets are
files/02 §8.2: *"Barge-in stop ≤ 150 ms. RED preemption ≤ 300 ms from rule
evaluation."* Raising at the first breach would abandon the patient to police
a number, so the path always completes and then raises
:class:`RedPathViolation` carrying the whole outcome.

What is deliberately **not** here: the Work queue's RED seal, which
files/12 §7.1 places on Layer B and INT-092 built — a second implementation
of one rule is how the two drift; and the files/12 §5 HMAC attestation, which
has no backlog issue and is recorded in docs/evidence/INT-093.md.
"""

from __future__ import annotations

import enum
import logging
import warnings
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Literal, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import RedLocation, RedRegister, RulesTriageResult, TriageLevel
from protocols.generic_red import DEFAULT_GENERIC_RED_REGISTER, GENERIC_RED_SCRIPT_IDS
from pydantic import Field, StringConstraints

from intake_voice_runtime.metrics import PREEMPT_RED_LATENCY_MS
from intake_voice_runtime.ports import Clock
from intake_voice_runtime.talker.preemption import BackendResult, Priority

__all__ = [
    "E2E_BUDGET_MS",
    "DEFAULT_GENERIC_RED_REGISTER",
    "GENERIC_RED_SCRIPT_IDS",
    "ID_SHAPE",
    "REGISTER_DELIVERY",
    "STOP_BUDGET_MS",
    "ClinicNotifier",
    "MappingRedScriptIndex",
    "PlaybackCanceller",
    "RedDataChannel",
    "RedDelivery",
    "RedNotification",
    "RedPathViolation",
    "RedPreemption",
    "RedPreemptionOutcome",
    "RedScriptIndex",
    "RedTriggerAck",
    "RedTriggerMessage",
    "RedViolation",
]

logger = logging.getLogger("intake_voice_runtime.red_path")

#: files/02 §8.2 / files/03 §4.6 invariant 4: *"playback cancel ≤ 150 ms"*.
#: Measured server-side, from the rules-engine determination to the moment the
#: outbound audio path was cancelled. The device-side flush of already-buffered
#: audio is on-hardware evidence (INT-095), not something a fake clock can
#: honestly assert.
STOP_BUDGET_MS = 150.0

#: files/02 §8.2: *"RED preemption ≤ 300 ms from rule evaluation"*, holding at
#: p99 because the script is pre-positioned (files/03 §4.6 invariant 4).
E2E_BUDGET_MS = 300.0

#: Mirrors ``ID_SHAPE`` in ``apps/mobile/src/lib/livekit/red.ts`` byte for
#: byte. Ids are ids: no spaces, no free text, so a rule id can never carry
#: PHI (CLAUDE.md invariant 6) and a message this side builds is never one the
#: device would refuse. ``tests/voice/test_red_preemption.py`` reads the
#: pattern out of the client source and asserts the two agree.
ID_SHAPE = r"^[a-z0-9][a-z0-9._-]{0,127}$"

type _Id = Annotated[str, StringConstraints(pattern=ID_SHAPE)]


# The blueprint names the RED axis field `register` (CLAUDE.md invariant 21;
# files/02 §5.3); pydantic warns because ABCMeta exposes a classmethod of the
# same name. The blueprint name wins — suppress exactly those three messages,
# the way clinical_schemas.triage and protocols.dsl already do for theirs.
for _model in ("RedTriggerMessage", "RedNotification", "RedPreemptionOutcome"):
    warnings.filterwarnings(
        "ignore",
        message=f'Field name "register" in "{_model}" shadows an attribute in parent',
        category=UserWarning,
    )


class RedViolation(enum.StrEnum):
    """What went wrong on a RED that was nonetheless delivered."""

    STOP_BUDGET = "stop_budget"
    E2E_BUDGET = "e2e_budget"
    SERVER_SIDE_SPEECH = "server_side_speech"
    SCRIPT_UNADDRESSABLE = "script_unaddressable"


class RedPathViolation(RuntimeError):
    """A RED was delivered and something about it must not go unnoticed.

    Raised **after** the path has run to completion, so policing a budget
    never costs the patient the delivery it was policing.
    """

    def __init__(self, outcome: RedPreemptionOutcome) -> None:
        self.outcome = outcome
        self.violations = outcome.violations
        super().__init__(
            f"RED {outcome.work_id} delivered with "
            f"{[violation.value for violation in outcome.violations]} "
            f"(stop={outcome.stop_ms} ms, e2e={outcome.e2e_ms} ms)"
        )


class RedPathNotWired(LookupError):
    """A RED arrived at a session with no RED preemption path bound."""


# --- the wire ------------------------------------------------------------------------


class RedTriggerMessage(FrozenModel):
    """One RED trigger, as ``apps/mobile/src/lib/livekit/red.ts`` decodes it.

    Identifiers and axes only — never script text, never a number, never a
    Turkish string. That is what lets a RED render with the microphone track
    gone, the audio session torn down and only the data channel alive; and it
    is why the preemption path cannot reintroduce the 112 affordance INT-255
    made absent under ``ON_SITE``: the message has no field to put it in.
    """

    kind: Literal["red_trigger"] = Field(default="red_trigger")
    rule_id: _Id = Field(
        serialization_alias="ruleId", description="Rules-engine rule id (invariant 1)."
    )
    register: RedRegister = Field(description="How it is told. No default (invariant 21).")
    location: RedLocation = Field(description="What it tells the patient to do. No default.")
    script_id: _Id = Field(
        serialization_alias="scriptId",
        description="Addresses the pre-positioned script in the on-device pack.",
    )


class RedTriggerAck(FrozenModel):
    """When the pre-positioned script started, on the session clock."""

    script_started_at_ms: float = Field(ge=0.0)


class RedNotification(FrozenModel):
    """The clinician route. ``notify_clinic: always`` on every RED.

    Ids and closed enumerations only: ``RuleFire.evidence`` — *"which slot
    values satisfied the rule"* — is patient material and has no carrier here
    (CLAUDE.md invariant 6).
    """

    work_id: str = Field(min_length=1)
    rule_ids: tuple[str, ...] = Field(min_length=1)
    register: RedRegister
    location: RedLocation
    evaluated_at_ms: float = Field(ge=0.0)
    patient_facing: bool = Field(
        description="False for DEFERRED_CLINICIAN, whose whole definition is "
        "that the patient surface does not change (files/02 §5.3)."
    )


# --- the register table --------------------------------------------------------------


class RedDelivery(FrozenModel):
    """What one register does. Every row cites the sentence it comes from."""

    stops_intake: bool = Field(
        description="Cancel the agent's outbound audio and stop asking "
        "(files/03 §4.6: *Kırmızı (RED) = preempt, stop intake*)."
    )
    triggers_device: bool = Field(
        description="Send the trigger so the device renders the pre-positioned script."
    )
    source: str = Field(min_length=1, description="The blueprint sentence this row is.")


#: files/02 §5.3 Axis 2, total over the enum. Clinician notification is not a
#: column because it has no false row: every RED reaches the clinician.
REGISTER_DELIVERY: Mapping[RedRegister, RedDelivery] = {
    RedRegister.ALERT: RedDelivery(
        stops_intake=True,
        triggers_device=True,
        source="files/02 §5.3: red header, full screen takeover, spoken with urgent "
        "prosody — the default for adults where alarm aids action.",
    ),
    RedRegister.CALM: RedDelivery(
        stops_intake=True,
        triggers_device=True,
        source="files/02 §5.3: no red, no alarm colour, action first — spoken softly, "
        "no alert sound. Location does not change the register.",
    ),
    RedRegister.SILENT: RedDelivery(
        stops_intake=True,
        triggers_device=True,
        source="files/02 §5.3: screen only, the guidance appears in the flow of the "
        "session, *no audio, ever*. Stopping the agent's own audio is the only "
        "sound-affecting act this register admits, and it can only produce silence.",
    ),
    RedRegister.DEFERRED_CLINICIAN: RedDelivery(
        stops_intake=False,
        triggers_device=False,
        source="files/02 §5.3: patient screen unchanged, the finding routes to the "
        "clinician only, where patient-facing alarm has no useful patient action — "
        "and *exactly what device_functions=off requires*, under which triage is "
        "shadow-logged and the session runs on (files/03 §15b).",
    ),
}


# --- ports -------------------------------------------------------------------------------


@runtime_checkable
class PlaybackCanceller(Protocol):
    """Stops the agent's outbound audio. One member, and it carries nothing.

    ``AudioSink`` satisfies this structurally, so production wiring is a pass;
    the narrow type is what stops this module *reaching* ``play``.
    """

    def cancel(self) -> Awaitable[None]: ...


@runtime_checkable
class RedDataChannel(Protocol):
    """The reliable, ordered SCTP-over-DTLS channel (files/03 §4.1, §4.6 inv. 4).

    ``publish`` resolves when the pre-positioned script has started on the
    device, and the ack carries that stamp.
    """

    def publish(self, message: RedTriggerMessage) -> Awaitable[RedTriggerAck]: ...


@runtime_checkable
class ClinicNotifier(Protocol):
    """The clinician route. **No member of this port is awaitable.**

    The same structural trick ADR-009 uses on ``WorkSubmitter``: the one
    channel that must survive every failure runs first, and cannot delay the
    stop it runs before.
    """

    def notify(self, notification: RedNotification) -> None: ...


@runtime_checkable
class RedScriptIndex(Protocol):
    """Which pre-positioned script addresses this rule at this location.

    Supplied from the compiled pack the device already holds. Returning
    ``None`` is the honest answer when nothing is pre-positioned; the path
    refuses to derive an id, because a derived id addresses the wrong words.
    """

    def script_id_for(self, rule_id: str, location: RedLocation) -> str | None: ...


@dataclass(frozen=True)
class MappingRedScriptIndex:
    """The index as data. Empty by default, which is the fail-closed state."""

    entries: Mapping[tuple[str, RedLocation], str] = field(default_factory=dict)

    def script_id_for(self, rule_id: str, location: RedLocation) -> str | None:
        return self.entries.get((rule_id, location))


# The generic escalation (INT-453): what the device shows when a RED's own
# script cannot be addressed, at the result's own location, so ON_SITE still
# carries no 112. Ids, copy and register live in ``protocols.generic_red``.
# The copy and the register are CD-24 (INT-432), which is pending, so the copy
# is ``draft_needs_source`` and :attr:`RedPreemption.generic_register` defaults
# to ALERT until CD-24's servable document supplies it
# (``protocols.generic_red.generic_red_register``).


# --- the outcome ---------------------------------------------------------------------------


class RedPreemptionOutcome(FrozenModel):
    """Everything one RED did, and what it cost on the session clock."""

    work_id: str = Field(min_length=1)
    rule_ids: tuple[str, ...] = Field(min_length=1)
    register: RedRegister
    location: RedLocation
    script_id: str | None = Field(default=None)
    evaluated_at_ms: float = Field(ge=0.0, description="The rules-engine determination.")
    stopped_at_ms: float | None = Field(default=None)
    script_started_at_ms: float | None = Field(default=None)
    notified_clinician: bool = Field(default=False)
    media_plane_unreachable: bool = Field(
        default=False,
        description="The cancel could not run. Nothing was playing to stop — the "
        "case files/03 §4.6 invariant 4 exists for, not a failure of the RED.",
    )
    violations: tuple[RedViolation, ...] = Field(default=())

    @property
    def stop_ms(self) -> float | None:
        if self.stopped_at_ms is None:
            return None
        return self.stopped_at_ms - self.evaluated_at_ms

    @property
    def e2e_ms(self) -> float | None:
        if self.script_started_at_ms is None:
            return None
        return self.script_started_at_ms - self.evaluated_at_ms


# --- the path ------------------------------------------------------------------------------------


@dataclass
class RedPreemption:
    """One session's RED preemption path.

    Order is files/03 §4.3's, with one deliberate rearrangement: the clinician
    route runs **first**. §4.3 lists it last, but its port has no awaitable
    member, so running it first costs the stop nothing and buys the one
    guarantee worth buying — a RED reaches a human even if the media plane,
    the data channel and both budgets fail in the same instant.
    """

    canceller: PlaybackCanceller
    channel: RedDataChannel
    clinic: ClinicNotifier
    scripts: RedScriptIndex
    clock: Clock
    #: CD-24 (pending): the generic escalation's register. ALERT until a servable
    #: generic RED document supplies one (protocols.generic_red).
    generic_register: RedRegister = DEFAULT_GENERIC_RED_REGISTER
    _delivered: dict[str, RedPreemptionOutcome] = field(default_factory=dict, init=False)

    async def trigger(
        self, result: BackendResult, *, evaluated_at_ms: float
    ) -> RedPreemptionOutcome:
        """Deliver one rules-engine RED. ``evaluated_at_ms`` is the moment the
        determination was made, not the moment Layer A noticed it — measuring
        from arrival would understate the very budget this path polices."""
        triage = _rules_engine_red(result)
        recorded = self._delivered.get(result.work_id)
        if recorded is not None:
            if RedViolation.SCRIPT_UNADDRESSABLE in recorded.violations:
                # A replay of a RED the device could only show generically
                # re-sends the device trigger (INT-453): the pack may hold the
                # script now, and either way the patient is shown a RED again.
                # The intake is already stopped and the clinician already told.
                return await self._redeliver(recorded, triage)
            # files/03 §4.6 invariant 6 and files/12 §7.5: a re-derived RED
            # carries the same content-addressed work_id, so replay is a no-op.
            return recorded

        register, location = triage.register, triage.location
        assert register is not None and location is not None  # noqa: S101 - RulesTriageResult
        delivery = REGISTER_DELIVERY[register]
        rule_ids = tuple(fire.id for fire in triage.rules)

        self.clinic.notify(
            RedNotification(
                work_id=result.work_id,
                rule_ids=rule_ids,
                register=register,
                location=location,
                evaluated_at_ms=evaluated_at_ms,
                patient_facing=delivery.triggers_device,
            )
        )

        violations: list[RedViolation] = []
        if result.presentation.speech_tr is not None:
            # Invariant 21: RED words are pre-positioned, so this string has
            # no route. Refused rather than dropped (invariant 17).
            violations.append(RedViolation.SERVER_SIDE_SPEECH)

        stopped_at_ms: float | None = None
        media_plane_unreachable = False
        if delivery.stops_intake:
            try:
                await self.canceller.cancel()
            except Exception:  # the media plane is the least reliable thing here
                media_plane_unreachable = True
                logger.warning("red stop found no reachable media plane", exc_info=False)
            stopped_at_ms = self.clock.now_ms()
            if stopped_at_ms - evaluated_at_ms > STOP_BUDGET_MS:
                violations.append(RedViolation.STOP_BUDGET)

        script_id: str | None = None
        script_started_at_ms: float | None = None
        if delivery.triggers_device:
            script_id, script_started_at_ms, device_violations = await self._to_device(
                triage, evaluated_at_ms
            )
            violations.extend(device_violations)

        outcome = RedPreemptionOutcome(
            work_id=result.work_id,
            rule_ids=rule_ids,
            register=register,
            location=location,
            script_id=script_id,
            evaluated_at_ms=evaluated_at_ms,
            stopped_at_ms=stopped_at_ms,
            script_started_at_ms=script_started_at_ms,
            notified_clinician=True,
            media_plane_unreachable=media_plane_unreachable,
            violations=tuple(violations),
        )
        self._delivered[result.work_id] = outcome
        if violations:
            raise RedPathViolation(outcome)
        return outcome

    async def _to_device(
        self, triage: RulesTriageResult, evaluated_at_ms: float
    ) -> tuple[str, float, list[RedViolation]]:
        """Trigger the RED on the device — always (INT-453).

        The script is the one the rules engine named (``red_rule_id``): never a
        position in ``rules``, which is ordered by severity then id while the
        engine breaks a severity tie on register. A RED whose script the pack
        cannot address — pack drift, or a result that names no RED — is still
        shown: the generic escalation, at the most conservative register, for
        the result's own location (so no 112 under ON_SITE), and it fails
        loudly as SCRIPT_UNADDRESSABLE. A patient who is shown nothing is the
        one outcome this path must never produce.
        """
        register, location = triage.register, triage.location
        assert register is not None and location is not None  # noqa: S101 - RulesTriageResult
        violations: list[RedViolation] = []
        rule_id = _red_rule(triage)
        script_id = None if rule_id is None else self.scripts.script_id_for(rule_id, location)
        if rule_id is None or script_id is None:
            violations.append(RedViolation.SCRIPT_UNADDRESSABLE)
            message = RedTriggerMessage(
                rule_id=rule_id if rule_id is not None else triage.rules[0].id,
                register=self.generic_register,
                location=location,
                script_id=GENERIC_RED_SCRIPT_IDS[location],
            )
        else:
            message = RedTriggerMessage(
                rule_id=rule_id, register=register, location=location, script_id=script_id
            )
        ack = await self.channel.publish(message)
        elapsed_ms = ack.script_started_at_ms - evaluated_at_ms
        PREEMPT_RED_LATENCY_MS.observe(elapsed_ms)
        if elapsed_ms > E2E_BUDGET_MS:
            violations.append(RedViolation.E2E_BUDGET)
        return message.script_id, ack.script_started_at_ms, violations

    async def _redeliver(
        self, recorded: RedPreemptionOutcome, triage: RulesTriageResult
    ) -> RedPreemptionOutcome:
        script_id, started_at_ms, device_violations = await self._to_device(
            triage, recorded.evaluated_at_ms
        )
        kept = [
            violation
            for violation in recorded.violations
            if violation not in (RedViolation.SCRIPT_UNADDRESSABLE, RedViolation.E2E_BUDGET)
        ]
        outcome = recorded.model_copy(
            update={
                "script_id": script_id,
                "script_started_at_ms": started_at_ms,
                "violations": (*kept, *device_violations),
            }
        )
        self._delivered[recorded.work_id] = outcome
        if outcome.violations:
            raise RedPathViolation(outcome)
        return outcome

    @property
    def delivered_work_ids(self) -> tuple[str, ...]:
        return tuple(self._delivered)


def _rules_engine_red(result: BackendResult) -> RulesTriageResult:
    """Narrow one result to the only thing this path accepts."""
    if result.priority is not Priority.PREEMPT:
        raise ValueError(
            "the RED preemption path takes only a result at priority=preempt; "
            "everything else waits for a safe insertion window (CLAUDE.md invariant 9)"
        )
    triage = result.presentation.triage_update
    if not isinstance(triage, RulesTriageResult) or triage.level is not TriageLevel.RED:
        # Unreachable past BackendResult's own validator; narrowed rather than
        # assumed, because this is the one path where being wrong is fatal.
        raise ValueError("the RED preemption path takes only a rules-engine RED (invariant 1)")
    return triage


def _red_rule(triage: RulesTriageResult) -> str | None:
    """The RED the engine named; a lone fired rule is its own. Never a position."""
    if triage.red_rule_id is not None:
        return triage.red_rule_id
    if len(triage.rules) == 1:
        return triage.rules[0].id
    return None
