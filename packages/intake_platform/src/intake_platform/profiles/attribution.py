"""INT-133 — who is speaking, and what that does to the record.

files/02 §3 names **three** attribution values, not two:

- ``self_report`` — the patient, alone, in their own words;
- ``proxy_report`` — a companion answering *for* the patient (Zeynep mode
  (a): at home, doing the intake on his behalf);
- ``assisted_self_report`` — the patient's own words, spoken on a family
  member's device, with the family member present (Zeynep mode (b)). This
  value exists because the other two both lie about that situation: proxy
  mode misattributes her father's words to her, and self-report mode
  pretends he is alone.

Two firm rules ride the derivation and neither is a caller's choice:

1. **files/06 §6** — "Companion/proxy answers are always flagged
   ``proxy_reported`` on the record". So ``proxy_reported`` is DERIVED here
   from the declared role and speaker; no caller may assert it, and no
   caller may clear it.
2. **files/13 §13** — a third party present is "a **confound**, not a
   feature": every sensitive section switches to text and **safeguarding is
   not asked at all**. ``assisted_self_report`` implies a third party by
   definition, and a proxy is never asked safeguarding questions about the
   patient either, so both land in the same regime.

The proxy acknowledgement gates the companion roles: the protocol asks it
(``identity_check.proxy_reported`` in the base pack) and this module refuses
a companion session without it. It is an acknowledgement of ROLE, never of
representation — nothing here can make a companion a legal representative.
That question is ``guardian_relationship_proof`` and it is awaiting-human
(HUMAN_BLOCKERS HB-L20); the age gate in
:mod:`intake_platform.profiles.flow` runs first and refuses every minor
subject regardless of what was acknowledged.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "Attribution",
    "AttributionDecision",
    "ProxyAcknowledgement",
    "SensitiveDelivery",
    "Speaker",
    "SubjectRole",
    "resolve_attribution",
]

#: Returned when a companion session has no acknowledgement. A product rule
#: (the protocol asks the question), not a legal one — nothing is awaiting a
#: human here, so the flow's ``blocked_on`` stays empty for it.
PROXY_ACK_REQUIRED = "proxy_acknowledgement_required"


class SubjectRole(enum.StrEnum):
    """What the person holding the device declares about themselves.

    Mirrors the base pack's ``subject_role`` slot ("kendim için" /
    "yakınım adına") — the same two answers, typed.
    """

    SELF = "self"
    COMPANION = "companion"


class Speaker(enum.StrEnum):
    """Who is actually answering the questions. Only meaningful once the
    role is ``COMPANION``: a companion may be answering *for* the patient
    (proxy) or merely holding the device while the patient answers
    (assisted)."""

    PATIENT = "patient"
    COMPANION = "companion"


class Attribution(enum.StrEnum):
    """files/02 §3, exactly three values."""

    SELF_REPORT = "self_report"
    PROXY_REPORT = "proxy_report"
    ASSISTED_SELF_REPORT = "assisted_self_report"


class SensitiveDelivery(enum.StrEnum):
    """What delivery a sensitive section gets (files/13 §13).

    ``PROTOCOL`` means "whatever the pack declares" — this layer does not
    reach into the DSL. ``TEXT_ONLY`` is an override this layer imposes and
    the pack may never relax, because the reason for it (someone else is
    listening) is a session fact the pack cannot see.
    """

    PROTOCOL = "protocol"
    TEXT_ONLY = "text_only"


@dataclass(frozen=True)
class ProxyAcknowledgement:
    """The companion's in-session acknowledgement that they are answering on
    the patient's behalf, with the instant it happened.

    The two fields move together or the object refuses to exist: an
    acknowledgement with no instant cannot be evidenced, and an instant with
    no acknowledgement is a record of something that did not happen.
    """

    acknowledged: bool
    at: datetime | None = None

    def __post_init__(self) -> None:
        if self.acknowledged and self.at is None:
            raise ValueError("an acknowledgement must carry the instant it was given")
        if not self.acknowledged and self.at is not None:
            raise ValueError("an instant without an acknowledgement records nothing")


@dataclass(frozen=True)
class AttributionDecision:
    """The derived session facts. ``permitted`` is False only for the
    missing-acknowledgement case; the age axis is decided upstream by
    INT-223 and never re-decided here."""

    attribution: Attribution
    proxy_reported: bool
    third_party_present: bool
    sensitive_delivery: SensitiveDelivery
    safeguarding_asked: bool
    permitted: bool = True
    refusal_code: str | None = None


def _refused() -> AttributionDecision:
    """The fail-closed shape: no attribution is claimed, the most protective
    delivery applies, and safeguarding is not asked — a refusal must not be
    a cheaper path to a laxer regime."""
    return AttributionDecision(
        attribution=Attribution.PROXY_REPORT,
        proxy_reported=True,
        third_party_present=True,
        sensitive_delivery=SensitiveDelivery.TEXT_ONLY,
        safeguarding_asked=False,
        permitted=False,
        refusal_code=PROXY_ACK_REQUIRED,
    )


def resolve_attribution(
    *,
    role: SubjectRole,
    speaker: Speaker,
    acknowledgement: ProxyAcknowledgement | None = None,
    third_party_present: bool = False,
) -> AttributionDecision:
    """Derive the session's attribution and its consequences.

    ``third_party_present`` is an INPUT (declared by the patient or detected
    by the observer lanes), not something inferred from the role: a proxy
    filling the form at home has no third party in the room, and pretending
    otherwise would put a factual qualifier on the note that nobody
    observed (files/04 §4.3 — strictly factual, never a relationship
    inference). What the role DOES decide is the delivery regime, because a
    sensitive question answered by someone other than the subject is the
    same confound by another route.
    """
    if role is SubjectRole.SELF:
        if speaker is not Speaker.PATIENT:
            raise ValueError("a self role cannot declare a companion speaker")
        return AttributionDecision(
            attribution=Attribution.SELF_REPORT,
            proxy_reported=False,
            third_party_present=third_party_present,
            sensitive_delivery=(
                SensitiveDelivery.TEXT_ONLY if third_party_present else SensitiveDelivery.PROTOCOL
            ),
            safeguarding_asked=not third_party_present,
        )

    if acknowledgement is None or not acknowledgement.acknowledged:
        return _refused()

    if speaker is Speaker.PATIENT:
        # files/02 §3: the patient's own words on a family member's device.
        # The note records the patient as the speaker and the assistance as
        # context — so NOT proxy-reported — but a third party is present by
        # definition, which is the whole reason the value exists.
        return AttributionDecision(
            attribution=Attribution.ASSISTED_SELF_REPORT,
            proxy_reported=False,
            third_party_present=True,
            sensitive_delivery=SensitiveDelivery.TEXT_ONLY,
            safeguarding_asked=False,
        )

    # files/06 §6: companion/proxy answers are ALWAYS flagged.
    return AttributionDecision(
        attribution=Attribution.PROXY_REPORT,
        proxy_reported=True,
        third_party_present=third_party_present,
        sensitive_delivery=SensitiveDelivery.TEXT_ONLY,
        safeguarding_asked=False,
    )
