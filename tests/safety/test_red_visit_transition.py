"""INT-407 — a RED visit cannot silently move (files/02 §2b; invariant 49's last clause).

files/02 §2b, verbatim: *"A visit carrying an unresolved RED cannot silently
move. ``rescheduled`` or ``cancelled`` on a RED visit raises a clinic inbox
entry regardless of connector presence and re-shows the crisis signposting to
the patient in the register the original RED used (§5.3)."* And why: *"a
RED-flagged patient whose appointment moves two weeks out is invisible to
everyone … The alert fired, the patient rescheduled, and the system forgot."*

INT-406 built :meth:`SafetyInbox.visit_transition` with no caller. This suite
drives the real patient route — ``POST /v1/visits/{id}/transitions`` — over the
production Redis inbox store on ``fakeredis``, with **no connector wired at
all**, and a faked wall clock the inbox stamps, so nothing sleeps.

The re-show is a **pointer, never words**: the rule, the register the RED was
told in, and a location. Invariant 21 puts every RED script on the device
before the session starts; the server therefore sends nothing a device could
render except what the device already holds (the same argument as the
data-channel ``RedTriggerMessage``). The location is re-derived for where the
patient now stands — which, outside a session, cannot be known, so it is
``UNKNOWN`` and costs the rule's one question (files/02 §5.3 Axis 3) rather
than offering 112 to someone who may be in the building.

Near-miss controls beside every positive: a visit with no RED, a RED on
another visit, a confirm on a RED visit, a ``DEFERRED_CLINICIAN`` RED (clinic
entry, no patient re-show), and a RED whose register was never recorded (clinic
entry, no invented register). The inbox unwired or unreachable refuses the
move rather than letting it happen silently.

Everything is SYNTHETIC: rule ids carry no clinical meaning.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from clinical_schemas.triage import RedLocation, RedRegister
from intake_platform.safety_inbox import (
    EntryKind,
    InboxEntry,
    RedisSafetyInboxStore,
    SafetyInbox,
    SafetyInboxOutbox,
    SafetyInboxUnavailable,
    entry_id_for,
)
from intake_voice_runtime.safety_inbox import SafetyInboxNotifier
from intake_voice_runtime.talker.red_path import RedNotification

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import (  # noqa: E402
    ADMIN_TOKEN,
    PATIENT_TOKEN,
    ApiHarness,
    build_harness,
)
from intake_api.dev_fixture import DEV_TENANT_ID  # noqa: E402

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
TENANT = str(DEV_TENANT_ID)
RED_RULE = "rf.sentetik_kirmizi"
SECOND_RULE = "rf.sentetik_ikinci"
VISIT_BODY = {
    "hospital": "Sentetik Hastane",
    "department": "Sentetik Bölüm",
    "date": "2026-09-20",
    "time": "14:30",
    "time_source": "patient_entry",
}
RESCHEDULE = {
    "to": "rescheduled",
    "date": "2026-10-05",
    "time": "10:00",
    "time_source": "patient_entry",
}


class Clock:
    def __init__(self, at: datetime) -> None:
        self.now = at

    def __call__(self) -> datetime:
        return self.now


class Rig:
    def __init__(self, harness: ApiHarness, store: RedisSafetyInboxStore, clock: Clock) -> None:
        self.harness = harness
        self.store = store
        self.clock = clock

    def visit(self) -> str:
        response = self.harness.client.post(
            "/v1/visits", json=VISIT_BODY, headers=self.harness.patient()
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    def red(
        self,
        visit_id: str,
        *,
        work_id: str = "w-red-1",
        register: RedRegister | None = RedRegister.CALM,
        rule_ids: tuple[str, ...] = (RED_RULE,),
    ) -> InboxEntry:
        """A rules-engine RED as the runtime's notifier files it (the entry
        shape INT-406 writes; the register is the RED's own)."""
        return self.store.add(
            InboxEntry.for_red(
                tenant_id=TENANT,
                session_id=visit_id,
                visit_id=visit_id,
                work_id=work_id,
                rule_ids=rule_ids,
                register=register,
                at=T0 - timedelta(days=2),
            )
        )

    def move(self, visit_id: str, **body: Any) -> Any:
        return self.harness.client.post(
            f"/v1/visits/{visit_id}/transitions", json=body, headers=self.harness.patient()
        )

    def transition_entries(self) -> list[InboxEntry]:
        return [entry for entry in self.store.open_entries() if entry.kind is not EntryKind.RED]


