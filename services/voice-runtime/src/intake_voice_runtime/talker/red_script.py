"""The pre-positioned RED script, named rather than carried.

files/00 §3 D12, restated as files/03 §4.6 invariant 4: *"the RED script is
pre-positioned on the device — bundled with the app build rather than streamed
— and triggered by a data-channel message"*. The arithmetic behind it is
§4.5.1's: downlink p95 is 16 ms RAN + 165 ms jitter buffer + 25 ms device
output = 206 ms **before the clip's first sample is even scheduled**, and the
in-flight playback has to be cancelled first. A 300 ms end-to-end budget is
not reachable if the script travels the audio path, so it does not.

The consequence for this module is the whole of its design: **the runtime
never holds the script's Turkish.** A :class:`RedScriptRef` is an identity
(``script_id``), a binding (``script_hash``), the two axes it was resolved for,
and the two affordance facts the device needs. Three things fall out of that:

- **Invariant 10 (verbatim) becomes structural.** There is no string to
  paraphrase, and there is no code path here that could rewrite one. The
  device plays the copy it was bundled with, and ``script_hash`` refuses a
  copy that has drifted from the compiled pack.
- **Invariant 22 is checked once, where the text is.**
  :func:`script_ref_for_action` sees the compiler's own
  ``LocationAction``/``UnknownAction`` object and refuses a bare numeral in
  any of its Turkish carriers. The ref it returns carries none of them.
- **Invariant 21 is re-refused here.** ``protocols.dsl.RedFlagAction`` already
  rejects an ``ON_SITE`` action that offers 112. This module refuses it again
  on the ref, because *"absent, not de-emphasised"* is the one affordance rule
  that must not depend on a single validator holding.

The ``action_tr_ref`` form of an action carries no text at all — it names a
``docs/legal/strings.yaml`` entry under PolicyGuard with clinician sign-off
(files/04 §8.1) — so there is nothing for the numeral check to walk, and the
hash covers the reference, which is what the device resolves.
"""

from __future__ import annotations

import enum
import hashlib
import warnings

from clinical_schemas.common import FrozenModel, Sha256
from clinical_schemas.triage import RedLocation, RedRegister
from protocols.dsl import LocationAction, UnknownAction
from pydantic import Field, model_validator

from intake_voice_runtime.talker.orthography import NumeralOnTtsPathError, assert_no_numeral

__all__ = [
    "RedScriptKind",
    "RedScriptMismatch",
    "RedScriptRef",
    "RedScriptUnavailable",
    "script_id_for",
    "script_ref_for_action",
]


# The blueprint names the RED axis field `register` (CLAUDE.md invariant 21;
# files/02 §5.3); pydantic warns because ABCMeta exposes a classmethod of the
# same name. The blueprint name wins — suppress exactly that warning, the same
# way clinical_schemas.triage and protocols.dsl already do.
warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "RedScriptRef" shadows an attribute in parent',
    category=UserWarning,
)


class RedScriptUnavailable(LookupError):
    """A RED reached the preemption path with no pre-positioned script.

    Fails closed and loudly. The alternatives are worse in both directions:
    speaking nothing drops an emergency instruction silently, and composing a
    sentence here would be inventing patient-facing clinical copy (CLAUDE.md).
    The unconditional server-side effects of files/02 §5.3 — the visit-card
    state, the clinic inbox entry with its SLA, the +30 minute follow-back —
    do not run on Layer A and are unaffected by this refusal.
    """


class RedScriptMismatch(PermissionError):
    """The script offered is not the one this determination resolved to."""


class RedScriptKind(enum.StrEnum):
    """What the device is being asked to present.

    files/02 §5.3 Axis 3 makes ``UNKNOWN`` a different *kind* of thing rather
    than a third action: *"Ask exactly one question — 'Şu anda hastanede
    misiniz?' — and branch on the answer. Never guess"*. Modelling it as an
    action with weaker content is how a guess gets made.
    """

    ACTION = "action"
    LOCATION_QUESTION = "location_question"


def script_id_for(rule_id: str, location: RedLocation) -> str:
    """``red.<rule_id>.<location>`` — the device's lookup key.

    Derived rather than minted, for the same reason ``work_key`` is
    (files/12 §7.5): the app bundle and the runtime compute it from the same
    two facts, so they agree without a registry to keep in step.
    """
    return f"red.{rule_id}.{location.value.lower()}"


