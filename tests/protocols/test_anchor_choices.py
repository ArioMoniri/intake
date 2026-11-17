"""INT-522 — a closed onset choice resolves to its CD-05 day, against the session's clock.

GitHub #888, from INT-518 (#884). ``chest_pain.onset_at`` is the tense anchor
of ``rf.chest_pain_cardiac_features`` (KIRMIZI_K2) and of its SARI sibling. It
is a ``date`` slot answered by four closed choices, and CD-05 decided how each
choice resolves to a calendar day against the session's reference time. The
resolution was not built, so a live anchor read Unknown and K2 could not fire
from a conversation.

This suite pins ``protocols.anchor_choices`` — the build of CD-05 and nothing
more:

1. The table is CD-05's, choice for choice: the four bands, in CD-05's order,
   to the reference day, the reference day, the reference day (the
   twelve-to-seventy-two-hour band's *while-draft* resolution, labelled as
   such) and the reference day minus three. An answer that fits no choice is
   recorded UNCLEAR and resolves to the reference day, the most acute reading.
2. The slot asks CD-05's question and offers CD-05's choices, byte for byte.
3. The reference day is the reference time's own calendar day, in its own
   timezone — the day ``temporal_within`` compares against — and never a
   wall clock; a naive reference time is refused.
4. Every resolved day reads through the engine's tense windows as CD-05 says,
   with the window edges one day either side.
5. Every way a decision could ask for something this build does not do is
   refused, never guessed: an unknown day token, a draft band with no
   while-draft resolution, a band whose final resolution is no longer open, an
   unresolved answer less acute than a choice, a document or the council
   feeding the anchor.

Nothing here decides a clinical value. The twelve-to-seventy-two-hour band's
final resolution stays the invariant-17 literal inside CD-05 under
``draft_needs_source`` (the D18 lane), and this suite asserts it is still open.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.anchor_choices import (
    ANCHOR_DECISION_ID,
    AnchorBasis,
    AnchorChoice,
    AnchorChoiceError,
    AnchorChoiceTable,
    anchor_choice_table,
    load_anchor_choice_table,
    reference_day,
)
from protocols.clinical_decisions import ClinicalDecision, DecisionStatus, load_decision
from protocols.compile.life_threat import load_life_threat_set
from protocols.loader import load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.triage.context import temporal_within
from protocols.triage.expr import Truth
from protocols.types import RuleStatus, SlotType, Tense
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

REPO_ROOT = Path(__file__).resolve().parents[2]
CD05 = REPO_ROOT / "packages" / "protocols" / "decisions" / "CD-05.yaml"
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"
PACK_ROOTS = tuple(
    REPO_ROOT / "packages" / "protocols" / part for part in ("base", "review", "specialty")
)

ANCHOR = "chest_pain.onset_at"
REF = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)

NOW_CHOICE = "şu anda var"
TWELVE_HOURS = "son on iki saat içinde"
TWELVE_TO_72 = "on iki saatten önce ama son üç gün içinde"
OLDER = "üç günden daha önce"

#: CD-05 ``value.choices``, as this build must read it: the band, how many
#: calendar days before the reference day it resolves to, and on what basis.
CD05_CHOICES: tuple[tuple[str, int, AnchorBasis], ...] = (
    (NOW_CHOICE, 0, AnchorBasis.DECIDED),
    (TWELVE_HOURS, 0, AnchorBasis.DECIDED),
    (TWELVE_TO_72, 0, AnchorBasis.WHILE_DRAFT),
    (OLDER, 3, AnchorBasis.DECIDED),
)


def _raw() -> dict[str, Any]:
    loaded = yaml.safe_load(CD05.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _decision() -> ClinicalDecision:
    return load_decision(CD05)


def _table() -> AnchorChoiceTable:
    return load_anchor_choice_table()


def _choice_entry(value: dict[str, Any], choice_tr: str) -> dict[str, Any]:
    entry = next(item for item in value["choices"] if item["choice_tr"] == choice_tr)
    assert isinstance(entry, dict)
    return entry


def _mutated(change: Callable[[dict[str, Any]], None]) -> ClinicalDecision:
    """CD-05 with one change to its ``value``: the near miss of a refusal."""
    decision = _decision()
    value = copy.deepcopy(decision.value)
    change(value)
    return decision.model_copy(update={"value": value})


def _slots(path: Path) -> dict[str, dict[str, Any]]:
    """Every slot of one raw pack document, keyed ``<section>.<slot>``."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    found: dict[str, dict[str, Any]] = {}
    sections = loaded.get("sections") if isinstance(loaded, dict) else None
    for section_id, section in (sections or {}).items():
        for key, slot in ((section or {}).get("slots") or {}).items():
            if isinstance(slot, dict):
                found[f"{section_id}.{key}"] = slot
    return found


