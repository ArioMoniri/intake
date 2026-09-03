"""INT-296 — the resource lookup, and the fallback it does not have.

One property, stated three ways so that none of the three can be lost in a
refactor:

* :func:`resolve` takes ``(catalogues, locale, key)`` and nothing else. There
  is no ``default``, no ``fallback``, no ``or_else`` — not unused, *absent*.
* It raises :class:`MissingLocaleString` on a miss. It does not return ``""``,
  it does not return the key, and it does not reach for Turkish.
* ``tests/platform/test_session_locale.py`` asserts all of that against this
  module's **parsed source**, not against its behaviour. A permissive
  parameter that is unused today is passed tomorrow, and the review that would
  have caught it reads a diff, not a test run.

Why the property is worth this much machinery: a sentence half in Arabic and
half in Turkish is worse than a sentence in Turkish. It is not a degraded
translation, it is a sentence the patient cannot parse at all — and a fallback
chain is exactly how one gets built, one missing key at a time, invisibly.
Refusing at the missing key makes the gap a build failure instead of a
production sentence.

:func:`check_catalogue_completeness` is the build-time half: it turns the
whole question into a list of complaints a gate can fail on, so completeness is
a property of the tree rather than a runtime hope.
"""

from __future__ import annotations

from collections.abc import Mapping

from .registry import DEFAULT_LOCALE, safe_code

__all__ = [
    "MissingLocaleString",
    "check_catalogue_completeness",
    "resolve",
]


class MissingLocaleString(LookupError):
    """A string was asked for that this locale's catalogue does not carry.

    Raised rather than substituted. The message names the *key* — a developer
    id — and a shape-checked locale code, and never the caller's raw input
    (invariant 6: no free text a patient supplied reaches a log).
    """


def resolve(catalogues: Mapping[str, Mapping[str, str]], locale: str, key: str) -> str:
    """The one string for ``key`` in ``locale``, or a refusal.

    Three parameters, no defaults, one language. The absence of a fourth is
    the whole point of the function.
    """
    if locale not in catalogues:
        raise MissingLocaleString(
            f"no catalogue for locale {safe_code(locale)}; there is no fallback to "
            f"{DEFAULT_LOCALE} and there is not meant to be one"
        )
    catalogue = catalogues[locale]
    if key not in catalogue:
        raise MissingLocaleString(
            f"{key!r} is missing from the {safe_code(locale)} catalogue; a locale is "
            "offered only when it is complete, so this is a build defect rather than "
            "a runtime condition to paper over"
        )
    return catalogue[key]


def check_catalogue_completeness(
    catalogues: Mapping[str, Mapping[str, str]],
) -> tuple[str, ...]:
    """Every reason these catalogues are not shippable, in a stable order.

    ``tr`` is the reference and must be present — invariant 5 is generalised
    here, never weakened: the rule was *"``tr`` must exist"* and becomes
    *"``tr`` must exist **and** every other catalogue offered must be complete
    against it"*.

    An empty string counts as missing. A key present with a blank value is the
    more dangerous of the two, because it passes a key-parity check and renders
    as nothing at all on a screen.
    """
    complaints: list[str] = []
    if DEFAULT_LOCALE not in catalogues:
        complaints.append(
            f"no {DEFAULT_LOCALE} catalogue: {DEFAULT_LOCALE} is the source of truth "
            "(invariant 5) and every other locale is measured against it"
        )
        return tuple(complaints)

    reference = catalogues[DEFAULT_LOCALE]
    for key, value in sorted(reference.items()):
        if not value.strip():
            complaints.append(f"{DEFAULT_LOCALE}[{key!r}] is blank")

    for code in sorted(catalogues):
        if code == DEFAULT_LOCALE:
            continue
        catalogue = catalogues[code]
        for key in sorted(reference):
            if key not in catalogue:
                complaints.append(f"{safe_code(code)} is missing {key!r}")
            elif not catalogue[key].strip():
                complaints.append(f"{safe_code(code)}[{key!r}] is blank")
        for key in sorted(set(catalogue) - set(reference)):
            complaints.append(
                f"{safe_code(code)} defines {key!r} with no {DEFAULT_LOCALE} key: a "
                "string authored in another language first is the defect, not the "
                "missing mirror (invariant 5)"
            )
    return tuple(complaints)
