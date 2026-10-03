"""Protocol DSL v2 building blocks: slots, sections, voice, red flags (INT-040).

Field sets are taken from the blueprint only: files/03 §6 (pack example,
compiler outputs), files/04 §1 (voice fields v1.1), files/12 §2 (core types,
``source:`` per rule), files/13 §13 (delivery), files/02 §5.3 via the rule
schema documented inline in files/protocols/base.life_threat.yaml (route,
register, location-keyed actions, do-nots). A field the blueprint does not
name does not exist here, with one recorded exception: ``Slot.data_category``
comes from the owner's D3 decision of 2026-09-26 (INT-349).

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

from protocols.locale_text import (
    DEFAULT_LOCALE,
    LocaleChoices,
    LocaleCode,
    LocaleFlag,
    LocaleList,
    LocaleText,
)
from protocols.types import (
    SLOT_KEY_PATTERN,
    SLOT_REF_PATTERN,
    AbandonmentHandler,
    AckStyle,
    CrisisNumber,
    DataCategory,
    Delivery,
    EK4Level,
    NotifyClinic,
    OfflineDraftPath,
    Pace,
    Prosody,
    RedFlagRoute,
    RedRegister,
    RuleStatus,
    SlotType,
    Tense,
)

__all__ = [
    "AudioDelivery",
    "ClipManifestEntry",
    "Instrument",
    "InstrumentItem",
    "LocationAction",
    "OverlayActivation",
    "RedFlagAction",
    "RedFlagRule",
    "RuleId",
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
    locale: LocaleCode = Field(
        default=DEFAULT_LOCALE,
        description="The locale whose string this clip speaks (INT-297). The cache "
        "keys on (locale, voice) rather than on the voice alone: two locales may "
        "share a voice, and a clip found by text hash alone is then a clip of "
        "another language's string played into this session.",
    )


class VoiceSettings(FrozenModel):
    """Voice hints on a protocol or section (files/04 §1 v1.1: ``voice:
    {allow_paraphrase, backchannel_ok, ack_style, pace}``)."""

    allow_paraphrase: LocaleFlag | None = Field(
        default=None,
        description="Paraphrase permission PER LOCALE; validated instruments are "
        "always false (files/04 §1; CLAUDE.md invariant 10). Per locale because "
        "invariant 10 is about a language: permission granted for Turkish, whose "
        "register and reading level are checked, asserts nothing about a language "
        "where neither has been (INT-297).",
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
    ask_tr: LocaleText | None = Field(
        default=None,
        description="Spoken question per locale, ``tr`` required (files/04 §1 "
        "``ask_tr``; INT-297).",
    )
    confirm_tr: LocaleText | None = Field(
        default=None,
        description="Spoken confirm text per locale, ``tr`` required (files/04 §1 "
        "``confirm_tr``; INT-314). Spoken, so invariant 10 applies to it in "
        "whatever language it is spoken in.",
    )
    follow_up_tr: LocaleText | None = Field(
        default=None,
        description="Clarification follow-up per locale; mandatory on every required "
        "slot because the runtime asks ahead and reconciles behind (files/04 §1; "
        "files/13 §11.1), and required in every locale the slot can ask in "
        "(INT-297).",
    )
    choices_tr: LocaleChoices | None = Field(
        default=None,
        description="Spoken answer options per locale, one order and one arity "
        "(files/04 §1 ``choices_tr[]``; INT-297).",
    )
    delivery: Delivery | None = Field(
        default=None, description="voice|text_first|text_only (files/13 §13)."
    )
    data_category: DataCategory = Field(
        default=DataCategory.GENERAL_HEALTH,
        description="What kind of personal data the answer is, from the closed "
        "set of owner decision D3 (INT-349). Anything but general_health is "
        "envelope-encrypted at rest, and the compiler refuses to serve the slot "
        "while its category row in docs/legal/data-categories.yaml is incomplete.",
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
    text_tr: LocaleText = Field(
        description="Verbatim item text per locale, ``tr`` required — the tr "
        "resource is the source of truth (CLAUDE.md invariants 5 and 10). An "
        "instrument item in a second language is new clinical content rather than "
        "a translation of signed content (HB-C19), which is why the map is keyed "
        "and not merged."
    )
    allow_paraphrase: LocaleFlag = Field(
        description="Must be exactly false in every locale the item carries "
        "(files/04 §1); the validator rejects true rather than the schema, so the "
        "loader can still report the finding with its blueprint citation."
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
    snapshot under packages/protocols/sources/, and the url and retrieved_on
    must be the snapshot header's. Not enforced here, where the repository is
    out of reach: ``protocols.source_snapshots`` is the check, and
    ``protocols.compile.load_life_threat_set`` runs it on every life-threat
    rule at load (INT-465). A chain pack's red-flag rules cite no snapshot
    today; when one does, its loader runs the same check."""

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


