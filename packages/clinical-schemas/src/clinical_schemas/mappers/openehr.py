"""Internal ↔ openEHR canonical COMPOSITION (INT-032, the P3 export tier).

ADR-002 / files/00 §3 D8: FHIR R4 is canonical for exchange and openEHR is a
**P3 export**, kept viable by the archetype-path annotation INT-041 put on
every slot. This module is the openEHR half of the mapping layer files/03 §7
describes, sitting beside ``to_r4``/``from_r4`` and built the same way: a
minimal typed subset of the shapes we actually emit, bidirectional, with
every loss made explicit rather than silent.

**What it exports today is the envelope, and only the envelope.**

The committed operational template
(``packages/protocols/openehr/previsit_intake.v1.opt``) constrains archetype
ROOTS and nothing below them, because INT-041 refused to invent leaf
``atNNNN`` codes — a fabricated code produces a binding table that resolves
against a fiction, and there is no diff that makes that look wrong. An
archetype-root path addresses an ENTRY; a slot value needs a leaf path. So
:func:`session_composition` refuses every answered slot through
:class:`OpenEhrExportBlocked`, naming the archetype the slot was annotated
with and the one sentence a human must answer. There is deliberately no
placement branch: the binding table has no leaf column to branch on, and
writing placement machinery against a shape nobody has authored would be
building around the blocker rather than holding it open
(files/HUMAN_BLOCKERS.md Rule 2).

**Terminology is transcribed, never chosen.** ``category`` and ``setting``
codes come from the published openEHR terminology
(github.com/openEHR/terminology, ``openEHR_RM/en/openehr_terminology.xml``,
retrieved 29 Aug 2026): group *composition category* 431/433/435, group
*setting* 225-238. ``setting`` has no default — which setting a pre-visit
intake happens in is a modelling decision, not an engineering one, so the
caller states it.

**The CDR sees a pseudonym, never an identifier** (invariants 6 and 14).
:class:`IntakeEhr` accepts only the ``<key_id>.<64 hex>`` shape
``intake_platform.tokenization.Tokenizer.pseudonym`` returns.
"""

from __future__ import annotations

import datetime
import enum
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from pydantic import AwareDatetime, Field, field_validator

from clinical_schemas.common import FrozenModel
from clinical_schemas.session import SessionState

__all__ = [
    "COMPOSITION_ARCHETYPE_ID",
    "EHR_STATUS_ARCHETYPE_ID",
    "OPENEHR_RM_VERSION",
    "SUBJECT_ID_SCHEME",
    "SUBJECT_NAMESPACE",
    "TEMPLATE_ID",
    "CompositionCategory",
    "EhrSetting",
    "IntakeEhr",
    "IntakeEnvelope",
    "OpenEhrExportBlocked",
    "OpenEhrMappingError",
    "SlotBinding",
    "UnboundSlot",
    "composition_to_envelope",
    "ehr_status_to_intake_ehr",
    "envelope_to_composition",
    "intake_ehr_to_ehr_status",
    "session_composition",
    "slot_bindings",
    "unbound_slots",
]

OPENEHR_RM_VERSION: Final = "1.1.0"
"""The openEHR Reference Model release the canonical JSON is written against."""

TEMPLATE_ID: Final = "previsit_intake.v1"
COMPOSITION_ARCHETYPE_ID: Final = "openEHR-EHR-COMPOSITION.intake_previsit.v1"
EHR_STATUS_ARCHETYPE_ID: Final = "openEHR-EHR-EHR_STATUS.generic.v1"

SUBJECT_NAMESPACE: Final = "intake-token"
SUBJECT_ID_SCHEME: Final = "intake-tokenizer"

_TERMINOLOGY_OPENEHR: Final = "openehr"
_TERMINOLOGY_LANGUAGE: Final = "ISO_639-1"
_TERMINOLOGY_TERRITORY: Final = "ISO_3166-1"

