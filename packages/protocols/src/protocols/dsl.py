"""Protocol DSL v2 building blocks: slots, sections, voice, red flags (INT-040).

Field sets are taken from the blueprint only: files/03 §6 (pack example,
compiler outputs), files/04 §1 (voice fields v1.1), files/12 §2 (core types,
``source:`` per rule), files/13 §13 (delivery), files/02 §5.3 via the rule
schema documented inline in files/protocols/base.life_threat.yaml (route,
register, location-keyed actions, do-nots). A field the blueprint does not
name does not exist here.

Naming note (files/protocols/base.life_threat.yaml, schema_reconciliation):
the life-threat set spells the predicate ``gate:`` and the provenance block
``evidence:``; for chain packs this module uses the files/03 §6 / files/12
§2.4-2.5 names ``when:`` and ``source:``, which are also what the CI gate
names (``every_red_rule_has_a_source_block``).
"""

from __future__ import annotations

import hashlib
import unicodedata
import warnings
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from clinical_schemas.common import FrozenModel, Ref, Sha256
from pydantic import Field, StringConstraints, model_validator

from protocols.types import (
    SLOT_KEY_PATTERN,
    SLOT_REF_PATTERN,
    AckStyle,
    Delivery,
    EK4Level,
    NotifyClinic,
    Pace,
    RedFlagRoute,
    RedRegister,
    RuleStatus,
    SlotType,
    Tense,
)

__all__ = [
    "ClipManifestEntry",
    "Instrument",
    "InstrumentItem",
    "LocationAction",
    "OverlayActivation",
    "RedFlagAction",
    "RedFlagRule",
    "Section",
    "Slot",
    "SourceBlock",
    "UnknownAction",
    "VoiceSettings",
    "clip_text_hash",
]

# Key shapes. Slot/section keys are snake_case (files/03 §6 examples);
# instrument ids are the registry spellings (files/04 header table, e.g.
# PHQ-9); rule ids are rf.<snake_case>, with dotted qualifiers minted only
# by tighten_rule (files/12 §4 layer 2). Both key patterns come from
# protocols.types so the DSL and the ``when`` tokenizer cannot drift.
SlotKey = Annotated[str, StringConstraints(pattern=rf"^{SLOT_KEY_PATTERN}$")]
# A slot REFERENCE, as a red-flag predicate spells it: section-qualified
# (files/03 §6 ``hpi.single_hot_swollen_joint``; every exemplar in
# files/protocols/base.life_threat.yaml) or bare where the pack declares one
# flat namespace. Distinct from SlotKey, which names a slot inside its own
# section and therefore never carries a dot.
SlotRef = Annotated[str, StringConstraints(pattern=rf"^{SLOT_REF_PATTERN}$")]
InstrumentId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Za-z0-9-]*$")]
RuleId = Annotated[str, StringConstraints(pattern=r"^rf\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")]
# Action codes are SCREAMING_SNAKE (files/protocols/base.life_threat.yaml:
# CALL_112, GO_TO_IN_HOUSE_ACIL, SAME_DAY_ACIL_TODAY, CRISIS_SIGNPOST,
# NEAREST_ACIL_ADDRESS_AS_TEXT). The set is open — no blueprint enumerates it.
ActionCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]*$")]
TrText = Annotated[str, StringConstraints(min_length=1)]


def clip_text_hash(text: str) -> str:
    """Hash a scripted Turkish text for the clip manifest (files/03 §6
    compiler output (e): ``text_hash → clip_id`` per voice). NFC-normalised
    so the same visible Turkish always maps to the same clip."""
    return hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()


class ClipManifestEntry(FrozenModel):
    """One clip-manifest row (files/03 §6 output (e); CLAUDE.md invariant 10:
    scripted text is spoken verbatim from the clip cache or TTS)."""

    text_hash: Sha256 = Field(description="clip_text_hash of the scripted text (files/03 §6).")
    clip_id: Ref = Field(description="Pre-synthesised clip id (files/03 §6 output (e)).")
    voice: TrText = Field(description="Voice the clip was synthesised for (files/03 §6).")


