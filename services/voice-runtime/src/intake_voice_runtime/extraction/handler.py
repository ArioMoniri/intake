"""The ``extract_slots`` state handler — the registration INT-083 owed.

docs/evidence/INT-094.md finding 1(i): *"No module under ``services/``
registers an ``extract_slots`` state handler. INT-092 recorded that the
production handler was INT-083's; INT-083 built ``run_extraction`` and
``ExtractionResult.as_engine_call()`` and registered nothing."* Consequence:
a composed session raised ``UnregisteredWorkType`` on its first transcript,
so there was no turn to smoke-test against real adapters.

This module is the body between the two halves that already existed. It is
deliberately thin — four statements of substance — because everything
interesting is already somewhere better:

1. **take** the transcript from the session's vault by the digest the request
   carries (:mod:`intake_voice_runtime.transcript`). No text ever entered the
   queue, so this is where it re-enters the process, already wrapped as
   :class:`~intake_voice_runtime.extraction.boundary.PatientData`.
2. **run** :func:`~intake_voice_runtime.extraction.work.run_extraction` — the
   schema-constrained call, the nonce-fenced data block, the span and the
   eval row, all INT-083's.
3. **apply** the result through ``engine.apply_extraction(**as_engine_call())``
   — INT-081's reconcile-behind, called under the engine lock the queue is
   already holding.
4. **return** an empty :class:`~intake_voice_runtime.clinical_agent.work_queue.StateEffect`.

Four things this handler deliberately does **not** do:

- **It does not call ``mark_asked``.** files/03 §4.5 marks a step when the
  answer arrives; INT-081's ``mark_asked`` marks it when it is spoken. INT-095
  settled it in favour of *spoken* (see
  :class:`~intake_voice_runtime.ports.AskLedger`), and the way the other
  reading is made impossible is that this module has no call to it: the only
  producer of that engine write is the queue's ask-note pump, fed by the
  Talker's speech path. ``tests/voice/adapters/test_residency_contracts.py``
  asserts both halves — this file contains no ``mark_asked``, and exactly one
  module in the tree does.
- **It speaks nothing.** ``StateEffect.speech_tr`` stays ``None``:
  ``ExtractionResult`` has no ``speech_tr`` field precisely so that files/03
  §4.9.6 invariant 30's numeric-pairing rule cannot be broken from here, and
  inventing a Turkish acknowledgement would be patient copy no human signed
  off.
- **It sets no ``triage_update``.** The rules engine is
  ``packages/protocols/triage`` and running it from here is INT-096's scope,
  not this issue's; ``StateEffect.triage_update`` stays ``None`` so the
  queue's RED derivation has nothing to derive from. CLAUDE.md invariant 1 is
  untouched in the safe direction: an extraction cannot mint a level at all,
  and ``candidate_flags`` — the only triage-shaped material it produces — are
  clinician-facing and reach the note, never routing.
- **It never widens what the model may answer.** The declared slot set is the
  Work's own step plus whatever the engine currently lists as ``awaiting``
  (ask-ahead, files/03 §4.5), because those are exactly the steps
  ``IntakeEngine._bind`` will accept an answer for. A step outside that set
  could not bind, so offering it to the model would be inviting an answer the
  engine is about to drop.

**A refusal is an outcome, not a crash.** A parser refusal (the model answered
off-schema, or obeyed a planted instruction) leaves the slots unbound and the
question unanswered — the state files/13 §11.1 already knows how to act on. A
*gateway* refusal (an unconfigured lane, a missing recording, an endpoint that
did not answer) propagates, and the queue turns it into a failed
:class:`~intake_voice_runtime.clinical_agent.work_queue.WorkRecord` carrying
the exception's class name and nothing else.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from protocols.dsl import Slot

from intake_voice_runtime.adapters.pins import ModelPin
from intake_voice_runtime.clinical_agent.work_queue import StateContext, StateEffect
from intake_voice_runtime.extraction.gateway import ExtractionGateway
from intake_voice_runtime.extraction.work import ExtractionContext, ExtractionOutcome
from intake_voice_runtime.extraction.work import run_extraction as _run_extraction
from intake_voice_runtime.ports import Clock, work_key
from intake_voice_runtime.transcript import TranscriptSource

__all__ = ["UNPINNED_REVISION", "ExtractSlotsHandler"]

#: What goes on a span when the §4.9.1 row's registry entry carries no
#: structured ``model_id@revision``. Deliberately not hash-shaped: an auditor
#: reading a trace must see a gap, not a value they might try to look up
#: (files/HUMAN_BLOCKERS.md Rule 1).
UNPINNED_REVISION: Final = "unpinned"


def _session_id_hash(session_id: str) -> str:
    """The span's session identifier — a digest, never the id (INT-175)."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


@dataclass
class ExtractSlotsHandler:
    """One session's ``extract_slots`` handler, bound to its collaborators.

    A callable object rather than a closure so the wiring is inspectable: a
    reviewer can see which gateway, which vault and which pin this handler
    would use without reading the composition root's local variables.
    """

    transcripts: TranscriptSource
    gateway: ExtractionGateway
    slots: Mapping[str, Slot]
    pin: ModelPin
    clock: Clock
    tenant_id: str
    valuesets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    outcomes: list[ExtractionOutcome] = field(default_factory=list, init=False)

    def __call__(self, context: StateContext) -> StateEffect:
        request = context.request
        data = self.transcripts.take(request.input_hash)
        declared = self._declared_slots(context)
        outcome = _run_extraction(
            ExtractionContext(
                work_id=work_key(request),
                session_id_hash=_session_id_hash(request.session_id),
                tenant_id=self.tenant_id,
                protocol_hash=request.protocol_hash,
                model_id=self.pin.model_id or self.pin.component,
                model_revision=self.pin.revision or UNPINNED_REVISION,
                case_id=f"{request.step_id}@{request.engine_version}",
            ),
            step_id=request.step_id,
            slots=declared,
            valuesets=self.valuesets,
            transcript=data.text,
            gateway=self.gateway,
            now_ms=self.clock.now_ms,
        )
        self.outcomes.append(outcome)
        if outcome.result is not None:
            context.engine.apply_extraction(**outcome.result.as_engine_call())
        return StateEffect()

    def _declared_slots(self, context: StateContext) -> Mapping[str, Slot]:
        """The Work's own step plus every step the engine is awaiting.

        ``awaiting`` is the ask-ahead set (files/03 §4.5): the questions that
        have been spoken and not yet reconciled. Those are the only refs
        ``IntakeEngine._bind`` will accept, so they are the only refs worth
        declaring.
        """
        refs = {context.request.step_id, *context.engine.snapshot.awaiting}
        # An empty intersection means the Work names a step this pack does not
        # declare. ``slot_output_schema`` refuses an empty schema, and that is
        # the right answer: nobody could validate an answer to it.
        return {ref: self.slots[ref] for ref in sorted(refs) if ref in self.slots}