def _harness(tmp_path: Path, clock: Clock, inbox: SafetyInbox | None) -> Iterator[ApiHarness]:
    harnesses = build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, safety_inbox=inbox
    )
    harness = next(harnesses)
    harness.client.app.state.api.clock = clock  # type: ignore[attr-defined]
    yield harness
    for _ in harnesses:
        pass


@pytest.fixture()
def rig(tmp_path: Path) -> Iterator[Rig]:
    clock = Clock(T0)
    store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis())
    for harness in _harness(tmp_path, clock, SafetyInbox(store=store)):
        yield Rig(harness, store, clock)


# ======================================================================================
# the rule: reschedule or cancel on a RED visit raises an entry, connector or not
# ======================================================================================


@pytest.mark.parametrize(
    ("body", "kind"),
    [(RESCHEDULE, EntryKind.VISIT_RESCHEDULED), ({"to": "cancelled"}, EntryKind.VISIT_CANCELLED)],
)
def test_a_red_visit_that_moves_raises_a_clinic_entry_without_any_connector(
    rig: Rig, body: dict[str, str], kind: EntryKind
) -> None:
    visit_id = rig.visit()
    rig.red(visit_id)
    # no connector anywhere: the hospital connector slot is empty
    assert rig.harness.client.app.state.api.acibadem is None  # type: ignore[attr-defined]
    rig.clock.now = T0 + timedelta(hours=3)

    moved = rig.move(visit_id, **body)
    assert moved.status_code == 200, moved.text

    (entry,) = rig.transition_entries()
    assert entry.kind is kind
    assert entry.visit_id == visit_id
    assert entry.rule_ids == (RED_RULE,)
    assert entry.source_ref == moved.json()["transition_id"]
    # the entry's clock starts at the transition, on the faked wall clock
    assert entry.created_at == rig.clock.now
    assert entry.is_open


def test_an_acknowledged_red_still_moves_loudly(rig: Rig) -> None:
    """Nothing records a RED as resolved; an acknowledgement says a human saw
    it. The reading that raises more entries, never fewer (INT-406)."""
    visit_id = rig.visit()
    red = rig.red(visit_id)
    rig.store.acknowledge(TENANT, red.entry_id, by="kc-sub-clinical", at=T0)
    assert rig.move(visit_id, to="cancelled").status_code == 200
    assert [entry.kind for entry in rig.transition_entries()] == [EntryKind.VISIT_CANCELLED]


# ======================================================================================
# the re-show: the original RED, in its own register, as a pointer
# ======================================================================================


@pytest.mark.parametrize("register", [RedRegister.ALERT, RedRegister.CALM, RedRegister.SILENT])
@pytest.mark.parametrize("body", [RESCHEDULE, {"to": "cancelled"}])
def test_the_red_is_re_shown_in_the_register_it_was_told_in(
    rig: Rig, register: RedRegister, body: dict[str, str]
) -> None:
    visit_id = rig.visit()
    red = rig.red(visit_id, register=register, rule_ids=(RED_RULE, SECOND_RULE))
    moved = rig.move(visit_id, **body)
    assert moved.status_code == 200, moved.text
    expected = {
        "work_id": red.source_ref,
        # the addressed rule is the first, as on the data-channel trigger
        "rule_id": RED_RULE,
        "register": register.value,
        # outside a session nobody knows where the patient stands: the rule's
        # one question, never a 112 offered into a building (Axis 3)
        "location": RedLocation.UNKNOWN.value,
    }
    assert moved.json()["red_resurface"] == [expected]
    # persistent on the visit card, not a transient modal (files/02 §5.3)
    read = rig.harness.client.get(f"/v1/visits/{visit_id}", headers=rig.harness.patient())
    assert read.json()["red_resurface"] == [expected]