class VoiceSettings(FrozenModel):
    """Voice hints on a protocol or section (files/04 §1 v1.1: ``voice:
    {allow_paraphrase, backchannel_ok, ack_style, pace}``)."""

    allow_paraphrase: bool | None = Field(
        default=None,
        description="Paraphrase permission; validated instruments are always false "
        "(files/04 §1; CLAUDE.md invariant 10).",
    )
    backchannel_ok: bool | None = Field(
        default=None, description="Whether backchannels may play (files/04 §1)."
    )
    ack_style: AckStyle | None = Field(default=None, description="brief|warm|none (files/04 §1).")
    pace: Pace | None = Field(default=None, description="normal|slow (files/04 §1).")


class Slot(FrozenModel):
    """One typed answer slot (files/03 §6 slot examples; files/04 §1 voice
    fields; files/13 §13 delivery)."""

    type: SlotType = Field(description="Typed answer kind (files/03 §6; files/13 §9.5).")
    valueset: str | None = Field(
        default=None, description="Valueset id for code slots (files/03 §6 ``valueset:``)."
    )
    unit: str | None = Field(
        default=None, description="Unit for quantity slots (files/03 §6 ``unit: min``)."
    )
    required: bool = Field(
        default=False, description="Required slots must carry follow_up_tr (files/04 §1)."
    )
    must_ask: bool = Field(
        default=False,
        description="Clinician-marked must-ask; overlays never remove these "
        "(files/04 §2.3; files/12 §3.2 deny suffix /must_ask).",
    )
    ask_if: str | None = Field(
        default=None, description="Gate expression (files/03 §5-6 ``ask_if``)."
    )
    skip_if: str | None = Field(
        default=None, description="Skip expression (files/03 §5 ``skip_if``)."
    )
    confirm_required: bool = Field(
        default=False,
        description="Answer needs an explicit confirm step (files/12 §3.2 closed "
        "set_attr table names confirm_required).",
    )
    min_confidence: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Extraction confidence floor; set_attr may only increase it "
        "(files/12 §3.2). Decimal, never float (files/13 §9.5).",
    )
    ask_tr: TrText | None = Field(
        default=None, description="Spoken Turkish question (files/04 §1 ``ask_tr``)."
    )
    confirm_tr: TrText | None = Field(
        default=None, description="Spoken Turkish confirm text (files/04 §1 ``confirm_tr``)."
    )
    follow_up_tr: TrText | None = Field(
        default=None,
        description="Clarification follow-up; mandatory on every required slot because "
        "the runtime asks ahead and reconciles behind (files/04 §1; files/13 §11.1).",
    )
    choices_tr: tuple[TrText, ...] | None = Field(
        default=None, description="Spoken answer options (files/04 §1 ``choices_tr[]``)."
    )
    delivery: Delivery | None = Field(
        default=None, description="voice|text_first|text_only (files/13 §13)."
    )
    openehr_path: str | None = Field(
        default=None,
        description="The openEHR archetype-path annotation ADR-002 keeps on every "
        "slot so the P3 export is a migration and not a rewrite; validated against "
        "the committed operational template by the compiler, not here (files/12 §8.1).",
    )
    openehr_deferred_reason: str | None = Field(
        default=None,
        description="Why this slot carries no path yet. files/12 §8 makes the pair "
        "exclusive and exhaustive with a CHECK constraint, so absence is a recorded "
        "decision rather than an oversight; the compiler enforces the same rule.",
    )

    @model_validator(mode="after")
    def _typed_slot_shape(self) -> Slot:
        if self.type is SlotType.QUANTITY and self.unit is None:
            raise ValueError("a quantity slot requires a unit (files/03 §6)")
        if self.type is SlotType.CODE and self.valueset is None:
            raise ValueError("a code slot requires a valueset (files/03 §6; files/13 §9.5)")
        return self


class Section(FrozenModel):
    """One protocol section (files/03 §6 ``sections:``): slots, instrument
    references, voice hints and delivery channel."""

    slots: dict[SlotKey, Slot] = Field(
        default_factory=dict, description="Slot schema owned by the section (files/03 §5-6)."
    )
    questionnaires: tuple[InstrumentId, ...] = Field(
        default=(),
        description="Validated instruments administered as sub-protocols, scripted, "
        "never paraphrased (files/03 §6 ``questionnaires:``).",
    )
    voice: VoiceSettings | None = Field(
        default=None, description="Section-level voice hints (files/04 §1)."
    )
    delivery: Delivery | None = Field(
        default=None, description="Section delivery channel (files/13 §13)."
    )