#: ``<key_id>.<64 hex>`` — the exact shape ``Tokenizer.pseudonym`` returns
#: (INT-013 ``KEY_ID_SHAPE`` + ``DIGEST_HEX_LEN``). Duplicated here rather than
#: imported because clinical-schemas depends on pydantic and nothing else;
#: ``tests/schemas/test_openehr_export.py`` feeds a real ``Tokenizer`` output
#: through it so the two cannot drift apart unnoticed.
_PSEUDONYM_SHAPE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\.[0-9a-f]{64}")


class OpenEhrMappingError(ValueError):
    """A composition that does not carry what the internal side needs back."""


class UnboundSlot(FrozenModel):
    """One answered slot the export cannot place, and the ask that would."""

    slot_id: str = Field(description="``<section>.<key>`` as SessionState.slots keys it.")
    aql_path: str | None = Field(
        default=None,
        description="The archetype-ROOT path the compiler annotated, if any "
        "(files/12 §8 slot_definition.aql_path).",
    )
    rm_type: str | None = Field(
        default=None, description="The RM type that root resolved to in the committed template."
    )
    deferred_reason: str | None = Field(
        default=None,
        description="The compiler's recorded ``openehr_deferred_reason`` when the "
        "slot declares no path at all.",
    )
    ask: str = Field(description="The one sentence a human must answer to unblock it.")


class OpenEhrExportBlocked(ValueError):
    """The export would have had to invent a leaf path to carry an answer.

    Raised instead of dropping the answer or guessing an ``atNNNN`` code. The
    refusal is total: a slot the binding table does not know is refused too,
    because an unrecognised answer is the worst reason to write a composition
    that silently omits it.
    """

    def __init__(self, unbound: Sequence[UnboundSlot]) -> None:
        self.unbound: Final = tuple(unbound)
        names = ", ".join(u.slot_id for u in self.unbound)
        super().__init__(
            f"openEHR export blocked: {len(self.unbound)} answered slot(s) have no leaf "
            f"binding in {TEMPLATE_ID} ({names}). The committed template carries "
            "archetype roots only; a value needs a leaf path and none is authored. "
            "Author the leaf bindings, or export via FHIR R4 (ADR-002)."
        )


class CompositionCategory(enum.StrEnum):
    """openEHR terminology group *composition category*."""

    PERSISTENT = "persistent"
    EPISODIC = "episodic"
    EVENT = "event"

    @property
    def code(self) -> str:
        return _CATEGORY_CODES[self]


_CATEGORY_CODES: Final[dict[CompositionCategory, str]] = {
    CompositionCategory.PERSISTENT: "431",
    CompositionCategory.EPISODIC: "435",
    CompositionCategory.EVENT: "433",
}


class EhrSetting(enum.StrEnum):
    """openEHR terminology group *setting*, transcribed whole so a caller can
    never need a code this module would have had to invent."""

    HOME = "home"
    EMERGENCY_CARE = "emergency care"
    PRIMARY_MEDICAL_CARE = "primary medical care"
    PRIMARY_NURSING_CARE = "primary nursing care"
    PRIMARY_ALLIED_HEALTH_CARE = "primary allied health care"
    MIDWIFERY_CARE = "midwifery care"
    SECONDARY_MEDICAL_CARE = "secondary medical care"
    SECONDARY_NURSING_CARE = "secondary nursing care"
    SECONDARY_ALLIED_HEALTH_CARE = "secondary allied health care"
    COMPLEMENTARY_HEALTH_CARE = "complementary health care"
    DENTAL_CARE = "dental care"
    NURSING_HOME_CARE = "nursing home care"
    OTHER_CARE = "other care"

    @property
    def code(self) -> str:
        return _SETTING_CODES[self]


