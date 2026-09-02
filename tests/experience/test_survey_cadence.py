"""INT-242 — NPS scheduling and clinician pulse survey cadence.

Acceptance (docs/backlog/issues.yaml, verbatim): *"monthly NPS prompt honoring
quiet hours; quarterly pulse; opt-outs respected"*. legal: ``6563-IYS``;
sec_row: ``experience``.

What this file pins, in the order the harm arrives:

1. **The only two cadence figures in the code are the two the blueprint
   states.** ``nps → monthly`` and ``clinician_pulse → quarterly`` come from
   the acceptance line above and from files/08 §4 group F (``nps.monthly``,
   ``clinician.pulse`` "quarterly 1-5"). Nothing else is a number: no sampling
   rate, no cool-off window, no first-prompt delay, no send hour. Those are
   absent from every file in the tree, so the scheduler carries them as unset
   and **refuses** rather than picking a plausible one (HUMAN_BLOCKERS rule 1).

2. **A satisfaction survey invitation is a commercial electronic message, so
   the İYS gate stops it.** 6563 m.2/1(c) covers content sent *ticari
   amaçlarla*; the Yönetmelik (RG 29417) m.6 exempts messages about the
   change, use or maintenance of a service the recipient asked for, and
   notifications of subscription, collection, debt, information update,
   purchase and delivery "or similar" — and closes with *"bu iletilerde
   herhangi bir mal veya hizmet özendirilemez veya bunların tanıtımı
   yapılamaz"*. An NPS invitation is none of those: the patient's care is
   complete without it, it tells them nothing about their own transaction, and
   the question it asks is literally whether they would recommend us. So it is
   commercial, it needs an İYS-registered consent, no İYS registry exists
   (INT-141), and therefore **it cannot be sent at all today**. That is the
   outcome under test — not a limitation to be worked around.

3. **The transactional dispatcher cannot be used as a way round that.**
   ``ReminderKind`` has no survey member and ``TEMPLATES`` has no survey
   template, so there is no argument that carries an invitation through
   ``ReminderDispatcher.send`` and no copy for it to render even if there
   were.

4. **Opt-out and quiet hours are honoured through INT-141's own decision, not
   a second copy of it.** A survey scheduler that re-derived "is it quiet
   now?" would drift from the dispatcher on the first edit; the grid test here
   forces the two to agree on every combination.

5. **Nothing states an NPS figure** (invariant 20) and nothing logs or labels a
   recipient (invariant 6).
"""

from __future__ import annotations

import ast
import inspect
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from intake_platform.flags import SAFETY_FLAG_DEFAULTS, InMemoryProvider
from intake_platform.notifications import (
    SCHEDULING_OFFSET,
    TEMPLATES,
    Channel,
    DispatchStatus,
    IysConsentRecord,
    IysRegistryUnconfigured,
    Locale,
    MessageClass,
    NotificationPreferences,
    QuietWindow,
    ReminderDispatcher,
    ReminderKind,
    UnconfiguredIysRegistry,
    UnconfiguredTransport,
)
from intake_platform.notifications.preferences import QuietVerdict, quiet_verdict
from intake_platform.surveys import (
    CADENCE,
    MONTHS_PER_PERIOD,
    SATISFACTION_PROMPTS_FLAG,
    SURVEY_INVITATION_TOTAL,
    SURVEY_MESSAGE_CLASS,
    DueStatus,
    InvitationChannel,
    InvitationStatus,
    Period,
    SurveyInvitationPlanner,
    SurveyKind,
    SurveyPolicy,
    SurveyRecipient,
    advance,
    due,
    requires_iys_consent,
)

SURVEYS_SRC = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "intake_platform"
    / "src"
    / "intake_platform"
    / "surveys"
)

#: A policy with the missing values supplied. Only a test may do this: the
#: shipped :class:`SurveyPolicy` has them unset and the planner refuses.
SUPPLIED = SurveyPolicy(first_prompt_after=timedelta(days=7))

MIDDAY = datetime(2026, 3, 10, 12, 0, tzinfo=SCHEDULING_OFFSET)

#: A baseline quiet window the *test* supplies. INT-141 ships none, and this
#: file must not become the place one gets chosen for the product.
BASELINE = QuietWindow.parse("22:00", "08:00")


