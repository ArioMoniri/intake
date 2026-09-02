"""INT-296 — the session's one locale, and the only two ways it is ever set.

**One language per session, fixed at the start.** :class:`SessionLocale` is
frozen. It is a field of the session — recorded on ``sessions.locale`` — rather
than an argument threaded through every lookup, so the note, the audit entry
and the metric label all read the same value and no single turn can be
assembled out of two languages.

**Chosen, never inferred.** :class:`LocaleChoiceSource` has three members and
none of them means "worked out from what the patient said". This is not
squeamishness about a model's quality. Invariant 21 puts the red-flag script on
the device, fired over the data channel, because a failed escalation is the one
failure this product may not have — and a language guess that is wrong delivers
that script in a language the patient cannot read. The strongest version of a
guess this module will accept is an *offer*: something proposes a language, the
patient confirms it, and only the confirmation produces a locale.

**And the offer is unreachable while a RED script is in flight.** A language
prompt on top of "hold pressure, call 112" is a modal dialogue between the
patient and the sentence that matters most. :func:`offer_locale_switch` raises
rather than returning an offer nobody may show, and ``red_script_in_flight``
has no default, so a caller cannot leave the gate open by forgetting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .registry import (
    DEFAULT_LOCALE,
    LocaleNotOffered,
    offerable_intake_locales,
    registration,
    safe_code,
)

__all__ = [
    "METRIC_LABEL_NAME",
    "LocaleChoiceSource",
    "LocaleSwitchOffer",
    "RedScriptInFlight",
    "SessionLocale",
    "choose_session_locale",
    "confirm_locale_switch",
    "default_session_locale",
    "offer_locale_switch",
]

#: The label name under which a session's language may appear on a metric.
#: A closed code, never a name — see :func:`SessionLocale.metric_label`.
METRIC_LABEL_NAME = "locale"


class RedScriptInFlight(RuntimeError):
    """A locale offer was attempted during a red-flag script.

    Fail-closed by construction: the caller gets an exception, not an offer it
    might render anyway.
    """


class LocaleChoiceSource(StrEnum):
    """How a session came to be in the language it is in.

    Three members, and the absent fourth is the point: there is no member for
    a language worked out from speech, so a locale that arrived that way is
    not representable.
    """

    #: Nobody chose; the session runs in the source-of-truth language.
    DEFAULT = "default"
    #: The patient picked it from the chooser.
    PATIENT_CHOICE = "patient_choice"
    #: Something proposed it and the patient said yes.
    PATIENT_CONFIRMED_OFFER = "patient_confirmed_offer"


@dataclass(frozen=True, slots=True)
class SessionLocale:
    """The one language a session runs in.

    Frozen because "fixed at the start" has to be a property of the value.
    Two fields and no third: there is nowhere here for a display name, a
    confidence score or anything else a patient supplied to be carried along
    (invariant 6).
    """

    code: str
    source: LocaleChoiceSource

    @property
    def metric_label(self) -> str:
        """The value this session contributes to a ``locale`` metric label.

        Safe by construction rather than by sanitising on the way out: a
        ``SessionLocale`` only ever holds a registered code, because the two
        functions that build one both go through the registry.
        """
        return self.code


@dataclass(frozen=True, slots=True)
class LocaleSwitchOffer:
    """A proposal the patient has not yet answered.

    Holding it as a value — rather than switching and letting the patient undo
    it — is what makes the confirmation real. ``suggested`` is validated
    against the registry at construction, so an offer for a language this build
    does not run cannot exist to be rendered.
    """

    current: SessionLocale
    suggested: str


def default_session_locale() -> SessionLocale:
    """Turkish, unchosen. Invariant 5's default, stated as a value."""
    return SessionLocale(code=DEFAULT_LOCALE, source=LocaleChoiceSource.DEFAULT)


def choose_session_locale(code: str) -> SessionLocale:
    """The patient picked ``code`` from the chooser.

    Refused unless the locale is registered, complete **and** carries a
    clinical sign-off: an intake speaks red-flag scripts and instrument items,
    so a language good enough to draw a settings screen is not good enough
    here. The refusal echoes nothing the caller passed in.
    """
    entry = registration(code)
    if not entry.offerable_for_intake:
        raise LocaleNotOffered(
            f"locale {safe_code(code)} may render the app but may not run an intake: "
            "no clinician who reads it has signed its clinical text (HB-C19)"
        )
    return SessionLocale(code=entry.code, source=LocaleChoiceSource.PATIENT_CHOICE)


def offer_locale_switch(
    *, current: SessionLocale, suggested: str, red_script_in_flight: bool
) -> LocaleSwitchOffer:
    """Propose a language change for the patient to confirm.

    This is the *only* door through which anything other than a patient's own
    tap may influence the session language, and it does not open the door — it
    produces a proposal that :func:`confirm_locale_switch` turns into a locale
    if, and only if, the patient says yes.

    ``red_script_in_flight`` is keyword-only and has no default. A gate whose
    closed position is the one a forgetful caller gets is not a gate.
    """
    if red_script_in_flight:
        raise RedScriptInFlight(
            "a red-flag script is in flight: the language offer is unreachable until "
            "it has been delivered (invariant 21 — the RED script is pre-positioned "
            "on the device and nothing may sit in front of it)"
        )
    if suggested not in offerable_intake_locales():
        raise LocaleNotOffered(
            f"locale {safe_code(suggested)} may not be offered: this build runs an "
            f"intake in {', '.join(offerable_intake_locales())}"
        )
    return LocaleSwitchOffer(current=current, suggested=suggested)


def confirm_locale_switch(*, offer: LocaleSwitchOffer, patient_confirmed: bool) -> SessionLocale:
    """Answer an offer. ``False`` leaves the session exactly as it was."""
    if not patient_confirmed:
        return offer.current
    return SessionLocale(code=offer.suggested, source=LocaleChoiceSource.PATIENT_CONFIRMED_OFFER)
