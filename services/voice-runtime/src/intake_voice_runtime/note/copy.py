"""INT-084 — the note's fixed copy, declared as a KEY SET and never authored.

Same contract as :mod:`intake_api.dsar.strings` and for the same reason: the
Turkish wording behind every key is a human deliverable, and a "temporary"
string in source is indistinguishable from counsel's once merged.

Two authors stand behind this one key set and the module says so rather than
blurring them:

* ``previsit_note.footer`` is **files/06 §7**'s fixed note/PDF footer, the
  sentence 1219 m.8 and HHY m.15 are answered with. It is counsel's, under
  INT-210, and invariant 18 requires it to render only from ``docs/legal/``
  with hash binding.
* the headings, attribution markers and gap markers are **clinician-facing
  copy**. They ride the same hash-bound file so that one version and one
  SHA-256 bind the whole rendered document — which is what makes "this is
  what the note said" provable — and because a second catalogue with a second
  hash would let the two halves of one page drift apart.

There is no default anywhere in this module. ``docs/legal/strings.yaml`` does
not exist today, so :func:`note_copy_from_legal_strings` never gets a chance
to run in production and every renderer that needs copy fails closed
(HUMAN_BLOCKERS.md rule 2: build the mechanism, wire the gate, make it fail
closed, leave the content empty).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from intake_platform.legal import LegalStrings

from intake_voice_runtime.note.facts import Attribution, FactSubject, NoteGapReason

__all__ = [
    "NOTE_COPY_KEYS",
    "NOTE_COPY_SECTIONS",
    "NoteCopy",
    "note_copy_from_legal_strings",
]

#: The note sections that carry a human heading, in files/04 §5 note order.
#: ``triage``, ``data_gaps``, ``considerations``, ``suggested_focus_questions``
#: and ``patient_confirmed_sections`` are headed by ``previsit_note.heading.*``
#: instead, because they are blocks of the rendered document rather than
#: places a fact is filed.
NOTE_COPY_SECTIONS: Final[tuple[str, ...]] = (
    "chief_complaint",
    "hpi",
    "ros_pertinent",
    "pmh",
    "medications",
    "allergies",
    "family_social",
    "measurements",
    "screening",
    "konusma_ozellikleri",
    "imported_objective",
)

_HEADINGS: Final[tuple[str, ...]] = (
    "triage",
    "candidates",
    "considerations",
    "focus_questions",
    "confirmed",
    "gaps",
    "provenance",
)

_SOAP: Final[tuple[str, ...]] = ("subjective", "objective", "assessment", "plan")


def _keys() -> tuple[str, ...]:
    return (
        "previsit_note.title",
        "previsit_note.footer",
        *(f"previsit_note.soap.{block}" for block in _SOAP),
        *(f"previsit_note.heading.{name}" for name in _HEADINGS),
        *(f"previsit_note.section.{section}" for section in NOTE_COPY_SECTIONS),
        *(f"previsit_note.attribution.{item.value}" for item in Attribution),
        *(f"previsit_note.subject.{item.value}" for item in FactSubject),
        *(f"previsit_note.gap.{item.value}" for item in NoteGapReason),
    )


#: Every fixed string the note cannot be rendered without.
NOTE_COPY_KEYS: Final[tuple[str, ...]] = _keys()


@dataclass(frozen=True, slots=True)
class NoteCopy:
    """One loaded, hash-bound copy set, plus the binding that proves which
    bytes the document was rendered from."""

    values: Mapping[str, str]
    version: str
    text_hash: str

    def value(self, key: str) -> str:
        return self.values[key]

    def section(self, section_id: str) -> str:
        return self.values[f"previsit_note.section.{section_id}"]

    def attribution(self, attribution: Attribution) -> str:
        return self.values[f"previsit_note.attribution.{attribution.value}"]

    def subject(self, subject: FactSubject) -> str:
        return self.values[f"previsit_note.subject.{subject.value}"]

    def gap(self, reason: NoteGapReason) -> str:
        return self.values[f"previsit_note.gap.{reason.value}"]


def note_copy_from_legal_strings(strings: LegalStrings) -> NoteCopy:
    """Bind a loaded :class:`~intake_platform.legal.LegalStrings` to the note.

    The caller obtains ``strings`` with ``required=NOTE_COPY_KEYS``, so an
    absent file or an absent key has already raised
    :class:`~intake_platform.legal.LegalStringsMissingError` before reaching
    here — the note is refused as a whole rather than rendered with a hole
    where the disclaimer belongs.
    """
    missing = [key for key in NOTE_COPY_KEYS if key not in strings.values]
    if missing:
        raise KeyError(f"note copy is not bound: {', '.join(sorted(missing))}")
    return NoteCopy(
        values=MappingProxyType({key: strings.values[key] for key in NOTE_COPY_KEYS}),
        version=strings.version,
        text_hash=strings.text_hash,
    )
