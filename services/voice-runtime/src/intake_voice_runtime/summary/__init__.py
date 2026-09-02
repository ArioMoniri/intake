"""INT-085 — the patient summary (B1 Turkish) and its reading-level check.

The summary is the *patient's* view of what the clinician's note says, so it
inherits every attribution rule INT-084's composer enforces and must not undo
any of them in friendlier prose. It lives beside the note rather than in the
schema package for the same reason the note does: composing is a session
activity and the files/04 §5 types are its vocabulary.

Read the three modules in this order:

* :mod:`~intake_voice_runtime.summary.cards` — which of the note's fields a
  patient may read, decided once as a **partition** so a new note field cannot
  default onto a patient's screen. This is where acceptance clause 1
  (*"excludes wellbeing signals"*) is enforced, and where each exclusion
  carries its reason.
* :mod:`~intake_voice_runtime.summary.readability` — acceptance clause 2
  (*"readability metric gate"*), and an explicit written account of what the
  metric does **not** capture for an agglutinative language. It emits no score
  and no level, because CEFR B1 describes a reader and nothing here measured
  one.
* :mod:`~intake_voice_runtime.summary.builder` — the projection, and its four
  refusals.

Copy is a key set (:mod:`~intake_voice_runtime.summary.copy`), never authored:
patient-facing clinical and legal wording renders only from the hash-bound
``docs/legal/strings.yaml`` (invariant 18), which does not exist yet, so the
production path fails closed (HUMAN_BLOCKERS.md rule 2).
"""

from __future__ import annotations

from intake_voice_runtime.summary.builder import (
    ComposedSummary,
    SummaryLine,
    SummaryRefused,
    build_patient_summary,
)
from intake_voice_runtime.summary.cards import (
    EXCLUDED_SECTIONS,
    EXCLUSION_REASONS,
    SUMMARY_ATTRIBUTIONS,
    SUMMARY_CARD_SECTIONS,
    SUMMARY_SECTIONS,
    SUMMARY_SUBJECTS,
    BringItem,
    SummaryCardId,
)
from intake_voice_runtime.summary.copy import (
    SUMMARY_COPY_KEYS,
    SUMMARY_TRIAGE_LEVELS,
    PatientSummaryCopy,
    summary_copy_from_legal_strings,
)
from intake_voice_runtime.summary.readability import (
    B1_MAX_SUBORDINATE_CLAUSES,
    NotPatientReadableError,
    ReadabilityFinding,
    ReadabilityIssue,
    ReadabilityReport,
    SentenceMeasure,
    assert_patient_readable,
    measure_turkish,
    read_check,
    syllables,
)

__all__ = [
    "B1_MAX_SUBORDINATE_CLAUSES",
    "EXCLUDED_SECTIONS",
    "EXCLUSION_REASONS",
    "SUMMARY_ATTRIBUTIONS",
    "SUMMARY_CARD_SECTIONS",
    "SUMMARY_COPY_KEYS",
    "SUMMARY_SECTIONS",
    "SUMMARY_SUBJECTS",
    "SUMMARY_TRIAGE_LEVELS",
    "BringItem",
    "ComposedSummary",
    "NotPatientReadableError",
    "PatientSummaryCopy",
    "ReadabilityFinding",
    "ReadabilityIssue",
    "ReadabilityReport",
    "SentenceMeasure",
    "SummaryCardId",
    "SummaryLine",
    "SummaryRefused",
    "assert_patient_readable",
    "build_patient_summary",
    "measure_turkish",
    "read_check",
    "summary_copy_from_legal_strings",
    "syllables",
]
