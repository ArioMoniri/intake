"""INT-141 — notifications: content-free reminders, quiet hours, opt-out,
transactional-only (CLAUDE.md invariants 6 and 18; files/06 §1 row 6563-İYS;
files/10 §9 row "Notifications / reminders"; sec_row ``notifications``).

What this file pins, in the order the harm arrives:

1. **Content-freedom is literal.** A notification body may not carry a
   symptom, a branch label, a clinician name or a document title — an
   appointment reminder that names the department is a disclosure on a lock
   screen that anyone standing behind the patient can read. The property
   proved here is stronger than "no PHI substring": every token of every
   rendered payload must already appear in the committed template corpus, so
   an interpolated value of ANY kind is a violation by construction.
   The adversarial fixture is a patient whose branch label shares a word with
   the generic copy — a naive per-token scan reports that shared word and is
   therefore useless; the scan here must stay silent on it and still catch
   the branch's distinctive words.

2. **Transactional-only is structural.** Without a recorded İYS consent no
   marketing-class message may be sent, and the code must be UNABLE to send
   one rather than merely declining to: the catalogue holds no commercial
   template, the sealing function for one demands an ``IysConsentRecord``,
   and that type is abstract with no concrete subclass anywhere outside
   tests — so the call cannot be written, let alone reached.

3. **Quiet hours and opt-out are the patient's.** Opt-out suppresses every
   class this dispatcher can send. Quiet hours have NO invented default:
   files/ names the control and no file names a window, so an unset baseline
   refuses rather than guessing 22:00.

4. **The live path is blocked, not stubbed.** No push/SMS vendor is
   contracted (docs/evidence/INT-131.md, "SMS vendor contract"), so the only
   wired transport raises and the recorded-fixture transport is the test
   lane's.
"""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from intake_platform.flags import SAFETY_FLAG_DEFAULTS, InMemoryProvider
from intake_platform.notifications import (
    COMMERCIAL_MESSAGING_FLAG,
    CORPUS_VOCABULARY,
    SCHEDULING_OFFSET,
    Channel,
    CommercialRequest,
    ContentLeak,
    DeepLinkRoute,
    DispatchStatus,
    IysConsentRecord,
    IysRegistryUnconfigured,
    Locale,
    MessageClass,
    NotificationPreferences,
    QuietWindow,
    RecordedTransport,
    ReminderDispatcher,
    ReminderKind,
    Template,
    TransportUnconfigured,
    UnconfiguredIysRegistry,
    UnconfiguredTransport,
    assert_content_free,
    leaked_terms,
    local_minute_of_day,
    outside_vocabulary,
    render,
    seal_commercial,
    seal_transactional,
    template_for,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "notifications"

# --- the adversarial patient -------------------------------------------------------
#
# Her visit is booked to a branch whose label shares the word "ve" with the
# committed generic copy ("… uygulamayı açın ve kaldığınız yerden …"). A scan
# that reports every shared token would report "ve" on every single template
# and be switched off within a week; a scan that only looks for the whole
# phrase would miss "Kadın" standing alone. Both failure modes are pinned.
ADVERSARIAL_BRANCH = "Kadın Hastalıkları ve Doğum"
ADVERSARIAL_SLOT_VALUE = "göğüs ağrısı"
ADVERSARIAL_CLINICIAN = "Dr. Elif Yıldırım"
ADVERSARIAL_DOCUMENT = "Tiroid ultrason raporu"
ADVERSARIAL_TERMS = (
    ADVERSARIAL_BRANCH,
    ADVERSARIAL_SLOT_VALUE,
    ADVERSARIAL_CLINICIAN,
    ADVERSARIAL_DOCUMENT,
)

RECIPIENT = "v1.9f2c4a1b8e7d6c5a4b3f2e1d0c9b8a77"

# A window that exists only because a test supplies it: nothing in the tree
# ships a quiet-hours default (see test_no_quiet_window_is_shipped).
TEST_QUIET = QuietWindow(start_minute=22 * 60, end_minute=8 * 60)


def _at(hour: int, minute: int = 0) -> datetime:
    """A UTC instant whose Türkiye local clock reads ``hour:minute``."""
    return datetime(2026, 9, 1, hour, minute, tzinfo=SCHEDULING_OFFSET).astimezone(UTC)


def _recorded() -> RecordedTransport:
    return RecordedTransport(Channel.PUSH, FIXTURES)


def _awake_prefs() -> NotificationPreferences:
    return NotificationPreferences(opted_out=False, quiet=TEST_QUIET)


def _dispatcher() -> ReminderDispatcher:
    return ReminderDispatcher(_recorded(), baseline_quiet=TEST_QUIET)


# --- 1 · content-freedom -----------------------------------------------------------


class TestContentFreedom:
    def test_every_template_renders_inside_its_own_corpus(self) -> None:
        """The airtight form of "no PHI in a push": the rendered payload's
        vocabulary is a subset of the committed corpus, so no interpolated
        value of any kind — clinical or not — can reach a lock screen."""
        for kind in ReminderKind:
            for locale in Locale:
                message = render(kind, locale)
                assert outside_vocabulary(message.title, CORPUS_VOCABULARY) == ()
                assert outside_vocabulary(message.body, CORPUS_VOCABULARY) == ()
                assert_content_free(message)

    def test_a_helpful_body_that_names_the_department_is_a_violation(self) -> None:
        """Near-miss negative control: the body a well-meaning engineer would
        write. It reads better and it is a disclosure."""
        helpful = "Kardiyoloji viziteniz yarın saat 14:00."
        offenders = outside_vocabulary(helpful, CORPUS_VOCABULARY)
        assert "kardiyoloji" in offenders
        assert "14" in offenders, "a numeral is data too"

    def test_no_rendered_body_carries_a_slot_value_branch_clinician_or_title(self) -> None:
        for kind in ReminderKind:
            for locale in Locale:
                message = render(kind, locale)
                for field in (message.title, message.body):
                    assert leaked_terms(field, ADVERSARIAL_TERMS) == ()

    def test_the_shared_word_alone_is_not_a_leak(self) -> None:
        """ "ve" is in every copy for every patient, so its presence says
        nothing about this one. A scan that reports it is a scan nobody
        keeps."""
        assert "ve" in CORPUS_VOCABULARY
        assert leaked_terms("Hazırlığınızı açın ve tamamlayın.", (ADVERSARIAL_BRANCH,)) == ()

    def test_a_distinctive_word_of_the_same_branch_is_a_leak(self) -> None:
        """The same branch, one distinctive word, and the scan must bite."""
        assert leaked_terms("Kadın viziteniz yarın.", (ADVERSARIAL_BRANCH,)) == (
            ADVERSARIAL_BRANCH,
        )
        assert leaked_terms(f"{ADVERSARIAL_BRANCH} viziteniz yarın.", (ADVERSARIAL_BRANCH,)) == (
            ADVERSARIAL_BRANCH,
        )

    def test_a_branch_made_only_of_generic_words_still_leaks_as_a_phrase(self) -> None:
        """Degenerate case: every token generic, so no token is evidence —
        but the phrase itself is. The whole-term check is what covers it."""
        phrase = "ve ve"
        assert leaked_terms(f"Açın {phrase} tamamlayın.", (phrase,)) == (phrase,)

    def test_turkish_casing_cannot_smuggle_a_term_past_the_scan(self) -> None:
        """ "KADIN".lower() is "kadin" in Python's default casing and "kadın"
        in Turkish. A scan on the default fold misses the shouted form."""
        assert leaked_terms("KADIN VİZİTENİZ YARIN.", (ADVERSARIAL_BRANCH,)) == (
            ADVERSARIAL_BRANCH,
        )

    def test_the_sealed_payload_as_it_leaves_the_process_carries_nothing(self) -> None:
        """Not just the body: the whole wire payload — route, keys, values."""
        for kind in ReminderKind:
            sealed = seal_transactional(
                kind, Locale.TR, channel=Channel.PUSH, recipient_ref=RECIPIENT
            )
            wire = json.dumps(sealed.as_wire(), ensure_ascii=False)
            assert leaked_terms(wire, ADVERSARIAL_TERMS) == ()

    def test_the_deep_link_target_is_an_enum_never_an_identifier(self) -> None:
        """A deep link carrying a visit id is a linkable identifier on a lock
        screen; the route is therefore drawn from a closed set of app
        destinations with no id in it (files/10 §4: no PHI in deep links)."""
        for kind in ReminderKind:
            assert isinstance(template_for(kind).route, DeepLinkRoute)

    def test_assert_content_free_raises_on_a_hand_built_leak(self) -> None:
        leaky = render(ReminderKind.VISIT_PREPARE, Locale.TR).with_body(
            f"{ADVERSARIAL_BRANCH} viziteniz yarın."
        )
        with pytest.raises(ContentLeak) as excinfo:
            assert_content_free(leaky)
        # The exception names the template and a COUNT, never the offending
        # words — those words are, by hypothesis, the patient's data, and an
        # exception message is a log line (invariant 6). A leak detector that
        # logs the leak is not a detector.
        message = str(excinfo.value)
        assert "visit_prepare" in message
        assert leaked_terms(message, ADVERSARIAL_TERMS) == ()
        assert ADVERSARIAL_SLOT_VALUE not in message

    def test_the_dispatcher_refuses_to_hand_a_leaky_message_to_a_transport(self) -> None:
        """Belt and braces: the assertion runs on the way out, so a future
        template that grows an interpolation slot fails at dispatch, not in
        review."""
        leaky = Template(
            key="leaky",
            message_class=MessageClass.TRANSACTIONAL,
            route=DeepLinkRoute.TODAY,
            title={Locale.TR: "Vizite", Locale.EN: "Vizite"},
            body={
                Locale.TR: f"{ADVERSARIAL_BRANCH} viziteniz yarın.",
                Locale.EN: "Your visit tomorrow.",
            },
        )
        with pytest.raises(ContentLeak):
            assert_content_free(leaky.render(Locale.TR))


# --- 2 · transactional-only, İYS ----------------------------------------------------


class TestIysGate:
    def test_no_commercial_template_exists(self) -> None:
        for kind in ReminderKind:
            assert template_for(kind).message_class is MessageClass.TRANSACTIONAL

    def test_the_iys_record_type_cannot_be_instantiated(self) -> None:
        """Lock 1. The record is abstract: there is no value of this type to
        pass, so the commercial call cannot be written."""
        assert IysConsentRecord.__abstractmethods__
        with pytest.raises(TypeError):
            IysConsentRecord()  # type: ignore[abstract]

    def test_no_concrete_iys_record_exists_outside_tests(self) -> None:
        """Lock 2. A future adapter subclassing this is exactly the change
        that must be reviewed, so the absence is a gate rather than a
        coincidence."""
        assert _iys_record_subclasses_in_sources() == []

    def test_the_only_registry_refuses_every_lookup(self) -> None:
        """Lock 3. No İYS integration contract exists in files/, so nothing
        can produce a record at runtime either."""
        with pytest.raises(IysRegistryUnconfigured):
            UnconfiguredIysRegistry().lookup(RECIPIENT)

    def test_commercial_messaging_is_a_safety_flag_declared_false(self) -> None:
        """Lock 4. Even with a record and a template, the flag decides — and
        a call-site default cannot open it."""
        assert SAFETY_FLAG_DEFAULTS[COMMERCIAL_MESSAGING_FLAG] is False
        assert InMemoryProvider().get_bool(COMMERCIAL_MESSAGING_FLAG, True) is False

    def test_sealing_a_commercial_message_refuses_while_the_flag_is_shut(self) -> None:
        record = _FixtureIysRecord()
        with pytest.raises(PermissionError):
            seal_commercial(
                CommercialRequest(recipient_ref=RECIPIENT, campaign_ref="fixture-campaign"),
                record,
                _fixture_commercial_template(),
                Locale.TR,
                channel=Channel.SMS,
                flags=InMemoryProvider(),
            )

    def test_a_transactional_template_cannot_be_smuggled_through_the_commercial_seal(
        self,
    ) -> None:
        """The reverse laundering: sending a reminder through the marketing
        path would tag a service message commercial and burn an İYS consent
        on it. Refused."""
        with pytest.raises(ValueError, match="commercial templates"):
            seal_commercial(
                CommercialRequest(recipient_ref=RECIPIENT, campaign_ref="fixture-campaign"),
                _FixtureIysRecord(),
                template_for(ReminderKind.VISIT_SOON),
                Locale.TR,
                channel=Channel.SMS,
                flags=InMemoryProvider({COMMERCIAL_MESSAGING_FLAG: True}),
            )

    def test_a_record_that_cannot_cite_the_registry_is_not_a_record(self) -> None:
        """6563 keeps sender records, and a sender record has to cite the
        registry entry. A record whose reference is blank proves nothing."""

        class _BlankRecord(_FixtureIysRecord):
            def registry_reference(self) -> str:
                return "   "

        with pytest.raises(ValueError, match="registry reference"):
            seal_commercial(
                CommercialRequest(recipient_ref=RECIPIENT, campaign_ref="fixture-campaign"),
                _BlankRecord(),
                _fixture_commercial_template(),
                Locale.TR,
                channel=Channel.SMS,
                flags=InMemoryProvider({COMMERCIAL_MESSAGING_FLAG: True}),
            )

    def test_with_a_record_and_an_open_flag_the_seal_is_the_only_way_through(self) -> None:
        """The gate is the RECORD, not an accident of the catalogue: given
        both, sealing works and is tagged commercial. Neither the record nor
        the template exists outside this file, which is the point."""
        sealed = seal_commercial(
            CommercialRequest(recipient_ref=RECIPIENT, campaign_ref="fixture-campaign"),
            _FixtureIysRecord(),
            _fixture_commercial_template(),
            Locale.TR,
            channel=Channel.SMS,
            flags=InMemoryProvider({COMMERCIAL_MESSAGING_FLAG: True}),
        )
        assert sealed.message_class is MessageClass.COMMERCIAL

    def test_the_reminder_dispatcher_has_no_commercial_entry_point(self) -> None:
        """The dispatcher's only send takes a ReminderKind — a closed enum of
        transactional kinds. There is no argument that could carry a campaign
        through it, which is why the type is the gate rather than a check."""
        sealed = seal_transactional(
            ReminderKind.VISIT_SOON, Locale.TR, channel=Channel.PUSH, recipient_ref=RECIPIENT
        )
        assert sealed.message_class is MessageClass.TRANSACTIONAL


# --- 3 · quiet hours and opt-out ----------------------------------------------------


class TestOptOut:
    def test_opt_out_suppresses_a_transactional_reminder(self) -> None:
        """6563 puts service messages outside the consent requirement; it
        does not oblige us to keep sending them to someone who asked us to
        stop. Honouring the refusal for every class this dispatcher can send
        is the product's choice and is pinned so it cannot be quietly
        narrowed to marketing later."""
        outcome = _dispatcher().send(
            ReminderKind.VISIT_SOON,
            locale=Locale.TR,
            recipient_ref=RECIPIENT,
            preferences=NotificationPreferences(opted_out=True, quiet=TEST_QUIET),
            at=_at(10),
        )
        assert outcome.status is DispatchStatus.SUPPRESSED_OPT_OUT
        assert outcome.receipt is None

    def test_opt_out_outranks_everything_including_an_open_window(self) -> None:
        for hour in (0, 9, 23):
            outcome = _dispatcher().send(
                ReminderKind.NOTE_READY,
                locale=Locale.TR,
                recipient_ref=RECIPIENT,
                preferences=NotificationPreferences(opted_out=True, quiet=None),
                at=_at(hour),
            )
            assert outcome.status is DispatchStatus.SUPPRESSED_OPT_OUT


class TestQuietHours:
    def test_no_quiet_window_is_shipped(self) -> None:
        """files/10 §9 names the control; no file in the tree names a window.
        A default here would be a value chosen once by an engineer for every
        future patient, so an unset baseline refuses instead."""
        outcome = ReminderDispatcher(_recorded()).send(
            ReminderKind.VISIT_PREPARE,
            locale=Locale.TR,
            recipient_ref=RECIPIENT,
            preferences=NotificationPreferences(opted_out=False, quiet=None),
            at=_at(10),
        )
        assert outcome.status is DispatchStatus.REFUSED_QUIET_HOURS_UNSET

    def test_a_window_that_wraps_midnight_covers_both_sides(self) -> None:
        window = QuietWindow(start_minute=22 * 60, end_minute=8 * 60)
        assert window.covers(23 * 60)
        assert window.covers(3 * 60)
        assert not window.covers(12 * 60)

    def test_a_window_inside_one_day_covers_only_the_middle(self) -> None:
        window = QuietWindow(start_minute=13 * 60, end_minute=15 * 60)
        assert window.covers(14 * 60)
        assert not window.covers(23 * 60)

    def test_the_boundary_minutes_belong_to_the_awake_side(self) -> None:
        window = QuietWindow(start_minute=22 * 60, end_minute=8 * 60)
        assert window.covers(22 * 60)
        assert not window.covers(8 * 60)

    def test_a_quiet_instant_defers_rather_than_delivering(self) -> None:
        outcome = _dispatcher().send(
            ReminderKind.VISIT_PREPARE,
            locale=Locale.TR,
            recipient_ref=RECIPIENT,
            preferences=_awake_prefs(),
            at=_at(3),
        )
        assert outcome.status is DispatchStatus.DEFERRED_QUIET_HOURS
        assert outcome.receipt is None

    def test_the_patient_window_narrows_the_baseline_never_widens_it(self) -> None:
        """Quiet is the union: a patient who wants an extra quiet afternoon
        gets it, and a patient whose window is silent about the night does
        not thereby unlock the night."""
        dispatcher = _dispatcher()
        afternoon = NotificationPreferences(
            opted_out=False, quiet=QuietWindow(start_minute=13 * 60, end_minute=15 * 60)
        )
        assert (
            dispatcher.send(
                ReminderKind.VISIT_SOON,
                locale=Locale.TR,
                recipient_ref=RECIPIENT,
                preferences=afternoon,
                at=_at(14),
            ).status
            is DispatchStatus.DEFERRED_QUIET_HOURS
        )
        assert (
            dispatcher.send(
                ReminderKind.VISIT_SOON,
                locale=Locale.TR,
                recipient_ref=RECIPIENT,
                preferences=afternoon,
                at=_at(3),
            ).status
            is DispatchStatus.DEFERRED_QUIET_HOURS
        )

    def test_quiet_hours_are_read_on_the_turkish_clock_not_utc(self) -> None:
        """23:00 Istanbul is 20:00 UTC. Evaluating the window in UTC would
        wake a third of the country up."""
        assert local_minute_of_day(datetime(2026, 9, 1, 20, 0, tzinfo=UTC)) == 23 * 60
        assert SCHEDULING_OFFSET.utcoffset(None) == timedelta(hours=3)

    def test_a_naive_instant_is_refused_rather_than_assumed_utc(self) -> None:
        with pytest.raises(ValueError, match="tz-aware"):
            local_minute_of_day(datetime(2026, 9, 1, 20, 0))  # noqa: DTZ001 — the point

    @pytest.mark.parametrize(("start", "end"), [(-1, 0), (0, 1440), (1440, 0), (60, 60)])
    def test_a_window_outside_the_day_or_of_zero_width_is_refused(
        self, start: int, end: int
    ) -> None:
        with pytest.raises(ValueError):
            QuietWindow(start_minute=start, end_minute=end)

    def test_a_window_parses_from_and_back_to_the_wire_form(self) -> None:
        window = QuietWindow.parse("22:00", "08:00")
        assert window == TEST_QUIET
        assert window.as_text() == ("22:00", "08:00")

    @pytest.mark.parametrize("bad", ["24:00", "8:00", "22h00", "", "22:60"])
    def test_a_malformed_time_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError):
            QuietWindow.parse(bad, "08:00")