def _package_trees() -> Iterator[ast.Module]:
    for path in sorted(SURVEYS_SRC.rglob("*.py")):
        yield ast.parse(path.read_text(encoding="utf-8"))


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """Every constant that is a docstring, by identity — a value scan must not
    trip over the module prose that explains why the values are absent."""
    holders: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                holders.add(id(body[0].value))
    return holders


def _numbers_in(tree: ast.Module) -> set[float]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    }


def _strings_in(tree: ast.Module) -> set[str]:
    docstrings = _docstring_nodes(tree)
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def _numeric_literals() -> set[float]:
    return {value for tree in _package_trees() for value in _numbers_in(tree)}


def _string_literals() -> set[str]:
    return {value for tree in _package_trees() for value in _strings_in(tree)}


#: Names for the scheduling values no file in the tree states. None of them is
#: a knob here: an unset knob that always refuses would be theatre, and a set
#: one would be invented.
UNSOURCED_KNOBS = ("sample_rate", "sampling_rate", "cool_off", "cooloff", "cooldown")


def _package_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(SURVEYS_SRC.rglob("*.py")))


def _declared_unsourced_knobs(source: str) -> set[str]:
    folded = source.casefold()
    # the knob as any part of a name being assigned or annotated, so
    # COOL_OFF_DAYS and default_sample_rate are caught as readily as the bare
    # word — the control below is what proves that.
    return {
        knob
        for knob in UNSOURCED_KNOBS
        if re.search(rf"[a-z_]*{re.escape(knob)}[a-z_]*\s*[:=]", folded) is not None
    }


#: A near-miss control for all three value scans: a module that reads exactly
#: like something a well-meaning later edit would add.
_INVENTED = '''"""A plausible module. Every number here was chosen by an engineer."""

SAMPLE_RATE = 0.1
COOL_OFF_DAYS = 90
PREFERRED_SEND_TIME = "09:00"
'''


def _recipient(
    *, eligible_since: datetime = MIDDAY, last_prompted_at: datetime | None = None
) -> SurveyRecipient:
    return SurveyRecipient(
        recipient_ref="rcp-0f3b",
        eligible_since=eligible_since,
        last_prompted_at=last_prompted_at,
    )


def _open() -> NotificationPreferences:
    """A recipient who has not opted out and has set no window of her own."""
    return NotificationPreferences(opted_out=False, quiet=None)


def _planner(
    *,
    prompts_enabled: bool = True,
    baseline: QuietWindow | None = BASELINE,
    policy: SurveyPolicy = SUPPLIED,
) -> SurveyInvitationPlanner:
    return SurveyInvitationPlanner(
        iys=UnconfiguredIysRegistry(),
        flags=InMemoryProvider({SATISFACTION_PROMPTS_FLAG: prompts_enabled}),
        baseline_quiet=baseline,
        policy=policy,
    )


# --- 1. the cadence, and only the cadence -----------------------------------------


class TestCadenceIsSourced:
    def test_nps_is_monthly_and_the_pulse_is_quarterly(self) -> None:
        assert CADENCE[SurveyKind.NPS] is Period.MONTHLY
        assert CADENCE[SurveyKind.CLINICIAN_PULSE] is Period.QUARTERLY

    def test_the_cadence_table_is_total_over_the_survey_kinds(self) -> None:
        assert set(CADENCE) == set(SurveyKind)

    def test_a_period_is_a_calendar_span_of_one_or_three_months(self) -> None:
        """The only two numbers in this package, and both are stated."""
        assert MONTHS_PER_PERIOD == {Period.MONTHLY: 1, Period.QUARTERLY: 3}


