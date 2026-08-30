"""The IM-01…IM-14 scenario roster (INT-082).

**What the blueprint supplies.** files/04 §6 is the source of record for the
patient simulator. Its "starter set (40)" names exactly three IM scenarios —
IM-02, IM-09 and IM-14 — and files/10 §9 cites IM-14 once more as the test
for the companion/guardian row. Those three are transcribed verbatim into
:attr:`Scenario.blueprint_line`. **There is no definition anywhere in
``files/`` for IM-01, IM-03…IM-08 or IM-10…IM-13**, so those eleven carry
``blueprint_line=None`` and a :attr:`Scenario.mechanism_ref` naming the
property they exercise instead. A reader can therefore tell a transcription
from a mechanism without leaving this file, and nothing here invents a
clinical presentation to fill a gap.

**Every scenario's clinical content is empty and gated.** files/04 §6 makes
a scenario's hidden truth *"symptoms, meds, red flags"* and its expected
output *"triage level"*. None of that exists in this repository: every
red-flag family is ``draft_needs_source`` (HB-C1, HB-C2, HB-C7), the
paediatric set does not exist (HB-C3), the crisis escalation policy does not
exist (HB-C8), C-SSRS is licence-blocked (HB-L2) and the turn budget is an
open clinical decision (HB-C5). So :meth:`Scenario.clinical_truth` **raises**
for all fourteen. That is HUMAN_BLOCKERS Rule 2 exactly: the mechanism is
built, the gate is wired, the gate fails closed, the content is left empty.
There is no ``dev_only`` flag and no placeholder rule set — a scenario that
wanted a clinical expectation would have to get it from a clinician.

Nothing in this module can name a triage level; the simulator's only route to
one is :func:`protocols.triage.evaluate_triage` (CLAUDE.md invariant 1).
"""

from __future__ import annotations

from collections.abc import Mapping

from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import RedLocation
from pydantic import Field

__all__ = ["SCENARIOS", "ClinicalContentBlocked", "ClinicalTruth", "Scenario"]

_BLUEPRINT_REF = "files/04 §6 (patient-simulator scenarios, starter set)"
_SECURITY_REF = "files/10 §9 (companion / guardian profiles row)"

#: Blockers that gate the clinical content of *every* scenario, because they
#: gate every red-flag rule in the repository.
_UNIVERSAL_BLOCKERS = ("HB-C1", "HB-C2", "HB-C7")


class ClinicalContentBlocked(RuntimeError):
    """A scenario was asked for clinical content no human has supplied.

    Raised rather than defaulted: HUMAN_BLOCKERS Rule 1 — *"never invent a
    value to unblock yourself"* — and Rule 2 — the gate fails closed.
    """


class ClinicalTruth(FrozenModel):
    """files/04 §6 "hidden truth (symptoms, meds, red flags)" and "expected
    outputs (must-ask coverage, triage level, key slots)".

    The type exists so the shape is fixed before the content arrives; no
    instance is constructed anywhere in this repository, and
    :meth:`Scenario.clinical_truth` is the only thing that would return one.
    """

    hidden_symptoms: tuple[str, ...] = Field(default=(), description="files/04 §6 hidden truth.")
    hidden_medications: tuple[str, ...] = Field(default=(), description="files/04 §6 hidden truth.")
    expected_rule_ids: tuple[str, ...] = Field(
        default=(),
        description="Rule ids the scenario expects to fire. Never a level — the "
        "level is the rules engine's to compute (CLAUDE.md invariant 1).",
    )
    expected_key_slots: tuple[str, ...] = Field(default=(), description="files/04 §6 key slots.")


