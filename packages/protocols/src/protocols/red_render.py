"""Expanding a RED script's authoring markup before the screen and before TTS (INT-465).

RED action scripts are authored with two pieces of markup (files/02 §5.3 worked text;
files/protocols/base.life_threat.yaml exemplar 1; CD-24's ON_SITE line):

- ``**…**`` marks the action the eye must find first. It is emphasis for the author.
  No screen in this repository renders it, and spoken aloud it is noise inside a RED.
- ``[ — {{tenant.acil_location_tr}}]`` is an optional segment that carries the
  tenant's own acil servis location (files/02 §5.3). With a value it renders as
  "— <value>". With none, the **whole** segment is dropped. files/04 §8.2
  ``tenant_acil_location_string_is_never_defaulted``: a wrong direction inside a
  hospital costs the minutes the alert exists to save, so the location is never
  invented.

This module is the only reader of that markup. Anything else that looks like markup
is refused rather than guessed at. That covers an unknown template field, a template field
outside its optional segment, an unpaired marker and a stray bracket. A tenant value
that would smuggle markup or a second line back in is refused too.

``spoken_red_text`` is the rendered text run through the compiler's per-locale
expander (:func:`protocols.compile.number_expansion.expand_for_locale`), so no numeral
reaches a TTS model (CLAUDE.md invariant 22): "112 " becomes "yüz on iki ". The
rendered text is what the screen shows, and digits stay on the screen.

Rendering changes no word an author wrote. It removes the author's markers and
resolves the one segment the schema defines (CLAUDE.md invariant 10).
"""

from __future__ import annotations

import re

from protocols.compile.number_expansion import expand_for_locale
from protocols.locale_text import DEFAULT_LOCALE

__all__ = [
    "MAX_ACIL_LOCATION_LENGTH",
    "TENANT_ACIL_LOCATION",
    "RedRenderError",
    "assert_markup_free",
    "render_red_text",
    "spoken_red_text",
]

#: The one template field RED text may carry (files/02 §5.3).
TENANT_ACIL_LOCATION = "{{tenant.acil_location_tr}}"
#: A location string is a floor or a wing, not a paragraph.
MAX_ACIL_LOCATION_LENGTH = 120

_SEGMENT = re.compile(r"\[([^\[\]]*)\]")
_MARKUP = re.compile(r"[*{}\[\]]")
_TWELVE = re.compile(r"112|yüz\s+on\s+iki", re.IGNORECASE)


class RedRenderError(ValueError):
    """RED text carries markup this renderer does not define, or a bad tenant value."""


def _location(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip()
    if len(cleaned) > MAX_ACIL_LOCATION_LENGTH or "\n" in cleaned or "\r" in cleaned:
        raise RedRenderError("acil_location_tr must be one short line")
    if _MARKUP.search(cleaned):
        raise RedRenderError("acil_location_tr may not carry markup")
    if _TWELVE.search(cleaned):
        # The segment exists only in ON_SITE lines, where 112 is absent in every
        # carrier (CLAUDE.md invariant 21): a tenant value cannot bring it back.
        raise RedRenderError("acil_location_tr may not name 112")
    return cleaned


def _resolve_segment(match: re.Match[str], location: str | None) -> str:
    inner = match.group(1)
    if inner.count(TENANT_ACIL_LOCATION) != 1:
        raise RedRenderError(
            "an optional [ … ] segment carries exactly one tenant template field (files/02 §5.3)"
        )
    if location is None:
        return ""
    return inner.replace(TENANT_ACIL_LOCATION, location)


def render_red_text(authored: str, *, acil_location_tr: str | None) -> str:
    """The screen form of one authored RED string: markers removed, segment resolved."""
    location = _location(acil_location_tr)
    if authored.count("**") % 2:
        raise RedRenderError("an unpaired ** emphasis marker")
    text = authored.replace("**", "")
    text = _SEGMENT.sub(lambda match: _resolve_segment(match, location), text)
    if "{{" in text or "}}" in text:
        raise RedRenderError(
            "a template field outside its optional segment, or one this renderer does not define"
        )
    assert_markup_free(text)
    return text


def spoken_red_text(
    authored: str, *, acil_location_tr: str | None, locale: str = DEFAULT_LOCALE
) -> str:
    """What a TTS model may be given: rendered, then numerals expanded (invariant 22)."""
    spoken = expand_for_locale(render_red_text(authored, acil_location_tr=acil_location_tr), locale)
    assert_markup_free(spoken.text)
    return spoken.text


def assert_markup_free(text: str) -> None:
    """Raise unless ``text`` carries no ``*``, ``{``, ``}``, ``[`` or ``]``."""
    found = _MARKUP.search(text)
    if found is not None:
        raise RedRenderError(f"authoring markup {found.group(0)!r} left in RED text")