class AudioDelivery(FrozenModel):
    """The Audio column of the files/02 §5.3 Axis 2 register table, stated on
    the rule rather than derived.

    **No field here has a default, and that is the whole point.** The
    paediatric-airway rule is ``KIRMIZI_K1`` and ``CALM`` at once because a
    child with stridor *"deteriorates when distressed"* — a full-screen red
    alarm with urgent speech delivered to the parent standing next to that
    child *"produces the deterioration the alert exists to prevent"*
    (files/02 §5.3). A default chosen once, by an engineer, is exactly the
    failure CLAUDE.md invariant 21 names, so an author who writes ``audio:``
    writes all three legs of it or the rule does not load.

    The block is optional on the rule: the register table already states the
    audio for each register, and exemplars 1 and 2 carry no block at all.
    What is refused is a **partial** or **register-contradicting** one —
    see :meth:`RedFlagRule._delivery_invariants`.
    """

    spoken: bool = Field(
        description="Whether the RED is spoken at all (files/02 §5.3 Axis 2 "
        "Audio column). Required — every register must be fully comprehensible "
        "with the sound off, so speech is an enhancement and never the carrier."
    )
    prosody: Prosody | None = Field(
        description="How it is voiced — urgent (ALERT) or soft (CALM), and "
        "``null`` where nothing is spoken (files/02 §5.3). Required AND "
        "nullable: exemplar 4 writes ``prosody: null``, which is a decision; "
        "an absent prosody is not."
    )
    alert_sound: bool = Field(
        description="Whether an alert sound plays (files/02 §5.3 Axis 2). "
        "Required: this is the leg that turns a CALM rule into the alarm the "
        "register exists to prevent."
    )

    @model_validator(mode="after")
    def _speech_and_prosody_agree(self) -> AudioDelivery:
        if self.spoken and self.prosody is None:
            raise ValueError(
                "spoken audio carries a prosody — the files/02 §5.3 register "
                "table gives one for every spoken register"
            )
        if not self.spoken and self.prosody is not None:
            raise ValueError(
                "unspoken audio carries none — a prosody on speech that never "
                "happens is a delivery decision nothing will read (files/02 §5.3)"
            )
        return self


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
    action_tr: LocaleText | None = Field(
        default=None,
        description="Patient-facing action script per locale, action first, ``tr`` "
        "required (files/protocols/base.life_threat.yaml action_tr; <= B1 Turkish "
        "per files/04 header; INT-314). This is the field CLAUDE.md invariant 10's "
        "*red-flag action scripts are spoken verbatim* clause is about: before "
        "INT-314 the question half of a RED script was per locale and the action "
        "half was not, so the clause held for half a rule.",
    )
    action_tr_ref: str | None = Field(
        default=None,
        description="Reference into docs/legal/strings.yaml for PolicyGuard-owned "
        "text (files/protocols/base.life_threat.yaml exemplar 4 action_tr_ref).",
    )
    do_nots_tr: LocaleList = Field(
        default_factory=dict,
        description="Explicit do-not list per locale (files/04 §8.1 rule 6 "
        "do_nots_tr; INT-314). An empty map is no do-nots in any language — the "
        "pre-INT-314 empty tuple — and constrains no locale; ``{tr: []}`` is an "
        "author saying this branch has none in Turkish, and does. Every locale "
        "present carries the same number of instructions in the same order.",
    )
    why_tr: LocaleText | None = Field(
        default=None,
        description="Explanation per locale, never a diagnosis (files/protocols/"
        "base.life_threat.yaml why_tr; INT-297).",
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
    numbers: tuple[CrisisNumber, ...] = Field(
        default=(),
        description="The crisis numbers this action offers, from the closed "
        "files/04 §4.1 table (files/protocols/base.life_threat.yaml exemplar 4 "
        "``numbers: [112]``). Empty by default because an action that offers no "
        "number is the safe reading of silence, and closed as an enum because "
        "files/04 §4.1 is binding: no model, search tool or learning-loop "
        "proposal may ever populate a crisis number, and 182 — the MHRS "
        "appointment line — must be unwritable rather than merely discouraged. "
        "The accompanying Turkish lives in docs/legal/strings.yaml under "
        "PolicyGuard, reached through ``action_tr_ref``.",
    )
    carry_child: bool = Field(
        default=False,
        description="The action instructs the user to carry the patient — the "
        "paediatric-airway ON_SITE branch, *çocuğunuzu kucağınızda tutun ve "
        "Acil Servis'e götürün* (files/protocols/base.life_threat.yaml exemplar "
        "3). Only a rule whose ``subject_is_child`` may set it.",
    )
    open_question: str | None = Field(
        default=None,
        description="An open CLINICIAN decision about this action's text, "
        "recorded on the action instead of being resolved by an engineer — "
        "exemplar 3's is the Tebliğ MADDE 9(1) companion-separation question "
        "(HUMAN_BLOCKERS HB-C9, open for ClinicalAuthor). Never patient-facing, "
        "and never silently ignorable: protocols.compile.resolve refuses to "
        "compile a rule carrying one into a served pack.",
    )
    note: str | None = Field(
        default=None,
        description="Free-text commentary about this location branch — why the "
        "channel is what it is (exemplar 4's ON_SITE note on staff "
        "notification). Never patient-facing; the same class as "
        "``SourceBlock.note`` and reached by the same invariant-17 scan.",
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

    ask_one_tr: LocaleText = Field(
        description="The single disambiguation question per locale, ``tr`` required "
        "(files/04 §8.1 rule 7; INT-314). The answer picks ON_SITE or REMOTE, so "
        "the one-question gate in protocols.compile.resolve runs against EVERY "
        "locale's entry: a language in which this asked two questions would be a "
        "language deciding which action resolves (CLAUDE.md invariant 21)."
    )
    on_yes: Literal["ON_SITE", "REMOTE"] = Field(
        description="Branch taken on yes (files/protocols/base.life_threat.yaml)."
    )
    on_no: Literal["ON_SITE", "REMOTE"] = Field(
        description="Branch taken on no (files/protocols/base.life_threat.yaml)."
    )
    on_no_answer: Literal["REMOTE"] = Field(
        description="Safe branch if and only if the question was asked and went "
        "unanswered — never a silent assumption (files/protocols/"
        "base.life_threat.yaml). Always REMOTE (INT-465; files/04 §8.1 rule 7; "
        "CD-24 generic_red_unknown_no_answer_goes_remote): guessing that a patient "
        "who did not answer is already in the hospital is the unsafe direction."
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
        """Every carrier of the 112 affordance, closed under ON_SITE.

        files/02 §5.3: *"The 112'yi ara affordance is not rendered under
        ON_SITE at all. Not de-emphasised, not below the fold — absent."* A
        patient already in the building must not be sent out of it. There are
        three carriers, and closing one while leaving another open is the
        failure the invariant names: the flag, the number list, and the action
        codes. INT-254 recorded the third as open because closing it looked
        like it needed an enumerated action-code set, which no blueprint
        writes down — it does not. It needs a refusal of the one token
        invariant 21 forbids.
        """
        if self.on_site.show_112:
            raise ValueError(
                "ON_SITE action never offers 112 — the affordance is absent, not "
                "de-emphasised (CLAUDE.md invariant 21; files/04 §8.2)"
            )
        if CrisisNumber.EMERGENCY in self.on_site.numbers:
            raise ValueError(
                "the ON_SITE number list carries no 112 — the affordance is absent "
                "under ON_SITE, in every carrier (CLAUDE.md invariant 21; "
                "files/02 §5.3; files/04 §8.2 on_site_action_never_offers_112)"
            )
        for field, code in (
            ("primary", self.on_site.primary),
            ("secondary", self.on_site.secondary),
        ):
            if code is not None and str(CrisisNumber.EMERGENCY.value) in code:
                raise ValueError(
                    f"the ON_SITE {field} action code names 112 ({code}) — an action "
                    "code is a carrier of the affordance like any other (CLAUDE.md "
                    "invariant 21; files/02 §5.3)"
                )
        if CrisisNumber.EMERGENCY in self.remote.numbers and not self.remote.show_112:
            raise ValueError(
                "the 112 affordance has two carriers on this action and they "
                "disagree: numbers lists 112 while show_112 is false "
                "(CLAUDE.md invariant 21; files/04 §4.1)"
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
    subject_is_child: bool | None = Field(
        default=None,
        description="The rule's subject is a child and the user is therefore a "
        "proxy (files/02 §5.3 Axis 2 CALM row; files/protocols/"
        "base.life_threat.yaml exemplar 3). ``None`` means NOT STATED and is a "
        "third value rather than a default: it decides both the delivery "
        "register and, through ``age_band``, which reviewer must sign (HB-C1). "
        "A paediatric life-threat rule must state it — see "
        "protocols.compile.life_threat.LifeThreatRule.",
    )
    audio: AudioDelivery | None = Field(
        default=None,
        description="The register's Audio column, stated explicitly (files/02 "
        "§5.3 Axis 2). Optional — the register table already states the audio "
        "for each register and exemplars 1 and 2 carry no block — but a block "
        "that is written is written whole and may not contradict the register.",
    )
    suppress_attention_interrupt: bool | None = Field(
        default=None,
        description="Whether this rule suppresses the normal attention-grabbing "
        'interrupt (files/04 §8.1 rule 6: the airway rule *"must not run the '
        'normal attention-grabbing interrupt at all"*). ``None`` means NOT '
        "STATED, which is refused on a ``distress_sensitive`` rule in a register "
        "that takes the screen — those are exactly the rules a forgotten flag "
        "would give an interrupt to, and a default of False is the harm "
        "direction.",
    )
    consent_independent: bool | None = Field(
        default=None,
        description="The rule runs regardless of wellbeing-lane consent "
        "(files/04 §4.2 defect 3: consent-gating creates a hole exactly where it "
        "matters, and the people most likely to decline are the people most "
        "needing to be caught). Setting it declares the crisis path and forces "
        "the other three legs of files/04 §4.2 to be written.",
    )
    offline_draft_path: OfflineDraftPath | None = Field(
        default=None,
        description="Whether the item may enter the encrypted offline-resume "
        "cache (files/04 §8.2 crisis_items_have_no_offline_draft_path; §4.2 "
        "defect 2). Required on the crisis path, where the only admissible "
        "value is ``forbidden``.",
    )
    abandonment_handler: AbandonmentHandler | None = Field(
        default=None,
        description="What happens when a patient force-quits after a disclosure "
        "(files/04 §4.2 defect 2). Required on the crisis path; the mechanism "
        "the blueprint names is server-side evaluation on the answer.",
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

    @model_validator(mode="after")
    def _delivery_invariants(self) -> RedFlagRule:
        """The register axis, enforced rather than merely typed (INT-255).

        files/02 §5.3 is a table, and until now only its Presentation column
        reached the DSL as an enum. The rest of the row — who may be alarmed,
        what audio the register admits, whether the screen is taken — was
        prose the compiler could not read. Each clause below quotes the row it
        comes from; none is an engineering preference.
        """
        register, audio = self.register, self.audio

        if register is RedRegister.ALERT:
            for flag, why in (
                (
                    self.distress_sensitive,
                    "a distress_sensitive rule",
                ),
                (
                    self.subject_is_child,
                    "a rule whose subject is a child and whose user is a proxy",
                ),
                (
                    self.consent_independent,
                    "the consent-independent crisis path",
                ),
            ):
                if flag:
                    raise ValueError(
                        f"{why} is never told in the ALERT register — alarm is the "
                        "mechanism of harm here, not the delivery (files/02 §5.3 "
                        "Axis 2 CALM/SILENT rows; files/04 §4.2)"
                    )

        if audio is not None and register is not None:
            if register in (RedRegister.SILENT, RedRegister.DEFERRED_CLINICIAN):
                if audio.spoken or audio.alert_sound:
                    raise ValueError(
                        f"the {register.value} register carries no audio at all "
                        '(files/02 §5.3 Axis 2: SILENT is "No audio, ever" and '
                        "DEFERRED_CLINICIAN leaves the patient screen unchanged)"
                    )
            elif register is RedRegister.CALM and audio.alert_sound:
                raise ValueError(
                    "the CALM register is spoken softly with no alert sound "
                    "(files/02 §5.3 Axis 2) — the paediatric-airway case is CALM "
                    "precisely because the alarm is the harm"
                )

        if register in (RedRegister.ALERT, RedRegister.CALM):
            if self.distress_sensitive and self.suppress_attention_interrupt is None:
                raise ValueError(
                    "a distress_sensitive rule in a register that takes the screen "
                    "must state suppress_attention_interrupt — the rule that must "
                    "not run the interrupt AT ALL (files/04 §8.1 rule 6) is exactly "
                    "the rule an omission would silently give one, so there is no "
                    "permitted default"
                )
        elif register is not None and self.suppress_attention_interrupt is False:
            raise ValueError(
                f"the {register.value} register has no attention interrupt to run, "
                "so suppress_attention_interrupt: false asserts a takeover the "
                "register forbids (files/02 §5.3 Axis 2)"
            )

        if self.consent_independent:
            if self.offline_draft_path is not OfflineDraftPath.FORBIDDEN:
                raise ValueError(
                    "a consent-independent crisis item has no offline draft path — "
                    "it is evaluated server-side on the answer, or the disclosure "
                    "may never reach the server at all (files/04 §4.2 defect 2; "
                    "§8.2 crisis_items_have_no_offline_draft_path)"
                )
            if self.abandonment_handler is None:
                raise ValueError(
                    "a consent-independent crisis item must name its abandonment "
                    "handler — a patient who force-quits after answering is the "
                    "highest-risk state the product can enter (files/04 §4.2 defect 2)"
                )
            if self.notify_clinic is not NotifyClinic.ALWAYS:
                raise ValueError(
                    "clinician notification on the crisis path is unconditional and "
                    "time-bound, never conditional on a connector being present "
                    "(files/04 §4.2 defect 1)"
                )

        action = self.action
        if action is not None:
            for branch in (action.remote, action.on_site):
                if branch is not None and branch.carry_child and not self.subject_is_child:
                    raise ValueError(
                        "carry_child instructs the user to carry the patient, which "
                        "only a rule whose subject_is_child may do (files/02 §5.3; "
                        "files/protocols/base.life_threat.yaml exemplar 3)"
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
