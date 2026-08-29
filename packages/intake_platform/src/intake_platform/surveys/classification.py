"""INT-242 — is a survey invitation a transactional or a commercial message?

CLAUDE.md invariant 18: *"reminders are transactional-only unless an İYS
consent record exists."* files/06 §1 row 6563-İYS names INT-242 explicitly:
*"Appointment/service messages are non-commercial; **any** marketing message
requires İYS-registered consent; sender records kept."* So the classification
is not a detail — it decides whether the product may send this at all.

**The determination: a satisfaction survey invitation carried to a recipient
as an electronic message is COMMERCIAL.**

The reasoning, and it is worth being explicit because the easy answer is the
wrong one:

- 6563 m.2/1(c) defines a *ticari elektronik ileti* as data, voice or image
  content sent electronically **ticari amaçlarla** — for commercial purposes.
  The test is the sender's purpose, not whether the text sells something.
- The Yönetmelik (RG 29417, 15.07.2015) m.6 is where the consent-free
  messages live: those about the **change, use or maintenance** of a good or
  service the recipient asked for, and notifications of a continuing
  subscription, membership or partnership, collection, debt reminder,
  information update, purchase and delivery **or similar** — plus statutory
  information duties. It closes by forbidding those messages from promoting
  or advertising any good or service.
- An invitation to rate us is none of those. It does not concern the change,
  use or maintenance of the care the patient received; it notifies them of
  nothing about their own transaction; the service they asked for is complete
  and correct without it. It exists because **we** want the answer. And the
  NPS question is, literally, whether the recipient would recommend us — a
  loyalty and advocacy measure, which is the promotional edge of the carve-out
  rather than the safe middle of it.
- Contrast INT-141's reminders, which really are transactional: they tell the
  patient about the preparation for a visit **they** booked, and without them
  the service they asked for does not happen properly.

So the invitation needs an İYS-registered consent. No İYS registry exists in
this tree — :class:`~intake_platform.notifications.iys.UnconfiguredIysRegistry`
refuses every lookup and the record type is abstract with no concrete subclass
(INT-141) — which means **the patient-facing NPS invitation cannot be sent
today**. That is the correct outcome, not a gap to route around, and it is why
this module hands the planner a question rather than a switch.

Two honest boundaries:

1. **This is a legal judgement and it is recorded as an ask** (counsel;
   docs/evidence/INT-242.md). The classification that ships is the
   conservative one: reading a survey as commercial can only make the product
   send *less*, and if counsel later reads the m.6 "benzeri durumlar" clause
   more widely, relaxing it is a reviewed change rather than a silent one.
2. **The tacir/esnaf question is not answered here.** The Yönetmelik treats
   messages to merchants differently, and a clinician is a professional
   recipient — but "which of our clinician recipients is a *tacir* or *esnaf*"
   is a fact about each contract, not a fact about this code. Both kinds are
   classified the same way, which is the side that under-sends.

:class:`InvitationChannel` is the axis that decides whether 6563 engages at
all. An in-product prompt shown to someone already signed in is not an
*ileti* being sent anywhere: nothing arrives, no lock screen lights up, no
contact address is used. It is still governed by the ``satisfaction_prompts``
safety flag, so "6563 does not engage" is not "anything goes".
"""

from __future__ import annotations

import enum
from typing import Final

from intake_platform.notifications.catalogue import MessageClass

__all__ = [
    "SATISFACTION_PROMPTS_FLAG",
    "SURVEY_MESSAGE_CLASS",
    "InvitationChannel",
    "requires_iys_consent",
]


class InvitationChannel(enum.StrEnum):
    """How the invitation would reach the recipient."""

    #: Rendered inside the app to a signed-in user. Nothing is transmitted to
    #: a contact address, so no *elektronik ileti* is sent.
    IN_PRODUCT = "in_product"
    #: Push or SMS to a contact address — 6563 territory.
    ELECTRONIC_MESSAGE = "electronic_message"


#: The determination above, as a constant rather than a branch: **both**
#: survey kinds are commercial-class when carried as an electronic message.
#: There is no kind-dependent softer answer, because the argument that makes
#: NPS commercial does not turn on which survey it is.
SURVEY_MESSAGE_CLASS: Final = MessageClass.COMMERCIAL

#: Pre-declared False in ``intake_platform.flags`` since INT-023, with the
#: rationale "İYS posture (inv. 18): no prompt without consent" — this issue
#: is the first caller, and does not redefine it.
SATISFACTION_PROMPTS_FLAG: Final = "satisfaction_prompts"


def requires_iys_consent(channel: InvitationChannel) -> bool:
    """Whether 6563 engages for an invitation carried this way."""
    return channel is InvitationChannel.ELECTRONIC_MESSAGE
