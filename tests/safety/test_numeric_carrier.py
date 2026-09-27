"""INT-303 — one numeric carrier from extraction to a red-flag comparison.

files/13 §9.5 states the contract in one line: *"no floats anywhere,
``Decimal`` with declared scale and exact comparison, because floats are how
two machines disagree about the same session"*. CLAUDE.md invariant 22 states
the boundary rule: numbers never cross a representation boundary unguarded.

Three subsystems carried three different numeric types across that seam:
``intake_voice_runtime.extraction`` builds a :class:`~decimal.Decimal` (its
JSON reader passes ``parse_float=Decimal`` on purpose), the protocol compiler
emits ``Decimal | None`` for a numeric slot, and the triage carrier
(``clinical_schemas.common.JsonScalar``) admitted no ``Decimal`` at all — so
``canonical_scalar`` fell through to ``return None``, whose own docstring
says *"None reads Unknown"*. A red-flag rule gating on such a value would not
fire, and nothing would report it: the worst failure this system has, because
it is silent (CLAUDE.md invariant 1).

Every rule, slot and Turkish string here is SYNTHETIC (SENTETİK TEST VERİSİ);
zero clinical content (invariant 17).

Two near-miss negative controls, because a naive fix passes the positives:

1. ``miss/float-yuvarlama`` — a value strictly BELOW the threshold whose
   float image is exactly ON it. Any fix that keeps a float in the path
   reports a RED the rules never authorised.
2. ``miss/sayisal-metin`` — the same magnitude written as a string. It must
   stay a string and read Unknown, never be coerced into the comparison
   (files/03 §4.9.6: a separator cannot be resolved without an expected
   magnitude, so a numeric string is refused rather than parsed).
"""

from __future__ import annotations

import ast as python_ast
import inspect
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import protocols.triage as triage_pkg
import pytest
from clinical_schemas import common
from clinical_schemas.common import TAGGED_DECIMAL_PREFIX, JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from intake_voice_runtime.extraction import parse_extraction
from intake_voice_runtime.typed.affordance import SlotFacts
from intake_voice_runtime.typed.render import numeric_rail
from protocols import EK4Level
from protocols.dsl import Slot
from protocols.triage import SlotAnswer, TriageContext, canonical_scalar, evaluate_triage
from protocols.triage import context as triage_context
from protocols.types import SlotType
from pydantic import TypeAdapter
from synthetic_triage import ANCHOR, ctx, make_rule, present

REPO = Path(__file__).resolve().parents[2]

#: One JsonValue, dumped to INTAKE's own wire and validated straight back —
#: the crossing ADR-030 is about, in one call.
_WIRE = TypeAdapter(JsonValue)


def _through_the_wire(value: object) -> object:
    return _WIRE.validate_json(_WIRE.dump_json(value))


