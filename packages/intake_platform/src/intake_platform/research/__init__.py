"""INT-230 — the research data pipeline: study registry, export gate, register.

**This package performs pseudonymisation, not anonymisation.** The distinction
is legal, not stylistic. KSVY m.16(1) permits scientific work on health data
*anonim hâle getirilen* by the controller, under the KVKK m.28/1(b) exemption;
what this pipeline emits is a keyed HMAC pseudonym over a closed vocabulary,
re-derivable by whoever holds the tokenization key, and therefore personal
data. Calling that "anonymised" in a research export is the error that ends a
study, so no type, function or constant here carries the word — a test holds
that line by name — and the artefact is :class:`PseudonymisedExtract`.

The route this pipeline actually takes is the other one files/06 §75 states in
the same sentence: *"All research consented (`research`) or anonymised per
KSVY-16; ethics IDs recorded on every export."* Consent **and** an ethics id,
both enforced, neither assertable by a caller.

Five modules, five boundaries:

- :mod:`intake_platform.research.studies` — *whether there is a study*. The
  registry is the only source of an ethics approval id, it refuses outside
  the approval window with no grace day (files/10 §9, invariant 35), and it
  ships **empty** because no study exists (HB-L1, HB-R1).
- :mod:`intake_platform.research.values` — *what an extract may contain*. The
  closed per-dimension vocabulary, the id-shape rule and the INT-015 pattern
  tier, all answerable without a session or a study because the spec author
  asks them long before any patient row exists.
- :mod:`intake_platform.research.artefact` — *the shape of what leaves*, kept
  separate because the artefact's name is a legal claim and should be readable
  without the permission logic around it.
- :mod:`intake_platform.research.extract` — *whether this data may leave*.
  Consent through the one evaluator, the ethics approval, the retention row,
  and the INT-171 k gate over the quasi-identifier cross-tab.
- :mod:`intake_platform.research.register` — *what left, under what
  authority*. One row per served extract, carrying the ethics id and the
  content hash and no patient reference at all.

sec_row: `learning-loops`.  legal: KVKK-16, KSVY-16, ETİK.
"""

from __future__ import annotations

from intake_platform.research.artefact import (
    PseudonymisedExtract,
    PseudonymisedRow,
    SubjectRow,
    canonical_bytes,
)
from intake_platform.research.extract import (
    RESEARCH_EXTRACT_REFUSED,
    RESEARCH_EXTRACT_SERVED,
    ResearchExportGate,
)
from intake_platform.research.register import (
    ExtractRecord,
    ExtractRegister,
    ExtractRegisterStore,
    InMemoryExtractRegisterStore,
)
from intake_platform.research.studies import (
    STUDY_FIELD_SHAPE,
    StudyApprovalLapsedError,
    StudyApprovalNotYetInForceError,
    StudyRecord,
    StudyRegistry,
    StudyRegistryError,
    StudyRegistryRefusal,
    UnknownStudyError,
    default_registry_path,
    load_default_registry,
    load_registry,
)
from intake_platform.research.values import (
    EXPORT_VALUE_SHAPE,
    RESEARCH_SCOPE,
    ResearchExportRefused,
    ResearchExtractSpec,
    ResearchRefusalReason,
    check_export_field,
    check_export_value,
)

__all__ = [
    "EXPORT_VALUE_SHAPE",
    "RESEARCH_EXTRACT_REFUSED",
    "RESEARCH_EXTRACT_SERVED",
    "RESEARCH_SCOPE",
    "STUDY_FIELD_SHAPE",
    "ExtractRecord",
    "ExtractRegister",
    "ExtractRegisterStore",
    "InMemoryExtractRegisterStore",
    "PseudonymisedExtract",
    "PseudonymisedRow",
    "ResearchExportGate",
    "ResearchExportRefused",
    "ResearchExtractSpec",
    "ResearchRefusalReason",
    "StudyApprovalLapsedError",
    "StudyApprovalNotYetInForceError",
    "StudyRecord",
    "StudyRegistry",
    "StudyRegistryError",
    "StudyRegistryRefusal",
    "SubjectRow",
    "UnknownStudyError",
    "canonical_bytes",
    "check_export_field",
    "check_export_value",
    "default_registry_path",
    "load_default_registry",
    "load_registry",
]
