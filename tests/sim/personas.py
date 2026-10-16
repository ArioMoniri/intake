"""The scripted personas (INT-082).

files/04 §6 fixes what a persona is: *"persona (age, sex, literacy, dialect,
anxiety)"*, plus the department and the hidden truth. Age, sex, literacy,
dialect and anxiety are **behavioural** descriptions of a simulated speaker,
not clinical determinations, so they are authored here. The hidden truth is
not: symptoms, medications and red flags are clinical content, they are
blocked (HUMAN_BLOCKERS HB-C1…HB-C8), and :mod:`scenarios` keeps that gate
shut. What a persona carries instead is a script over the **synthetic**
pack's slots (files/04 §7).

**A persona cannot assert a triage level.** :class:`ScriptedAnswer` has no
field that could carry one, and nothing in this module imports a level, a
register or a route — the simulator's only route to a triage result is the
rules engine (CLAUDE.md invariant 1; ``tests/sim/test_scenarios.py``
asserts both halves by introspection).

**Low literacy is not "types badly".** files/02 §3 defines the low-literacy
path as *full operation without reading*: every chip label spoken and
selectable by voice, severity expressed with 3–4 ordinal spoken anchors
rather than a number, **no free text anywhere on the critical path**, and
acquisition that never asks *"okuyabiliyor musunuz?"*. :attr:`Persona.
literacy` therefore changes which answer form the persona can use and how
often it needs a repeat — never its spelling.

The overlays a persona would carry (``overlay.oncology_patient``,
``overlay.low_literacy``, ``overlay.cognitive_impairment`` — files/04 §2.3)
are named as **references**. The overlay packs themselves are INT-056 and do
not exist; naming them without authoring them is the point.

**Four of the personas answer something other than the question they were
asked**, because a roster that only walks the happy path certifies nothing
while looking like coverage. files/13 §9.6 makes the engine under-bind by
construction — *"nothing binds to a question that was not asked"* — and that
rule is only exercised by a patient who breaks the turn order:
``P15`` answers a question nobody put yet and says nothing about the one that
was; ``P16`` volunteers the trigger three turns after its question closed;
``P17`` reverses an answer it already gave; ``P11`` says clearly, four steps
late, the thing the engine had already given up on. Each drop is recorded by
:class:`~driver.UnboundUpdate`, because the engine keeps no trace of one.

The four behaviour markers — :attr:`Persona.topic_shifts`,
:attr:`Persona.volunteers_late`, :attr:`Persona.contradicts_earlier_answer`
and :attr:`Persona.telegraphic` — are **checked against the script** by a
validator rather than declared beside it, so a persona cannot claim to be
difficult without being difficult.

The baseline script covers both intake modes. The ``sistem_sorgusu`` and
``gecmis_delta`` entries exist only in the Detaylı pack, so in Hızlı they are
never reached: one script, and the resolution decides what is put to it
(files/02 §2, *"same engine, different protocol profile"*).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.overlay import LearnedFact, LearnedFactSource, PatientOverlay
from protocol import REFERENCE_TIME
from pydantic import Field, model_validator

__all__ = [
    "PERSONAS",
    "AgeBand",
    "Anxiety",
    "Literacy",
    "Persona",
    "ScriptedAnswer",
    "SubjectRole",
]

_TODAY = REFERENCE_TIME.date().isoformat()


class AgeBand(enum.StrEnum):
    """Coarse age band. Bands are behavioural here; the clinical age-band
    boundaries are a paediatrician's determination (HUMAN_BLOCKERS HB-C3)."""

    CHILD = "child"
    ADULT = "adult"
    OLDER_ADULT = "older_adult"


class Sex(enum.StrEnum):
    FEMALE = "female"
    MALE = "male"


class Literacy(enum.StrEnum):
    """files/02 §3: the low-literacy path is full operation without reading."""

    STANDARD = "standard"
    LOW = "low"