def _string_literals(source: str) -> list[str]:
    """Every string literal in a module except its docstrings.

    A docstring is prose about the code; a literal is the code. Only the
    second can smuggle a second copy of the wire tag into a running path.
    """
    tree = python_ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in python_ast.walk(tree)
        if isinstance(
            node,
            (python_ast.Module, python_ast.ClassDef)
            + (python_ast.FunctionDef, python_ast.AsyncFunctionDef),
        )
        and node.body
        and isinstance(node.body[0], python_ast.Expr)
        and isinstance(node.body[0].value, python_ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in python_ast.walk(tree)
        if isinstance(node, python_ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


# The synthetic fever-shaped gate: one numeric threshold, both directions.
FEVER = "sentetik.olcum_c"
FEVER_RULE = make_rule("rf.sentetik_olcum", EK4Level.KIRMIZI_K2, f"{FEVER} >= 38")


def _fire(value: object) -> TriageLevel:
    evaluation = evaluate_triage((FEVER_RULE,), ctx(**{FEVER: present(value)}), RedLocation.REMOTE)
    return evaluation.result.level


class TestTheCarrierAdmitsTheTypeExtractionProduces:
    def test_a_decimal_canonicalises_to_itself_rather_than_to_unknown(self) -> None:
        assert canonical_scalar(Decimal("38.5")) == Decimal("38.5")

    def test_the_declared_scale_survives_canonicalisation(self) -> None:
        canonical = canonical_scalar(Decimal("38.50"))
        assert isinstance(canonical, Decimal)
        assert canonical.as_tuple().exponent == -2

    def test_a_slot_answer_keeps_the_decimal_it_was_given(self) -> None:
        """The schema boundary must not downcast. Pydantic resolves a union by
        the value's own type, so a carrier that omits ``Decimal`` does not
        reject the value — it silently rewrites it as a float."""
        answer = SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(Decimal("38.50"),))
        carried = answer.values[0]
        assert isinstance(carried, Decimal)
        assert not isinstance(carried, float)
        assert carried.as_tuple().exponent == -2

    def test_a_decimal_slot_value_fires_the_rule_that_gates_on_it(self) -> None:
        assert _fire(Decimal("38.5")) is TriageLevel.RED


class TestUnknownAndUncomparableAreNotTheSameOutcome:
    """The defect was silent because one ``return None`` served both *"this
    slot has no answer"* and *"I cannot compare this type"*. The first is a
    reading the grammar defines; the second is a programming error."""

    @pytest.mark.parametrize("value", [None, [], ["a"], {}, {"k": 1}])
    def test_null_and_collections_still_read_unknown(self, value: object) -> None:
        assert canonical_scalar(value) is None

    def test_the_refusal_is_part_of_the_published_triage_api(self) -> None:
        """A caller cannot catch what the package does not export."""
        assert "UncomparableSlotValue" in triage_pkg.__all__

    def test_a_value_outside_the_carrier_raises_instead_of_reading_unknown(self) -> None:
        # Attribute access rather than a module-level import, so this module
        # collects and every test in it fails on behaviour rather than on a
        # missing name (the red run in docs/evidence/INT-303.md).
        with pytest.raises(triage_context.UncomparableSlotValue):
            canonical_scalar(date(2026, 8, 28))

    def test_the_refusal_names_the_type_and_never_the_value(self) -> None:
        """invariant 6: an exception that interpolated the value would put a
        patient's answer in a log."""
        with pytest.raises(triage_context.UncomparableSlotValue) as raised:
            canonical_scalar(datetime(2026, 8, 28, 10, 0, tzinfo=UTC))
        message = str(raised.value)
        assert "datetime" in message
        assert "2026" not in message


class TestTheNearMissNegativeControls:
    def test_a_value_below_the_threshold_whose_float_image_is_on_it_does_not_fire(
        self,
    ) -> None:
        """miss/float-yuvarlama. ``Decimal("37.999999999999999999") < 38`` is
        exact; ``float(...)`` of it is ``38.0``. A fix that routes the value
        through a float turns a GREEN into a RED the rules never authorised —
        which is why this control sits on the firing side of the boundary."""
        below = Decimal("37.999999999999999999")
        assert below < Decimal(38)
        assert float(below) == 38.0
        assert _fire(below) is TriageLevel.GREEN

    def test_the_same_magnitude_written_as_a_string_is_not_coerced(self) -> None:
        """miss/sayisal-metin. A cross-type comparison is Unknown, never False
        and never True (files/12 §1.1), so the rule does not fire — and the
        string is carried as a string rather than parsed into the gate."""
        assert canonical_scalar("38.5") == "38.5"
        assert not isinstance(canonical_scalar("38.5"), Decimal)
        assert _fire("38.5") is TriageLevel.GREEN

    def test_a_boolean_is_still_a_boolean_and_not_the_number_one(self) -> None:
        """``True == 1`` in Python; the carrier must keep them apart or a
        boolean answer would satisfy a numeric threshold of 1."""
        assert canonical_scalar(True) is True
        assert canonical_scalar(1) == Decimal(1)
        rule = make_rule("rf.sentetik_bir", EK4Level.KIRMIZI_K2, "sentetik.sayac >= 1")
        assert (
            evaluate_triage(
                (rule,), ctx(**{"sentetik.sayac": present(True)}), RedLocation.REMOTE
            ).result.level
            is TriageLevel.GREEN
        )


class TestTheExtractionSeamHandsOverADecimal:
    """``ExtractionResult.as_engine_call()`` is the one place the runtime's
    numeric type met the engine's. It bridged by casting to ``float``, which
    is the crossing files/13 §9.5 forbids and invariant 22 calls unguarded."""

    SLOTS = {
        "hpi.olcum_c": Slot(
            type=SlotType.QUANTITY, unit="c", ask_tr={"tr": "Sentetik ölçüm sorusu?"}
        )
    }

    def _parsed(self, literal: str) -> object:
        raw = (
            f'{{"slots": {{"hpi.olcum_c": {{"value": {literal}, "unit": "c",'
            ' "confidence": 0.9}}, "candidate_flags": [], "clarification_needed": false}'
        )
        result = parse_extraction(raw=raw, slots=self.SLOTS, valuesets={}, step_id="hpi.olcum_c")
        return result.as_engine_call()["slot_updates"]["hpi.olcum_c"]

    def test_a_fractional_quantity_crosses_as_a_decimal_not_a_float(self) -> None:
        carried = self._parsed("38.5")
        assert isinstance(carried, Decimal)
        assert not isinstance(carried, float)
        assert carried == Decimal("38.5")

    def test_the_scale_the_patient_stated_is_not_dropped_on_the_way(self) -> None:
        carried = self._parsed("38.50")
        assert isinstance(carried, Decimal)
        assert carried.as_tuple().exponent == -2

    def test_the_value_the_seam_hands_over_is_the_value_the_rule_reads(self) -> None:
        carried = self._parsed("38.5")
        context = TriageContext(
            reference_time=datetime(2026, 8, 28, 10, 0, tzinfo=UTC),
            answers={
                ANCHOR: present("2026-08-28"),
                FEVER: SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(carried,)),
            },
        )
        assert evaluate_triage((FEVER_RULE,), context, RedLocation.REMOTE).result.level is (
            TriageLevel.RED
        )


