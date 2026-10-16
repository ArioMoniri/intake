"""The session's close: no tense anchor outlives it (INT-540).

The INT-522 clinical review, F1: a session abandoned between the patient's
first 'bilmiyorum' to the onset question and their last answer left
``chest_pain.onset_at`` ``ASKED_PENDING`` for good, so it read Unknown and K2
— whose ``when`` may already hold on a cardiac answer — could never fire.

The close is one state-lane Work, ``close_session``:

- **It queues behind the session's last answers.** ``SessionStack.close`` (and
  so ``VoiceSessionRouter.end``) submits it and returns at once; the Backend
  pump runs it in FIFO order after every answer already submitted, so an
  answer the patient gave before leaving binds first, and the close sees
  what is truly still open. Nothing here is awaited by the Talker
  (invariant 9).
- **It closes only an asked, unanswered tense anchor.** For each CD-05 anchor
  the protocol holds that is ``ASKED_PENDING`` — its follow-up pending
  included — :meth:`~intake_voice_runtime.clinical_agent.fsm.IntakeEngine.close_unanswered`
  records UNCLEAR and the gap, exactly what a spent clarification records,
  and CD-05 resolves it to the reference day. A step that was never asked is
  not touched (files/13 §9.6); nor is any slot that is not an anchor.
- **It decides nothing.** The handler returns an empty effect. The queue
  compares the answers the served rules read before and after it, as it does
  for every state Work, and the rules engine — and nothing else — evaluates
  the change (invariant 1). A RED takes the path every RED takes: the queue
  derives ``preempt``, the clinician route is told as it settles, the queue
  seals, and the Talker, if the device is still there, triggers the
  pre-positioned script over the data channel (invariant 21). The session
  router keeps the Talker's between-turn watch running past ``end`` until the
  close has settled, because an ended session takes no turn that could
  deliver it otherwise (INT-545).

The request is content-addressed like every other Work, from the session and
a fixed marker, so closing twice is one close.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Final

from clinical_schemas.session import AnswerState

from intake_voice_runtime.clinical_agent.anchors import SessionAnchors, UnclearCause
from intake_voice_runtime.clinical_agent.work_queue import StateContext, StateEffect
from intake_voice_runtime.ports import WorkRequest, WorkType

__all__ = ["CLOSE_STEP_ID", "SessionCloseHandler", "close_request"]

#: The close answers no question. A ``/`` and no ``.``, so it can never be a
#: plan step's ``<section>.<slot>`` id.
CLOSE_STEP_ID: Final = "session/close"
_CLOSE_INPUT: Final = hashlib.sha256(WorkType.CLOSE_SESSION.value.encode("utf-8")).hexdigest()


def close_request(*, session_id: str, protocol_hash: str) -> WorkRequest:
    """The one close request a session has: the same id however often asked."""
    return WorkRequest(
        session_id=session_id,
        work_type=WorkType.CLOSE_SESSION,
        step_id=CLOSE_STEP_ID,
        input_hash=_CLOSE_INPUT,
        protocol_hash=protocol_hash,
        # the close answers no offered question, so no snapshot version is its
        engine_version=0,
    )


@dataclass
class SessionCloseHandler:
    """Close each asked, unanswered tense anchor; decide nothing."""

    anchors: SessionAnchors | None
    #: The anchors the protocol holds — the only steps this handler may close.
    steps: Collection[str]
    #: The anchors closed, in order: ids only.
    closed: list[str] = field(default_factory=list, init=False)

    def __call__(self, context: StateContext) -> StateEffect:
        engine = context.engine
        if self.anchors is None:
            return StateEffect()
        for anchor in sorted(self.anchors.refs.intersection(self.steps)):
            if engine.state_of(anchor) is AnswerState.ASKED_PENDING:
                engine.close_unanswered(anchor)
                self.anchors.note_unclear(anchor, UnclearCause.SESSION_CLOSED)
                self.closed.append(anchor)
        return StateEffect()
