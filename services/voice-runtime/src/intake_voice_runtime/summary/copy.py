"""INT-085 — the patient summary's fixed copy: a key set, never authored.

Same contract as :mod:`intake_voice_runtime.note.copy` and for a stronger
reason. The note's copy is read by a clinician who has training and a second
source; this copy is read by the patient, with nothing between the sentence
and belief. Every fixed string here is therefore a human deliverable —
counsel's for anything legal, the clinical author's for the rest — rendered
only from ``docs/legal/strings.yaml`` with hash binding (invariant 18). That
file does not exist, so the production path fails closed and the summary is
refused rather than rendered with a hole where a card title belongs.

**A separate key namespace from the note's, on purpose.**
``previsit_note.attribution.patient_self`` is *"hasta beyanı"* — the
clinician's phrase for what the patient said. Reusing it would print the
clinician's word for the patient on the patient's own screen. The summary's
markers are a different set of keys so the copy owner can word them for the
person reading them.

**The gate runs here.** Every value is checked against
:func:`~intake_voice_runtime.summary.readability.assert_patient_readable` as
it is bound, and a single failure refuses the whole catalogue. A catalogue
that binds is a catalogue whose every patient-facing string passed the B1
check; nothing downstream has to re-derive that.

**There is no key for a RED triage message**, and that absence is invariant
21: RED is route × register × location, its script is pre-positioned on the
device and triggered over the data channel, and a card set is none of those
three axes. A RED sentence whose register is decided by page layout is the
default the invariant forbids, so the vocabulary for one does not exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from clinical_schemas.triage import TriageLevel
from intake_platform.legal import LegalStrings

from intake_voice_runtime.note import Attribution, FactSubject
from intake_voice_runtime.summary.cards import (
    SUMMARY_ATTRIBUTIONS,
    SUMMARY_SUBJECTS,
    BringItem,
    SummaryCardId,
)
from intake_voice_runtime.summary.readability import assert_patient_readable

__all__ = [
    "SUMMARY_COPY_KEYS",
    "SUMMARY_TRIAGE_LEVELS",
    "PatientSummaryCopy",
    "summary_copy_from_legal_strings",
]

#: The levels the summary has a message for. ``RED`` is absent — see the module
#: docstring, and :func:`~intake_voice_runtime.summary.builder.build_patient_summary`,
#: which refuses a RED note outright rather than rendering it without one.
SUMMARY_TRIAGE_LEVELS: Final[tuple[TriageLevel, ...]] = (TriageLevel.GREEN, TriageLevel.YELLOW)


def _keys() -> tuple[str, ...]:
    return (
        *(f"patient_summary.card.{card.value}" for card in SummaryCardId),
        *(f"patient_summary.attribution.{item.value}" for item in SUMMARY_ATTRIBUTIONS),
        *(f"patient_summary.subject.{item.value}" for item in SUMMARY_SUBJECTS),
        *(f"patient_summary.bring.{item.value}" for item in BringItem),
        *(
            f"patient_summary.triage_message.{level.value.lower()}"
            for level in SUMMARY_TRIAGE_LEVELS
        ),
    )


#: Every fixed string the summary cannot be rendered without.
SUMMARY_COPY_KEYS: Final[tuple[str, ...]] = _keys()


@dataclass(frozen=True, slots=True)
class PatientSummaryCopy:
    """One loaded, hash-bound patient-copy set.

    The binding travels with the copy for the same reason it does on the note:
    "this is what the patient was shown" is only provable against the bytes it
    was rendered from.
    """

    values: Mapping[str, str]
    version: str
    text_hash: str

    def card(self, card: SummaryCardId) -> str:
        return self.values[f"patient_summary.card.{card.value}"]

    def attribution(self, attribution: Attribution) -> str:
        return self.values[f"patient_summary.attribution.{attribution.value}"]

    def subject(self, subject: FactSubject) -> str:
        return self.values[f"patient_summary.subject.{subject.value}"]

    def bring(self, item: BringItem) -> str:
        return self.values[f"patient_summary.bring.{item.value}"]

    def triage_message(self, level: TriageLevel) -> str:
        return self.values[f"patient_summary.triage_message.{level.value.lower()}"]


def summary_copy_from_legal_strings(strings: LegalStrings) -> PatientSummaryCopy:
    """Bind the catalogue, and run the readability gate over it.

    The caller obtains ``strings`` with ``required=SUMMARY_COPY_KEYS``, so an
    absent file or an absent key has already raised
    :class:`~intake_platform.legal.LegalStringsMissingError`. What is left for
    this function is the clause the note has no equivalent of: the copy is
    patient-facing, so it has to be B1 before it may be bound at all.
    """
    missing = [key for key in SUMMARY_COPY_KEYS if key not in strings.values]
    if missing:
        raise KeyError(f"patient summary copy is not bound: {', '.join(sorted(missing))}")
    for key in SUMMARY_COPY_KEYS:
        assert_patient_readable(strings.values[key], where=key)
    return PatientSummaryCopy(
        values=MappingProxyType({key: strings.values[key] for key in SUMMARY_COPY_KEYS}),
        version=strings.version,
        text_hash=strings.text_hash,
    )
