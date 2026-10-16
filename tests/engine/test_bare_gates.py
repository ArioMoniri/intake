"""INT-355 — a gated question is asked once its gate opens, however it is spelled.

The defect, as a verifier reproduced it with a real :class:`IntakeEngine`: the
engine keys every step ``<section>.<slot>`` and read a gate atom as written,
so a gate spelled with a bare slot name (``base.intake``'s ``subject_role !=
'kendim'`` and ``pregnancy_status != 'hayir'``, and every specialty/cluster
candidate's ``<slot> == true``) looked up a key no step carries, evaluated
Unknown for the whole session, and never opened. files/13 §9.5 opens a gate
only on TRUE, so the dependent question was silently dropped. With the gate
spelled ``sorular.<slot>`` it appeared.

The fix resolves a bare name to the one slot of that name across the resolved
chain, and refuses a plan whose gate names two slots or none — a gate that
cannot resolve can never open (:mod:`protocols.gates`). Triage is untouched:
the rules engine reads its own section-qualified references, and nothing here
can produce a level (CLAUDE.md invariant 1).

Synthetic ids and strings throughout (files/04 §7), except the section that
drives the authored ``base.intake`` gates, which reads the committed pack.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from intake_voice_runtime.clinical_agent import IntakeEngine, PlanError, build_plan
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.loader import load_pack
from protocols.triage.expr import Truth
from protocols.types import Delivery, SlotType

NOW = datetime.datetime(2026, 9, 26, 9, 0, tzinfo=datetime.UTC)
HASH = "0" * 64
BASE_INTAKE = (
    Path(__file__).resolve().parents[2] / "packages" / "protocols" / "base" / "intake.yaml"
)


def _slot(**fields: object) -> Slot:
    return Slot.model_validate(fields)


def _resolved(section_id: str, key: str, slot: Slot) -> ResolvedSlot:
    return ResolvedSlot(
        section_id=section_id,
        key=key,
        fhir_link_id=f"{section_id}.{key}",
        slot=slot,
        delivery=Delivery.VOICE,
    )


def _section(section_id: str, *slots: tuple[str, Slot]) -> ResolvedSection:
    return ResolvedSection(
        id=section_id,
        delivery=Delivery.VOICE,
        allow_paraphrase=False,
        slots=tuple(_resolved(section_id, key, slot) for key, slot in slots),
    )


def _protocol(*sections: ResolvedSection) -> ResolvedProtocol:
    return ResolvedProtocol(
        pack_id="specialty.sentetik_kapi",
        version="1.0.0",
        chain=("base.sentetik_kapi", "specialty.sentetik_kapi"),
        sections=sections,
        resolved_protocol_hash=HASH,
    )


def _belirti() -> Slot:
    return _slot(
        type=SlotType.BOOLEAN,
        required=True,
        must_ask=True,
        ask_tr={"tr": "Sentetik belirtiniz var mı?"},
        follow_up_tr={"tr": "Sentetik belirti takip sorusu."},
    )


def _gated(*, ask_if: str | None = None, skip_if: str | None = None) -> Slot:
    return _slot(
        type=SlotType.STRING,
        ask_if=ask_if,
        skip_if=skip_if,
        ask_tr={"tr": "Sentetik bağımlı soru."},
    )


def _offered(engine: IntakeEngine) -> set[str]:
    return {step.step_id for step in engine.frontier()}


def _answer(engine: IntakeEngine, step_id: str, value: JsonValue) -> None:
    engine.mark_asked(step_id)
    engine.apply_extraction(step_id, {step_id: value})


# ---------------------------------------------------------------------------
# The reproduction: a specialty-style gate on a slot of the same section.
# ---------------------------------------------------------------------------

SPELLINGS = (
    "belirti_var == true",  # the specialty/cluster candidate spelling
    "belirti_var",  # the bare boolean atom (files/03 §6 ``symptoms.fever``)
    "sorular.belirti_var == true",  # the qualified spelling — the control
)


def _sorular(gate: str) -> IntakeEngine:
    protocol = _protocol(
        _section("sorular", ("belirti_var", _belirti()), ("sure", _gated(ask_if=gate)))
    )
    return IntakeEngine(protocol=protocol, reference_time=NOW)


@pytest.mark.parametrize("gate", SPELLINGS)
def test_the_gated_question_is_offered_once_the_gate_slot_is_true(gate: str) -> None:
    engine = _sorular(gate)
    _answer(engine, "sorular.belirti_var", True)
    assert "sorular.sure" in _offered(engine)
    head = engine.next_step()
    assert head is not None
    assert head.step_id == "sorular.sure"


@pytest.mark.parametrize("gate", SPELLINGS)
def test_the_gated_question_stays_closed_when_the_gate_slot_is_false(gate: str) -> None:
    engine = _sorular(gate)
    _answer(engine, "sorular.belirti_var", False)
    assert "sorular.sure" not in _offered(engine)
    assert engine.next_step() is None


@pytest.mark.parametrize("gate", SPELLINGS)
def test_the_gated_question_stays_closed_while_the_gate_slot_is_unanswered(gate: str) -> None:
    """files/13 §9.5: UNKNOWN does not open a gate — a not-yet-known slot is
    never read as a positive either."""
    engine = _sorular(gate)
    assert _offered(engine) == {"sorular.belirti_var"}
    engine.mark_asked("sorular.belirti_var")
    assert "sorular.sure" not in _offered(engine)


def test_a_bare_gate_reads_a_slot_another_section_owns() -> None:
    """A specialty pack gating on a slot its base pack declares: the bare name
    resolves across the whole resolved chain, not inside its own section."""
    protocol = _protocol(
        _section("ziyaret", ("belirti_var", _belirti())),
        _section("sorular", ("sure", _gated(ask_if="belirti_var == true"))),
    )
    engine = IntakeEngine(protocol=protocol, reference_time=NOW)
    _answer(engine, "ziyaret.belirti_var", True)
    assert "sorular.sure" in _offered(engine)


def test_a_bare_skip_if_retires_its_step() -> None:
    protocol = _protocol(
        _section(
            "sorular",
            ("belirti_var", _belirti()),
            ("ek_not", _gated(skip_if="belirti_var == false")),
        )
    )
    engine = IntakeEngine(protocol=protocol, reference_time=NOW)
    assert "sorular.ek_not" in _offered(engine)  # UNKNOWN never retires
    _answer(engine, "sorular.belirti_var", False)
    assert "sorular.ek_not" not in _offered(engine)


def test_a_bare_skip_if_closing_behind_an_asked_step_invalidates_it() -> None:
    """files/13 §11.3, the ask-ahead race, through a bare name: the step is
    asked ahead while its skip_if is Unknown, then the gate slot lands and
    retires it — the pending answer is discarded, never stored."""
    protocol = _protocol(
        _section(
            "sorular",
            ("belirti_var", _belirti()),
            ("ek_not", _gated(skip_if="!belirti_var")),
        )
    )
    engine = IntakeEngine(protocol=protocol, reference_time=NOW)
    engine.mark_asked("sorular.belirti_var")
    engine.mark_asked("sorular.ek_not")
    engine.apply_extraction("sorular.belirti_var", {"sorular.belirti_var": False})
    assert engine.snapshot.invalidated == ("sorular.ek_not",)
    engine.apply_extraction("sorular.ek_not", {"sorular.ek_not": "sentetik"})
    assert engine.value_of("sorular.ek_not") is None
    assert engine.state_of("sorular.ek_not") is AnswerState.NOT_ASKED


def test_must_ask_coverage_reads_a_bare_gate_as_closed_on_false() -> None:
    """files/13 §9.4 obligations are must-ask steps whose gate is TRUE or
    UNKNOWN; a closed bare gate discharges the obligation instead of leaving
    it open forever."""
    gated_must_ask = _slot(
        type=SlotType.STRING,
        must_ask=True,
        ask_if="belirti_var",
        ask_tr={"tr": "Sentetik zorunlu bağımlı soru."},
    )
    protocol = _protocol(
        _section("sorular", ("belirti_var", _belirti()), ("zorunlu", gated_must_ask))
    )
    engine = IntakeEngine(protocol=protocol, reference_time=NOW)
    assert build_plan(protocol).gate_truth("sorular.zorunlu", lambda _ref: None) is Truth.UNKNOWN
    assert "sorular.zorunlu" in engine.must_ask_coverage().obliged
    _answer(engine, "sorular.belirti_var", False)
    coverage = engine.must_ask_coverage()
    assert coverage.obliged == ("sorular.belirti_var",)
    assert coverage.outstanding == ()


# ---------------------------------------------------------------------------
# Refused at build: a gate that cannot name exactly one slot can never open.
# ---------------------------------------------------------------------------


def test_a_bare_gate_two_sections_hold_is_refused_at_build() -> None:
    protocol = _protocol(
        _section("ziyaret", ("belirti_var", _belirti())),
        _section(
            "sorular",
            ("belirti_var", _belirti()),
            ("sure", _gated(ask_if="belirti_var == true")),
        ),
    )
    with pytest.raises(PlanError, match="ambiguous") as excinfo:
        build_plan(protocol)
    assert "sorular.belirti_var" in str(excinfo.value)
    assert "ziyaret.belirti_var" in str(excinfo.value)


def test_the_same_plan_builds_once_the_gate_is_qualified() -> None:
    """Near-miss negative control: same duplicated key, qualified gate."""
    protocol = _protocol(
        _section("ziyaret", ("belirti_var", _belirti())),
        _section(
            "sorular",
            ("belirti_var", _belirti()),
            ("sure", _gated(ask_if="sorular.belirti_var == true")),
        ),
    )
    engine = IntakeEngine(protocol=protocol, reference_time=NOW)
    _answer(engine, "sorular.belirti_var", True)
    assert "sorular.sure" in _offered(engine)


@pytest.mark.parametrize(
    ("field", "gate"),
    [
        ("ask_if", "ates_var == true"),
        ("ask_if", "yok.belirti_var == true"),
        ("skip_if", "ates_var"),
    ],
)
def test_a_gate_naming_no_slot_is_refused_at_build(field: str, gate: str) -> None:
    slot = _gated(ask_if=gate) if field == "ask_if" else _gated(skip_if=gate)
    protocol = _protocol(_section("sorular", ("belirti_var", _belirti()), ("sure", slot)))
    with pytest.raises(PlanError, match="names no slot"):
        build_plan(protocol)


# ---------------------------------------------------------------------------
# The authored base.intake gates, driven through a real engine.
# ---------------------------------------------------------------------------


def _base_intake() -> ResolvedProtocol:
    """``base.intake`` projected section by section into the resolved shape.

    The compiler refuses this pack by design — it is L0 and every red-flag
    family is an unsourced draft (HUMAN_BLOCKERS HB-C1) — so the gate mechanics
    are driven over its authored sections directly rather than by promoting or
    stripping anything. Slots with no ``ask_tr`` (the red-flag probes and the
    instrument items) are left out: a step is spoken verbatim from ``ask_tr``
    and cannot exist without one (CLAUDE.md invariant 10), and neither gated
    slot nor either gate slot is among them.
    """
    pack = load_pack(BASE_INTAKE)
    sections = []
    for section_id, section in pack.sections.items():
        slots = tuple(
            ResolvedSlot(
                section_id=section_id,
                key=key,
                fhir_link_id=f"{section_id}.{key}",
                slot=slot,
                delivery=slot.delivery or section.delivery or Delivery.VOICE,
            )
            for key, slot in section.slots.items()
            if slot.ask_tr is not None
        )
        sections.append(
            ResolvedSection(
                id=section_id,
                delivery=section.delivery or Delivery.VOICE,
                allow_paraphrase=False,
                slots=slots,
            )
        )
    return ResolvedProtocol(
        pack_id=pack.id,
        version=pack.version,
        chain=(pack.id,),
        sections=tuple(sections),
        resolved_protocol_hash=HASH,
    )


def _base_engine() -> IntakeEngine:
    return IntakeEngine(protocol=_base_intake(), reference_time=NOW)


def _choices(step_id: str) -> tuple[str, ...]:
    """The authored ``tr`` choices of a base.intake code slot — the only values
    the slot carries, so the only values these tests answer with (INT-441).
    The tests before INT-441 answered ``"yakinim"``, ``"kendim"`` and
    ``"hayir"``, which no patient can give, and so passed over the defect."""
    section_id, key = step_id.split(".")
    choices = load_pack(BASE_INTAKE).sections[section_id].slots[key].choices_tr
    assert choices is not None
    return choices["tr"]


class TestBaseIntakeProxyReported:
    """``identity_check.proxy_reported`` — ``ask_if: "subject_role == 'yakınım adına'"``
    (INT-441). It used to compare against ``'kendim'``, which no answer equals, so
    a patient answering for themselves was asked whether they speak for someone
    else."""

    def test_the_answers_driven_here_are_the_authored_choices(self) -> None:
        assert _choices("identity_check.subject_role") == ("kendim için", "yakınım adına")

    def test_closed_while_subject_role_is_unanswered(self) -> None:
        assert "identity_check.proxy_reported" not in _offered(_base_engine())

    def test_opens_when_the_session_is_on_someone_elses_behalf(self) -> None:
        engine = _base_engine()
        _answer(engine, "identity_check.subject_role", "yakınım adına")
        assert "identity_check.proxy_reported" in _offered(engine)

    def test_stays_closed_when_the_patient_speaks_for_themselves(self) -> None:
        engine = _base_engine()
        _answer(engine, "identity_check.subject_role", "kendim için")
        assert "identity_check.proxy_reported" not in _offered(engine)

    def test_stays_closed_while_the_role_is_unclear(self) -> None:
        """files/13 §9.5: an UNCLEAR answer reads Unknown and opens no gate."""
        engine = _base_engine()
        engine.mark_asked("identity_check.subject_role")
        engine.apply_extraction("identity_check.subject_role", {}, clarification_needed=True)
        assert "identity_check.proxy_reported" not in _offered(engine)


class TestBaseIntakeLmpDate:
    """``pmh_fh_sh.lmp_date`` — asked once ``pregnancy_status`` is answered, with any
    authored answer (INT-441 keeps the behaviour the unreachable ``'hayir'``
    literal produced; whether "hayır" may skip the LMP is HB-C6's to decide)."""

    def test_closed_while_pregnancy_status_is_unanswered(self) -> None:
        assert "pmh_fh_sh.lmp_date" not in _offered(_base_engine())

    @pytest.mark.parametrize("status", ["evet", "hayır", "emin değilim"])
    def test_every_authored_answer_opens_it(self, status: str) -> None:
        assert status in _choices("pmh_fh_sh.pregnancy_status")
        engine = _base_engine()
        _answer(engine, "pmh_fh_sh.pregnancy_status", status)
        assert "pmh_fh_sh.lmp_date" in _offered(engine)

    def test_the_cases_above_are_every_authored_answer(self) -> None:
        assert _choices("pmh_fh_sh.pregnancy_status") == ("evet", "hayır", "emin değilim")
