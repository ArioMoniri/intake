"""Code systems, extension URLs and fixed codings for the INT-033 mappers.

files/03 §7 pins the code systems: ICD-10 (e-Nabız/SGK usage), ATC for
drugs, LOINC for labs; SNOMED CT is not licensed in Türkiye and is not
used. Everything INTAKE-local lives under the ``urn:intake:`` namespace —
self-describing URIs that claim no domain.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from clinical_schemas.note import PreVisitNote
from clinical_schemas.records import CodeSystem

# --- standard terminology systems (files/03 §7) ------------------------------

LOINC: Final = "http://loinc.org"
ATC: Final = "http://www.whocc.no/atc"
ICD10: Final = "http://hl7.org/fhir/sid/icd-10"

CODE_SYSTEM_URI: Final[Mapping[CodeSystem, str]] = MappingProxyType(
    {
        CodeSystem.LOINC: LOINC,
        CodeSystem.ATC: ATC,
        CodeSystem.ICD10: ICD10,
    }
)
URI_CODE_SYSTEM: Final[Mapping[str, CodeSystem]] = MappingProxyType(
    {uri: system for system, uri in CODE_SYSTEM_URI.items()}
)

OBSERVATION_CATEGORY: Final = "http://terminology.hl7.org/CodeSystem/observation-category"
CONDITION_VER_STATUS: Final = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
ALLERGY_VER_STATUS: Final = "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification"
ALLERGY_CLINICAL: Final = "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical"

# --- INTAKE-local systems -----------------------------------------------------

SECTION_SYSTEM: Final = "urn:intake:fhir:CodeSystem:note-section"
DOC_TYPE_SYSTEM: Final = "urn:intake:fhir:CodeSystem:document-type"
TRIAGE_LEVEL_SYSTEM: Final = "urn:intake:fhir:CodeSystem:triage-level"
TRIAGE_RULE_SYSTEM: Final = "urn:intake:fhir:CodeSystem:triage-rule"
TRIAGE_METHOD_SYSTEM: Final = "urn:intake:fhir:CodeSystem:triage-method"
SCREENING_SYSTEM: Final = "urn:intake:fhir:CodeSystem:screening-instrument"
SESSION_ID_SYSTEM: Final = "urn:intake:fhir:NamingSystem:session"
VISIT_ID_SYSTEM: Final = "urn:intake:fhir:NamingSystem:visit"
PROTOCOL_CANONICAL_PREFIX: Final = "urn:intake:protocol:"

# The method coding is invariant 1 carried in-band: only a resource that
# names the rules engine as its method may ever become a routing result.
TRIAGE_METHOD_RULES: Final = "rules"

# --- extension URLs -----------------------------------------------------------

_EXT: Final = "urn:intake:fhir:StructureDefinition:"

EXT_DOCUMENT_REF: Final = f"{_EXT}source-document"
EXT_PAGE: Final = f"{_EXT}source-page"
EXT_BBOX: Final = f"{_EXT}source-bbox"
EXT_UNIT_CONFLICT: Final = f"{_EXT}unit-conflict"
EXT_VERIFICATION: Final = f"{_EXT}verification-status"
EXT_RED_REGISTER: Final = f"{_EXT}red-register"
EXT_RED_LOCATION: Final = f"{_EXT}red-location"
EXT_PROTOCOL_HASH: Final = f"{_EXT}protocol-hash"
EXT_MODE: Final = f"{_EXT}intake-mode"
EXT_MODEL: Final = f"{_EXT}note-model"
EXT_PROMPT_VERSION: Final = f"{_EXT}prompt-version"
EXT_FACT_PROVENANCE: Final = f"{_EXT}fact-provenance"
EXT_SESSION_STATUS: Final = f"{_EXT}session-status"
EXT_LIST_SLOT: Final = f"{_EXT}list-slot"
EXT_RECONCILIATION: Final = f"{_EXT}reconciliation"
EXT_ADHERENCE: Final = f"{_EXT}adherence"
EXT_MED_SOURCE: Final = f"{_EXT}medication-source"
EXT_PMH_SOURCE: Final = f"{_EXT}pmh-source"
EXT_ALLERGY_SEVERITY: Final = f"{_EXT}allergy-severity"
EXT_ADMINISTRATION_MODE: Final = f"{_EXT}administration-mode"
EXT_PROXY_REPORTED: Final = f"{_EXT}proxy-reported"
EXT_THIRD_PARTY_PRESENT: Final = f"{_EXT}third-party-present"
EXT_QUALIFIER_TR: Final = f"{_EXT}qualifier-tr"

# --- screening instruments -----------------------------------------------------

# LOINC total-score codes verified against the NLM Clinical Table Search
# Service on 2026-08-28 (docs/evidence/INT-033.md). GAD-2 has no verified
# standalone total-score LOINC (70272-0 is PHQ-4), so it carries only the
# local coding — never a guessed code (files/03 §4.6).
LOINC_TOTALS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "phq9": "44261-6",
        "gad7": "70274-6",
        "phq2": "55758-7",
    }
)

SCREENING_INSTRUMENTS: Final = ("phq2", "gad2", "phq9", "gad7")

# --- note sections --------------------------------------------------------------

NOTE_SECTION_IDS: Final[tuple[str, ...]] = tuple(
    name for name in PreVisitNote.model_fields if name != "meta"
)
"""The stable Composition section codes: the authoritative files/04 §5 note
keys, in note order (``meta`` feeds the Composition itself, not a section)."""

DOCUMENT_TYPE_CODE: Final = "previsit_note"
DOCUMENT_TITLE_TR: Final = "Ön görüşme notu"

FHIR_INT32_MIN: Final = -(2**31)
FHIR_INT32_MAX: Final = 2**31 - 1
