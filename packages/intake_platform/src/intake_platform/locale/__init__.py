"""INT-296 — session locale: one language per session, chosen rather than
inferred, and a resource layer that refuses an incomplete one.

Three modules, three questions:

* :mod:`~intake_platform.locale.registry` — *which* languages this build may
  offer, on two separate conditions (a complete UI catalogue; a clinician who
  reads the language and signs its clinical text). It ships holding exactly
  ``tr``: HB-O5 names the rest and HB-C19 signs them.
* :mod:`~intake_platform.locale.resolver` — how a string is looked up, and the
  fallback that does not exist.
* :mod:`~intake_platform.locale.session` — the session's one locale, and the
  only two ways it is ever set, neither of which is a guess.

Invariant 5 is unchanged throughout: ``tr`` is the source of truth and the
default, and every other locale is additive and fails closed.
"""

from __future__ import annotations

from .registry import (
    DEFAULT_LOCALE,
    LOCALE_CODE_PATTERN,
    LOCALE_REGISTRY,
    LocaleClinicalSignoff,
    LocaleNotOffered,
    LocaleRegistration,
    enabled_locales,
    offerable_app_locales,
    offerable_intake_locales,
    registration,
    safe_code,
)
from .resolver import MissingLocaleString, check_catalogue_completeness, resolve
from .session import (
    METRIC_LABEL_NAME,
    LocaleChoiceSource,
    LocaleSwitchOffer,
    RedScriptInFlight,
    SessionLocale,
    choose_session_locale,
    confirm_locale_switch,
    default_session_locale,
    offer_locale_switch,
)

__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_CODE_PATTERN",
    "LOCALE_REGISTRY",
    "METRIC_LABEL_NAME",
    "LocaleChoiceSource",
    "LocaleClinicalSignoff",
    "LocaleNotOffered",
    "LocaleRegistration",
    "LocaleSwitchOffer",
    "MissingLocaleString",
    "RedScriptInFlight",
    "SessionLocale",
    "check_catalogue_completeness",
    "choose_session_locale",
    "confirm_locale_switch",
    "default_session_locale",
    "enabled_locales",
    "offer_locale_switch",
    "offerable_app_locales",
    "offerable_intake_locales",
    "registration",
    "resolve",
    "safe_code",
]