# ------------------------------------------------- INT-309 · the wire (ADR-030)


class TestTheWireTagNeverReachesAHuman:
    """ADR-030 makes a ``Decimal`` self-describing on INTAKE's own wire by
    reserving a one-character prefix. That is total and bijective only while
    every reader goes through the codec: if one path does not, a patient or a
    clinician reads the literal ``~d38.50``, which is invariant 22's failure
    mode wearing a different mask and worse than the trailing zero the tag
    exists to protect. These are the gate, in the shape of the gate that
    stops a numeral reaching TTS.
    """

    def test_one_module_owns_the_reserved_prefix(self) -> None:
        """The prefix is reserved only while a single module spells it. A
        second hand-rolled tag is a second, drifting encoding, and the two
        would disagree the first time one of them changed.

        The sweep reads string *literals* rather than raw file text, because
        ``:class:`~decimal.Decimal``` is a Sphinx cross-reference in three
        docstrings and matching it would make the gate cry wolf until
        somebody deleted it.
        """
        owner = Path(inspect.getsourcefile(common) or "")
        offenders: list[str] = []
        for path in sorted(
            [*REPO.glob("packages/*/src/**/*.py"), *REPO.glob("services/*/src/**/*.py")]
        ):
            if path == owner:
                continue
            if any(
                TAGGED_DECIMAL_PREFIX in text for text in _string_literals(path.read_text("utf-8"))
            ):
                offenders.append(str(path.relative_to(REPO)))
        assert offenders == []

    def test_the_typed_numeric_rail_shows_the_digits_and_not_the_tag(self) -> None:
        """files/03 §4.6 invariant 30: in typed, the rail is the only channel
        the number has. A tagged string reaching it would either print the
        tag or — worse, because it is silent — be skipped as a non-magnitude
        and the number would vanish from the patient's screen."""
        facts = {
            FEVER: SlotFacts(
                step_id=FEVER,
                slot_type=SlotType.QUANTITY,
                critical_path=True,
                unit="°C",
            )
        }
        rail = numeric_rail({FEVER: Decimal("38.50")}, facts, locale="tr")
        assert TAGGED_DECIMAL_PREFIX not in rail[FEVER]
        # INT-386: the rail is written for a Turkish reader, who takes a full
        # stop as grouping. The digits and the printed precision are the same;
        # only the decimal point is the reader's.
        assert "38,50" in rail[FEVER]
        assert "38.50" not in rail[FEVER]

        crossed = _through_the_wire(Decimal("38.50"))
        assert numeric_rail({FEVER: crossed}, facts, locale="tr") == rail

    def test_the_clinician_evidence_line_shows_the_digits_and_not_the_tag(self) -> None:
        """``triage.rules[].evidence`` is read by a clinician (files/04 §5)."""
        crossed = _through_the_wire(Decimal("38.50"))
        evaluation = evaluate_triage(
            (FEVER_RULE,), ctx(**{FEVER: present(crossed)}), RedLocation.REMOTE
        )
        assert evaluation.result.level is TriageLevel.RED
        evidence = evaluation.result.rules[0].evidence
        assert TAGGED_DECIMAL_PREFIX not in evidence
        assert "38.50" in evidence

    def test_a_patient_answer_beginning_with_the_prefix_is_carried_not_refused(
        self,
    ) -> None:
        """Near-miss control on the escape rule: the reserved prefix must
        never turn a patient's own words into a validation error, and must
        never turn them into a number."""
        for spoken in ("~d38.50", "~", "~~", "~dokuz"):
            carried = _through_the_wire(spoken)
            assert carried == spoken
            assert not isinstance(carried, Decimal)