_SETTING_CODES: Final[dict[EhrSetting, str]] = {
    EhrSetting.HOME: "225",
    EhrSetting.EMERGENCY_CARE: "227",
    EhrSetting.PRIMARY_MEDICAL_CARE: "228",
    EhrSetting.PRIMARY_NURSING_CARE: "229",
    EhrSetting.PRIMARY_ALLIED_HEALTH_CARE: "230",
    EhrSetting.MIDWIFERY_CARE: "231",
    EhrSetting.SECONDARY_MEDICAL_CARE: "232",
    EhrSetting.SECONDARY_NURSING_CARE: "233",
    EhrSetting.SECONDARY_ALLIED_HEALTH_CARE: "234",
    EhrSetting.COMPLEMENTARY_HEALTH_CARE: "235",
    EhrSetting.DENTAL_CARE: "236",
    EhrSetting.NURSING_HOME_CARE: "237",
    EhrSetting.OTHER_CARE: "238",
}
_SETTING_BY_CODE: Final[dict[str, EhrSetting]] = {v: k for k, v in _SETTING_CODES.items()}


class IntakeEhr(FrozenModel):
    """The EHR an intake writes into: a pseudonymous subject and nothing else."""

    subject_token: str = Field(
        description="An INT-013 tokenizer pseudonym (``<key_id>.<64 hex>``). Never a "
        "TCKN, a phone, an e-mail or an internal patient id (invariants 6, 14).",
    )

    @field_validator("subject_token")
    @classmethod
    def _must_be_a_pseudonym(cls, value: str) -> str:
        if not _PSEUDONYM_SHAPE.fullmatch(value):
            raise ValueError(
                "subject_token must be a tokenizer pseudonym (<key_id>.<64 hex>); the "
                "refused value is not echoed"
            )
        return value