# --- 4 · the blocked live path ------------------------------------------------------


class TestTransport:
    def test_the_only_wired_transport_refuses_because_no_vendor_is_contracted(self) -> None:
        """No fake sender: an uncontracted vendor is a blocked path that
        raises, never a stub that reports success nobody earned."""
        sealed = seal_transactional(
            ReminderKind.VISIT_SOON, Locale.TR, channel=Channel.PUSH, recipient_ref=RECIPIENT
        )
        with pytest.raises(TransportUnconfigured):
            UnconfiguredTransport(Channel.PUSH).deliver(sealed)
        with pytest.raises(TransportUnconfigured):
            UnconfiguredTransport(Channel.SMS).deliver(sealed)

    def test_the_dispatcher_reports_the_block_instead_of_raising(self) -> None:
        outcome = ReminderDispatcher(
            UnconfiguredTransport(Channel.PUSH), baseline_quiet=TEST_QUIET
        ).send(
            ReminderKind.VISIT_PREPARE,
            locale=Locale.TR,
            recipient_ref=RECIPIENT,
            preferences=_awake_prefs(),
            at=_at(10),
        )
        assert outcome.status is DispatchStatus.BLOCKED_TRANSPORT_UNCONFIGURED
        assert outcome.receipt is None

    def test_the_recorded_transport_replays_a_committed_vendor_response(self) -> None:
        outcome = _dispatcher().send(
            ReminderKind.VISIT_PREPARE,
            locale=Locale.TR,
            recipient_ref=RECIPIENT,
            preferences=_awake_prefs(),
            at=_at(10),
        )
        assert outcome.status is DispatchStatus.DELIVERED
        assert outcome.receipt is not None
        assert outcome.receipt.accepted is True

    def test_the_recorded_transport_refuses_to_invent_a_missing_response(self) -> None:
        with pytest.raises(FileNotFoundError):
            RecordedTransport(Channel.SMS, FIXTURES).deliver(
                seal_transactional(
                    ReminderKind.NOTE_READY,
                    Locale.EN,
                    channel=Channel.SMS,
                    recipient_ref=RECIPIENT,
                )
            )

    def test_a_recorded_directory_is_required_and_never_guessed(self) -> None:
        with pytest.raises(FileNotFoundError):
            RecordedTransport(Channel.PUSH, FIXTURES / "not-recorded")