class InstrumentItem(FrozenModel):
    """One instrument item: verbatim Turkish text, never paraphrased
    (files/04 header instrument fidelity; CLAUDE.md invariant 10 ``text_tr``)."""

    id: SlotKey = Field(description="Stable item id within the instrument.")
    text_tr: TrText = Field(
        description="Verbatim Turkish item text — the tr resource is the source of "
        "truth (CLAUDE.md invariants 5 and 10)."
    )
    allow_paraphrase: bool = Field(
        description="Must be exactly false on instrument items (files/04 §1); the "
        "validator rejects true rather than the schema, so the loader can still "
        "report the finding with its blueprint citation."
    )


class Instrument(FrozenModel):
    """A validated instrument as a sub-protocol (files/03 §6). Licensing is
    checked against the registry stub in :mod:`protocols.licences`; a non-GO
    instrument never validates into a compilable pack (files/04 header)."""

    id: InstrumentId = Field(description="Registry spelling, e.g. the files/04 header ids.")
    voice: VoiceSettings | None = Field(
        default=None, description="Voice hints; allow_paraphrase must not be true here."
    )
    items: tuple[InstrumentItem, ...] = Field(
        min_length=1, description="Instrument items (files/04 header instrument fidelity)."
    )


class SourceBlock(FrozenModel):
    """Per-rule provenance (files/12 §2.5; files/04 §8.1 rule 3; CLAUDE.md
    clinical content rules). The quote must appear verbatim in a committed
    snapshot under packages/protocols/sources/ — enforced by the compiler
    slice (INT-041), not here."""

    guideline_id: TrText = Field(description="Guideline identifier (files/12 §2.5).")
    guideline_title: TrText | None = Field(
        default=None, description="Guideline title (files/12 §2.5)."
    )
    version_or_date: TrText = Field(description="Guideline version or date (files/12 §2.5).")
    url: TrText = Field(description="Guideline URL (files/12 §2.5).")
    retrieved_on: date = Field(description="Retrieval date (files/12 §2.5).")
    quote: TrText = Field(description="Verbatim supporting quote (files/12 §2.5).")
    quote_snapshot: str | None = Field(
        default=None,
        description="Committed snapshot path under packages/protocols/sources/ "
        "(files/12 §2.5; files/protocols/base.life_threat.yaml exemplar 1).",
    )
    note: str | None = Field(
        default=None,
        description="Provenance commentary about the citation itself — why the "
        "guideline is read as it is, or which sibling rules its split produced "
        "(files/protocols/base.life_threat.yaml exemplar 1, whose note records "
        "the EK-4 three-way chest-pain split and names the gate asserting the "
        "third arm). Never patient-facing and never a substitute for the quote: "
        "the invariant-17 pending-value scan in protocols.validator walks it "
        "with every other rule string.",
    )


class LocationAction(FrozenModel):
    """The action for one resolved location (REMOTE or ON_SITE), per the rule
    schema in files/protocols/base.life_threat.yaml and files/04 §8.1 rule 7."""

    primary: ActionCode = Field(
        description="Primary action code (files/protocols/base.life_threat.yaml, "
        "e.g. CALL_112, GO_TO_IN_HOUSE_ACIL)."
    )
    secondary: ActionCode | None = Field(
        default=None,
        description="A second action code carried ALONGSIDE the primary, never "
        "instead of it (files/protocols/base.life_threat.yaml exemplar 1: "
        "``primary: CALL_112`` with ``secondary: "
        "NEAREST_ACIL_ADDRESS_AS_TEXT``). Folding it into ``primary`` would "
        "make one field mean two actions and put the ordering — which one the "
        "patient does first — beyond the schema's reach.",
    )
    show_112: bool = Field(
        description="Whether the 112 affordance is shown; never under ON_SITE "
        "(files/04 §8.2 on_site_action_never_offers_112)."
    )
    action_tr: TrText | None = Field(
        default=None,
        description="Patient-facing Turkish, action first (files/protocols/"
        "base.life_threat.yaml action_tr; <= B1 Turkish per files/04 header).",
    )
    action_tr_ref: str | None = Field(
        default=None,
        description="Reference into docs/legal/strings.yaml for PolicyGuard-owned "
        "text (files/protocols/base.life_threat.yaml exemplar 4 action_tr_ref).",
    )
    do_nots_tr: tuple[TrText, ...] = Field(
        default=(),
        description="Explicit do-not list (files/04 §8.1 rule 6 do_nots_tr).",
    )
    why_tr: TrText | None = Field(
        default=None,
        description="Explanation, never a diagnosis (files/protocols/"
        "base.life_threat.yaml why_tr).",
    )
    why_tr_ref: str | None = Field(
        default=None,
        description="strings.yaml reference form of why_tr (files/protocols/"
        "base.life_threat.yaml exemplar 4).",
    )
    notify_staff_immediate: bool = Field(
        default=False,
        description="Under ON_SITE the inbox entry is the primary channel (files/04 §8.1 rule 7).",
    )

    @model_validator(mode="after")
    def _exactly_one_text_carrier(self) -> LocationAction:
        if (self.action_tr is None) == (self.action_tr_ref is None):
            raise ValueError(
                "exactly one of action_tr / action_tr_ref must be set "
                "(files/protocols/base.life_threat.yaml exemplar 4)"
            )
        return self