class IntakeEnvelope(FrozenModel):
    """Everything a pre-visit composition can carry today. Every field is an
    RM attribute of COMPOSITION or EVENT_CONTEXT — nothing here needs an
    archetype node, which is exactly why it survives the missing leaf codes."""

    reference_time: AwareDatetime = Field(
        description="The session's 'now' (files/13 §9.2), written as "
        "``context.start_time``. Timezone-aware always: a naive instant in a CDR "
        "is a clinical ambiguity."
    )
    composer: str = Field(
        min_length=1,
        description="``COMPOSITION.composer`` — the system that authored the "
        "composition, never the patient's name.",
    )
    setting: EhrSetting = Field(
        description="``context.setting``. No default: which care setting a pre-visit "
        "intake happens in is a modelling decision nobody has recorded."
    )
    category: CompositionCategory = Field(
        default=CompositionCategory.EVENT,
        description="``COMPOSITION.category``. An intake is a single dated encounter "
        "record, which is what openEHR calls an *event* composition.",
    )
    language: str = Field(
        default="tr", pattern=r"^[a-z]{2}$", description="ISO 639-1; Turkish-first."
    )
    territory: str = Field(default="TR", pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alpha-2.")


class SlotBinding(FrozenModel):
    """One row of the files/12 §8 ``slot_definition`` table, exactly as the
    INT-041 compiler emits it into ``openehr_bindings.json``."""

    fhir_link_id: str
    section_id: str
    slot_key: str
    slot_type: str
    aql_path: str | None = None
    rm_type: str | None = None
    openehr_deferred_reason: str | None = None

    @property
    def slot_id(self) -> str:
        return f"{self.section_id}.{self.slot_key}"


def slot_bindings(rows: Iterable[Mapping[str, Any]]) -> tuple[SlotBinding, ...]:
    """Parse ``openehr_bindings.json`` rows into typed bindings."""
    return tuple(SlotBinding.model_validate(dict(row)) for row in rows)


# --- codes and primitives ---------------------------------------------------------


def _code_phrase(terminology: str, code: str) -> dict[str, Any]:
    return {
        "_type": "CODE_PHRASE",
        "terminology_id": {"_type": "TERMINOLOGY_ID", "value": terminology},
        "code_string": code,
    }


def _coded_text(value: str, terminology: str, code: str) -> dict[str, Any]:
    return {
        "_type": "DV_CODED_TEXT",
        "value": value,
        "defining_code": _code_phrase(terminology, code),
    }


def _require(node: Mapping[str, Any] | None, *path: str) -> Any:
    cursor: Any = node
    for step in path:
        if not isinstance(cursor, Mapping) or step not in cursor:
            raise OpenEhrMappingError(
                f"composition is missing {'/'.join(path)} — the export roundtrip needs "
                "every envelope field back, and a missing one is loss, not a default"
            )
        cursor = cursor[step]
    return cursor


# --- EHR_STATUS --------------------------------------------------------------------


def intake_ehr_to_ehr_status(ehr: IntakeEhr) -> dict[str, Any]:
    """The EHR_STATUS EHRbase requires when an EHR is created."""
    return {
        "_type": "EHR_STATUS",
        "name": {"_type": "DV_TEXT", "value": "EHR Status"},
        "archetype_node_id": EHR_STATUS_ARCHETYPE_ID,
        "subject": {
            "_type": "PARTY_SELF",
            "external_ref": {
                "_type": "PARTY_REF",
                "namespace": SUBJECT_NAMESPACE,
                "type": "PERSON",
                "id": {
                    "_type": "GENERIC_ID",
                    "value": ehr.subject_token,
                    "scheme": SUBJECT_ID_SCHEME,
                },
            },
        },
        "is_modifiable": True,
        "is_queryable": True,
    }


def ehr_status_to_intake_ehr(status: Mapping[str, Any]) -> IntakeEhr:
    """The inverse. Refuses a subject that is not carried under our scheme —
    a foreign namespace means the CDR holds an identifier we did not tokenize."""
    external_ref = _require(status, "subject", "external_ref")
    scheme = _require(external_ref, "id", "scheme")
    if scheme != SUBJECT_ID_SCHEME:
        raise OpenEhrMappingError(
            f"EHR subject is carried under scheme {scheme!r}, not {SUBJECT_ID_SCHEME!r}: "
            "the CDR holds a subject this service did not pseudonymise"
        )
    return IntakeEhr(subject_token=_require(external_ref, "id", "value"))


# --- COMPOSITION --------------------------------------------------------------------


def envelope_to_composition(envelope: IntakeEnvelope) -> dict[str, Any]:
    """Canonical openEHR COMPOSITION JSON for the envelope, with empty content."""
    return {
        "_type": "COMPOSITION",
        "name": {"_type": "DV_TEXT", "value": "Ön görüşme"},
        "archetype_node_id": COMPOSITION_ARCHETYPE_ID,
        "archetype_details": {
            "_type": "ARCHETYPED",
            "archetype_id": {"_type": "ARCHETYPE_ID", "value": COMPOSITION_ARCHETYPE_ID},
            "template_id": {"_type": "TEMPLATE_ID", "value": TEMPLATE_ID},
            "rm_version": OPENEHR_RM_VERSION,
        },
        "language": _code_phrase(_TERMINOLOGY_LANGUAGE, envelope.language),
        "territory": _code_phrase(_TERMINOLOGY_TERRITORY, envelope.territory),
        "category": _coded_text(
            envelope.category.value, _TERMINOLOGY_OPENEHR, envelope.category.code
        ),
        "composer": {"_type": "PARTY_IDENTIFIED", "name": envelope.composer},
        "context": {
            "_type": "EVENT_CONTEXT",
            "start_time": {
                "_type": "DV_DATE_TIME",
                "value": envelope.reference_time.isoformat(),
            },
            "setting": _coded_text(
                envelope.setting.value, _TERMINOLOGY_OPENEHR, envelope.setting.code
            ),
        },
        "content": [],
    }


def composition_to_envelope(composition: Mapping[str, Any]) -> IntakeEnvelope:
    """The inverse, over what a CDR hands back (which re-serialises freely)."""
    template_id = _require(composition, "archetype_details", "template_id", "value")
    if template_id != TEMPLATE_ID:
        raise OpenEhrMappingError(
            f"composition declares template {template_id!r}, not {TEMPLATE_ID!r}"
        )
    setting_code = _require(composition, "context", "setting", "defining_code", "code_string")
    if setting_code not in _SETTING_BY_CODE:
        raise OpenEhrMappingError(
            f"context.setting carries openEHR code {setting_code!r}, which is not in the "
            "published setting group — this module never guesses a rubric for a code"
        )
    category_code = _require(composition, "category", "defining_code", "code_string")
    category = next((c for c, code in _CATEGORY_CODES.items() if code == category_code), None)
    if category is None:
        raise OpenEhrMappingError(
            f"category carries openEHR code {category_code!r}, which is not in the "
            "published composition-category group"
        )
    start_time = _require(composition, "context", "start_time", "value")
    return IntakeEnvelope(
        reference_time=_parse_dv_date_time(start_time),
        composer=_require(composition, "composer", "name"),
        setting=_SETTING_BY_CODE[setting_code],
        category=category,
        language=_require(composition, "language", "code_string"),
        territory=_require(composition, "territory", "code_string"),
    )


def _parse_dv_date_time(value: str) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise OpenEhrMappingError(f"context.start_time is not ISO 8601: {exc}") from exc
    if parsed.tzinfo is None:
        raise OpenEhrMappingError(
            "context.start_time came back without an offset; a naive instant in a "
            "clinical record is an ambiguity, not a default"
        )
    return parsed


# --- the gate ------------------------------------------------------------------------


_LEAF_ASK: Final = (
    "Which leaf archetype path (and its at-code) inside {archetype} carries this "
    "answer? Until a clinical-informatics author states it against a CKM revision, "
    "the export refuses rather than invents one."
)
_NO_PATH_ASK: Final = (
    "This slot declares no archetype path at all. Which archetype, and which leaf "
    "path within it, should carry this answer — or is it deliberately outside the "
    "openEHR export?"
)
_UNKNOWN_ASK: Final = (
    "This slot is not in the compiled binding table. Recompile the pack, or state "
    "where the answer belongs in the operational template."
)


def unbound_slots(
    state: SessionState, *, bindings: Sequence[SlotBinding]
) -> tuple[UnboundSlot, ...]:
    """Every answered slot the export cannot place, in slot-id order.

    Today that is *every* answered slot: the committed template carries
    archetype roots only, so no binding row resolves to a datum. The rows are
    still consulted, because the refusal has to say which archetype the slot
    was annotated with — that is the diff a clinical-informatics author works
    from.
    """
    by_id = {b.slot_id: b for b in bindings}
    out: list[UnboundSlot] = []
    for slot_id in sorted(state.slots):
        value = state.slots[slot_id]
        if value is None:
            # A slot with no value is not an answer, so nothing is being lost.
            continue
        binding = by_id.get(slot_id)
        if binding is None:
            out.append(UnboundSlot(slot_id=slot_id, ask=_UNKNOWN_ASK))
        elif binding.aql_path is None:
            out.append(
                UnboundSlot(
                    slot_id=slot_id,
                    deferred_reason=binding.openehr_deferred_reason,
                    ask=_NO_PATH_ASK,
                )
            )
        else:
            out.append(
                UnboundSlot(
                    slot_id=slot_id,
                    aql_path=binding.aql_path,
                    rm_type=binding.rm_type,
                    ask=_LEAF_ASK.format(archetype=binding.aql_path),
                )
            )
    return tuple(out)


def session_composition(
    state: SessionState,
    *,
    envelope: IntakeEnvelope,
    bindings: Sequence[SlotBinding],
) -> dict[str, Any]:
    """One session as a canonical openEHR composition, or a typed refusal.

    Fails closed before anything reaches a transport, so a session that cannot
    be exported leaves no partial record in the CDR.
    """
    blocked = unbound_slots(state, bindings=bindings)
    if blocked:
        raise OpenEhrExportBlocked(blocked)
    return envelope_to_composition(envelope)
