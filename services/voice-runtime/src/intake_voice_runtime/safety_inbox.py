"""The clinician route into the clinic Safety inbox (INT-406; invariant 49).

:class:`SafetyInboxNotifier` is the production
:class:`~intake_voice_runtime.talker.red_path.ClinicNotifier`: it turns one
:class:`~intake_voice_runtime.talker.red_path.RedNotification` into one
:class:`~intake_platform.safety_inbox.InboxEntry` and puts it in the process's
:class:`~intake_platform.safety_inbox.SafetyInboxOutbox`. That is the whole of
it, and each property of the port survives:

- **Nothing awaits and nothing dials.** ``notify`` is an append under a lock;
  the outbox's worker writes the shared store. The RED path's first step
  cannot delay its stop (the port's contract), and no connector, network call
  or hospital system sits between the RED and the entry — "regardless of
  connector presence" (files/02 §8.2) holds by construction.
- **Ids only** (invariant 6). The notification carries ids and closed axes and
  the entry keeps the ids plus the register — a closed enum the clinician
  queue does not show, recorded because files/02 §2b re-shows a RED "in the
  register the original RED used" when its visit moves (INT-407). The location
  is not kept: it is re-derived for wherever the patient then stands.
- **Bound per session, checked at binding.** The tenant, session and visit are
  the session's; a mis-shaped one raises here, when the session is composed,
  rather than at the RED.

The same notifier may be bound to both of the RED path's clinician routes —
Layer B's, at the determination, and the preemption path's — because the
entry id is derived from the RED's content-addressed ``work_id``: the second
notification lands on the first entry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from intake_platform.safety_inbox import InboxEntry, SafetyInboxOutbox
from intake_platform.safety_inbox.model import require_id, require_tenant_id

from intake_voice_runtime.talker.red_path import RedNotification

__all__ = ["SafetyInboxNotifier"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SafetyInboxNotifier:
    outbox: SafetyInboxOutbox
    tenant_id: str
    session_id: str
    #: INT-197: a visit is a session row, so this is usually the session's id;
    #: it is separate because files/02 §2b's transitions are keyed by visit.
    visit_id: str
    wall_clock: Callable[[], datetime] = field(default=_utc_now)

    def __post_init__(self) -> None:
        require_tenant_id(self.tenant_id)
        require_id(self.session_id)
        require_id(self.visit_id)

    def notify(self, notification: RedNotification) -> None:
        self.outbox.put(
            InboxEntry.for_red(
                tenant_id=self.tenant_id,
                session_id=self.session_id,
                visit_id=self.visit_id,
                work_id=notification.work_id,
                rule_ids=notification.rule_ids,
                at=self.wall_clock(),
                # INT-407: the register rides on the one server-side record of
                # the RED, so a later files/02 §2b re-show is told the same way
                register=notification.register,
            )
        )
