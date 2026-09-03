"""INT-297 — the DSL's authored text, keyed by locale, with ``tr`` required.

``text_tr``, ``ask_tr``, ``follow_up_tr``, ``choices_tr`` and ``why_tr`` carry a
map from locale code to content rather than one string. Three properties are
load-bearing, and each is a refusal rather than a convention:

**``tr`` is required.** CLAUDE.md invariant 5 — *"``tr`` resource keys are the
source of truth; lint fails on missing ``tr``"*. A map without ``tr`` is refused
by the schema exactly as a missing scalar field is today, so no pack can lose
its Turkish by acquiring another language.

**A key the registry does not know is refused.** INT-296's ``LOCALE_REGISTRY``
ships holding exactly ``tr``: which languages this build offers is HB-O5's
question and what they say clinically is HB-C19's. A well-formed but
unregistered code — ``de`` is the near-miss — is content nobody nominated a
signer for, so it is refused at the schema rather than parked in a pack where a
later registration would silently make it speakable.

**There is no fallback.** :func:`entry_for` takes no default and raises on a
miss, mirroring :mod:`intake_platform.locale.resolver` exactly: *a sentence half
in one language and half in Turkish is worse than a sentence in Turkish, and a
fallback chain is how that happens*.

**Why the registry is restated here rather than imported.** ``protocols`` may
not import ``intake_platform``: files/09 §7 gives the authoring surface *zero*
access to patient data, and ``tests/protocols/test_l0_guard.py``
``test_import_boundary_no_patient_data_access`` enforces that by AST scan with a
four-name allow-list. INT-296's registry lives in ``intake_platform.locale``,
behind that boundary. So the closed set is declared once more here — and
``tests/protocols/test_locale_maps.py``
``test_the_dsl_and_the_session_registry_agree_about_which_locales_exist``
asserts the two are the *same set*, in both directions, so they cannot drift:
a locale registered for sessions but unknown to the DSL, or content in a pack
for a locale no session can select, both fail CI. That test is the seam; it is
not decoration, and removing it re-opens exactly the drift this note describes.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

#: Invariant 5. Not a configurable value: the source of truth is not a setting.
#: Must equal ``intake_platform.locale.DEFAULT_LOCALE`` — asserted in tests.
DEFAULT_LOCALE = "tr"

#: Must equal ``intake_platform.locale.LOCALE_CODE_PATTERN`` — asserted in tests.
LOCALE_CODE_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2})?$")

#: The locales a pack may carry content for. Must equal the key set of
#: ``intake_platform.locale.LOCALE_REGISTRY`` — asserted in tests. It holds
#: exactly ``tr``: which languages this build offers is a product decision
#: (HB-O5) and what they say clinically is a clinical one (HB-C19), and neither
#: is answered by adding a key here.
KNOWN_LOCALES = frozenset({DEFAULT_LOCALE})

#: What a refusal says instead of the value it refused (invariant 6).
REDACTED_CODE = "<not-a-locale-code>"


def safe_code(value: str) -> str:
    """The only way a locale string reaches a message or a log line.

    Mirrors ``intake_platform.locale.safe_code``: a well-formed tag is short,
    closed and non-identifying, so it passes through; anything else — a
    sentence, a phone number, a name — is replaced wholesale rather than
    truncated, because a truncated identifier is still an identifier.
    """
    if LOCALE_CODE_PATTERN.match(value):
        return value
    return REDACTED_CODE


__all__ = [
    "DEFAULT_LOCALE",
    "KNOWN_LOCALES",
    "LOCALE_CODE_PATTERN",
    "LocaleChoices",
    "LocaleCode",
    "LocaleEntryAbsent",
    "LocaleFlag",
    "LocaleList",
    "LocaleText",
    "common_locales",
    "entry_for",
    "known_locales",
    "locales_of",
    "safe_code",
]

#: The shape of a locale key. Identical to INT-296's, because a key shape that
#: drifted would let a pack carry a code the session layer cannot name.
LocaleCode = Annotated[str, StringConstraints(pattern=LOCALE_CODE_PATTERN.pattern)]

_Content = Annotated[str, StringConstraints(min_length=1)]


class LocaleEntryAbsent(LookupError):
    """A locale was asked of a field that carries no entry for it.

    Raised rather than resolved. Carries only a shape-checked code, so a
    caller-supplied string can never reach a log line through it (invariant 6).
    """


def known_locales() -> frozenset[str]:
    """Every locale a pack may carry content for (INT-296's registry)."""
    return KNOWN_LOCALES


def _registered_keys[V](value: Mapping[str, V]) -> Mapping[str, V]:
    unknown = sorted(set(value) - known_locales())
    if unknown:
        raise ValueError(
            "locale "
            + ", ".join(safe_code(code) for code in unknown)
            + " is not registered; this build offers "
            + ", ".join(sorted(known_locales()))
            + " (INT-296; HB-O5 names the rest, HB-C19 signs them)"
        )
    return value


def _requires_tr[V](value: Mapping[str, V]) -> Mapping[str, V]:
    if DEFAULT_LOCALE not in value:
        raise ValueError(
            f"every locale map must carry {DEFAULT_LOCALE!r} — tr resource keys are "
            "the source of truth and a pack may not lose its Turkish by acquiring "
            "another language (CLAUDE.md invariant 5)"
        )
    return _registered_keys(value)


def _equal_arity(value: Mapping[str, tuple[str, ...]]) -> Mapping[str, tuple[str, ...]]:
    """Every locale offers the same number of choices, and at least one.

    A locale that offers three options where Turkish offers two is not a
    translation of the question: it is a different question, and the extraction
    that reads the answer indexes both by position.
    """
    _requires_tr(value)
    arity = len(value[DEFAULT_LOCALE])
    if arity == 0:
        raise ValueError("choices_tr may not be empty (files/04 §1 ``choices_tr[]``)")
    mismatched = sorted(code for code, choices in value.items() if len(choices) != arity)
    if mismatched:
        raise ValueError(
            "every locale must offer the same choices in the same order; "
            + ", ".join(safe_code(code) for code in mismatched)
            + f" disagrees with {DEFAULT_LOCALE} ({arity})"
        )
    return value


#: One authored string per locale.
LocaleText = Annotated[dict[LocaleCode, _Content], AfterValidator(_requires_tr)]

#: The spoken answer options, per locale, in one order.
LocaleChoices = Annotated[dict[LocaleCode, tuple[_Content, ...]], AfterValidator(_equal_arity)]


def _equal_arity_or_silent(
    value: Mapping[str, tuple[str, ...]],
) -> Mapping[str, tuple[str, ...]]:
    """INT-314. Like :func:`_equal_arity`, except that *nothing* is sayable.

    ``do_nots_tr`` is the one migrated field whose absence is meaningful: most
    red-flag branches carry no explicit do-not list at all, and the DSL spelled
    that as an empty tuple. An empty **map** keeps that meaning — no do-nots in
    any language, and therefore no constraint on which languages the pack can
    be run in. It is not the same as ``{tr: []}``, which is an author saying
    this branch has no do-nots *in Turkish*.

    Where entries do exist the arity rule is the stricter one, and for a harder
    reason than ``choices_tr``'s: each line of a do-not list is a separate
    instruction — *Kendi aracınızla yola çıkmayın* is not a rephrasing of *Bir
    şey yiyip içmeyin* — so a locale carrying fewer of them has dropped a
    safety instruction rather than translated one.
    """
    if not value:
        return value
    return _equal_arity_permitting_empty(value)


def _equal_arity_permitting_empty(
    value: Mapping[str, tuple[str, ...]],
) -> Mapping[str, tuple[str, ...]]:
    _requires_tr(value)
    arity = len(value[DEFAULT_LOCALE])
    mismatched = sorted(code for code, items in value.items() if len(items) != arity)
    if mismatched:
        raise ValueError(
            "every locale must carry the same do-not instructions in the same order; "
            + ", ".join(safe_code(code) for code in mismatched)
            + f" disagrees with {DEFAULT_LOCALE} ({arity}) — a locale with fewer "
            "do-nots has dropped a safety instruction, not translated one"
        )
    return value


#: A list of separate instructions per locale, where having none is a position.
LocaleList = Annotated[
    dict[LocaleCode, tuple[_Content, ...]], AfterValidator(_equal_arity_or_silent)
]

#: A paraphrase permission per locale (CLAUDE.md invariant 10, restated per
#: language rather than weakened): permission granted for Turkish says nothing
#: about a language whose register and reading level nobody has checked.
LocaleFlag = Annotated[dict[LocaleCode, bool], AfterValidator(_requires_tr)]


def entry_for[V](mapping: Mapping[str, V], locale: str) -> V:
    """The locale's own entry, or a refusal. No default, no fallback."""
    try:
        return mapping[locale]
    except KeyError:
        raise LocaleEntryAbsent(
            f"no entry for locale {safe_code(locale)}; this field carries "
            + ", ".join(sorted(mapping))
            + " — there is no per-string fallback (INT-296)"
        ) from None


def locales_of(mapping: Mapping[str, object] | None) -> frozenset[str]:
    """Which locales a field can speak. An absent field constrains nothing."""
    if mapping is None:
        return known_locales()
    return frozenset(mapping)


def common_locales(mappings: Iterable[Mapping[str, object] | None]) -> frozenset[str]:
    """The locales every one of these fields can speak.

    An intersection, never a union: a locale that can ask the first question and
    not the second cannot run the intake, and offering it would produce exactly
    the half-and-half session INT-296 refuses.
    """
    common = known_locales()
    for mapping in mappings:
        common &= locales_of(mapping)
    return common