def test_the_re_show_carries_no_words(rig: Rig) -> None:
    """Invariant 21: the script is pre-positioned on the device; the server
    sends a pointer, so no field could carry a sentence, a number or a 112."""
    visit_id = rig.visit()
    rig.red(visit_id)
    (item,) = rig.move(visit_id, to="cancelled").json()["red_resurface"]
    assert set(item) == {"work_id", "rule_id", "register", "location"}


def test_every_red_on_the_visit_is_re_shown(rig: Rig) -> None:
    visit_id = rig.visit()
    rig.red(visit_id, work_id="w-red-1", register=RedRegister.ALERT)
    rig.red(visit_id, work_id="w-red-2", register=RedRegister.SILENT, rule_ids=(SECOND_RULE,))
    items = rig.move(visit_id, **RESCHEDULE).json()["red_resurface"]
    assert sorted((item["work_id"], item["register"]) for item in items) == [
        ("w-red-1", "ALERT"),
        ("w-red-2", "SILENT"),
    ]


def test_a_deferred_clinician_red_reaches_the_clinic_and_leaves_the_patient_screen_alone(
    rig: Rig,
) -> None:
    """files/02 §5.3: DEFERRED_CLINICIAN — *"Patient screen unchanged. Finding
    routes to the clinician only."* The move still raises the clinic entry."""
    visit_id = rig.visit()
    rig.red(visit_id, register=RedRegister.DEFERRED_CLINICIAN)
    moved = rig.move(visit_id, to="cancelled")
    assert moved.status_code == 200
    assert moved.json()["red_resurface"] == []
    assert [entry.kind for entry in rig.transition_entries()] == [EntryKind.VISIT_CANCELLED]


def test_a_red_whose_register_was_never_recorded_is_never_given_one(rig: Rig) -> None:
    """A default register would be chosen once, by an engineer, for every
    future RED — *"which is how the paediatric airway case gets an alarm"*.
    The clinic entry is raised; the patient re-show is withheld, not guessed."""
    visit_id = rig.visit()
    rig.red(visit_id, register=None)
    moved = rig.move(visit_id, to="cancelled")
    assert moved.status_code == 200
    assert moved.json()["red_resurface"] == []
    assert [entry.kind for entry in rig.transition_entries()] == [EntryKind.VISIT_CANCELLED]


# ======================================================================================
# near-miss controls
# ======================================================================================


def test_a_visit_without_a_red_moves_without_an_entry(rig: Rig) -> None:
    visit_id = rig.visit()
    other = rig.visit()
    rig.red(other)  # a RED on ANOTHER visit of the same patient
    moved = rig.move(visit_id, **RESCHEDULE)
    assert moved.status_code == 200
    assert moved.json()["red_resurface"] == []
    assert rig.transition_entries() == []


def test_a_confirm_on_a_red_visit_is_not_a_move(rig: Rig) -> None:
    visit_id = rig.visit()
    rig.red(visit_id)
    moved = rig.move(visit_id, to="confirmed")
    assert moved.status_code == 200
    assert moved.json()["red_resurface"] == []
    assert rig.transition_entries() == []


def test_a_refused_transition_on_a_red_visit_raises_nothing(rig: Rig) -> None:
    visit_id = rig.visit()
    rig.red(visit_id)
    assert rig.move(visit_id, to="cancelled").status_code == 200
    before = rig.transition_entries()
    assert rig.move(visit_id, **RESCHEDULE).status_code == 409
    assert rig.transition_entries() == before


# ======================================================================================
# fail closed: a move nobody can check is a move that does not happen
# ======================================================================================


def _state(harness: ApiHarness, visit_id: str) -> dict[str, Any]:
    body: dict[str, Any] = harness.client.get(
        f"/v1/visits/{visit_id}", headers=harness.patient()
    ).json()
    return body


@pytest.mark.parametrize("body", [RESCHEDULE, {"to": "cancelled"}])
def test_an_unwired_inbox_refuses_the_move(tmp_path: Path, body: dict[str, str]) -> None:
    for harness in _harness(tmp_path, Clock(T0), None):
        created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
        visit_id = str(created.json()["id"])
        before = _state(harness, visit_id)
        audited = len(harness.audit_store.entries())
        refused = harness.client.post(
            f"/v1/visits/{visit_id}/transitions", json=body, headers=harness.patient()
        )
        assert refused.status_code == 503
        assert refused.json() == {"error": "safety_inbox_unconfigured"}
        assert len(harness.audit_store.entries()) == audited
        assert _state(harness, visit_id) == before
        # a transition that cannot move the visit needs no inbox
        confirmed = harness.client.post(
            f"/v1/visits/{visit_id}/transitions",
            json={"to": "confirmed"},
            headers=harness.patient(),
        )
        assert confirmed.status_code == 200