class UnknownAction(FrozenModel):
    """The UNKNOWN location branch: exactly one question, then branch —
    never a guess (files/04 §8.1 rule 7; files/04 §8.2
    unknown_location_asks_exactly_one_question)."""

    ask_one_tr: TrText = Field(
        description="The single disambiguation question (files/04 §8.1 rule 7)."
    )
    on_yes: Literal["ON_SITE", "REMOTE"] = Field(
        description="Branch taken on yes (files/protocols/base.life_threat.yaml)."
    )
    on_no: Literal["ON_SITE", "REMOTE"] = Field(
        description="Branch taken on no (files/protocols/base.life_threat.yaml)."
    )
    on_no_answer: Literal["ON_SITE", "REMOTE"] = Field(
        description="Safe branch if and only if the question was asked and went "
        "unanswered — never a silent assumption (files/protocols/"
        "base.life_threat.yaml)."
    )


class RedFlagAction(FrozenModel):
    """Location-keyed action block. All three keys — REMOTE, ON_SITE,
    UNKNOWN — must be present and resolve, with no default (CLAUDE.md
    invariant 21; files/04 §8.1 rule 7)."""

    remote: LocationAction = Field(alias="REMOTE", description="files/02 §5.3 Axis 3 REMOTE.")
    on_site: LocationAction = Field(alias="ON_SITE", description="files/02 §5.3 Axis 3 ON_SITE.")
    unknown: UnknownAction = Field(alias="UNKNOWN", description="files/02 §5.3 Axis 3 UNKNOWN.")

    @model_validator(mode="after")
    def _on_site_never_offers_112(self) -> RedFlagAction:
        if self.on_site.show_112:
            raise ValueError(
                "ON_SITE action never offers 112 — the affordance is absent, not "
                "de-emphasised (CLAUDE.md invariant 21; files/04 §8.2)"
            )
        return self


# The blueprint names the RED axis field `register` (CLAUDE.md invariant 21;
# files/02 §5.3); pydantic warns because ABCMeta exposes a classmethod of the
# same name. The blueprint name wins — suppress exactly that warning, the
# same way clinical_schemas.triage does for RulesTriageResult.
warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "RedFlagRule" shadows an attribute in parent',
    category=UserWarning,
)


