"""INT-085 — which of the note's fields a patient may read, decided once.

The acceptance clause is *"plain-language summary excludes wellbeing
signals"*. The obvious shape for that is a filter at the end of the builder,
and the obvious shape is wrong: a filter names what it removes, so a field
added to :class:`~clinical_schemas.note.PreVisitNote` tomorrow is included by
**default** and nobody notices until it is on a patient's screen.

So the classification is a **partition**. Every ``PreVisitNote`` field is
named exactly once, in :data:`SUMMARY_SECTIONS` or in
:data:`EXCLUDED_SECTIONS`, a test asserts the two cover the model's fields and
do not overlap, and every exclusion carries the reason in
:data:`EXCLUSION_REASONS`. A new note field fails that test until somebody
decides, in review, whether a patient may read it.

The cards themselves are a closed enum for the same reason the note's
attribution table is a table: a card a caller can spell is a card that can be
added without a reviewer seeing it.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from intake_voice_runtime.note import Attribution, FactSubject

__all__ = [
    "EXCLUDED_SECTIONS",
    "EXCLUSION_REASONS",
    "SUMMARY_ATTRIBUTIONS",
    "SUMMARY_CARD_SECTIONS",
    "SUMMARY_SECTIONS",
    "SUMMARY_SUBJECTS",
    "BringItem",
    "SummaryCardId",
]


class SummaryCardId(enum.StrEnum):
    """files/04 §5 ``PatientSummary.cards[]``, as a closed set.

    The order of the members is the order the cards are built in, so the
    patient's own account comes first and the material that arrived from
    somewhere else comes after it.
    """

    STORY = "story"
    HISTORY = "history"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    FAMILY = "family"
    MEASUREMENTS = "measurements"
    DOCUMENTS = "documents"


class BringItem(enum.StrEnum):
    """files/04 §5 ``PatientSummary.bring_list``.

    A closed enum with a structural trigger each, rather than free strings: a
    bring list a caller can type is a place to write an instruction to a
    patient without any of the review that patient copy gets. Each member's
    wording lives in the hash-bound catalogue; only *whether* it applies is
    decided here, and only from what the note holds.
    """

    MEDICATIONS = "medications"
    DOCUMENTS = "documents"


#: Which note sections feed which card, in build order.
SUMMARY_CARD_SECTIONS: Final[Mapping[SummaryCardId, tuple[str, ...]]] = MappingProxyType(
    {
        SummaryCardId.STORY: ("chief_complaint", "hpi"),
        SummaryCardId.HISTORY: ("pmh",),
        SummaryCardId.MEDICATIONS: ("medications",),
        SummaryCardId.ALLERGIES: ("allergies",),
        SummaryCardId.FAMILY: ("family_social",),
        SummaryCardId.MEASUREMENTS: ("measurements",),
        SummaryCardId.DOCUMENTS: ("imported_objective",),
    }
)

#: The note sections a patient may read, derived from the card table so the two
#: cannot disagree.
SUMMARY_SECTIONS: Final[tuple[str, ...]] = tuple(
    section for sections in SUMMARY_CARD_SECTIONS.values() for section in sections
)

#: Why each remaining ``PreVisitNote`` field is not on a patient's screen. The
#: reasons are load-bearing: several of these fields are things the patient
#: themselves said, so "it is the patient's data" is not on its own an argument
#: for showing it back to them in this artefact.
EXCLUSION_REASONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "meta": (
            "Session bookkeeping — visit id, protocol hash, model and prompt version. "
            "Not content, and the model/prompt pins are supply-chain facts (invariant 19) "
            "with no patient-facing meaning."
        ),
        "triage": (
            "The level reaches the summary only as `triage_message_tr`, worded by the "
            "catalogue. `rules[].evidence` and `llm_candidates[]` are clinician-review "
            "material with a YELLOW_REVIEW ceiling (invariant 1) and files/12 §2.3's "
            "closure test exists precisely to stop them being added here for debugging."
        ),
        "ros_pertinent": (
            "A pertinent-negative list is a clinical instrument, not a transcript: which "
            "absences are *pertinent* is a clinical judgement (files/13 §9.3). Rendered to "
            "the patient as a list of things they do not have, it reads as a finding about "
            "them, which is the diagnosis line invariant 2 draws."
        ),
        "screening": (
            "The acceptance clause. files/02 §5.6 puts wellbeing results on their own "
            "consent-gated surface, 'never scores and never labels'; a PHQ-2 total in a "
            "pre-visit summary is a screening output on a surface that did not ask for it "
            "(threat model `wellbeing`, [Dd])."
        ),
        "konusma_ozellikleri": (
            "Observer-lane output. files/03 §4.7 makes the lanes read-only and keeps them "
            "off every patient-facing surface; §4.7.1 is explicit that an interpretive "
            "statement about the patient's state is the device function itself."
        ),
        "data_gaps": (
            "The 'eksik' affordance belongs to the review screen (files/02 §5.4) where it "
            "is actionable. Restating it read-only is also unsafe: the "
            "`deferred_environment` reason exists because a second voice was audible, so "
            "printing it tells the person in the room that sensitive questions were "
            "deferred because of them (files/02 §33)."
        ),
        "suggested_focus_questions": (
            "Written for the resident who reads the note first (files/02 §5.7), not for "
            "the patient. The field name reads patient-facing and its reader is not the "
            "patient, which is exactly how clinician material gets laundered into patient "
            "copy. The patient's own questions arrive separately, from their own words."
        ),
        "considerations": (
            "Patterns offered to a clinician, never diagnoses (invariant 2). The same "
            "sentence read by the patient has no clinician between it and belief."
        ),
        "patient_confirmed_sections": (
            "Note metadata: which sections the patient ticked. The confirmation UI is the "
            "review screen's; echoing the list back adds no fact the patient does not "
            "already have."
        ),
    }
)

#: Everything in ``PreVisitNote`` that is not summarised.
EXCLUDED_SECTIONS: Final[tuple[str, ...]] = tuple(EXCLUSION_REASONS)

#: The attributions that can reach a patient-facing card.
#:
#: ``RULES_ENGINE`` and ``LLM_CANDIDATE`` are absent, and their absence is the
#: enforcement: there is no marker key by which a fired rule or a candidate
#: flag could be worded onto a card, so invariant 1's summary face is a missing
#: vocabulary rather than a filter somebody has to remember to run. INT-299
#: added ``TRANSLATED`` and left that property exactly as it was — the two
#: absences are asserted by name, not by counting members.
#:
#: ``TRANSLATED`` is *present* because every line carries a marker, including
#: the ones that are not exceptional (INT-085): a marker on the exceptions
#: makes the unmarked lines read as endorsed. What the marked line shows is
#: the patient's **own** words, never the rendering —
#: :func:`~intake_voice_runtime.summary.builder.build_patient_summary`.
SUMMARY_ATTRIBUTIONS: Final[tuple[Attribution, ...]] = (
    Attribution.PATIENT_SELF,
    Attribution.TRANSLATED,
    Attribution.RELATIVE,
    Attribution.CARRIED,
    Attribution.RECORD,
)

#: The subjects a summary line can name. ``PATIENT`` is absent: a line about
#: the patient is named by the attribution marker, and a "hasta" label on the
#: patient's own screen is the clinician's word for them.
SUMMARY_SUBJECTS: Final[tuple[FactSubject, ...]] = tuple(
    subject for subject in FactSubject if subject.is_relative
)