class RedScriptRef(FrozenModel):
    """One pre-positioned script, as the runtime is allowed to know it."""

    rule_id: str = Field(min_length=1, description="The winning rule (files/04 §5).")
    kind: RedScriptKind
    register: RedRegister = Field(description="Axis 2 — no default (invariant 21).")
    location: RedLocation = Field(description="Axis 3 — no default (invariant 21).")
    script_id: str = Field(min_length=1)
    script_hash: Sha256 = Field(
        description="sha256 over the compiled action object. The device refuses "
        "to present a bundled copy whose hash differs, which is what makes "
        "'verbatim' hold across the bundle boundary (invariant 10)."
    )
    show_112: bool = Field(
        description="Whether the 112 affordance is rendered. Never under ON_SITE, "
        "and not under UNKNOWN until the one question is answered (files/02 §5.3)."
    )
    notify_staff: bool = Field(
        description="ON_SITE promotes the staff notification from a button to an "
        "automatic action (files/02 §5.3)."
    )

    @model_validator(mode="after")
    def _axes_resolve(self) -> RedScriptRef:
        if self.location is RedLocation.ON_SITE and self.show_112:
            raise ValueError(
                "ON_SITE never offers 112 — the affordance is absent, not "
                "de-emphasised (CLAUDE.md invariant 21; files/02 §5.3)"
            )
        if self.location is RedLocation.UNKNOWN:
            if self.kind is not RedScriptKind.LOCATION_QUESTION:
                raise ValueError(
                    "UNKNOWN resolves to exactly one question, never an action "
                    "script (files/02 §5.3 Axis 3)"
                )
            if self.show_112:
                raise ValueError(
                    "112 is not rendered under UNKNOWN until the one question is "
                    "answered (files/02 §5.3 Axis 3)"
                )
        elif self.kind is not RedScriptKind.ACTION:
            raise ValueError(
                f"{self.location.value} resolves to the rule's action script (files/02 §5.3 Axis 3)"
            )
        if self.script_id != script_id_for(self.rule_id, self.location):
            raise ValueError(
                f"script_id {self.script_id!r} is not the derived key for "
                f"({self.rule_id!r}, {self.location.value}) — the device looks the "
                "script up by the derived key and would find nothing"
            )
        return self

    def assert_resolves(
        self, *, rule_ids: frozenset[str], register: RedRegister, location: RedLocation
    ) -> None:
        """Refuse a script that is not this determination's own.

        The provenance gate of INT-091 stops a forged *level*; this stops a
        forged *script* — a real RED carrying the ref of a different rule's,
        or a different location's, pre-positioned copy.
        """
        if self.rule_id not in rule_ids:
            raise RedScriptMismatch(
                f"the pre-positioned script names rule {self.rule_id!r}, which the "
                "determination did not fire"
            )
        if self.register is not register or self.location is not location:
            raise RedScriptMismatch(
                f"the script was resolved for ({self.register.value}, "
                f"{self.location.value}) and the determination is ({register.value}, "
                f"{location.value}) — register and location travel with the script "
                "they were clinician-approved for (files/02 §5.3)"
            )


def _turkish_carriers(action: LocationAction | UnknownAction) -> tuple[str, ...]:
    """Every patient-facing Turkish string the action carries inline."""
    if isinstance(action, UnknownAction):
        return (action.ask_one_tr,)
    carriers = [*action.do_nots_tr]
    for text in (action.action_tr, action.why_tr):
        if text is not None:
            carriers.append(text)
    return tuple(carriers)


def script_ref_for_action(
    *,
    rule_id: str,
    register: RedRegister,
    location: RedLocation,
    action: LocationAction | UnknownAction,
) -> RedScriptRef:
    """Build the ref for one rule's location-resolved action.

    The input is the object ``protocols.triage.engine.evaluate_triage`` puts on
    ``TriageEvaluation.action`` — *"the winning rule's own frozen action object
    for the resolved location"* — so nothing is re-derived here and there is no
    second place a location could resolve differently.
    """
    if (location is RedLocation.UNKNOWN) != isinstance(action, UnknownAction):
        raise ValueError(
            f"location {location.value} does not match the resolved action type "
            f"{type(action).__name__} (files/02 §5.3 Axis 3)"
        )
    for text in _turkish_carriers(action):
        try:
            assert_no_numeral(text)
        except NumeralOnTtsPathError as err:
            raise NumeralOnTtsPathError(
                f"the RED action script for rule {rule_id!r} under "
                f"{location.value} carries an unexpanded numeral, so the compiler's "
                f"Turkish expansion did not run for it: {err}"
            ) from err
    digest = hashlib.sha256(action.model_dump_json().encode("utf-8")).hexdigest()
    return RedScriptRef(
        rule_id=rule_id,
        kind=(
            RedScriptKind.LOCATION_QUESTION
            if isinstance(action, UnknownAction)
            else RedScriptKind.ACTION
        ),
        register=register,
        location=location,
        script_id=script_id_for(rule_id, location),
        script_hash=digest,
        show_112=action.show_112 if isinstance(action, LocationAction) else False,
        notify_staff=(
            action.notify_staff_immediate if isinstance(action, LocationAction) else False
        ),
    )