class Anxiety(enum.StrEnum):
    """files/04 §6 persona axis."""

    CALM = "calm"
    RAISED = "raised"
    HIGH = "high"


class SubjectRole(enum.StrEnum):
    """Who is speaking, and about whom (files/02 §3 attribution values)."""

    #: The patient, alone.
    SELF = "self_report"
    #: Someone answering *for* the patient — guardian or carer.
    PROXY = "proxy_report"
    #: The patient's own words on a family member's device, that member
    #: present. Third party present by definition (files/02 §3).
    ASSISTED_SELF = "assisted_self_report"


class ScriptedAnswer(FrozenModel):
    """One recorded reply: what the patient said, and what a (recorded, not
    inferred) extraction would have made of it.

    There is deliberately no confidence, no candidate flag and no level: this
    is the *fixture* side of the extraction boundary, and a fixture that could
    name a level would be a patient asserting a triage.
    """

    transcript_tr: str = Field(min_length=1, description="Synthetic Turkish utterance.")
    slot_updates: dict[str, JsonValue] = Field(
        default_factory=dict, description="What the recorded extraction bound."
    )
    clarification_needed: bool = Field(
        default=False, description="The extraction could not read the answer (files/13 §11.1)."
    )
    declines: bool = Field(
        default=False,
        description="The patient declined. Recorded as an intent; the IntakeEngine "
        "has no path to AnswerState.DECLINED, which the scenario suite pins.",
    )

    @model_validator(mode="after")
    def _a_reply_that_carries_no_answer_carries_no_updates(self) -> ScriptedAnswer:
        """A clarification request and a decline both bind nothing.

        ``IntakeEngine.apply_extraction`` ignores ``slot_updates`` outright
        when ``clarification_needed`` is set, and the driver never passes the
        updates of a decline. A fixture that set both would therefore lose
        data silently — so the combination is unrepresentable rather than
        handled.
        """
        if self.slot_updates and (self.clarification_needed or self.declines):
            raise ValueError(
                "a reply that asks for clarification or declines binds nothing; "
                "slot_updates beside either would be discarded without a trace"
            )
        return self