class TestCalendarPeriods:
    def test_one_month_on_is_the_same_day_next_month(self) -> None:
        start = datetime(2026, 3, 10, 9, 30, tzinfo=SCHEDULING_OFFSET)
        assert advance(start, Period.MONTHLY) == datetime(
            2026, 4, 10, 9, 30, tzinfo=SCHEDULING_OFFSET
        )

    def test_a_month_end_clamps_rather_than_overflowing(self) -> None:
        """31 Jan + 1 month is 28 Feb, not 3 March. Thirty days would be a
        different, invented, cadence."""
        start = datetime(2026, 1, 31, 9, 0, tzinfo=SCHEDULING_OFFSET)
        assert advance(start, Period.MONTHLY) == datetime(
            2026, 2, 28, 9, 0, tzinfo=SCHEDULING_OFFSET
        )

    def test_a_leap_february_takes_the_29th(self) -> None:
        start = datetime(2028, 1, 31, 9, 0, tzinfo=SCHEDULING_OFFSET)
        assert advance(start, Period.MONTHLY).day == 29

    def test_a_quarter_is_three_calendar_months_and_crosses_the_year(self) -> None:
        start = datetime(2026, 11, 30, 9, 0, tzinfo=SCHEDULING_OFFSET)
        assert advance(start, Period.QUARTERLY) == datetime(
            2027, 2, 28, 9, 0, tzinfo=SCHEDULING_OFFSET
        )

    def test_the_calendar_is_read_on_the_turkish_clock_not_utc(self) -> None:
        """23:30 UTC on 31 March is already 1 April in Türkiye, so the next
        month is May — the same +03 posture INT-141 takes with quiet hours."""
        start = datetime(2026, 3, 31, 23, 30, tzinfo=UTC)
        assert advance(start, Period.MONTHLY).month == 5

    def test_a_naive_instant_is_refused_rather_than_assumed_utc(self) -> None:
        with pytest.raises(ValueError, match="tz-aware"):
            advance(datetime(2026, 3, 10, 12, 0), Period.MONTHLY)  # noqa: DTZ001


