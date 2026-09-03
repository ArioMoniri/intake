"""Two decorators — the only places a session actually spends.

Both wrap a port the runtime already speaks, so metering is added by
composition rather than by editing the thing being measured. Neither changes
what its inner adapter does on the happy path, and neither is awaitable
(CLAUDE.md invariant 9).

**The asymmetry between them is the design.** The gateway can refuse and the
synthesizer cannot, because their budgets are different kinds:

* ``llm_extraction`` is a **CAP**. It refuses the *elective* lane only, and it
  refuses **before** the endpoint is dialled — a refusal after the call would
  have spent the tokens it was trying to save.
* ``tts`` is a **TARGET**. :class:`MeteredSpeechSynthesizer` has no refusal at
  all, by construction rather than by policy: CLAUDE.md invariant 10 says a
  scripted step is spoken verbatim from ``text_tr``, and a synthesizer that
  could decline would be a synthesizer that stops mid-question.

There is deliberately **no metered transcriber.** The ``Transcriber`` port
takes opaque ``bytes`` and declares no sample format, so a decorator there
could only charge audio seconds it had guessed — see
:mod:`intake_voice_runtime.metering.meter`.
"""

from __future__ import annotations

from dataclasses import dataclass

from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall, ExtractionGateway
from intake_voice_runtime.metering.components import ChargeClass, MeteredComponent
from intake_voice_runtime.metering.meter import SessionMeter
from intake_voice_runtime.ports import SpeechSynthesizer

__all__ = [
    "ElectiveWorkRefused",
    "MeteredExtractionGateway",
    "MeteredSpeechSynthesizer",
]


class ElectiveWorkRefused(RuntimeError):
    """A discretionary model call the session's budget could not admit.

    Not an error in the operator's sense and not a failure of the model: it is
    the cap doing its job. The obligatory lane is unaffected, so the
    conversation continues and the note records the slot as unbound — the
    state files/13 §11.1 already knows how to act on.
    """


@dataclass
class MeteredExtractionGateway:
    """Charge the tokens the endpoint reported; gate the elective lane.

    ``charge_class`` is a constructor argument rather than a per-call one so
    that "which lane is this?" is answered where the session is composed. A
    deployment that grows a speculative extraction lane wires a **second**
    instance with ``ChargeClass.ELECTIVE``; it does not pass a flag from
    somewhere inside a turn.
    """

    inner: ExtractionGateway
    meter: SessionMeter
    charge_class: ChargeClass = ChargeClass.OBLIGATORY

    def complete(self, call: ExtractionCall) -> Completion:
        admission = self.meter.admits(MeteredComponent.LLM_EXTRACTION, self.charge_class)
        if not admission.admitted:
            raise ElectiveWorkRefused(
                f"elective extraction refused: {admission.reason.value}. The obligatory "
                "lane is unaffected; nothing the patient is owed is withheld "
                "(files/10 §5 LLM10)"
            )
        completion = self.inner.complete(call)
        self.meter.charge_extraction_tokens(completion.input_tokens, completion.output_tokens)
        return completion


@dataclass
class MeteredSpeechSynthesizer:
    """Charge the characters that were synthesised. It cannot refuse.

    Implements :class:`~intake_voice_runtime.ports.SpeechSynthesizer`, so it
    drops into ``SpeechRouter``'s slot unchanged. The charge is taken **after**
    the inner call so a synthesis that raised is not billed for audio nobody
    heard.
    """

    inner: SpeechSynthesizer
    meter: SessionMeter

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        frames = self.inner.synthesize(text_tr, voice_id)
        self.meter.charge_tts_chars(text_tr)
        return frames