class Persona(FrozenModel):
    """One scripted simulated patient. Identified by id everywhere it is
    logged; ``label_tr`` is documentation and never reaches a log line
    (CLAUDE.md invariant 6)."""

    persona_id: str = Field(min_length=1, description="Stable id — the only thing logged.")
    label_tr: str = Field(min_length=1, description="Human-readable description; never logged.")
    age_band: AgeBand
    sex: Sex
    literacy: Literacy
    dialect: str = Field(min_length=1, description="files/04 §6 persona axis.")
    anxiety: Anxiety
    subject_role: SubjectRole
    third_party_present: bool = Field(
        default=False, description="files/04 §5 screening.provenance.third_party_present."
    )
    crisis_path: bool = Field(
        default=False,
        description="The persona would reach the files/04 §4.2 escalation path. The "
        "policy itself does not exist (HB-C8), so this only marks the scenario.",
    )
    overlay_refs: tuple[str, ...] = Field(
        default=(), description="Overlay pack ids this persona would activate (INT-056)."
    )
    code_switches: bool = Field(
        default=False, description="Turkish with English medical terms (files/04 §6 Noise-01)."
    )
    answers: dict[str, ScriptedAnswer] = Field(
        default_factory=dict, description="Script keyed by step id."
    )
    clarify_steps: frozenset[str] = Field(
        default=frozenset(),
        description="Steps this persona can never be read on — every attempt returns "
        "clarification_needed, so the files/13 §11.1 bound is what stops the loop.",
    )
    repeat_steps: frozenset[str] = Field(
        default=frozenset(),
        description="Steps the persona asks to have repeated before answering "
        "(request_repeat_or_clarify; mock voice only).",
    )
    hold_reconcile: frozenset[str] = Field(
        default=frozenset(),
        description="Steps whose extraction lands late — the ask-ahead race of "
        "files/13 §11.3, reconciled after the frontier drains.",
    )
    reconcile_order: tuple[str, ...] = Field(
        default=(), description="Order the held extractions land in."
    )
    overlay: PatientOverlay | None = Field(
        default=None, description="Prior confirmed facts driving delta mode (files/09 §3)."
    )
    contradicts_prefill: frozenset[str] = Field(
        default=frozenset(),
        description="Prefilled steps the persona contradicts on the confirm turn "
        "(files/09 §3 'full HPI only on change').",
    )
    topic_shifts: bool = Field(
        default=False,
        description="At least one reply answers a question that was NOT asked, and "
        "answers nothing about the one that was. Derived from the script, never "
        "declared independently of it (see the validator).",
    )
    volunteers_late: bool = Field(
        default=False,
        description="At least one reply answers its own question and volunteers "
        "something about a step whose question already closed.",
    )
    contradicts_earlier_answer: bool = Field(
        default=False,
        description="A volunteered value that REVERSES an answer this same session "
        "already recorded — the case AnswerState.CONTESTED exists for and that "
        "nothing in the engine assigns.",
    )
    telegraphic: bool = Field(
        default=False,
        description="Every reply is one or two words. Enforced, not asserted.",
    )

    @model_validator(mode="after")
    def _the_behaviour_markers_cannot_lie_about_the_script(self) -> Persona:
        """Each marker is checked against the script that has to realise it.

        These four are the shapes files/04 §6's *"forbidden behaviours"* and
        files/13 §9.6's under-binding rule are actually about, and a marker
        that could be set without the script doing it would let a persona
        *claim* to be difficult. ``topic_shifts`` and the volunteering pair
        are told apart by whether the reply also answers its own question: a
        reply that binds only foreign refs answered a different question, one
        that binds its own and a foreign ref volunteered something extra.
        """
        shifting = any(
            answer.slot_updates and step_id not in answer.slot_updates
            for step_id, answer in self.answers.items()
        )
        volunteering = any(
            step_id in answer.slot_updates and set(answer.slot_updates) - {step_id}
            for step_id, answer in self.answers.items()
        )
        if shifting is not self.topic_shifts:
            raise ValueError(
                f"{self.persona_id}: topic_shifts={self.topic_shifts} but the script "
                f"{'does' if shifting else 'does not'} answer a question that was not asked"
            )
        if volunteering is not (self.volunteers_late or self.contradicts_earlier_answer):
            raise ValueError(
                f"{self.persona_id}: the script "
                f"{'does' if volunteering else 'does not'} volunteer a value for another "
                "step, which must be declared as volunteers_late or "
                "contradicts_earlier_answer"
            )
        if self.telegraphic and any(
            len(answer.transcript_tr.split()) > _TELEGRAPHIC_MAX_WORDS
            for answer in self.answers.values()
        ):
            raise ValueError(
                f"{self.persona_id}: a telegraphic persona says no more than "
                f"{_TELEGRAPHIC_MAX_WORDS} words"
            )
        return self

    @property
    def proxy_reported(self) -> bool:
        """files/04 §5 ``screening.provenance.proxy_reported``."""
        return self.subject_role is SubjectRole.PROXY

    def reply(self, step_id: str) -> ScriptedAnswer:
        """The persona's reply to one step. Pure: same step, same answer."""
        origin = step_id.split("/clarify/")[0]
        if origin in self.clarify_steps:
            return ScriptedAnswer(transcript_tr=_CLARIFY_TRANSCRIPT, clarification_needed=True)
        scripted = self.answers.get(origin)
        if scripted is None:
            return ScriptedAnswer(transcript_tr=_SILENT_TRANSCRIPT)
        return scripted


_CLARIFY_TRANSCRIPT = "Sentetik anlaşılmayan yanıt."
_SILENT_TRANSCRIPT = "Sentetik yanıt yok."