class TestDueDates:
    def test_a_recipient_prompted_a_month_ago_is_due_again(self) -> None:
        recipient = _recipient(
            last_prompted_at=datetime(2026, 2, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
        )
        decision = due(SurveyKind.NPS, recipient, SUPPLIED, at=MIDDAY)
        assert decision.status is DueStatus.DUE
        assert decision.due_at == datetime(2026, 3, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)

    def test_a_recipient_prompted_this_month_is_not_due(self) -> None:
        recipient = _recipient(
            last_prompted_at=datetime(2026, 3, 1, 9, 0, tzinfo=SCHEDULING_OFFSET)
        )
        assert due(SurveyKind.NPS, recipient, SUPPLIED, at=MIDDAY).status is DueStatus.NOT_YET_DUE

    def test_the_pulse_waits_a_quarter_where_nps_waits_a_month(self) -> None:
        last = datetime(2026, 2, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
        recipient = _recipient(last_prompted_at=last)
        assert due(SurveyKind.NPS, recipient, SUPPLIED, at=MIDDAY).status is DueStatus.DUE
        pulse = due(SurveyKind.CLINICIAN_PULSE, recipient, SUPPLIED, at=MIDDAY)
        assert pulse.status is DueStatus.NOT_YET_DUE
        assert pulse.due_at == datetime(2026, 5, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)

    def test_the_due_instant_is_the_boundary_itself(self) -> None:
        """Half-open the other way round from a quiet window: the moment the
        period elapses, the recipient is due."""
        last = datetime(2026, 2, 10, 12, 0, tzinfo=SCHEDULING_OFFSET)
        recipient = _recipient(last_prompted_at=last)
        assert due(SurveyKind.NPS, recipient, SUPPLIED, at=MIDDAY).status is DueStatus.DUE
        one_second_early = MIDDAY - timedelta(seconds=1)
        assert (
            due(SurveyKind.NPS, recipient, SUPPLIED, at=one_second_early).status
            is DueStatus.NOT_YET_DUE
        )


# --- 2. the values that are not invented ------------------------------------------


class TestValuesNotInvented:
    def test_the_shipped_policy_has_no_first_prompt_delay(self) -> None:
        assert SurveyPolicy().first_prompt_after is None

    def test_a_never_prompted_recipient_refuses_rather_than_guessing_a_start(self) -> None:
        decision = due(SurveyKind.NPS, _recipient(), SurveyPolicy(), at=MIDDAY)
        assert decision.status is DueStatus.REFUSED_FIRST_PROMPT_DELAY_UNSET
        assert decision.due_at is None

    def test_with_the_value_supplied_the_first_prompt_falls_after_eligibility(self) -> None:
        """The mechanism is complete — it is the value that is missing. Given
        one, the first invitation lands where the value says and nowhere
        chosen by this code."""
        recipient = _recipient(eligible_since=datetime(2026, 3, 1, 9, 0, tzinfo=SCHEDULING_OFFSET))
        decision = due(SurveyKind.NPS, recipient, SUPPLIED, at=MIDDAY)
        assert decision.due_at == datetime(2026, 3, 8, 9, 0, tzinfo=SCHEDULING_OFFSET)
        assert decision.status is DueStatus.DUE

    def test_a_naive_eligibility_instant_is_refused(self) -> None:
        recipient = _recipient(eligible_since=datetime(2026, 3, 1, 9, 0))  # noqa: DTZ001
        with pytest.raises(ValueError, match="tz-aware"):
            due(SurveyKind.NPS, recipient, SUPPLIED, at=MIDDAY)

    def test_an_already_prompted_recipient_needs_no_invented_value(self) -> None:
        """The period alone answers "when next" once there is a last prompt —
        the unset value is only the *first* one, which is the honest scope of
        the gap."""
        recipient = _recipient(
            last_prompted_at=datetime(2026, 2, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
        )
        assert due(SurveyKind.NPS, recipient, SurveyPolicy(), at=MIDDAY).status is DueStatus.DUE

    def test_the_planner_refuses_a_never_prompted_recipient_on_the_shipped_policy(self) -> None:
        outcome = _planner(policy=SurveyPolicy()).plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.REFUSED_SCHEDULE_UNSET

    def test_the_package_declares_no_sampling_rate_or_cool_off(self) -> None:
        """A sampling rate and a cross-survey cool-off are exactly the values
        the blueprint does not state. Neither is a knob here — an unset knob
        that always refuses would be theatre, and a set one would be invented.
        This scan is what keeps a later edit from quietly adding one."""
        assert _declared_unsourced_knobs(_package_source()) == set()

    def test_the_only_numbers_in_the_package_are_the_two_stated_periods(self) -> None:
        """The tightest statement available, and the one that actually holds:
        one month, three months, and the twelve the calendar arithmetic needs.
        A sampling fraction, a cool-off of 90 days, a 30-day "month" or an
        08:00 send hour would each have to appear here as a literal, and each
        would fail. Docstrings are excluded — this is about values, and the
        prose is checked separately."""
        assert _numeric_literals() == {1, 3, 12}

    def test_no_hour_of_day_is_chosen_for_the_send(self) -> None:
        """Quiet hours come from INT-141 and its baseline is unset. Nothing
        here may name a send hour as a value instead (the module prose may of
        course discuss one, which is why this reads constants, not text)."""
        for value in _string_literals():
            assert re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is None, (
                f"{value!r} is a time-of-day literal; no file in the tree names a send hour"
            )

    def test_the_two_scans_catch_a_plausible_invented_module(self) -> None:
        """Near-miss negative control. Without this, both scans above are just
        assertions that the package happens to be small."""
        tree = ast.parse(_INVENTED)
        assert _numbers_in(tree) - {1, 3, 12} == {0.1, 90}
        assert any(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in _strings_in(tree))
        assert _declared_unsourced_knobs(_INVENTED) == {"sample_rate", "cool_off"}


# --- 3. the transactional-vs-commercial determination -----------------------------


class TestClassification:
    def test_a_survey_invitation_carried_as_a_message_is_commercial(self) -> None:
        assert SURVEY_MESSAGE_CLASS is MessageClass.COMMERCIAL

    def test_an_electronic_message_needs_an_iys_consent(self) -> None:
        assert requires_iys_consent(InvitationChannel.ELECTRONIC_MESSAGE) is True

    def test_an_in_product_prompt_is_not_an_electronic_message_at_all(self) -> None:
        """Nothing is sent, so 6563 does not engage — the survey is shown to
        someone already signed in. The safety flag still governs it."""
        assert requires_iys_consent(InvitationChannel.IN_PRODUCT) is False

    def test_the_classification_is_total_over_the_channels(self) -> None:
        for channel in InvitationChannel:
            assert isinstance(requires_iys_consent(channel), bool)


class TestIysGateIsNotBypassed:
    def test_the_shipped_planner_blocks_a_patient_nps_invitation(self) -> None:
        outcome = _planner().plan(
            SurveyKind.NPS,
            channel=InvitationChannel.ELECTRONIC_MESSAGE,
            recipient=_recipient(
                last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.BLOCKED_IYS_CONSENT_ABSENT

    def test_opening_the_safety_flag_alone_does_not_unblock_it(self) -> None:
        """Two independent locks, and the legal one outranks the operational
        one: a tenant who turns satisfaction prompts on still sends nothing."""
        outcome = _planner(prompts_enabled=True).plan(
            SurveyKind.NPS,
            channel=InvitationChannel.ELECTRONIC_MESSAGE,
            recipient=_recipient(
                last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.BLOCKED_IYS_CONSENT_ABSENT

    def test_the_only_registry_in_the_tree_still_refuses(self) -> None:
        with pytest.raises(IysRegistryUnconfigured):
            UnconfiguredIysRegistry().lookup("rcp-0f3b")

    def test_a_registry_that_produces_a_record_clears_the_gate(self) -> None:
        """The near-miss: the gate must be a real check on a real record, not
        a constant False that happens to look like one. No such registry
        exists outside this file, and INT-141's AST scan is what keeps it that
        way."""
        planner = SurveyInvitationPlanner(
            iys=_FixtureIysRegistry(),
            flags=InMemoryProvider({SATISFACTION_PROMPTS_FLAG: True}),
            baseline_quiet=BASELINE,
            policy=SUPPLIED,
        )
        outcome = planner.plan(
            SurveyKind.NPS,
            channel=InvitationChannel.ELECTRONIC_MESSAGE,
            recipient=_recipient(
                last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.ISSUED

    def test_a_record_that_cannot_cite_the_registry_does_not_clear_it(self) -> None:
        """6563 keeps sender records; a record with nothing to cite is not
        one. Same check ``seal_commercial`` makes, on the scheduling side."""
        planner = SurveyInvitationPlanner(
            iys=_FixtureIysRegistry(reference="   "),
            flags=InMemoryProvider({SATISFACTION_PROMPTS_FLAG: True}),
            baseline_quiet=BASELINE,
            policy=SUPPLIED,
        )
        outcome = planner.plan(
            SurveyKind.NPS,
            channel=InvitationChannel.ELECTRONIC_MESSAGE,
            recipient=_recipient(
                last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.BLOCKED_IYS_CONSENT_ABSENT

    def test_there_is_no_survey_reminder_kind(self) -> None:
        """The transactional dispatcher takes a ``ReminderKind``. If a survey
        member existed here, a commercial invitation would have a
        consent-free route to a patient's lock screen."""
        for kind in ReminderKind:
            assert "survey" not in kind.value
            assert "nps" not in kind.value
            assert "pulse" not in kind.value

    def test_there_is_no_survey_template_to_render(self) -> None:
        """Even with every gate open there is no copy: patient-facing
        invitation text is B1/PolicyGuard territory and no file states it."""
        corpus = " ".join(
            text
            for template in TEMPLATES.values()
            for mapping in (template.title, template.body)
            for text in mapping.values()
        ).casefold()
        for term in ("anket", "puan", "tavsiye", "survey", "recommend", "score"):
            assert term not in corpus

    def test_every_template_in_the_catalogue_is_still_transactional(self) -> None:
        assert {template.message_class for template in TEMPLATES.values()} == {
            MessageClass.TRANSACTIONAL
        }


# --- 4. opt-out and quiet hours, decided once -------------------------------------


class TestOptOutAndQuietHours:
    def test_the_message_register_is_a_required_argument_with_no_default(self) -> None:
        """A planner that assumed "nobody has opted out" when the caller
        forgot the argument would invite exactly the people who asked not to
        be. The same "no permitted default" posture invariant 21 takes with a
        RED register — and the reason a clinician-side register being absent
        is an ask rather than a silent False."""
        parameter = inspect.signature(SurveyInvitationPlanner.plan).parameters["preferences"]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    def test_an_opted_out_recipient_is_never_invited(self) -> None:
        outcome = _planner().plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=NotificationPreferences(opted_out=True, quiet=None),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.SUPPRESSED_OPT_OUT

    def test_opt_out_outranks_the_legal_block_in_the_report(self) -> None:
        """Both stop the send. The recipient's own refusal is the one worth
        naming, so it is read first."""
        outcome = _planner().plan(
            SurveyKind.NPS,
            channel=InvitationChannel.ELECTRONIC_MESSAGE,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=NotificationPreferences(opted_out=True, quiet=None),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.SUPPRESSED_OPT_OUT

    def test_a_due_invitation_inside_quiet_hours_is_deferred(self) -> None:
        night = datetime(2026, 3, 10, 23, 30, tzinfo=SCHEDULING_OFFSET)
        outcome = _planner().plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=night,
        )
        assert outcome.status is InvitationStatus.DEFERRED_QUIET_HOURS

    def test_an_unset_baseline_refuses_the_invitation(self) -> None:
        """INT-141 ships no quiet window because no file names an hour. A
        survey scheduler must inherit that refusal, not route around it."""
        outcome = _planner(baseline=None).plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.REFUSED_QUIET_HOURS_UNSET

    def test_the_recipients_own_window_narrows_the_baseline(self) -> None:
        afternoon = datetime(2026, 3, 10, 14, 30, tzinfo=SCHEDULING_OFFSET)
        preferences = NotificationPreferences(
            opted_out=False, quiet=QuietWindow.parse("14:00", "16:00")
        )
        outcome = _planner().plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=preferences,
            at=afternoon,
        )
        assert outcome.status is InvitationStatus.DEFERRED_QUIET_HOURS

    @pytest.mark.parametrize("opted_out", [False, True])
    @pytest.mark.parametrize("baseline", [None, QuietWindow.parse("22:00", "08:00")])
    @pytest.mark.parametrize(
        "own", [None, QuietWindow.parse("14:00", "16:00"), QuietWindow.parse("00:00", "23:59")]
    )
    @pytest.mark.parametrize("hour", [3, 9, 15, 23])
    def test_the_planner_and_the_reminder_dispatcher_never_disagree(
        self, opted_out: bool, baseline: QuietWindow | None, own: QuietWindow | None, hour: int
    ) -> None:
        """One implementation, proved on the whole grid. A survey scheduler
        with its own copy of "is it quiet?" would drift from the dispatcher on
        the first edit, and the patient would find out first."""
        at = datetime(2026, 3, 10, hour, 0, tzinfo=SCHEDULING_OFFSET)
        preferences = NotificationPreferences(opted_out=opted_out, quiet=own)
        dispatch = ReminderDispatcher(
            UnconfiguredTransport(Channel.PUSH), baseline_quiet=baseline
        ).send(
            ReminderKind.VISIT_SOON,
            locale=Locale.TR,
            recipient_ref="rcp-0f3b",
            preferences=preferences,
            at=at,
        )
        plan = _planner(baseline=baseline).plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=preferences,
            at=at,
        )
        equivalent = {
            DispatchStatus.SUPPRESSED_OPT_OUT: InvitationStatus.SUPPRESSED_OPT_OUT,
            DispatchStatus.REFUSED_QUIET_HOURS_UNSET: InvitationStatus.REFUSED_QUIET_HOURS_UNSET,
            DispatchStatus.DEFERRED_QUIET_HOURS: InvitationStatus.DEFERRED_QUIET_HOURS,
            # the dispatcher got past every suppression and died on the missing
            # vendor; the planner got past the same ones and issued.
            DispatchStatus.BLOCKED_TRANSPORT_UNCONFIGURED: InvitationStatus.ISSUED,
        }
        assert plan.status is equivalent[dispatch.status]

    def test_the_shared_quiet_verdict_is_total_over_its_three_answers(self) -> None:
        at = datetime(2026, 3, 10, 23, 30, tzinfo=SCHEDULING_OFFSET)
        assert quiet_verdict(_open(), baseline=None, at=at) is QuietVerdict.UNSET
        assert (
            quiet_verdict(_open(), baseline=QuietWindow.parse("22:00", "08:00"), at=at)
            is QuietVerdict.QUIET
        )
        assert (
            quiet_verdict(_open(), baseline=QuietWindow.parse("22:00", "23:00"), at=at)
            is QuietVerdict.CLEAR
        )


# --- 5. the safety flag -----------------------------------------------------------


class TestSafetyFlag:
    def test_satisfaction_prompts_is_a_predeclared_safety_flag_at_false(self) -> None:
        assert SATISFACTION_PROMPTS_FLAG == "satisfaction_prompts"
        assert SAFETY_FLAG_DEFAULTS[SATISFACTION_PROMPTS_FLAG] is False

    def test_the_default_provider_blocks_every_invitation(self) -> None:
        planner = SurveyInvitationPlanner(
            iys=UnconfiguredIysRegistry(),
            baseline_quiet=BASELINE,
            policy=SUPPLIED,
        )
        outcome = planner.plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.BLOCKED_PROMPTS_DISABLED

    def test_a_call_site_default_cannot_open_the_flag(self) -> None:
        """``SAFETY_FLAG_DEFAULTS`` outranks the caller default in both
        providers (INT-023); this is the survey-side proof of it."""
        planner = SurveyInvitationPlanner(
            iys=UnconfiguredIysRegistry(),
            flags=InMemoryProvider(),
            baseline_quiet=BASELINE,
            policy=SUPPLIED,
        )
        outcome = planner.plan(
            SurveyKind.CLINICIAN_PULSE,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2025, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.BLOCKED_PROMPTS_DISABLED


# --- 6. what the scheduler is allowed to say out loud -----------------------------


class TestNoPhiEscapes:
    def test_the_plan_carries_no_recipient_handle(self) -> None:
        outcome = _planner().plan(
            SurveyKind.NPS,
            channel=InvitationChannel.ELECTRONIC_MESSAGE,
            recipient=_recipient(
                last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert "rcp-0f3b" not in repr(outcome)

    def test_planning_logs_enums_only_never_the_recipient(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="intake_platform.surveys.planner"):
            _planner().plan(
                SurveyKind.NPS,
                channel=InvitationChannel.ELECTRONIC_MESSAGE,
                recipient=_recipient(
                    last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
                ),
                preferences=_open(),
                at=MIDDAY,
            )
        emitted = "\n".join(record.getMessage() for record in caplog.records)
        assert "survey_invitation" in emitted
        assert "rcp-0f3b" not in emitted

    def test_the_metric_labels_are_closed_enumerations(self) -> None:
        assert SURVEY_INVITATION_TOTAL._labelnames == (
            "kind",
            "channel",
            "message_class",
            "status",
        )

    def test_planning_counts_the_outcome(self) -> None:
        def read() -> float:
            value = SURVEY_INVITATION_TOTAL.labels(
                kind=SurveyKind.NPS.value,
                channel=InvitationChannel.ELECTRONIC_MESSAGE.value,
                message_class=MessageClass.COMMERCIAL.value,
                status=InvitationStatus.BLOCKED_IYS_CONSENT_ABSENT.value,
            )._value.get()
            return float(value)

        before = read()
        _planner().plan(
            SurveyKind.NPS,
            channel=InvitationChannel.ELECTRONIC_MESSAGE,
            recipient=_recipient(
                last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert read() == before + 1


class TestNoAccuracyClaim:
    def test_the_package_states_no_satisfaction_figure(self) -> None:
        """Invariant 20. A scheduler has no business carrying a score, and a
        docstring is where one would arrive — so this reads the prose, while
        ``test_the_only_numbers_in_the_package_are_the_two_stated_periods``
        covers the values."""
        for path in sorted(SURVEYS_SRC.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            assert re.search(r"\d\s*%", text) is None, f"{path.name} states a percentage"
            assert (
                re.search(
                    r"(?i)\b(?:target|hedef|ortalama|average|benchmark|puan|score)\b[^.\n]{0,40}?\d",
                    text,
                )
                is None
            ), f"{path.name} puts a figure next to a performance word"


# --- 7. the order of refusal, stated once and pinned ------------------------------


class TestOrderOfRefusal:
    def test_the_order_is_opt_out_then_law_then_flag_then_schedule_then_hours(self) -> None:
        """Every lock below is shut at once; each assertion removes the one
        above it and reads the next answer."""
        never = _recipient()
        due_now = _recipient(last_prompted_at=datetime(2026, 1, 10, 9, 0, tzinfo=SCHEDULING_OFFSET))
        night = datetime(2026, 3, 10, 23, 30, tzinfo=SCHEDULING_OFFSET)

        def plan(
            *,
            prompts: bool,
            channel: InvitationChannel,
            recipient: SurveyRecipient,
            policy: SurveyPolicy,
            preferences: NotificationPreferences,
            at: datetime,
        ) -> InvitationStatus:
            return (
                _planner(prompts_enabled=prompts, policy=policy)
                .plan(
                    SurveyKind.NPS,
                    channel=channel,
                    recipient=recipient,
                    preferences=preferences,
                    at=at,
                )
                .status
            )

        assert (
            plan(
                prompts=False,
                channel=InvitationChannel.ELECTRONIC_MESSAGE,
                recipient=never,
                policy=SurveyPolicy(),
                preferences=NotificationPreferences(opted_out=True, quiet=None),
                at=night,
            )
            is InvitationStatus.SUPPRESSED_OPT_OUT
        )
        assert (
            plan(
                prompts=False,
                channel=InvitationChannel.ELECTRONIC_MESSAGE,
                recipient=never,
                policy=SurveyPolicy(),
                preferences=_open(),
                at=night,
            )
            is InvitationStatus.BLOCKED_IYS_CONSENT_ABSENT
        )
        assert (
            plan(
                prompts=False,
                channel=InvitationChannel.IN_PRODUCT,
                recipient=never,
                policy=SurveyPolicy(),
                preferences=_open(),
                at=night,
            )
            is InvitationStatus.BLOCKED_PROMPTS_DISABLED
        )
        assert (
            plan(
                prompts=True,
                channel=InvitationChannel.IN_PRODUCT,
                recipient=never,
                policy=SurveyPolicy(),
                preferences=_open(),
                at=night,
            )
            is InvitationStatus.REFUSED_SCHEDULE_UNSET
        )
        assert (
            plan(
                prompts=True,
                channel=InvitationChannel.IN_PRODUCT,
                recipient=due_now,
                policy=SUPPLIED,
                preferences=_open(),
                at=night,
            )
            is InvitationStatus.DEFERRED_QUIET_HOURS
        )
        assert (
            plan(
                prompts=True,
                channel=InvitationChannel.IN_PRODUCT,
                recipient=due_now,
                policy=SUPPLIED,
                preferences=_open(),
                at=MIDDAY,
            )
            is InvitationStatus.ISSUED
        )

    def test_a_recipient_who_is_not_yet_due_is_reported_as_such(self) -> None:
        outcome = _planner().plan(
            SurveyKind.NPS,
            channel=InvitationChannel.IN_PRODUCT,
            recipient=_recipient(
                last_prompted_at=datetime(2026, 3, 1, 9, 0, tzinfo=SCHEDULING_OFFSET)
            ),
            preferences=_open(),
            at=MIDDAY,
        )
        assert outcome.status is InvitationStatus.NOT_YET_DUE
        assert outcome.due_at == datetime(2026, 4, 1, 9, 0, tzinfo=SCHEDULING_OFFSET)


# --- 8. the catalogue (invariant 13) ----------------------------------------------


def _catalog_names() -> Iterator[str]:
    import yaml

    path = Path(__file__).resolve().parents[2] / "observability" / "metrics_catalog.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    for entry in document["metrics"]:
        yield str(entry["name"])


class TestCatalogued:
    def test_the_invitation_counter_is_in_the_catalogue(self) -> None:
        assert "survey_invitation_total" in set(_catalog_names())


# --- fixtures that exist only here ------------------------------------------------


class _FixtureIysRecord(IysConsentRecord):
    """A stand-in for a record the İYS integration would return. The real
    shape is not specified anywhere in files/ (INT-141 keeps the production
    type abstract for exactly that reason), so the made-up version lives here,
    where a made-up shape is allowed to be made up."""

    def __init__(self, reference: str) -> None:
        self._reference = reference

    def registry_reference(self) -> str:
        return self._reference

    def recorded_at(self) -> datetime:
        return datetime(2026, 9, 1, tzinfo=UTC)


class _FixtureIysRegistry:
    """A registry that answers. Nothing in packages/ or services/ does, and
    INT-141's AST scan is what keeps it that way."""

    def __init__(self, reference: str = "fixture-registry-reference") -> None:
        self._reference = reference

    def lookup(self, recipient_ref: str) -> IysConsentRecord:
        return _FixtureIysRecord(self._reference)