# --- 1 · the table is CD-05's ---------------------------------------------------------


def test_the_table_is_cd05_choice_for_choice() -> None:
    table = _table()
    assert table.decision_id == ANCHOR_DECISION_ID == "CD-05"
    assert table.anchors == frozenset({ANCHOR})
    assert table.choices == tuple(
        AnchorChoice(choice_tr=choice, days_before_reference=days, basis=basis)
        for choice, days, basis in CD05_CHOICES
    )
    assert table.choice_texts == tuple(choice for choice, _, _ in CD05_CHOICES)
    assert table.unresolved_days_before_reference == 0


def test_the_table_reads_the_committed_decision_and_not_a_copy() -> None:
    """The choices and the question are CD-05's own strings, in CD-05's order;
    the only anchors resolved are the ones CD-05 marks active."""
    raw = _raw()["value"]
    table = _table()
    assert table.choice_texts == tuple(item["choice_tr"] for item in raw["choices"])
    assert table.question_tr == raw["anchor_question_tr"]
    active = {item["anchor"] for item in raw["anchors"] if item["status"] == "active"}
    drafted = {item["anchor"] for item in raw["anchors"] if item["status"] != "active"}
    assert table.anchors == frozenset(active)
    assert drafted and not (drafted & table.anchors)


@pytest.mark.parametrize(
    ("choice", "days", "basis"), CD05_CHOICES, ids=[c for c, _, _ in CD05_CHOICES]
)
def test_each_authored_choice_resolves_to_its_cd05_day(
    choice: str, days: int, basis: AnchorBasis
) -> None:
    resolution = _table().resolve(ANCHOR, choice, REF)
    assert resolution.resolved_on == (REF.date() - timedelta(days=days)).isoformat()
    assert resolution.basis is basis
    assert resolution.choice_tr == choice  # the record keeps the choice beside the date
    assert (resolution.anchor, resolution.decision_id) == (ANCHOR, "CD-05")


def test_an_answer_that_fits_no_choice_resolves_to_the_most_acute_day() -> None:
    """CD-05 ``unresolved_answer``: recorded UNCLEAR, resolved to the reference
    day — the more acute reading (``ambiguity: more_acute``)."""
    raw = _raw()["value"]["unresolved_answer"]
    assert (raw["answer_state"], raw["resolves_to"], raw["status"]) == (
        "UNCLEAR",
        "reference_day",
        "active",
    )
    resolution = _table().resolve_unresolved(ANCHOR, REF)
    assert resolution.resolved_on == REF.date().isoformat()
    assert resolution.basis is AnchorBasis.UNRESOLVED
    assert resolution.choice_tr is None
    # the most acute reading: no authored choice resolves to a more recent day
    assert all(
        resolution.resolved_on >= _table().resolve(ANCHOR, c, REF).resolved_on
        for c, _, _ in CD05_CHOICES
    )


def test_the_twelve_to_seventy_two_hour_band_stays_open_for_the_d18_lane() -> None:
    """CD-05 leaves the band's final resolution to a signing clinician: it is
    the invariant-17 literal under ``draft_needs_source``. While it is draft,
    CD-05's ``while_draft`` resolution applies — never Unknown — and the record
    carries CD-05's own label for it."""
    entry = _choice_entry(_raw()["value"], TWELVE_TO_72)
    assert entry["status"] == DecisionStatus.DRAFT_NEEDS_SOURCE.value
    assert PLACEHOLDER_SIGNOFF_RE.fullmatch(entry["resolves_to"])
    assert entry["source_gap"].strip()
    while_draft = entry["while_draft"]
    assert (while_draft["resolves_to"], while_draft["never_unknown"]) == ("reference_day", True)
    assert while_draft["record_label"] == AnchorBasis.WHILE_DRAFT.value
    resolution = _table().resolve(ANCHOR, TWELVE_TO_72, REF)
    assert resolution.basis is AnchorBasis.WHILE_DRAFT
    assert resolution.resolved_on == REF.date().isoformat()


def test_no_document_and_no_council_feeds_the_anchor() -> None:
    raw = _raw()["value"]
    assert raw["document_may_feed_anchor"] is False
    assert raw["council_may_fill"] is False
    assert raw["ambiguity"] == "more_acute"


# --- 2 · the slot is CD-05's question and choices ------------------------------------