class RedFlagRule(FrozenModel):
    """One red-flag rule (files/04 §3; files/12 §2.4-2.5; the rule schema in
    files/protocols/base.life_threat.yaml). RED rules carry register and a
    location-resolved action with no permitted default (invariant 21)."""

    id: RuleId = Field(
        description="Stable rf.<snake_case> id, never renamed once served "
        "(files/protocols/base.life_threat.yaml)."
    )
    label_tr: TrText = Field(
        description="Clinician-facing Turkish label — NOT patient-facing, NOT a "
        "diagnosis (files/protocols/base.life_threat.yaml)."
    )
    when: TrText = Field(
        description="Trigger predicate (files/03 §6 ``when:``; three-valued per "
        "files/12 §1.1 — deny-suffixed against overlay edits, files/12 §3.2)."
    )
    tense: Tense = Field(description="Event tense (files/12 §2.4; files/04 §8.1 rule 4).")
    tense_anchor: SlotRef = Field(
        description="Slot carrying the event timestamp; a tense-qualified rule "
        "cannot fire on an undated symptom (files/12 §2.4). A REFERENCE, in the "
        "same namespace the ``when`` predicate reads — protocols.triage.engine "
        "unions it into ``referenced_slots(when)`` and TriageContext keys "
        "answers by that spelling — so it is section-qualified "
        "(``chest_pain.onset_at``) wherever the pack's sections are."
    )
    level: EK4Level = Field(description="EK-4 acuity, five-valued (files/12 §2.1).")
    route: RedFlagRoute = Field(description="Patient route axis (files/02 §5.3 Axis 1).")
    register: RedRegister | None = Field(
        default=None,
        description="RED register axis — required on KIRMIZI with no default "
        "(CLAUDE.md invariant 21; files/02 §5.3 Axis 2).",
    )
    distress_sensitive: bool = Field(
        default=False,
        description="Marks rules where alarm is the harm (files/02 §5.3; "
        "files/protocols/base.life_threat.yaml exemplar 3).",
    )
    notify_clinic: NotifyClinic = Field(
        description="always|never; always for every RED, unconditional and "
        "time-bound (files/protocols/base.life_threat.yaml; files/04 §4.2)."
    )
    status: RuleStatus = Field(
        description="active | draft_needs_source (files/04 §8.1 rule 3); draft "
        "rules are never compiled into a served pack (CLAUDE.md invariant 17)."
    )
    source: SourceBlock | None = Field(
        default=None,
        description="Provenance block, required on active SARI/KIRMIZI rules (files/12 §2.5).",
    )
    source_gap: str | None = Field(
        default=None,
        description="Non-empty statement of what is missing, required on "
        "draft_needs_source rules (files/04 §8.1 rule 3).",
    )
    action: RedFlagAction | None = Field(
        default=None,
        description="Location-keyed action block, required on KIRMIZI rules "
        "(invariant 21; files/04 §8.1 rule 7).",
    )

    @model_validator(mode="after")
    def _rule_invariants(self) -> RedFlagRule:
        if self.status is RuleStatus.DRAFT_NEEDS_SOURCE:
            if self.source is not None:
                raise ValueError(
                    "a draft_needs_source rule carries a source_gap, never a source "
                    "block (files/04 §8.1 rule 3 — no invented citations)"
                )
            if self.source_gap is None or not self.source_gap.strip():
                raise ValueError(
                    "status draft_needs_source requires a non-empty source_gap "
                    "(files/04 §8.1 rule 3)"
                )
        elif self.level.severity >= EK4Level.SARI_K2.severity and self.source is None:
            raise ValueError(
                "an active rule at SARI or KIRMIZI level requires a source block "
                "(files/12 §2.5; files/04 §8.1 rule 3)"
            )
        if self.level.is_red:
            if self.register is None:
                raise ValueError(
                    "a KIRMIZI rule requires register — no permitted default "
                    "(CLAUDE.md invariant 21; files/02 §5.3)"
                )
            if self.action is None:
                raise ValueError(
                    "a KIRMIZI rule requires a location-resolved action for REMOTE, "
                    "ON_SITE and UNKNOWN (CLAUDE.md invariant 21; files/04 §8.1 rule 7)"
                )
            if not self.action.on_site.notify_staff_immediate:
                raise ValueError(
                    "under ON_SITE the staff notification is the primary channel — "
                    "notify_staff_immediate must be true on a KIRMIZI rule "
                    "(files/04 §8.1 rule 7)"
                )
            if self.notify_clinic is not NotifyClinic.ALWAYS:
                raise ValueError(
                    "for every RED, notify_clinic is always — unconditional and "
                    "time-bound (files/protocols/base.life_threat.yaml; files/04 §4.2)"
                )
        return self


class OverlayActivation(FrozenModel):
    """Activation of an overlay pack from patient context (files/03 §6
    ``overlays: [{id, when}]``; files/04 §2.3: overlays are activated from
    confirmed PatientOverlay facts)."""

    id: Annotated[str, StringConstraints(pattern=r"^overlay\.[a-z][a-z0-9_.]*$")] = Field(
        description="Overlay pack id (files/12 §1 overlay/ directory)."
    )
    when: TrText = Field(description="Activation predicate (files/03 §6 overlay ``when:``).")