class Scenario(FrozenModel):
    """One simulator scenario. Identity is transcribed; content is gated."""

    scenario_id: str = Field(pattern=r"^IM-\d{2}$", description="The blueprint's own id.")
    proves: str = Field(min_length=1, description="What running this scenario establishes.")
    persona_ids: tuple[str, ...] = Field(min_length=1, description="Personas it is run over.")
    blueprint_line: str | None = Field(
        default=None,
        description="The scenario's definition, transcribed verbatim from files/. "
        "None where files/ defines no such scenario.",
    )
    blueprint_ref: str | None = Field(
        default=None, description="Where the transcribed line comes from."
    )
    mechanism_ref: str = Field(
        default="",
        description="For a scenario files/ does not define: the blueprint section "
        "whose mechanism it exercises instead.",
    )
    location: RedLocation = Field(
        default=RedLocation.UNKNOWN,
        description="The RED location axis for this scenario, derived from the visit "
        "lifecycle by the caller and never guessed (files/02 §5.3 Axis 3). UNKNOWN is "
        "the honest default for a pre-visit session and resolves to the rule's own "
        "one question, not to a route.",
    )
    blockers: tuple[str, ...] = Field(
        min_length=1, description="HUMAN_BLOCKERS ids gating this scenario's content."
    )

    def clinical_truth(self) -> ClinicalTruth:
        """The scenario's hidden truth and expected outputs — always refused.

        Left empty on purpose: no clinician has authored it, and a plausible
        invented one reads as authoritative to every subsequent reader
        (HUMAN_BLOCKERS Rule 1).
        """
        raise ClinicalContentBlocked(
            f"{self.scenario_id}: files/04 §6 makes a scenario's hidden truth and "
            f"expected triage level clinical content, and none is authored — "
            f"blocked on {', '.join(self.blockers)}. Build the mechanism, leave the "
            "content empty (HUMAN_BLOCKERS Rule 2)."
        )


def _scenario(
    scenario_id: str,
    *,
    proves: str,
    persona_ids: tuple[str, ...],
    blueprint_line: str | None = None,
    blueprint_ref: str | None = None,
    mechanism_ref: str = "",
    extra_blockers: tuple[str, ...] = (),
) -> Scenario:
    return Scenario(
        scenario_id=scenario_id,
        proves=proves,
        persona_ids=persona_ids,
        blueprint_line=blueprint_line,
        blueprint_ref=blueprint_ref,
        mechanism_ref=mechanism_ref,
        blockers=_UNIVERSAL_BLOCKERS + extra_blockers,
    )


