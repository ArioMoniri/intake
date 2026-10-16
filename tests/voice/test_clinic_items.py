"""INT-547 — the clinic is told when chest-pain arms stay unresolved.

GitHub #927, split from #917 finding F3. Verified decisions already decide a clinician-only
clinic-inbox item, and nothing raised it in a live session:

- **CD-04** ``unresolved_after_follow_up``: a CD-01 chest-pain slot still
  UNCLEAR after its ``follow_up_tr`` has been asked once raises a CD-08 item,
  kind ``chest_pain_arms_unresolved`` — under three-valued logic it can leave
  both chest-pain arms silent, so the session can end GREEN on a pain nobody
  could characterise (the golden ``hedge/c2-karakter-belirsiz``).

What this suite holds, on both profiles, over the committed ``base.intake`` and
the committed active ``base.life_threat`` rules:

1. The item is raised exactly when its decision says, at most once per
   session, ids and closed kinds only (invariant 6), through the clinic route
   the RED already uses (the Safety inbox, INT-406/INT-475), audited
   (invariant 4).
2. Near misses: a slot resolved by its follow-up, a hedge whose follow-up is
   not yet spent, an anchor closed before its follow-up was ever asked
   (rounds 1 and 2 of CD-04; round 3 is pending on INT-519), and an UNCLEAR
   slot CD-04 does not name.
3. The item is not a RED: it never carries a priority, never changes the Work's
   determination and never seals the queue (invariants 1 and 9). A route that
   fails costs the Work nothing, pages, and the item lands on a later Work.
4. A session that serves the chest-pain rules and has no route for the items
   is not composed; one that serves no such rule has nothing to raise.

The gateway is a table keyed by what the patient said; nothing dials a model.
The transcripts are synthetic (files/04 §7).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import fakeredis
import pytest
import test_extraction_valuesets as int518
import test_live_triage as int521
import test_onset_anchor as int522
from clinic_item_harness import RecordingClinicItems
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from intake_platform.audit import GENESIS_PREV_HASH, AuditChain, InMemoryAuditStore
from intake_platform.safety_inbox import (
    EntryKind,
    RedisSafetyInboxStore,
    SafetyInbox,
    SafetyInboxOutbox,
)
from intake_voice_runtime.clinical_agent.clinic_items import (
    ClinicItem,
    ClinicItemRouteMissing,
    ClinicItemWatch,
    clinic_item_id,
)
from intake_voice_runtime.clinical_agent.work_queue import StateContext, StateEffect
from intake_voice_runtime.composition import (
    RedWiring,
    build_residency_tr_session,
    build_typed_session,
)
from intake_voice_runtime.ports import WorkRequest, WorkState, WorkType
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.safety_inbox import ClinicItemNotifier
from intake_voice_runtime.talker.preemption import Priority
from prometheus_client import REGISTRY
from protocols.clinic_items import ClinicItemKind, load_clinic_item_rules
from protocols.triage import evaluate_triage
from pydantic import ValidationError
from red_harness import RecordingClinicNotifier, RecordingDataChannel
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingScreen,
    RecordingSink,
    RecordingSynthesizer,
)

K2 = int522.K2
SARI = int521.SARI
SUBJECT = int522.SUBJECT
PRESENT = int522.PRESENT
CHARACTER = int522.CHARACTER
RADIATION = int522.RADIATION
ONSET = int522.ONSET
ARMS = ClinicItemKind.CHEST_PAIN_ARMS_UNRESOLVED
CHEST_RULES = (K2, SARI)

#: What the patient says, synthetic. The model double flags the hedges (the
#: extraction contract's rule 8) and records nothing for them.
HEDGE = "Bilmiyorum."
STILL_HEDGED = "Hatırlamıyorum ki."
LAST_HEDGE = "Gerçekten bilemiyorum."
SAID_BASKI = "Daha çok bir baskı gibi."
FREE_DATE = "hpi.onset_date"


def _seven() -> tuple[str, ...]:
    return tuple(sorted(load_clinic_item_rules().arms.slots))


def _model(
    character: str = "baskı",
    *,
    extra: Mapping[str, Mapping[str, JsonValue]] | None = None,
    clarify: tuple[str, ...] = (HEDGE, STILL_HEDGED, LAST_HEDGE),
) -> int522.SpokenModel:
    lines: dict[str, Mapping[str, JsonValue]] = {
        HEDGE: {},
        STILL_HEDGED: {},
        LAST_HEDGE: {},
        SAID_BASKI: {CHARACTER: "baskı"},
    }
    lines.update(extra or {})
    return int522._model(character, "yok", extra=lines, clarify=clarify)


def _route(rig: int522.Rig) -> RecordingClinicItems:
    watch = rig.stack.clinic_items
    assert watch is not None
    return cast(RecordingClinicItems, watch.route)


def _watch(rig: int522.Rig) -> ClinicItemWatch:
    watch = rig.stack.clinic_items
    assert watch is not None
    return watch


def _reentry(rig: int522.Rig, origin: str) -> str:
    [reentry] = [step for step in rig.stack.engine.follow_ups if step.startswith(origin)]
    return reentry


def _hedge_until_unclear(rig: int522.Rig, slot: str) -> str:
    """Ask ``slot``, answer 'bilmiyorum', and answer every follow-up the engine
    gives it with another hedge until it records UNCLEAR. Returns the last Work."""
    work_id = int522._say(rig, slot, HEDGE)
    for said in (STILL_HEDGED, LAST_HEDGE):
        if rig.stack.engine.state_of(slot) is AnswerState.UNCLEAR:
            break
        work_id = int522._say(rig, _reentry(rig, slot), said)
    assert rig.stack.engine.state_of(slot) is AnswerState.UNCLEAR
    return work_id


def _to_character(rig: int522.Rig) -> None:
    int522._say(rig, SUBJECT, int522.SAID[SUBJECT])
    int522._say(rig, PRESENT, int522.SAID[PRESENT])


def _raised(kind: ClinicItemKind) -> float:
    value = REGISTRY.get_sample_value("clinic_inbox_items_raised_total", {"kind": kind.value})
    return value or 0.0


def _route_failures(kind: ClinicItemKind) -> float:
    value = REGISTRY.get_sample_value(
        "clinic_inbox_item_route_failures_total", {"kind": kind.value}
    )
    return value or 0.0


def _unaudited(kind: ClinicItemKind) -> float:
    value = REGISTRY.get_sample_value("clinic_inbox_item_unaudited_total", {"kind": kind.value})
    return value or 0.0


# --- 0 · the item: ids and closed kinds, never a priority -----------------------------------


def _item(**overrides: Any) -> ClinicItem:
    fields: dict[str, Any] = {
        "item_id": clinic_item_id(int518.SESSION, ARMS),
        "kind": ARMS,
        "session_id": int518.SESSION,
        "slot_refs": (CHARACTER,),
        "rule_ids": CHEST_RULES,
        "decision_ids": ("CD-04", "CD-08"),
    }
    fields.update(overrides)
    return ClinicItem(**fields)


def test_an_item_carries_ids_and_closed_kinds_and_nothing_a_queue_reads_as_priority() -> None:
    assert set(ClinicItem.model_fields) == {
        "item_id",
        "kind",
        "session_id",
        "slot_refs",
        "rule_ids",
        "decision_ids",
    }
    item = _item()
    for forbidden in ("priority", "register", "location", "level", "triage_update"):
        with pytest.raises(ValidationError):
            ClinicItem.model_validate({**item.model_dump(), forbidden: "preempt"})
    with pytest.raises(ValidationError):
        ClinicItem.model_validate({**item.model_dump(), "kind": "red"})


def test_the_item_id_is_derived_from_the_session_and_the_kind() -> None:
    first = clinic_item_id(int518.SESSION, ARMS)
    assert first == clinic_item_id(int518.SESSION, ARMS)
    assert first != clinic_item_id("22222222-2222-4333-8444-555555555555", ARMS)
    assert first.startswith("ci_") and len(first) == 35


@pytest.mark.parametrize(
    ("field", "prose"),
    [
        ("slot_refs", ("göğsümde baskı var",)),
        ("rule_ids", ("Kalp krizi olabilir",)),
        ("session_id", "Ayşe Yılmaz"),
    ],
)
def test_prose_is_refused_and_never_echoed(field: str, prose: object) -> None:
    with pytest.raises(ValidationError) as raised:
        _item(**{field: prose})
    text = prose if isinstance(prose, str) else prose[0]  # type: ignore[index]
    assert text not in str(raised.value)


def test_each_kind_is_a_clinic_item_kind_of_the_inbox() -> None:
    for kind in ClinicItemKind:
        assert EntryKind(kind.value).is_clinic_item


# --- 1 · the arms item: CD-04 ----------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_character_still_unclear_after_its_follow_up_raises_the_item_once(
    profile: VoiceProfile,
) -> None:
    """The golden ``hedge/c2-karakter-belirsiz``, live: 'bilmiyorum' to the
    character survives its follow-ups, both arms read Unknown, nothing fires —
    and the clinic is told, once, by ids."""
    rig = int522._rig(profile, _model())
    before = _raised(ARMS)
    _to_character(rig)
    _hedge_until_unclear(rig, CHARACTER)
    assert _route(rig).items == [
        _item(item_id=clinic_item_id(int518.SESSION, ARMS), slot_refs=(CHARACTER,))
    ]
    assert _raised(ARMS) - before == 1
    assert list(_watch(rig).raised) == [ARMS]
    assert rig.clinic.notifications == [] and rig.stack.agent.sealed is False
    # a second slot left unresolved later in the session raises nothing more
    _hedge_until_unclear(rig, RADIATION)
    assert len(_route(rig).items) == 1 and _route(rig).calls == 1
    assert _raised(ARMS) - before == 1


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_follow_up_answered_with_a_choice_raises_nothing(
    profile: VoiceProfile,
) -> None:
    """The arm resolves: the character binds on its follow-up, and the session
    has nothing unresolved to tell the clinic."""
    rig = int522._rig(profile, _model())
    _to_character(rig)
    int522._say(rig, CHARACTER, HEDGE)
    int522._say(rig, _reentry(rig, CHARACTER), SAID_BASKI)
    assert rig.stack.engine.value_of(CHARACTER) == "baskı"
    assert _route(rig).items == [] and _watch(rig).raised == {}


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_hedge_whose_follow_up_is_not_yet_spent_raises_nothing(
    profile: VoiceProfile,
) -> None:
    rig = int522._rig(profile, _model())
    _to_character(rig)
    int522._say(rig, CHARACTER, HEDGE)
    assert rig.stack.engine.state_of(CHARACTER) is AnswerState.ASKED_PENDING
    assert _route(rig).items == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_session_that_answers_every_chest_pain_slot_raises_nothing(
    profile: VoiceProfile,
) -> None:
    rig = int522._rig(profile, _model(extra=int522._onset(int522.OLDER)))
    int522._lead(rig)
    int522._say(rig, ONSET, int522.SAID_ONSET[int522.OLDER])
    assert rig.stack.engine.value_of(ONSET) == int522._day(3)
    assert _route(rig).items == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_an_unresolved_onset_raises_the_item_beside_k2_and_the_red_is_untouched(
    profile: VoiceProfile,
) -> None:
    """CD-04: for the onset the anchor is also resolved by CD-05's more-acute
    rule; the item still records that the patient could not date the episode.
    K2 fires on the same Work, through its own route, exactly as before."""
    rig = int522._rig(profile, _model())
    int522._lead(rig)
    int522._say(rig, ONSET, HEDGE)
    last = int522._say(rig, _reentry(rig, ONSET), STILL_HEDGED)
    assert [(item.kind, item.slot_refs) for item in _route(rig).items] == [(ARMS, (ONSET,))]
    assert [n.rule_ids for n in rig.clinic.notifications] == [(K2,)]
    [result] = [r for r in rig.stack.agent.drain_results() if r.work_id == last]
    expected = evaluate_triage(
        int521._served_rules(), rig.triage.context(rig.stack.engine), RedLocation.REMOTE
    ).result
    assert result.presentation.triage_update == expected
    assert expected.level is TriageLevel.RED and result.priority is Priority.PREEMPT


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_close_raises_the_item_for_an_onset_whose_follow_up_was_asked(
    profile: VoiceProfile,
) -> None:
    """'Bilmiyorum.', the follow-up spoken, and the patient is gone: the close
    records the anchor UNCLEAR after its follow-up, and the item is raised on
    the close Work."""
    rig = int522._rig(profile, _model("başka bir his"))
    int522._lead(rig)
    int522._say(rig, ONSET, HEDGE)
    rig.stack.session.ask_ledger.note_asked(_reentry(rig, ONSET))  # the follow-up is spoken
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    assert rig.stack.agent.record(ticket.work_id).state is WorkState.COMPLETED
    assert rig.stack.engine.state_of(ONSET) is AnswerState.UNCLEAR
    assert [(item.kind, item.slot_refs) for item in _route(rig).items] == [(ARMS, (ONSET,))]
    assert rig.clinic.notifications == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("hedged", [False, True])
def test_near_miss_an_onset_closed_before_its_follow_up_was_asked_raises_nothing(
    profile: VoiceProfile, hedged: bool
) -> None:
    """CD-04 rounds 1 and 2 raise the item after the follow-up has been asked.
    An onset asked and never answered — or hedged, its follow-up queued and
    never spoken — is closed UNCLEAR with no follow-up asked. Raising it at
    close is the round-3 amendment pending on INT-519 (items 5, 10 and 11)."""
    rig = int522._rig(profile, _model("başka bir his"))
    int522._lead(rig)
    if hedged:
        int522._say(rig, ONSET, HEDGE)
    else:
        rig.stack.session.ask_ledger.note_asked(ONSET)
        rig.stack.agent.run_pending()
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    assert rig.stack.engine.state_of(ONSET) is AnswerState.UNCLEAR
    assert _route(rig).items == []


# --- 2 · the item is not a RED -----------------------------------------------------------------


def test_the_watch_returns_the_handlers_own_effect_and_adds_nothing_to_it() -> None:
    """Invariant 1: the watch wraps a state handler and hands back the very
    effect object the handler returned — it has no way to add a
    determination, and a StateEffect has no priority field to set."""
    rig = int522._rig(VoiceProfile.TYPED, _model())
    effect = StateEffect()

    def inner(context: StateContext) -> StateEffect:
        return effect

    wrapped = _watch(rig).wrap(inner)
    request = WorkRequest(
        session_id=int518.SESSION,
        work_type=WorkType.EXTRACT_SLOTS,
        step_id=SUBJECT,
        input_hash="0" * 64,
        protocol_hash=int518.HASH,
        engine_version=0,
    )
    context = StateContext(request=request, engine=rig.stack.engine)
    assert wrapped(context) is effect


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_work_that_raised_the_item_settles_routine_and_seals_nothing(
    profile: VoiceProfile,
) -> None:
    rig = int522._rig(profile, _model())
    _to_character(rig)
    last = _hedge_until_unclear(rig, CHARACTER)
    [result] = [r for r in rig.stack.agent.drain_results() if r.work_id == last]
    assert result.priority is Priority.NORMAL
    assert result.presentation.triage_update is None or (
        result.presentation.triage_update.level is not TriageLevel.RED
    )
    assert rig.stack.agent.sealed is False and rig.channel.published == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_route_that_fails_costs_the_work_nothing_pages_and_the_item_lands_later(
    profile: VoiceProfile, caplog: pytest.LogCaptureFixture
) -> None:
    """CD-08: never dropped; a delivery failure counts as an SLA breach and is
    an emitted event. The Work completes and is evaluated as usual; the next
    Work raises the item again, and it lands once."""
    rig = int522._rig(profile, _model())
    _route(rig).fail = 1
    before = _route_failures(ARMS)
    _to_character(rig)
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.clinical_agent.clinic_items"):
        last = _hedge_until_unclear(rig, CHARACTER)
    assert rig.stack.agent.record(last).state is WorkState.COMPLETED
    assert _route(rig).items == [] and _watch(rig).raised == {}
    assert _route_failures(ARMS) - before == 1
    [record] = [r for r in caplog.records if r.getMessage() == "clinic item route failed"]
    assert (record.session_id, record.kind) == (int518.SESSION, ARMS.value)  # type: ignore[attr-defined]
    int522._say(rig, RADIATION, int518.TRANSCRIPTS[3][1])
    assert [item.kind for item in _route(rig).items] == [ARMS]
    assert _route(rig).calls == 2


# --- 4 · composition --------------------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_session_serving_the_chest_pain_rules_with_no_item_route_is_not_composed(
    profile: VoiceProfile,
) -> None:
    clock = FakeClock()
    red = RedWiring(
        location=RedLocation.REMOTE,
        channel=RecordingDataChannel(clock=clock),
        scripts=int521._scripts(),
    )
    common: dict[str, Any] = {
        "protocol": int521._served_protocol(),
        "reference_time": int518.NOW,
        "session_id": int518.SESSION,
        "protocol_hash": int518.HASH,
        "gateway": int518.AnswerTable({}),
        "memory": InMemoryPatientMemory(),
        "tenant_id": int518.TENANT,
        "clinic": RecordingClinicNotifier(),
        "clock": clock,
        "red": red,
    }
    with pytest.raises(ClinicItemRouteMissing, match=ARMS.value):
        if profile is VoiceProfile.TYPED:
            build_typed_session(**common, screen=RecordingScreen())
        else:
            build_residency_tr_session(
                **common,
                voice_id=int518.VOICE_ID,
                synthesizer=RecordingSynthesizer(),
                clip_store=RecordedClipStore(),
                sink=RecordingSink(clock=clock),
            )


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_session_serving_no_rule_has_nothing_to_raise(profile: VoiceProfile) -> None:
    stack = int518._compose(profile, protocol=int518._base_intake(), gateway=int518.AnswerTable({}))
    assert stack.clinic_items is None


def test_both_roots_compose_the_watch_with_the_committed_decisions() -> None:
    for profile in VoiceProfile:
        rig = int522._rig(profile, _model())
        watch = _watch(rig)
        assert watch.rules == load_clinic_item_rules()
        assert watch.session_id == int518.SESSION
        assert set(watch.arms) == set(_seven())
        assert watch.arms["trauma.recent"] == (SARI,)  # only the SARI arm reads it
        assert all(watch.arms[slot] == CHEST_RULES for slot in (PRESENT, CHARACTER, ONSET))


def test_a_session_whose_served_rules_read_no_chest_pain_slot_has_no_watch() -> None:
    """No chest-pain arm is served, so there is none to leave unresolved, and
    no route is asked for."""
    k2 = next(rule for rule in int521._served_rules() if rule.id == K2)
    other = k2.model_copy(
        update={
            "id": "rf.sentetik_baska",
            "when": "hpi.trajectory == 'daha kötü'",
            "tense_anchor": "hpi.onset_date",
        }
    )
    protocol = int521._served_protocol((other,))
    assert ClinicItemWatch.for_protocol(protocol, route=None, session_id=int518.SESSION) is None


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_an_unclear_slot_cd04_does_not_name_raises_nothing(
    profile: VoiceProfile,
) -> None:
    """The free complaint-onset date hedged to UNCLEAR after its follow-ups is
    a gap in the note, not a chest-pain arm."""
    rig = int522._rig(profile, _model())
    _to_character(rig)
    _hedge_until_unclear(rig, FREE_DATE)
    assert _route(rig).items == []


# --- 5 · the production route: the Safety inbox, audited ---------------------------------------


TENANT = int518.TENANT


def _notifier(audit: AuditChain, outbox: SafetyInboxOutbox) -> ClinicItemNotifier:
    return ClinicItemNotifier(
        outbox=outbox,
        audit=audit,
        tenant_id=TENANT,
        session_id=int518.SESSION,
        visit_id=int518.SESSION,
    )


def test_the_notifier_puts_one_entry_and_appends_one_audit_row() -> None:
    audit = AuditChain(InMemoryAuditStore())
    outbox = SafetyInboxOutbox()
    item = _item()
    _notifier(audit, outbox).raise_item(item)
    [entry] = outbox.pending()
    assert entry.kind is EntryKind.CHEST_PAIN_ARMS_UNRESOLVED
    assert (entry.source_ref, entry.rule_ids, entry.session_id) == (
        item.item_id,
        CHEST_RULES,
        int518.SESSION,
    )
    [row] = audit.export_worm().decode().splitlines()[:-1]
    assert '"action":"voice.clinic_item.raised"' in row
    assert f'"resource_ref":"safety_inbox:{TENANT}:{entry.entry_id}"' in row
    assert '"consent_scope_ref":"scope:core"' in row
    assert '"actor":"svc:voice-runtime"' in row
    assert audit.verify().ok


def test_raising_an_item_twice_is_one_entry_in_the_store() -> None:
    audit = AuditChain(InMemoryAuditStore())
    outbox = SafetyInboxOutbox()
    notifier = _notifier(audit, outbox)
    notifier.raise_item(_item())
    notifier.raise_item(_item())
    store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis())
    outbox.flush(store)
    assert len(store.tenant_entries(TENANT)) == 1


class _BrokenAudit:
    def append(self, **_: str) -> object:
        raise RuntimeError("synthetic audit store fault")


class _BrokenOutbox(SafetyInboxOutbox):
    def put(self, entry: object) -> None:  # type: ignore[override]
        raise RuntimeError("synthetic outbox fault")


def test_a_failed_audit_append_is_counted_and_the_entry_is_still_put() -> None:
    """INT-475's order: the clinic first, the paperwork after; a row that could
    not be written is counted rather than holding the item back."""
    outbox = SafetyInboxOutbox()
    before = _unaudited(ARMS)
    notifier = ClinicItemNotifier(
        outbox=outbox,
        audit=cast(AuditChain, _BrokenAudit()),
        tenant_id=TENANT,
        session_id=int518.SESSION,
        visit_id=int518.SESSION,
    )
    notifier.raise_item(_item())
    assert len(outbox.pending()) == 1
    assert _unaudited(ARMS) - before == 1


def test_a_failed_put_raises_and_writes_no_audit_row() -> None:
    """No entry, no share to audit: the watch counts the failure and retries."""
    audit = AuditChain(InMemoryAuditStore())
    with pytest.raises(RuntimeError):
        _notifier(audit, _BrokenOutbox()).raise_item(_item())
    assert audit.head == GENESIS_PREV_HASH


@pytest.mark.parametrize("field", ["tenant_id", "session_id", "visit_id"])
def test_the_notifier_refuses_a_mis_shaped_binding(field: str) -> None:
    kwargs: dict[str, Any] = {
        "outbox": SafetyInboxOutbox(),
        "audit": AuditChain(InMemoryAuditStore()),
        "tenant_id": TENANT,
        "session_id": int518.SESSION,
        "visit_id": int518.SESSION,
    }
    kwargs[field] = "Ayşe Yılmaz"
    with pytest.raises(ValueError) as raised:
        ClinicItemNotifier(**kwargs)
    assert "Ayşe" not in str(raised.value)


def test_the_notifier_refuses_an_item_of_another_session() -> None:
    notifier = _notifier(AuditChain(InMemoryAuditStore()), SafetyInboxOutbox())
    other = _item(session_id="22222222-2222-4333-8444-555555555555")
    with pytest.raises(ValueError, match="another session"):
        notifier.raise_item(other)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_end_to_end_the_item_reaches_the_console_queue_with_no_sla(
    profile: VoiceProfile, caplog: pytest.LogCaptureFixture
) -> None:
    """The live session, the production route, the shared store and the
    console's queue: the clinic sees the item by kind and ids, with no SLA
    (CD-08 leaves it draft), and no transcript reaches the item, the entry,
    the audit row or a log line (invariant 6)."""
    audit = AuditChain(InMemoryAuditStore())
    outbox = SafetyInboxOutbox()
    rig = int522._rig(profile, _model(), clinic_items=_notifier(audit, outbox))
    with caplog.at_level(logging.DEBUG):
        _to_character(rig)
        _hedge_until_unclear(rig, CHARACTER)
    store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis())
    outbox.flush(store)
    [row] = SafetyInbox(store=store).queue(TENANT, datetime.now(UTC))
    assert row.entry.kind is EntryKind.CHEST_PAIN_ARMS_UNRESOLVED
    assert row.entry.rule_ids == CHEST_RULES
    assert row.sla is None and row.band is None
    assert audit.verify().ok
    spoken = (HEDGE, STILL_HEDGED, LAST_HEDGE, *int522.SAID.values())
    shown = " ".join(
        [
            row.entry.model_dump_json(),
            audit.export_worm().decode(),
            *(record.getMessage() + str(record.__dict__) for record in caplog.records),
        ]
    )
    for said in spoken:
        assert said not in shown
