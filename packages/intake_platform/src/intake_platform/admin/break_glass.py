"""The break-glass ceremony's content rules (INT-180; files/08 §2.5, §2.6).

§2.5 collapses four unmanaged read paths into one governed one. The ceremony
itself — distinct human, distinct authenticator, own session, single-use
assertion, expiry — is :mod:`intake_platform.admin.four_eyes`. What lives here
is the part that decides whether the ceremony may start at all:

1. a **closed-category** reason plus at least twenty characters of free text;
2. a **controller instruction reference** whenever we act as a processor,
   because a processor may act only on documented controller instruction;
3. a **refusal for the controller deployment**, which is the one clause that
   looks like a gap and is not.

On (3): §2.6 states the problem and this module obeys it rather than routing
around it. In the consumer deployment INTAKE is the controller; post-7499 the
health regime aligns to GDPR Art. 9, so legitimate interest is unavailable and
m.6/3's care ground runs to persons under a healthcare obligation of secrecy —
which an INTAKE support engineer is not. files/06 §2 enumerates no staff-access
purpose at all, so there is **no consent scope to check**, and invariant 4 says
every read of clinical data checks one. The inference §2.6 draws — an unbundled
``support_access`` explicit-consent purpose obtained at the point of the
support request — is counsel's call, recorded as HUMAN_BLOCKERS **HB-L6**
together with the controller-instruction reference and the 24-hour
patient-notice window. Until it is answered the controller path refuses.

The grant TTL is the one number here, and it is quoted, not chosen: §2.5 item
4 says "TTL <= 60 min, single use".
"""

from __future__ import annotations

import enum
from datetime import timedelta

from intake_platform.admin.four_eyes import Justification

__all__ = [
    "BREAK_GLASS_GRANT_TTL",
    "MIN_JUSTIFICATION_CHARS",
    "BreakGlassReason",
    "BreakGlassRefused",
    "Deployment",
    "build_break_glass_justification",
]

#: files/08 §2.5 item 4.
BREAK_GLASS_GRANT_TTL = timedelta(minutes=60)

#: files/08 §2.5 item 1: "a closed-category reason plus >= 20 characters of
#: free text". Twenty is the spec's floor, not a chosen one.
MIN_JUSTIFICATION_CHARS = 20


class Deployment(enum.StrEnum):
    """Which side of the controller/processor line the target tenant sits on.

    This is a property of the tenant, not of the actor's employer: in the
    hospital deployment we are the processor, in the consumer deployment the
    controller (files/08 §2.6). No file in this repository records it per
    tenant, so the map the console consults ships EMPTY and an unknown tenant
    refuses — see :mod:`intake_api.admin`.
    """

    PROCESSOR = "processor"
    CONTROLLER = "controller"


class BreakGlassReason(enum.StrEnum):
    """The closed category. Small on purpose: every member is a class an
    alert can be written against and a patient's access log can render, which
    an open reason string could never be."""

    PATIENT_SUPPORT_REQUEST = "patient_support_request"
    CLINICAL_SAFETY_INCIDENT = "clinical_safety_incident"
    DATA_SUBJECT_REQUEST = "data_subject_request"
    SECURITY_INCIDENT = "security_incident"
    REGULATORY_INSPECTION = "regulatory_inspection"


class BreakGlassRefused(Exception):
    """A refusal to open the ceremony. ``code`` is stable and machine-shaped;
    the free text that caused a length refusal is never echoed back."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_break_glass_justification(
    *,
    reason_class: BreakGlassReason,
    free_text: str,
    controller_instruction_ref: str | None,
    deployment: Deployment,
) -> Justification:
    """Validate §2.5's content rules and return the §8.1 justification block."""
    if deployment is Deployment.CONTROLLER:
        raise BreakGlassRefused(
            "no_lawful_basis",
            "no staff-access purpose exists for a controller deployment (files/08 §2.6; "
            "HUMAN_BLOCKERS HB-L6): invariant 4 needs a consent scope to check and "
            "files/06 §2 enumerates none",
        )
    if len(free_text.strip()) < MIN_JUSTIFICATION_CHARS:
        raise BreakGlassRefused(
            "justification_too_short",
            f"break-glass needs at least {MIN_JUSTIFICATION_CHARS} characters of free "
            "text (files/08 §2.5); the submitted text is not echoed here (invariant 6)",
        )
    if not controller_instruction_ref:
        raise BreakGlassRefused(
            "controller_instruction_required",
            "as a processor we may act only on documented controller instruction "
            "(files/08 §2.5 item 3), so the access has no basis to record without one",
        )
    return Justification(
        reason_class=reason_class,
        free_text=free_text.strip(),
        controller_instruction_ref=controller_instruction_ref,
    )