_TELEGRAPHIC_MAX_WORDS = 2
"""What "telegraphic" means here. Two words, not a style: the property under
test is that the sentence is not the channel — the recorded extraction is —
so the bound state has to come out identical to the fluent persona's."""


def _answer(transcript: str, **updates: JsonValue) -> ScriptedAnswer:
    return ScriptedAnswer(transcript_tr=transcript, slot_updates=dict(updates))


# --- the baseline script ----------------------------------------------------
#
# Every value below is a synthetic code from the fixture pack's own valuesets.
# `sentetik_tetik` is the string the synthetic RED rule gates on and
# `sentetik_yakin_tetik` is its near miss — the one differing conjunct, and
# the case that starts firing if that gate is ever loosened.

_BASELINE: Mapping[str, ScriptedAnswer] = {
    "ziyaret.bildiren_rol": _answer(
        "Kendim için yanıtlıyorum.", **{"ziyaret.bildiren_rol": "kendim için"}
    ),
    "ziyaret.basvuru_nedeni": _answer(
        "Sentetik sakin neden.", **{"ziyaret.basvuru_nedeni": "sentetik_sakin"}
    ),
    "ziyaret.olay_tarihi": _answer("Bugün başladı.", **{"ziyaret.olay_tarihi": _TODAY}),
    "oyku.belirti_var": _answer("Evet, var.", **{"oyku.belirti_var": True}),
    "oyku.siddet_derece": _answer("Orta.", **{"oyku.siddet_derece": "sentetik_orta"}),
    "oyku.seyir": _answer("Aynı.", **{"oyku.seyir": "sentetik_ayni"}),
    "oyku.ek_bilgi": _answer("Sentetik ek bilgi.", **{"oyku.ek_bilgi": "sentetik ek bilgi metni"}),
    "ilac.ilac_kullanimi": _answer("Hayır.", **{"ilac.ilac_kullanimi": False}),
    "beklenti.beklenti_metni": _answer(
        "Sentetik beklenti.", **{"beklenti.beklenti_metni": "sentetik beklenti metni"}
    ),
    "tarama.tarama_onayi": _answer("Evet.", **{"tarama.tarama_onayi": True}),
    # Detaylı mod only. These steps exist solely in the visit_type pack, so in
    # Hızlı they are never asked and these entries are never reached — the
    # script is written once and the resolution decides what is put to it,
    # which is files/02 §2's "same engine, different protocol profile" from
    # the patient's side.
    "sistem_sorgusu.birinci_alan": _answer(
        "Hayır, değişmedi.", **{"sistem_sorgusu.birinci_alan": False}
    ),
    "sistem_sorgusu.ikinci_alan": _answer(
        "Hayır, o da aynı.", **{"sistem_sorgusu.ikinci_alan": False}
    ),
    "sistem_sorgusu.ucuncu_alan": _answer(
        "Aynı.", **{"sistem_sorgusu.ucuncu_alan": "sentetik_ayni"}
    ),
    "gecmis_delta.onceki_kayit_degisti": _answer(
        "Hayır, değişmedi.", **{"gecmis_delta.onceki_kayit_degisti": False}
    ),
    "gecmis_delta.yakin_oykusu_degisti": _answer(
        "Hayır.", **{"gecmis_delta.yakin_oykusu_degisti": False}
    ),
}


def _script(**overrides: ScriptedAnswer) -> dict[str, ScriptedAnswer]:
    merged = dict(_BASELINE)
    merged.update({key.replace("__", "."): value for key, value in overrides.items()})
    return merged