def test_the_onset_slot_asks_cd05s_question_and_offers_cd05s_choices() -> None:
    pack = load_pack(BASE_INTAKE)
    slot = pack.sections["chest_pain"].slots["onset_at"]
    assert slot.type is SlotType.DATE
    assert slot.choices_tr is not None and slot.ask_tr is not None
    table = _table()
    offered = tuple(slot.choices_tr[TR])
    assert [choice.encode("utf-8") for choice in offered] == [
        choice.encode("utf-8") for choice in table.choice_texts
    ]
    assert slot.ask_tr[TR] == table.question_tr


def test_every_active_anchor_is_the_tense_anchor_of_an_active_life_threat_rule() -> None:
    rules = [entry.rule for entry in load_life_threat_set(LIFE_THREAT).rules]
    active = {rule.tense_anchor for rule in rules if rule.status is RuleStatus.ACTIVE}
    raw = _raw()["value"]["anchors"]
    cd05 = {item["rule"]: item for item in raw if item["status"] == "active"}
    for rule in rules:
        if rule.status is RuleStatus.ACTIVE:
            assert cd05[rule.id]["anchor"] == rule.tense_anchor
            assert cd05[rule.id]["tense"] == rule.tense.value
    assert _table().anchors == frozenset(active)


def test_every_closed_choice_date_slot_in_a_committed_pack_is_a_cd05_anchor() -> None:
    """A date answered by a closed choice needs a decided resolution, or it
    could never bind. Today there is exactly one, and CD-05 resolves it."""
    closed: set[str] = set()
    for root in PACK_ROOTS:
        for path in sorted(root.rglob("*.yaml")):
            for ref, slot in _slots(path).items():
                if slot.get("type") == SlotType.DATE.value and "choices_tr" in slot:
                    closed.add(ref)
    assert closed == {ANCHOR}
    assert closed <= _table().anchors


# --- 3 · the reference day is the reference time's own day ---------------------------


ISTANBUL = timezone(timedelta(hours=3))


@pytest.mark.parametrize(
    ("reference_time", "day"),
    [
        pytest.param(
            datetime(2026, 10, 16, 0, 0, 0, tzinfo=ISTANBUL), "2026-10-16", id="midnight+03"
        ),
        pytest.param(
            datetime(2026, 10, 15, 23, 59, 59, tzinfo=ISTANBUL),
            "2026-10-15",
            id="one-second-before",
        ),
        pytest.param(datetime(2026, 10, 16, 0, 30, tzinfo=ISTANBUL), "2026-10-16", id="00:30+03"),
        pytest.param(
            datetime(2026, 10, 15, 21, 30, tzinfo=UTC), "2026-10-15", id="same-instant-utc"
        ),
        pytest.param(
            datetime(2031, 2, 28, 12, 0, tzinfo=UTC), "2031-02-28", id="not-the-wall-clock"
        ),
    ],
)
def test_the_reference_day_is_the_reference_times_own_calendar_day(
    reference_time: datetime, day: str
) -> None:
    """The day ``temporal_within`` compares against (``reference_time.date()``),
    so a resolved anchor and the tense window can never disagree by a timezone.
    00:30+03 and 21:30 UTC are one instant and two reference days: the caller's
    clock decides, and this module reads no other."""
    assert reference_day(reference_time, 0) == day
    assert _table().resolve(ANCHOR, TWELVE_HOURS, reference_time).resolved_on == day
    assert temporal_within(day, Tense.NOW, reference_time) is Truth.TRUE


@pytest.mark.parametrize(
    ("reference_time", "older"),
    [
        pytest.param(datetime(2027, 3, 1, 9, 0, tzinfo=UTC), "2027-02-26", id="month-edge"),
        pytest.param(datetime(2028, 3, 1, 9, 0, tzinfo=UTC), "2028-02-27", id="leap-year"),
        pytest.param(datetime(2027, 1, 2, 9, 0, tzinfo=UTC), "2026-12-30", id="year-edge"),
    ],
)
def test_reference_day_minus_three_crosses_calendar_edges(
    reference_time: datetime, older: str
) -> None:
    assert _table().resolve(ANCHOR, OLDER, reference_time).resolved_on == older


def test_a_naive_reference_time_is_refused() -> None:
    """A naive time cannot be placed on the session's clock — the same reading
    ``TriageContext`` (``AwareDatetime``) and ``temporal_within`` apply."""
    naive = datetime(2026, 10, 16, 9, 0)
    with pytest.raises(AnchorChoiceError, match="timezone"):
        reference_day(naive, 0)
    with pytest.raises(AnchorChoiceError):
        _table().resolve(ANCHOR, NOW_CHOICE, naive)
    with pytest.raises(AnchorChoiceError):
        _table().resolve_unresolved(ANCHOR, naive)