class _EntryWriteFails(SafetyInbox):
    """Reads the visit's REDs, then cannot write the transition entry — the
    store going away between the two calls."""

    def visit_transition(self, **kwargs: Any) -> InboxEntry | None:
        raise SafetyInboxUnavailable("safety_inbox_unreachable")


def test_a_move_whose_entry_cannot_be_written_is_rolled_back(tmp_path: Path) -> None:
    """The entry is written before any audit row and before the commit: a RED
    visit whose entry cannot be filed does not move, loses no share, and the
    audit chain claims nothing that did not happen."""
    store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis())
    for harness in _harness(tmp_path, Clock(T0), _EntryWriteFails(store=store)):
        rig = Rig(harness, store, Clock(T0))
        visit_id = rig.visit()
        rig.red(visit_id)
        sent = harness.client.put(
            f"/v1/visits/{visit_id}/note",
            json={
                "sections": [{"id": "hpi", "title": "Öykü", "lines": ["Sentetik"]}],
                "scopes": {},
                "status": "sent",
            },
            headers=harness.patient(),
        )
        assert sent.status_code == 200, sent.text
        before = _state(harness, visit_id)
        audited = len(harness.audit_store.entries())
        refused = rig.move(visit_id, to="cancelled")
        assert refused.status_code == 503
        assert refused.json() == {"error": "safety_inbox_unreachable"}
        assert len(harness.audit_store.entries()) == audited
        after = _state(harness, visit_id)
        assert (after["state"], after["note_status"]) == ("planned", "sent")
        assert after == before


def test_an_unreachable_inbox_refuses_the_move(tmp_path: Path) -> None:
    server = fakeredis.FakeServer()
    store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis(server=server))
    for harness in _harness(tmp_path, Clock(T0), SafetyInbox(store=store)):
        created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
        visit_id = str(created.json()["id"])
        before = _state(harness, visit_id)
        server.connected = False
        refused = harness.client.post(
            f"/v1/visits/{visit_id}/transitions",
            json={"to": "cancelled"},
            headers=harness.patient(),
        )
        assert refused.status_code == 503
        assert refused.json() == {"error": "safety_inbox_unreachable"}
        assert _state(harness, visit_id) == before


# ======================================================================================
# the runtime records the register the RED was told in
# ======================================================================================


def test_the_runtime_notifier_files_the_red_with_its_register() -> None:
    outbox = SafetyInboxOutbox(clock=lambda: T0)
    visit_id = str(uuid.uuid4())
    SafetyInboxNotifier(
        outbox=outbox,
        tenant_id=TENANT,
        session_id=visit_id,
        visit_id=visit_id,
        wall_clock=lambda: T0,
    ).notify(
        RedNotification(
            work_id="w-red-1",
            rule_ids=(RED_RULE,),
            register=RedRegister.SILENT,
            location=RedLocation.REMOTE,
            evaluated_at_ms=0.0,
            patient_facing=True,
        )
    )
    (entry,) = outbox.pending()
    assert entry.kind is EntryKind.RED
    assert entry.register is RedRegister.SILENT


def test_only_a_red_entry_carries_a_register() -> None:
    red = InboxEntry.for_red(
        tenant_id=TENANT,
        session_id="s-1",
        visit_id="v-1",
        work_id="w-1",
        rule_ids=(RED_RULE,),
        register=RedRegister.ALERT,
        at=T0,
    )
    with pytest.raises(ValueError, match="register"):
        InboxEntry.model_validate(
            {
                **red.model_dump(),
                "kind": EntryKind.VISIT_CANCELLED.value,
                "source_ref": "t-1",
                "entry_id": entry_id_for(TENANT, EntryKind.VISIT_CANCELLED, "t-1"),
            }
        )