_TERSE_TRANSCRIPTS: Mapping[str, str] = {
    "ziyaret.bildiren_rol": "Kendim.",
    "ziyaret.basvuru_nedeni": "Sakinlik.",
    "ziyaret.olay_tarihi": "Bugün.",
    "oyku.belirti_var": "Var.",
    "oyku.siddet_derece": "Orta.",
    "oyku.seyir": "Aynı.",
    "oyku.ek_bilgi": "Yok.",
    "ilac.ilac_kullanimi": "Yok.",
    "beklenti.beklenti_metni": "Rahatlamak.",
    "tarama.tarama_onayi": "Olur.",
    "sistem_sorgusu.birinci_alan": "Yok.",
    "sistem_sorgusu.ikinci_alan": "Yok.",
    "sistem_sorgusu.ucuncu_alan": "Aynı.",
    "gecmis_delta.onceki_kayit_degisti": "Yok.",
    "gecmis_delta.yakin_oykusu_degisti": "Yok.",
}
"""One or two words per step. A missing entry raises rather than falling back
to the fluent sentence, so a slot added to the baseline cannot quietly leave
the telegraphic persona speaking in paragraphs."""


def _terse(script: dict[str, ScriptedAnswer]) -> dict[str, ScriptedAnswer]:
    """The same recorded extractions, said in one or two words.

    The transcript changes and ``slot_updates`` does not, which is the whole
    property: INT-083 put a data boundary between what the patient said and
    what the engine records, so the sentence must not be the channel.
    """
    return {
        step_id: answer.model_copy(update={"transcript_tr": _TERSE_TRANSCRIPTS[step_id]})
        for step_id, answer in script.items()
    }


def _overlay(*facts: tuple[str, JsonValue]) -> PatientOverlay:
    return PatientOverlay(
        patient_ref="sentetik-hasta",
        version=1,
        facts=tuple(
            LearnedFact(
                key=key,
                value=value,
                source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
                source_ref="sentetik-kaynak",
                confidence=1.0,
                confirmed_at=REFERENCE_TIME,
            )
            for key, value in facts
        ),
    )