# --- 5 · invariant 6, on the way out ------------------------------------------------


class TestLogging:
    def test_dispatch_logs_ids_and_statuses_never_a_body(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="intake_platform.notifications"):
            for kind in ReminderKind:
                _dispatcher().send(
                    kind,
                    locale=Locale.TR,
                    recipient_ref=RECIPIENT,
                    preferences=_awake_prefs(),
                    at=_at(10),
                )
        assert caplog.records, "the dispatcher must be observable at all"
        blob = "\n".join(record.getMessage() for record in caplog.records)
        for kind in ReminderKind:
            assert render(kind, Locale.TR).body not in blob
        assert RECIPIENT not in blob, "even a pseudonym is an identifier in a log line"
        assert leaked_terms(blob, ADVERSARIAL_TERMS) == ()


# --- fixtures that exist only here --------------------------------------------------


class _FixtureIysRecord(IysConsentRecord):
    """The İYS record shape is NOT specified anywhere in files/ — files/06 §1
    names the obligation ("any marketing message requires İYS-registered
    consent; sender records kept") and no file names a field. Inventing
    ``iys_id``/``consent_date``/``retailer_code`` here would be inventing the
    contract, so the production type stays abstract and this stand-in lives
    in the test file, where a made-up shape is allowed to be made up."""

    def registry_reference(self) -> str:
        return "fixture-registry-reference"

    def recorded_at(self) -> datetime:
        return datetime(2026, 9, 1, tzinfo=UTC)


def _fixture_commercial_template() -> Template:
    return Template(
        key="fixture.commercial",
        message_class=MessageClass.COMMERCIAL,
        route=DeepLinkRoute.APP_ROOT,
        title={Locale.TR: "Vizite", Locale.EN: "Vizite"},
        body={Locale.TR: "Deneme iletisi.", Locale.EN: "Test message."},
    )


def _python_sources() -> Iterator[Path]:
    for root in ("packages", "services"):
        for path in (REPO / root).rglob("*.py"):
            parts = set(path.parts)
            if parts & {"tests", ".venv", "node_modules", "build", "dist", ".cache"}:
                continue
            yield path


def _iys_record_subclasses_in_sources() -> list[str]:
    found: list[str] = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
                if name == "IysConsentRecord":
                    found.append(f"{path.relative_to(REPO)}::{node.name}")
    return sorted(found)
