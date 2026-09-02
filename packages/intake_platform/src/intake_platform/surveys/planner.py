"""INT-242 — the survey invitation planner: five locks and an order.

The planner decides whether one recipient may be invited to one survey at one
instant. It does **not** send: sending is INT-141's dispatcher, which takes a
:class:`~intake_platform.notifications.catalogue.ReminderKind` — an enum with
no survey member — from a catalogue with no survey template. So even
``ISSUED`` is a statement about eligibility, never a delivery.

Order of refusal, and each step is a different authority:

1. **Opt-out.** The recipient's own refusal, read first because it is the one
   worth naming even when something else would also have stopped the send.
2. **İYS.** A survey invitation carried as an electronic message is
   commercial-class (see ``classification``), so it needs a registered
   consent; the only registry in the tree refuses, and the block is reported
   rather than raised — "no İYS integration exists" is a state of the world a
   scheduler should record, not crash on.
3. **The ``satisfaction_prompts`` safety flag**, pre-declared False since
   INT-023. Law before configuration: a tenant opening the flag does not open
   the İYS gate, and the test grid proves it.
4. **The schedule.** Refuses when the first-prompt value nobody has supplied
   is needed; otherwise due or not yet due.
5. **Quiet hours**, evaluated by INT-141's own
   :func:`~intake_platform.notifications.preferences.quiet_verdict` — one
   implementation, not a second copy — with an unset baseline refusing.

Quiet hours apply to every channel rather than only to messages. An in-product
card does not wake anyone, so the narrower reading is defensible; the wider
one costs nothing, needs no invented distinction, and errs toward asking
people less.

Logging is kind, channel and status. Not the recipient handle: a tokenized
pseudonym in a log line is still an identifier (invariant 6).
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import final

from intake_platform.flags import FlagProvider, InMemoryProvider
from intake_platform.notifications.iys import IysRegistry, IysRegistryUnconfigured
from intake_platform.notifications.preferences import (
    NotificationPreferences,
    QuietVerdict,
    QuietWindow,
    quiet_verdict,
)
from intake_platform.surveys.cadence import (
    DueStatus,
    SurveyKind,
    SurveyPolicy,
    SurveyRecipient,
    due,
)
from intake_platform.surveys.classification import (
    SATISFACTION_PROMPTS_FLAG,
    SURVEY_MESSAGE_CLASS,
    InvitationChannel,
    requires_iys_consent,
)
from intake_platform.surveys.metrics import SURVEY_INVITATION_TOTAL

__all__ = ["InvitationOutcome", "InvitationStatus", "SurveyInvitationPlanner"]

logger = logging.getLogger(__name__)

#: What the metric's ``message_class`` label says for an in-product prompt.
#: Not "transactional": that would assert a 6563 class for something 6563 does
#: not reach, and the distinction is the whole determination.
_NOT_A_MESSAGE = "not_a_message"


class InvitationStatus(enum.StrEnum):
    ISSUED = "issued"
    NOT_YET_DUE = "not_yet_due"
    SUPPRESSED_OPT_OUT = "suppressed_opt_out"
    BLOCKED_IYS_CONSENT_ABSENT = "blocked_iys_consent_absent"
    BLOCKED_PROMPTS_DISABLED = "blocked_prompts_disabled"
    REFUSED_SCHEDULE_UNSET = "refused_schedule_unset"
    DEFERRED_QUIET_HOURS = "deferred_quiet_hours"
    REFUSED_QUIET_HOURS_UNSET = "refused_quiet_hours_unset"


@final
@dataclass(frozen=True, slots=True)
class InvitationOutcome:
    """The decision. Carries no recipient handle — a caller that needs to act
    on it already holds the recipient it asked about."""

    status: InvitationStatus
    kind: SurveyKind
    channel: InvitationChannel
    due_at: datetime | None = None


@final
class SurveyInvitationPlanner:
    """Says whether a recipient may be invited, or honestly why not."""

    def __init__(
        self,
        *,
        iys: IysRegistry,
        policy: SurveyPolicy,
        flags: FlagProvider | None = None,
        baseline_quiet: QuietWindow | None = None,
    ) -> None:
        self._iys = iys
        self._policy = policy
        self._flags = flags if flags is not None else InMemoryProvider()
        self._baseline_quiet = baseline_quiet

    def plan(
        self,
        kind: SurveyKind,
        *,
        channel: InvitationChannel,
        recipient: SurveyRecipient,
        preferences: NotificationPreferences,
        at: datetime,
    ) -> InvitationOutcome:
        """``preferences`` has no default on purpose: a planner that assumed
        "nobody has opted out" when the caller forgot the argument would
        invite exactly the people who asked not to be."""
        status, due_at = self._decide(kind, channel, recipient, preferences, at)
        message_class = (
            SURVEY_MESSAGE_CLASS.value if requires_iys_consent(channel) else _NOT_A_MESSAGE
        )
        SURVEY_INVITATION_TOTAL.labels(
            kind=kind.value,
            channel=channel.value,
            message_class=message_class,
            status=status.value,
        ).inc()
        logger.info(
            "survey_invitation kind=%s channel=%s message_class=%s status=%s",
            kind.value,
            channel.value,
            message_class,
            status.value,
        )
        return InvitationOutcome(status=status, kind=kind, channel=channel, due_at=due_at)

    def _decide(
        self,
        kind: SurveyKind,
        channel: InvitationChannel,
        recipient: SurveyRecipient,
        preferences: NotificationPreferences,
        at: datetime,
    ) -> tuple[InvitationStatus, datetime | None]:
        if preferences.opted_out:
            return InvitationStatus.SUPPRESSED_OPT_OUT, None
        if requires_iys_consent(channel) and not self._iys_cleared(recipient):
            return InvitationStatus.BLOCKED_IYS_CONSENT_ABSENT, None
        if not self._flags.get_bool(SATISFACTION_PROMPTS_FLAG, False):
            return InvitationStatus.BLOCKED_PROMPTS_DISABLED, None
        decision = due(kind, recipient, self._policy, at=at)
        match decision.status:
            case DueStatus.REFUSED_FIRST_PROMPT_DELAY_UNSET:
                return InvitationStatus.REFUSED_SCHEDULE_UNSET, None
            case DueStatus.NOT_YET_DUE:
                return InvitationStatus.NOT_YET_DUE, decision.due_at
            case DueStatus.DUE:
                pass
        match quiet_verdict(preferences, baseline=self._baseline_quiet, at=at):
            case QuietVerdict.UNSET:
                return InvitationStatus.REFUSED_QUIET_HOURS_UNSET, decision.due_at
            case QuietVerdict.QUIET:
                return InvitationStatus.DEFERRED_QUIET_HOURS, decision.due_at
            case QuietVerdict.CLEAR:
                return InvitationStatus.ISSUED, decision.due_at

    def _iys_cleared(self, recipient: SurveyRecipient) -> bool:
        """A commercial-class message needs a registered consent. The lookup
        raising is the honest negative today; a registry that answered "no"
        would be indistinguishable from a real one that had looked."""
        try:
            record = self._iys.lookup(recipient.recipient_ref)
        except IysRegistryUnconfigured:
            return False
        # 6563 keeps sender records, so a record that cannot cite the registry
        # is not a record — the same check seal_commercial makes.
        return bool(record.registry_reference().strip())
