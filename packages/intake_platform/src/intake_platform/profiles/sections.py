"""INT-133 — the adolescent-private section, released and rendered.

files/06 §6, verbatim: "the adolescent-private section is delivered to the
clinician; guardian visibility of that section follows the treating clinic's
written policy within HHY information rights — the app records which policy
applied".

INT-223 turned that into :func:`~intake_platform.consent.minors.
adolescent_private_visibility` and it stays the decider — this module adds
the two things a flow needs on top of a release decision:

- **which section** — one id, so the note pipeline and the guardian-facing
  view name the same thing rather than each inventing a label;
- **whether it may be drawn right now**, which is a different question from
  whether the audience is entitled to it. A guardian who IS entitled still
  must not have the section painted onto a screen the adolescent is looking
  over — files/13 §13's third-party rule applies to rendering as much as to
  asking. ``renderable_on_shared_device`` carries that, and it can only ever
  narrow ``released``, never widen it.

Where no clinic policy is recorded the guardian sees nothing and the
decision says so: ``adolescent_private_guardian_default`` is awaiting-human
(HB-L20) and its fail-closed reading is withhold. That default is not
softened here under any argument.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from intake_platform.consent.minors import (
    ClinicPolicy,
    SectionAudience,
    adolescent_private_visibility,
)

__all__ = [
    "ADOLESCENT_PRIVATE_SECTION",
    "SectionRelease",
    "release_adolescent_private_section",
]

#: The one section files/06 §6 names. An id, never a label: the tr copy for
#: it lives in the i18n catalogue (invariant 5).
ADOLESCENT_PRIVATE_SECTION = "adolescent_private"


@dataclass(frozen=True)
class SectionRelease:
    """Who may receive the section, whether it may be drawn now, and under
    which recorded policy."""

    section: str
    audience: SectionAudience
    released: bool
    renderable_on_shared_device: bool
    policy_entry: str
    applied_policy: str | None = None
    blocked_on: tuple[str, ...] = field(default=())


def release_adolescent_private_section(
    *,
    audience: SectionAudience,
    clinic_policy: ClinicPolicy | None = None,
    third_party_present: bool = False,
) -> SectionRelease:
    """Resolve the release for one audience.

    ``third_party_present`` narrows the render only. A guardian entitled by
    a recorded policy stays entitled — the section is simply not painted
    while someone else can see the screen.
    """
    decision = adolescent_private_visibility(audience, clinic_policy=clinic_policy)
    blocked_on: tuple[str, ...] = ()
    if not decision.visible and decision.policy_entry == "adolescent_private_guardian_default":
        # no recorded clinic policy: the withholding IS the fail-closed
        # reading of an open HB-L20 question, so name it
        blocked_on = ("adolescent_private_guardian_default",)
    return SectionRelease(
        section=ADOLESCENT_PRIVATE_SECTION,
        audience=audience,
        released=decision.visible,
        renderable_on_shared_device=decision.visible and not third_party_present,
        policy_entry=decision.policy_entry,
        applied_policy=decision.applied_policy,
        blocked_on=blocked_on,
    )