_ALL: tuple[Scenario, ...] = (
    _scenario(
        "IM-01",
        proves="A clean session traverses the whole resolved protocol and terminates "
        "with an empty frontier, in typed and in mock voice, with must_ask coverage "
        "computed and one question per turn.",
        persona_ids=("P01-self-adult-cooperative",),
        mechanism_ref="files/03 §5 (engine outputs); files/04 §6 forbidden behaviours",
        extra_blockers=("HB-C5",),
    ),
    _scenario(
        "IM-02",
        proves="A YELLOW is produced by a rule in packages/protocols/triage over the "
        "simulated answers, and by nothing else. The persona has no way to name one.",
        persona_ids=("P08-anxious-asks-for-a-diagnosis",),
        blueprint_line="IM-02 uncontrolled HTN with headache (YELLOW)",
        blueprint_ref=_BLUEPRINT_REF,
    ),
    _scenario(
        "IM-03",
        proves="The near-miss negative control: one differing conjunct away from the "
        "RED gate, the session must not go RED. This is the case that starts firing "
        "if the gate is ever loosened.",
        persona_ids=("P09-code-switching",),
        mechanism_ref="CLAUDE.md clinical content rules (near-miss negative control); "
        "files/04 §8.1",
    ),
    _scenario(
        "IM-04",
        proves="A RED arises from the rules engine on the simulated answers and "
        "resolves an action for all three locations; under ON_SITE the 112 affordance "
        "is absent rather than de-emphasised.",
        persona_ids=("P07-oncology-overlay",),
        mechanism_ref="CLAUDE.md invariants 1 and 21; files/02 §5.3",
    ),
    _scenario(
        "IM-05",
        proves="The ask-ahead race is closed by discarding: a step whose gate closes "
        "while it is pending is invalidated and its late answer is dropped, never "
        "stored as elicited data.",
        persona_ids=("P14-answers-ahead-of-the-question",),
        mechanism_ref="files/13 §11.3; files/03 §4.5 (ADR-011)",
    ),
    _scenario(
        "IM-06",
        proves="A must_ask slot that cannot be read after two clarifications goes "
        "UNCLEAR, the session still terminates, and the abandoned clinician-mandated "
        "question stays visible as an outstanding coverage obligation and a data gap.",
        persona_ids=("P11-never-readable-on-one-step",),
        mechanism_ref="files/13 §11.1, §9.2, §9.4; files/04 §2.3",
    ),
    _scenario(
        "IM-07",
        proves="Delta mode from a PatientOverlay confirms instead of re-asking, and "
        "never removes a step a clinician marked must_ask.",
        persona_ids=("P12-frequent-attender-delta",),
        mechanism_ref="files/09 §3; files/04 §2.3",
    ),
    _scenario(
        "IM-08",
        proves="Contradicting a pre-filled fact on the confirm turn re-opens the full "
        "ask rather than binding the contradiction to a confirm question.",
        persona_ids=("P13-contradicts-a-prior-record",),
        mechanism_ref="files/09 §3 ('full HPI only on change')",
    ),
    _scenario(
        "IM-09",
        proves="The screening/crisis path is text_only, so nothing sensitive is spoken; "
        "the instrument content and the escalation policy are blocked, and the "
        "simulator asks no instrument item because none compiles.",
        persona_ids=("P06-crisis-disclosure",),
        blueprint_line="IM-09 passive SI on PHQ-9 (YELLOW + safety script)",
        blueprint_ref=_BLUEPRINT_REF,
        extra_blockers=("HB-C8", "HB-L2"),
    ),
    _scenario(
        "IM-10",
        proves="The low-literacy path runs to completion without reading: every "
        "critical-path step is answerable from spoken ordinal choices, no free text is "
        "required, and the patient is never asked whether they can read.",
        persona_ids=("P05-low-literacy-chips-only", "P04-assisted-self-older-adult"),
        mechanism_ref="files/02 §3 (the low-literacy path); files/04 §2.3 overlay.low_literacy",
    ),
    _scenario(
        "IM-11",
        proves="A patient who declines an item is not punished by coverage — and pins "
        "that the IntakeEngine currently has no path to AnswerState.DECLINED at all.",
        persona_ids=("P10-declines-screening",),
        mechanism_ref="files/13 §9.3 (seven answer states); coverage COVERED_STATES",
    ),
    _scenario(
        "IM-12",
        proves="An overlay reference adds or tightens and never removes a must_ask "
        "obligation; the oncology overlay pack itself does not exist and is not faked.",
        persona_ids=("P07-oncology-overlay",),
        mechanism_ref="files/04 §2.3 (overlays never remove must_ask questions)",
    ),
    _scenario(
        "IM-13",
        proves="Interruption and code-switching noise: a repeat request re-asks the "
        "same authored sentence verbatim, never a reworded second attempt.",
        persona_ids=("P09-code-switching",),
        mechanism_ref="files/03 §4.2 (request_repeat_or_clarify); files/04 §6 Noise-01",
    ),
    _scenario(
        "IM-14",
        proves="A companion answering for the patient is asked who they are answering "
        "for before anything else, and the proxy attribution reaches the result.",
        persona_ids=(
            "P02-proxy-guardian-child",
            "P03-proxy-carer-older-adult",
            "P04-assisted-self-older-adult",
        ),
        blueprint_line="IM-14 companion reporting for father with dementia",
        blueprint_ref=f"{_BLUEPRINT_REF}; {_SECURITY_REF}",
        extra_blockers=("HB-C3", "HB-C9"),
    ),
)

SCENARIOS: Mapping[str, Scenario] = {scenario.scenario_id: scenario for scenario in _ALL}
"""IM-01 … IM-14, in order."""