def test_a_negative_day_count_is_refused() -> None:
    with pytest.raises(AnchorChoiceError):
        reference_day(REF, -1)


# --- 4 · through the engine's tense windows, edges one day either side ---------------


@pytest.mark.parametrize(
    ("choice", "now", "today", "within_7d"),
    [
        pytest.param(NOW_CHOICE, Truth.TRUE, Truth.TRUE, Truth.TRUE, id="now"),
        pytest.param(TWELVE_HOURS, Truth.TRUE, Truth.TRUE, Truth.TRUE, id="twelve-hours"),
        pytest.param(TWELVE_TO_72, Truth.TRUE, Truth.TRUE, Truth.TRUE, id="while-draft"),
        pytest.param(OLDER, Truth.FALSE, Truth.FALSE, Truth.TRUE, id="older"),
    ],
)
def test_each_resolved_day_reads_through_the_tense_windows_as_cd05_says(
    choice: str, now: Truth, today: Truth, within_7d: Truth
) -> None:
    """CD-05: the first three bands sit on the reference day, so the now-tensed
    K2 and the today-tensed SARI may both read True; 'üç günden daha önce' fires
    neither active rule, and a draft within_7d rule would still read True."""
    day = _table().resolve(ANCHOR, choice, REF).resolved_on
    assert temporal_within(day, Tense.NOW, REF) is now
    assert temporal_within(day, Tense.TODAY, REF) is today
    assert temporal_within(day, Tense.WITHIN_7D, REF) is within_7d


def test_near_miss_one_day_either_side_of_each_resolved_day() -> None:
    """The window edges: the reference day is inside ``now`` and the day before
    it is not; the day after is a future anchor and reads Unknown. Three days
    back is inside ``within_7d`` one day either side."""
    today = REF.date()
    assert temporal_within((today - timedelta(days=1)).isoformat(), Tense.NOW, REF) is Truth.FALSE
    assert temporal_within((today + timedelta(days=1)).isoformat(), Tense.NOW, REF) is (
        Truth.UNKNOWN
    )
    for days in (2, 3, 4):
        assert temporal_within(
            (today - timedelta(days=days)).isoformat(), Tense.WITHIN_7D, REF
        ) is (Truth.TRUE)
    older = _table().resolve(ANCHOR, OLDER, REF).resolved_on
    assert older == (today - timedelta(days=3)).isoformat()
    assert older != (today - timedelta(days=2)).isoformat()
    assert older != (today - timedelta(days=4)).isoformat()


# --- 5 · an answer outside the table, or a decision outside this build, is refused ----


@pytest.mark.parametrize(
    "near_miss",
    [
        pytest.param("Şu anda var", id="capitalised"),
        pytest.param("su anda var", id="no-diacritic"),
        pytest.param("şu anda var ", id="trailing-space"),
        pytest.param("bugün", id="calendar-word"),
        pytest.param("2026-10-16", id="an-iso-date"),
        pytest.param("bilmiyorum", id="i-do-not-know"),
    ],
)
def test_near_miss_a_string_that_is_not_an_authored_choice_does_not_resolve(
    near_miss: str,
) -> None:
    """Byte equality with an authored choice, never a fold: a near spelling is
    not a choice, and a date is not something the model may supply. The
    refusal names no value (invariant 6)."""
    with pytest.raises(AnchorChoiceError) as refused:
        _table().resolve(ANCHOR, near_miss, REF)
    assert near_miss.strip() not in str(refused.value)


def test_a_slot_that_is_not_an_anchor_does_not_resolve() -> None:
    with pytest.raises(AnchorChoiceError, match="hpi.onset_date"):
        _table().resolve("hpi.onset_date", NOW_CHOICE, REF)
    with pytest.raises(AnchorChoiceError, match="airway.onset_at"):
        _table().resolve_unresolved("airway.onset_at", REF)


def _set(path: tuple[str | int, ...], new: object) -> Callable[[dict[str, Any]], None]:
    def change(value: dict[str, Any]) -> None:
        node: Any = value
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = new

    return change


def _drop(path: tuple[str | int, ...]) -> Callable[[dict[str, Any]], None]:
    def change(value: dict[str, Any]) -> None:
        node: Any = value
        for part in path[:-1]:
            node = node[part]
        del node[path[-1]]

    return change