_ALL: tuple[Persona, ...] = (
    Persona(
        persona_id="P01-self-adult-cooperative",
        label_tr="Kendi adına yanıtlayan, akıcı konuşan yetişkin",
        age_band=AgeBand.ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        answers=_script(),
    ),
    Persona(
        persona_id="P02-proxy-guardian-child",
        label_tr="Çocuğu adına yanıtlayan veli",
        age_band=AgeBand.CHILD,
        sex=Sex.MALE,
        literacy=Literacy.STANDARD,
        dialect="ankara",
        anxiety=Anxiety.RAISED,
        subject_role=SubjectRole.PROXY,
        answers=_script(
            ziyaret__bildiren_rol=_answer(
                "Çocuğum için yanıtlıyorum.", **{"ziyaret.bildiren_rol": "yakınım adına"}
            )
        ),
    ),
    Persona(
        persona_id="P03-proxy-carer-older-adult",
        label_tr="Bilişsel gerilemesi olan babası adına yanıtlayan kızı",
        age_band=AgeBand.OLDER_ADULT,
        sex=Sex.MALE,
        literacy=Literacy.STANDARD,
        dialect="izmir",
        anxiety=Anxiety.RAISED,
        subject_role=SubjectRole.PROXY,
        overlay_refs=("overlay.cognitive_impairment",),
        answers=_script(
            ziyaret__bildiren_rol=_answer(
                "Babam için yanıtlıyorum.", **{"ziyaret.bildiren_rol": "yakınım adına"}
            )
        ),
    ),
    Persona(
        persona_id="P04-assisted-self-older-adult",
        label_tr="Oğlunun telefonundan kendi sözleriyle yanıtlayan yaşlı hasta",
        age_band=AgeBand.OLDER_ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.LOW,
        dialect="karadeniz",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.ASSISTED_SELF,
        third_party_present=True,
        answers=_script(),
    ),
    Persona(
        persona_id="P05-low-literacy-chips-only",
        label_tr="Okumadan, yalnızca sesli seçeneklerle ilerleyen hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.MALE,
        literacy=Literacy.LOW,
        dialect="konya",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        overlay_refs=("overlay.low_literacy",),
        repeat_steps=frozenset({"ziyaret.basvuru_nedeni"}),
        answers=_script(),
    ),
    Persona(
        persona_id="P06-crisis-disclosure",
        label_tr="Tarama bölümünde kriz sinyali veren hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.HIGH,
        subject_role=SubjectRole.SELF,
        crisis_path=True,
        answers=_script(),
    ),
    Persona(
        persona_id="P07-oncology-overlay",
        label_tr="Onkoloji izlemindeki hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.MALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.RAISED,
        subject_role=SubjectRole.SELF,
        overlay_refs=("overlay.oncology_patient", "overlay.immunosuppressed"),
        answers=_script(
            ziyaret__basvuru_nedeni=_answer(
                "Sentetik tetikleyici neden.", **{"ziyaret.basvuru_nedeni": "sentetik_tetik"}
            )
        ),
    ),
    Persona(
        persona_id="P08-anxious-asks-for-a-diagnosis",
        label_tr="Tanı isteyen, kaygısı yüksek hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.HIGH,
        subject_role=SubjectRole.SELF,
        answers=_script(
            oyku__siddet_derece=_answer("Ağır.", **{"oyku.siddet_derece": "sentetik_agir"})
        ),
    ),
    Persona(
        persona_id="P09-code-switching",
        label_tr="Türkçe ile İngilizce terimleri karıştıran, sözü kesilen hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.MALE,
        literacy=Literacy.STANDARD,
        dialect="adana",
        anxiety=Anxiety.RAISED,
        subject_role=SubjectRole.SELF,
        code_switches=True,
        repeat_steps=frozenset({"ziyaret.basvuru_nedeni", "oyku.belirti_var"}),
        answers=_script(
            ziyaret__basvuru_nedeni=_answer(
                "Sentetik tetiğe yakın neden.",
                **{"ziyaret.basvuru_nedeni": "sentetik_yakin_tetik"},
            )
        ),
    ),
    Persona(
        persona_id="P10-declines-screening",
        label_tr="Tarama bölümünü yanıtlamak istemeyen hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        answers=_script(
            tarama__tarama_onayi=ScriptedAnswer(
                transcript_tr="Bu bölümü yanıtlamak istemiyorum.", declines=True
            )
        ),
    ),
    Persona(
        persona_id="P11-never-readable-on-one-step",
        label_tr="Bir soruda hiçbir denemede anlaşılamayan hasta",
        age_band=AgeBand.OLDER_ADULT,
        sex=Sex.MALE,
        literacy=Literacy.STANDARD,
        dialect="erzurum",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        clarify_steps=frozenset({"oyku.seyir"}),
        volunteers_late=True,
        answers=_script(
            # Two attempts failed and the engine gave up on `oyku.seyir`
            # (files/13 §11.1: "there is no third attempt"). Four steps later
            # the patient says it clearly, unprompted. There is no way back
            # in: an UNCLEAR slot has left the frontier, so the clear answer
            # lands on a step nothing will ask again and is dropped.
            beklenti__beklenti_metni=_answer(
                "Sentetik beklenti; seyir de aynıydı.",
                **{
                    "beklenti.beklenti_metni": "sentetik beklenti metni",
                    "oyku.seyir": "sentetik_ayni",
                },
            )
        ),
    ),
    Persona(
        persona_id="P12-frequent-attender-delta",
        label_tr="Sık başvuran, önceki kayıtları doğrulanmış hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        overlay_refs=("overlay.frequent_attender",),
        overlay=_overlay(("ilac.ilac_kullanimi", False)),
        answers=_script(),
    ),
    Persona(
        persona_id="P13-contradicts-a-prior-record",
        label_tr="Önceki kaydını doğrulamayan, değişikliği bildiren hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.MALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        overlay_refs=("overlay.frequent_attender",),
        overlay=_overlay(("ilac.ilac_kullanimi", False)),
        contradicts_prefill=frozenset({"ilac.ilac_kullanimi"}),
        answers=_script(
            ilac__ilac_kullanimi=_answer("Evet, değişti.", **{"ilac.ilac_kullanimi": True})
        ),
    ),
    Persona(
        persona_id="P14-answers-ahead-of-the-question",
        label_tr="Sorular sırayla kapanmadan konuşmaya devam eden hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.RAISED,
        subject_role=SubjectRole.SELF,
        hold_reconcile=frozenset({"oyku.belirti_var", "oyku.ek_bilgi"}),
        reconcile_order=("oyku.belirti_var", "oyku.ek_bilgi"),
        answers=_script(oyku__belirti_var=_answer("Hayır, yok.", **{"oyku.belirti_var": False})),
    ),
    # --- the four shapes a happy-path script never produces ------------------
    #
    # Each of these is a *reply that binds something other than the question
    # it was given*, which is the only way the under-binding rule of files/13
    # §9.6 can be exercised at all: nothing binds to a question that was not
    # asked, and the four personas below are the four ways a real patient
    # walks into that.
    Persona(
        persona_id="P15-answers-a-different-question",
        label_tr="Sorulan sorunun yerine başka bir soruyu yanıtlayan hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="bursa",
        anxiety=Anxiety.RAISED,
        subject_role=SubjectRole.SELF,
        topic_shifts=True,
        answers=_script(
            # Asked why they came; talks about the symptom instead. The reply
            # is fluent, it means something, and a recorded extraction reads
            # it correctly — as an answer to a question nobody put yet. The
            # asked step gets nothing and no clarification is requested,
            # because from the extraction's side nothing went wrong.
            ziyaret__basvuru_nedeni=_answer(
                "Sentetik belirtimden söz edeyim.", **{"oyku.belirti_var": True}
            )
        ),
    ),
    Persona(
        persona_id="P16-discloses-after-the-question-closed",
        label_tr="Kapanmış bir sorunun yanıtını sonradan söyleyen hasta",
        age_band=AgeBand.ADULT,
        sex=Sex.MALE,
        literacy=Literacy.STANDARD,
        dialect="istanbul",
        anxiety=Anxiety.RAISED,
        subject_role=SubjectRole.SELF,
        volunteers_late=True,
        contradicts_earlier_answer=True,
        answers=_script(
            # Three steps after `ziyaret.basvuru_nedeni` closed on the calm
            # code, the patient says the trigger code instead. IM-04 proves
            # the synthetic RED rule fires when that value binds on its own
            # turn; here it does not bind, and the session stays GREEN.
            oyku__seyir=_answer(
                "Aslında sentetik tetikleyici neden vardı.",
                **{
                    "oyku.seyir": "sentetik_ayni",
                    "ziyaret.basvuru_nedeni": "sentetik_tetik",
                },
            )
        ),
    ),
    Persona(
        persona_id="P17-contradicts-an-earlier-answer",
        label_tr="Daha önce verdiği yanıtı sonradan geri alan hasta",
        age_band=AgeBand.OLDER_ADULT,
        sex=Sex.FEMALE,
        literacy=Literacy.STANDARD,
        dialect="izmir",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        contradicts_earlier_answer=True,
        answers=_script(
            ilac__ilac_kullanimi=_answer(
                "Yok; aslında o sentetik belirti de yok.",
                **{"ilac.ilac_kullanimi": False, "oyku.belirti_var": False},
            )
        ),
    ),
    Persona(
        persona_id="P18-telegraphic-answers",
        label_tr="Tek kelimeyle yanıtlayan hasta",
        age_band=AgeBand.OLDER_ADULT,
        sex=Sex.MALE,
        literacy=Literacy.LOW,
        dialect="konya",
        anxiety=Anxiety.CALM,
        subject_role=SubjectRole.SELF,
        telegraphic=True,
        answers=_terse(_script()),
    ),
)

PERSONAS: Mapping[str, Persona] = {persona.persona_id: persona for persona in _ALL}
"""The scripted roster, by id. The acceptance asks for twelve or more."""
