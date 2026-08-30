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
"""

from __future__ import annotations

import enum
from collections.abc import Mapping

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.overlay import LearnedFact, LearnedFactSource, PatientOverlay
from protocol import REFERENCE_TIME
from pydantic import Field

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
        "Kendim için yanıtlıyorum.", **{"ziyaret.bildiren_rol": "kendim"}
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
}


def _script(**overrides: ScriptedAnswer) -> dict[str, ScriptedAnswer]:
    merged = dict(_BASELINE)
    merged.update({key.replace("__", "."): value for key, value in overrides.items()})
    return merged


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
                "Çocuğum için yanıtlıyorum.", **{"ziyaret.bildiren_rol": "yakinim"}
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
                "Babam için yanıtlıyorum.", **{"ziyaret.bildiren_rol": "yakinim"}
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
        answers=_script(),
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
)

PERSONAS: Mapping[str, Persona] = {persona.persona_id: persona for persona in _ALL}
"""The scripted roster, by id. The acceptance asks for twelve or more."""