def _duplicate_first_choice(value: dict[str, Any]) -> None:
    value["choices"].append(copy.deepcopy(value["choices"][0]))


def _only_draft_anchors(value: dict[str, Any]) -> None:
    for item in value["anchors"]:
        item["status"] = "draft_needs_source"


OPEN_LITERAL = "TO" + "DO: resolving this band requires clinical sign-off"

REFUSALS = [
    pytest.param(_set(("choices", 0, "resolves_to"), "reference_week"), id="unknown-token"),
    pytest.param(_set(("choices", 3, "resolves_to"), "reference_day_minus_0"), id="minus-zero"),
    pytest.param(_set(("choices", 3, "resolves_to"), "reference_day_minus_03"), id="leading-zero"),
    pytest.param(_set(("choices", 0, "resolves_to"), OPEN_LITERAL), id="active-but-open"),
    pytest.param(_set(("choices", 0, "status"), "proposed"), id="unknown-status"),
    pytest.param(_set(("choices", 0, "choice_tr"), ""), id="empty-choice"),
    pytest.param(_set(("choices", 0, "choice_tr"), 7), id="choice-not-a-string"),
    pytest.param(_duplicate_first_choice, id="duplicate-choice"),
    pytest.param(_set(("choices",), []), id="no-choices"),
    pytest.param(_set(("choices",), "şu anda var"), id="choices-not-a-list"),
    pytest.param(_set(("choices", 0), "şu anda var"), id="choice-not-a-mapping"),
    pytest.param(_drop(("choices", 2, "while_draft")), id="draft-without-while-draft"),
    pytest.param(_set(("choices", 2, "while_draft", "never_unknown"), False), id="may-be-unknown"),
    pytest.param(
        _set(("choices", 2, "while_draft", "record_label"), "provisional"), id="other-label"
    ),
    pytest.param(
        _set(("choices", 2, "while_draft", "resolves_to"), OPEN_LITERAL), id="while-draft-open"
    ),
    pytest.param(_set(("choices", 2, "resolves_to"), "reference_day"), id="draft-but-decided"),
    pytest.param(_set(("unresolved_answer", "answer_state"), "DECLINED"), id="not-unclear"),
    pytest.param(
        _set(("unresolved_answer", "status"), "draft_needs_source"), id="unresolved-draft"
    ),
    pytest.param(
        _set(("unresolved_answer", "resolves_to"), "reference_day_minus_3"), id="less-acute"
    ),
    pytest.param(_drop(("unresolved_answer",)), id="no-unresolved-rule"),
    pytest.param(_set(("ambiguity",), "less_acute"), id="other-ambiguity"),
    pytest.param(_set(("document_may_feed_anchor",), True), id="document-feeds"),
    pytest.param(_set(("council_may_fill",), True), id="council-fills"),
    pytest.param(_only_draft_anchors, id="no-active-anchor"),
    pytest.param(_set(("anchors", 0, "anchor"), ""), id="empty-anchor"),
    pytest.param(_set(("anchors",), {}), id="anchors-not-a-list"),
    pytest.param(_set(("anchor_question_tr",), ""), id="no-question"),
]


@pytest.mark.parametrize("change", REFUSALS)
def test_a_decision_this_build_cannot_follow_exactly_is_refused(
    change: Callable[[dict[str, Any]], None],
) -> None:
    """Each one change to CD-05 asks for a resolution this module does not
    build. It is refused at load — before a session is composed — rather than
    guessed, defaulted or left to read Unknown."""
    with pytest.raises(AnchorChoiceError):
        anchor_choice_table(_mutated(change))


def test_near_miss_the_unchanged_decision_builds() -> None:
    """The refusals above are each one change away from a table that builds."""
    assert anchor_choice_table(_mutated(lambda value: None)) == _table()


def test_a_decision_that_is_itself_draft_is_refused() -> None:
    draft = _decision().model_copy(update={"status": DecisionStatus.DRAFT_NEEDS_SOURCE})
    with pytest.raises(AnchorChoiceError, match="draft_needs_source"):
        anchor_choice_table(draft)


def test_the_resolution_record_shows_no_choice_and_no_date() -> None:
    """invariant 6: the record's repr names the anchor and the basis, never
    what the patient chose or the day it resolved to."""
    resolution = _table().resolve(ANCHOR, TWELVE_TO_72, REF)
    shown = f"{resolution!r} {resolution}"
    assert TWELVE_TO_72 not in shown
    assert resolution.resolved_on not in shown
    assert ANCHOR in shown and AnchorBasis.WHILE_DRAFT.value in shown
