"""INT-080 — the `when` condition grammar and its three-valued evaluation.

Grammar sources, each cited in the implementation: files/03 §6 (`&&`, `||`,
`>=`, `==`, dotted slot atoms), files/03 §8 (CEL-like sandboxed expressions),
files/protocols/base.life_threat.yaml exemplars (`!`, `in {...}`, string and
boolean literals, parentheses), files/13 §9.5 (Decimal not float; Kleene
three-valued logic), files/12 §1.1 (fire only on TRUE), files/12 §2.4
(tense/tense_anchor), files/12 §7.3 (contested slots evaluate on the union
of values and take max acuity). A construct none of those define is refused
at load, never guessed.

All fixtures are SYNTHETIC (SENTETİK TEST VERİSİ) — zero clinical content.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation
from protocols import EK4Level
from protocols.triage import (
    SlotAnswer,
    TriageContext,
    Truth,
    WhenGrammarError,
    canonical_scalar,
    evaluate_triage,
    parse_when,
    rule_truth,
    when_truth,
)
from pydantic import ValidationError
from synthetic_triage import ANCHOR, REF_TIME, answer, ctx, make_rule, present


def truth(text: str, **slots: SlotAnswer) -> Truth:
    return when_truth(text, ctx(**slots))


# ---------------------------------------------------------------------------
# Accepted constructs — each is used by files/03 §6 or the life-threat
# exemplars, and each parses.
# ---------------------------------------------------------------------------


class TestAcceptedGrammar:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("isaret == true", Truth.TRUE),
            ("isaret != false", Truth.TRUE),
            ("isaret", Truth.TRUE),
            ("!isaret", Truth.FALSE),
            ("sayi >= 38", Truth.TRUE),
            ("sayi > 38", Truth.FALSE),
            ("sayi <= 38", Truth.TRUE),
            ("sayi < 38", Truth.FALSE),
            ("38 <= sayi", Truth.TRUE),
            ("sayi == 38.0", Truth.TRUE),
            ("metin == 'kirmizi'", Truth.TRUE),
            ('metin == "kirmizi"', Truth.TRUE),
            ("metin in {'kirmizi', 'sari'}", Truth.TRUE),
            ("metin in {'yesil'}", Truth.FALSE),
            ("isaret && sayi >= 38", Truth.TRUE),
            ("!isaret || metin == 'kirmizi'", Truth.TRUE),
            ("(isaret || !isaret) && metin == 'kirmizi'", Truth.TRUE),
            ("nokta.li_ad == true", Truth.TRUE),
        ],
    )
    def test_construct(self, text: str, expected: Truth) -> None:
        assert (
            truth(
                text,
                isaret=present(True),
                sayi=present(38),
                metin=present("kirmizi"),
                **{"nokta.li_ad": present(True)},
            )
            is expected
        )

    def test_decimal_not_float(self) -> None:
        # files/13 §9.5: Decimal with exact comparison, no floats anywhere.
        assert truth("oran == 0.3", oran=present(0.3)) is Truth.TRUE
        assert truth("oran == 0.30", oran=present(0.3)) is Truth.TRUE
        assert truth("oran == 0.1", oran=present(0.3)) is Truth.FALSE


# ---------------------------------------------------------------------------
# Refused constructs — nothing the blueprint does not define evaluates.
# ---------------------------------------------------------------------------


class TestRefusedGrammar:
    @pytest.mark.parametrize(
        "text",
        [
            "f(isaret)",  # function calls are not in the red-flag grammar
            "sayi + 1 == 2",  # arithmetic is not defined
            "isaret & isaret",  # single & is not &&
            "isaret | isaret",  # single | is not ||
            "isaret = true",  # assignment is not comparison
            "Isaret == true",  # identifiers are lowercase slot references
            "@isaret",  # unknown character
            "-1 == sayi",  # signed literals are not defined
            "metin in {}",  # an empty set is not defined
            "metin in {sayi}",  # a set may contain only literals
            "metin in 'kirmizi'",  # in takes a set literal
            "true",  # a bare literal is not a predicate
            "isaret == true extra",  # trailing tokens
            "isaret ==",  # missing operand
            "(isaret == true",  # unbalanced parenthesis
            "(isaret == true}",  # mismatched closer
            "isaret == (",  # a parenthesis is not an operand
            "metin == 'acik",  # unterminated string
            "",  # an empty predicate is not a rule
            "isaret == true && ",  # dangling operator
            "in {'a'}",  # in without a left operand
        ],
    )
    def test_refused_at_load(self, text: str) -> None:
        with pytest.raises(WhenGrammarError):
            parse_when(text)


# ---------------------------------------------------------------------------
# Kleene three-valued logic (files/12 §1.1; files/13 §9.5): not_asked reads
# Unknown, F && U = F, T || U = T, gates open only on TRUE.
# ---------------------------------------------------------------------------


class TestKleene:
    def test_missing_slot_is_unknown(self) -> None:
        assert truth("bilinmeyen == true") is Truth.UNKNOWN

    @pytest.mark.parametrize(
        "state",
        [
            AnswerState.NOT_ASKED,
            AnswerState.ASKED_PENDING,
            AnswerState.UNCLEAR,
            AnswerState.DECLINED,
        ],
    )
    def test_valueless_states_are_unknown(self, state: AnswerState) -> None:
        assert truth("isaret == true", isaret=answer(state)) is Truth.UNKNOWN

    def test_asked_absent_supplies_its_value(self) -> None:
        absent = answer(AnswerState.ASKED_ABSENT, False)
        assert truth("isaret == true", isaret=absent) is Truth.FALSE
        assert truth("!isaret", isaret=absent) is Truth.TRUE

    def test_false_and_unknown_is_false(self) -> None:
        assert truth("isaret && bilinmeyen", isaret=present(False)) is Truth.FALSE

    def test_true_or_unknown_is_true(self) -> None:
        assert truth("isaret || bilinmeyen", isaret=present(True)) is Truth.TRUE

    def test_true_and_unknown_is_unknown(self) -> None:
        assert truth("isaret && bilinmeyen", isaret=present(True)) is Truth.UNKNOWN

    def test_false_or_unknown_is_unknown(self) -> None:
        assert truth("isaret || bilinmeyen", isaret=present(False)) is Truth.UNKNOWN

    def test_not_unknown_is_unknown(self) -> None:
        assert truth("!bilinmeyen") is Truth.UNKNOWN

    def test_null_value_is_unknown(self) -> None:
        assert truth("isaret == true", isaret=present(None)) is Truth.UNKNOWN

    @pytest.mark.parametrize(
        ("text", "slot"),
        [
            ("metin >= 3", present("kirmizi")),  # ordering is numeric-only
            ("metin >= 'a'", present("kirmizi")),  # ditto, both sides
            ("isaret == 3", present(True)),  # bool vs number
            ("metin == true", present("kirmizi")),  # string vs bool
            ("sayi", present(7)),  # bare atom must be boolean-valued
            ("dizi == true", present([1, 2])),  # collections do not compare
        ],
    )
    def test_type_mismatch_is_unknown_not_false(self, text: str, slot: SlotAnswer) -> None:
        name = text.split(" ")[0].lstrip("!")
        assert truth(text, **{name: slot}) is Truth.UNKNOWN

    def test_in_folds_equality_under_kleene(self) -> None:
        # one element matches → TRUE even though another mismatches in type
        assert truth("metin in {3, 'kirmizi'}", metin=present("kirmizi")) is Truth.TRUE
        # no match, one type mismatch → UNKNOWN, never FALSE
        assert truth("metin in {3, 'yesil'}", metin=present("kirmizi")) is Truth.UNKNOWN


# ---------------------------------------------------------------------------
# Contested slots (files/12 §7.3): triage evaluates on the union of head and
# superseded values and takes max acuity — per-world, exact.
# ---------------------------------------------------------------------------


class TestContested:
    def test_any_contested_value_can_fire(self) -> None:
        contested = answer(AnswerState.CONTESTED, False, True)
        assert truth("isaret == true", isaret=contested) is Truth.TRUE

    def test_worlds_are_evaluated_exactly_not_per_atom(self) -> None:
        # {3, 20}: neither value satisfies both conjuncts — per-atom OR would
        # wrongly report TRUE; per-world evaluation reports FALSE.
        contested = answer(AnswerState.CONTESTED, 3, 20)
        assert truth("sayi >= 5 && sayi <= 10", sayi=contested) is Truth.FALSE
        assert (
            truth("sayi >= 5 && sayi <= 10", sayi=answer(AnswerState.CONTESTED, 3, 7)) is Truth.TRUE
        )

    def test_contested_escalates_triage(self) -> None:
        rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K2, "isaret == true")
        contested = answer(AnswerState.CONTESTED, False, True)
        evaluation = evaluate_triage((rule,), ctx(isaret=contested), RedLocation.REMOTE)
        assert evaluation.ek4 is EK4Level.SARI_K2

    def test_slot_answer_shape_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            SlotAnswer(state=AnswerState.CONTESTED, values=(True,))  # union needs >= 2
        with pytest.raises(ValidationError):
            SlotAnswer(state=AnswerState.ASKED_PRESENT, values=())  # value-bearing
        with pytest.raises(ValidationError):
            SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(True, False))
        with pytest.raises(ValidationError):
            SlotAnswer(state=AnswerState.NOT_ASKED, values=(True,))  # valueless


# ---------------------------------------------------------------------------
# Tense and tense_anchor (files/12 §2.4): the temporal guard conjoins the
# `when` predicate, returns Unknown on an undated anchor, and a rule can
# never fire on an undated symptom.
# ---------------------------------------------------------------------------


def _tense_truth(tense: str, anchor: SlotAnswer | None) -> Truth:
    answers: dict[str, SlotAnswer] = {"isaret": present(True)}
    if anchor is not None:
        answers[ANCHOR] = anchor
    context = TriageContext(reference_time=REF_TIME, answers=answers)
    rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K2, "isaret == true", tense=tense)
    return rule_truth(rule, context)


class TestTense:
    @pytest.mark.parametrize(
        ("tense", "anchor_iso", "expected"),
        [
            ("today", "2026-08-28", Truth.TRUE),
            ("today", "2026-08-27", Truth.FALSE),
            ("now", "2026-08-28", Truth.TRUE),  # engine window == today; see context.py
            ("now", "2026-08-27", Truth.FALSE),
            ("within_7d", "2026-08-21", Truth.TRUE),
            ("within_7d", "2026-08-20", Truth.FALSE),
            ("within_30d", "2026-07-29", Truth.TRUE),
            ("within_30d", "2026-07-28", Truth.FALSE),
            ("ever", "1990-01-01", Truth.TRUE),
        ],
    )
    def test_calendar_windows(self, tense: str, anchor_iso: str, expected: Truth) -> None:
        assert _tense_truth(tense, present(anchor_iso)) is expected

    def test_an_undated_symptom_cannot_fire(self) -> None:
        assert _tense_truth("ever", None) is Truth.UNKNOWN
        assert _tense_truth("ever", answer(AnswerState.NOT_ASKED)) is Truth.UNKNOWN

    def test_a_future_anchor_is_unknown_never_true(self) -> None:
        assert _tense_truth("ever", present("2026-08-29")) is Truth.UNKNOWN

    def test_aware_datetime_anchor_converts_to_the_reference_day(self) -> None:
        # 23:30 UTC on the 27th is already the 28th in UTC+3 — but the
        # reference clock here is UTC, so it stays the 27th.
        assert _tense_truth("today", present("2026-08-27T23:30:00+00:00")) is Truth.FALSE
        assert _tense_truth("today", present("2026-08-28T00:30:00+03:00")) is Truth.FALSE
        assert _tense_truth("today", present("2026-08-28T10:00:00+03:00")) is Truth.TRUE

    def test_a_naive_datetime_anchor_is_unknown(self) -> None:
        assert _tense_truth("today", present("2026-08-28T10:00:00")) is Truth.UNKNOWN

    def test_an_unparseable_anchor_is_unknown(self) -> None:
        assert _tense_truth("today", present("dun aksam")) is Truth.UNKNOWN
        assert _tense_truth("today", present(42)) is Truth.UNKNOWN

    def test_a_contested_anchor_takes_the_escalating_value(self) -> None:
        contested = answer(AnswerState.CONTESTED, "2026-08-01", "2026-08-28")
        assert _tense_truth("today", contested) is Truth.TRUE

    def test_when_false_beats_tense_true(self) -> None:
        context = TriageContext(
            reference_time=REF_TIME,
            answers={"isaret": present(False), ANCHOR: present("2026-08-28")},
        )
        rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K2, "isaret == true")
        assert rule_truth(rule, context) is Truth.FALSE


# ---------------------------------------------------------------------------
# The context is a pure value: reference time comes from the session fold
# (files/13 §9.2), never a wall clock.
# ---------------------------------------------------------------------------


class TestContextShape:
    def test_reference_time_must_be_timezone_aware(self) -> None:
        with pytest.raises(ValidationError):
            TriageContext(
                reference_time=datetime(2026, 8, 28, 10, 0, 0),  # noqa: DTZ001
                answers={},
            )

    def test_evaluation_is_a_pure_function_of_its_inputs(self) -> None:
        context = TriageContext(
            reference_time=datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC),
            answers={"isaret": present(True), ANCHOR: present("2026-08-28")},
        )
        rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K2, "isaret == true")
        first = evaluate_triage((rule,), context, RedLocation.REMOTE)
        second = evaluate_triage((rule,), context, RedLocation.REMOTE)
        assert first == second


# ---------------------------------------------------------------------------
# INT-267 — the Decimal carrier. `canonical_scalar` declares
# `bool | Decimal | str | None` and its docstring says "Numbers become
# Decimal (files/13 §9.5: exact comparison, no floats)" — so a Decimal is
# the function's OWN output type, and feeding one back in must not lose it.
#
# It matters because INT-083's extraction emits decimal and quantity slot
# values as exact `Decimal` (a float would breach CLAUDE.md invariant 22),
# so every such value reaching a gate today reads Unknown — and Unknown is
# not a safe default merely because it is not FALSE.
# ---------------------------------------------------------------------------


class TestDecimalCarrier:
    def test_the_round_trip_through_the_declared_return_type_is_lossless(self) -> None:
        # The identity case: canonical_scalar's own output, fed back in.
        converted = canonical_scalar(38.5)
        assert converted == Decimal("38.5")
        assert canonical_scalar(converted) == converted

    def test_a_decimal_is_accepted_and_returned_unchanged(self) -> None:
        # Unchanged means the same object: no re-conversion, not through
        # `str` and not through `quantize`.
        value = Decimal("38.5")
        assert canonical_scalar(value) is value

    def test_the_declared_scale_is_carried_never_normalised(self) -> None:
        # THE SCALE DECISION, asserted rather than left to fall out of the
        # implementation. files/13 §9.5 types a decimal slot as "Decimal
        # with declared scale and exact comparison": the scale belongs to
        # the slot that was authored, not to this function, so 38.50 stays
        # 38.50. Comparison in expr.py is `Decimal == / < / >=`, which is by
        # numeric value and ignores trailing zeros, so carrying the scale
        # can never change a verdict — it only keeps `str()` and any
        # textual render (evidence, notes, TTS orthography) honest.
        carried = canonical_scalar(Decimal("38.50"))
        assert isinstance(carried, Decimal)
        assert str(carried) == "38.50"
        assert carried.as_tuple().exponent == -2

    def test_trailing_zeros_never_change_a_verdict(self) -> None:
        assert canonical_scalar(Decimal("38.50")) == canonical_scalar(Decimal("38.5"))
        assert truth("olcum == 38.5", olcum=present(Decimal("38.50"))) is Truth.TRUE
        assert truth("olcum >= 38.5", olcum=present(Decimal("38.50"))) is Truth.TRUE
        assert truth("olcum > 38.5", olcum=present(Decimal("38.50"))) is Truth.FALSE

    def test_the_answer_carrier_preserves_the_decimal_it_was_given(self) -> None:
        # `tuple[JsonValue, ...]` admits float and would coerce a Decimal
        # into one — the exact unguarded representation boundary invariant
        # 22 names, and a silent loss of the authored scale.
        carried = present(Decimal("38.50")).values[0]
        assert isinstance(carried, Decimal)
        assert not isinstance(carried, float)
        assert str(carried) == "38.50"

    @pytest.mark.parametrize("value", [38, 38.5, True, False, "38.5", "kirmizi", None])
    def test_admitting_a_decimal_reroutes_no_other_carrier(self, value: object) -> None:
        # Widening the carrier must not pull an existing type through
        # Decimal on the way in: "38.5" is still a string and 38 is still
        # an int, so nothing that compares today starts comparing
        # differently tomorrow.
        assert type(present(value).values[0]) is type(value)

    @pytest.mark.parametrize(
        ("carrier", "over", "at", "under"),
        [
            ("decimal", Decimal("38.6"), Decimal("38.5"), Decimal("38.4")),
            ("int", 39, None, 38),
            ("float", 38.6, 38.5, 38.4),
        ],
    )
    def test_every_carrier_reads_the_same_threshold(
        self, carrier: str, over: object, at: object, under: object
    ) -> None:
        # The near miss is the point: just under the threshold must be
        # FALSE — not Unknown, which is what a gate that cannot decide
        # returns, and not TRUE.
        assert truth("olcum >= 38.5", olcum=present(over)) is Truth.TRUE
        assert truth("olcum >= 38.5", olcum=present(under)) is Truth.FALSE
        if at is not None:
            assert truth("olcum >= 38.5", olcum=present(at)) is Truth.TRUE

    @pytest.mark.parametrize(
        "value",
        [
            Decimal("NaN"),
            Decimal("sNaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
            float("nan"),
            float("inf"),
            float("-inf"),
        ],
    )
    def test_a_non_finite_number_reads_unknown(self, value: object) -> None:
        # An ordered comparison against a NaN raises InvalidOperation and an
        # infinity is not a magnitude any slot declares, so a non-finite
        # number is a data defect: it reads Unknown (review), never FALSE
        # (false reassurance). A signalling NaN reaches canonical_scalar
        # only through an unvalidated carrier — SlotAnswer's own validation
        # refuses it — which is exactly why the guard lives in the function.
        assert canonical_scalar(value) is None

    @pytest.mark.parametrize(
        "value",
        [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), float("nan"), float("inf")],
    )
    def test_a_non_finite_answer_never_raises_on_the_triage_path(self, value: object) -> None:
        assert truth("olcum >= 38.5", olcum=present(value)) is Truth.UNKNOWN
        assert truth("olcum == 38.5", olcum=present(value)) is Truth.UNKNOWN
