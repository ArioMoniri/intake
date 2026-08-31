"""INT-016 — the patient-visible access-log view model (KVKK-12, KSVY-7).

The hash chain stores actor ids, hashes and consent-scope refs. A data
subject exercising KVKK m.11(d) needs *who, when, what for* — so this suite
pins the projection between the two, and the three properties that make the
projection safe rather than merely convenient:

- **own records only, enforced in the query.** The view is built from the set
  of resource refs the app database says belong to this subject; a ref that is
  not in that set never reaches the source, so no caller can widen it.
- **the read is itself audited, and does not feed itself.** Every access-log
  read appends one chain entry (write-ahead, files/10 §2's break-glass
  ordering). The subject's OWN access-log reads are suppressed *in the query*,
  so the view is stable across repeated reads and a small ``limit`` is not
  consumed by them. A staff read of the same log is NOT suppressed — that is
  the entry the patient most needs to see.
- **no copy, no names, no free text.** Rows carry closed enum values, id-shaped
  refs and ``tr`` keys. The Turkish wording is the app catalogue's
  (invariant 5); a role that is not one of files/08 §2.1's ids is dropped
  rather than rendered, because the thing an unknown "role" is most likely to
  be is a person's name (invariant 6).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from api_harness import ApiHarness
from intake_api.dev_fixture import DEV_PATIENT_ID, PATIENT_ACCOUNT
from intake_platform.access_log import (
    ACCESS_LOG_TR_KEYS,
    CONSOLE_ROLE_IDS,
    SELF_READ_ACTION,
    AccessKind,
    AccessLogQuery,
    AccessLogSource,
    ActorKind,
    NoRoleDirectory,
    RecordKind,
    SqlAlchemyAccessLogSource,
    StoreScanAccessLogSource,
    access_tr_key,
    actor_tr_key,
    classify_access,
    classify_record,
    project,
    record_tr_key,
)
from intake_platform.audit import AuditChain, AuditEntry, InMemoryAuditStore, verify_entries
from intake_platform.db.audit_store import AuditChainRow, SqlAlchemyAuditStore
from intake_platform.db.models import Base
from sqlalchemy import Engine, create_engine

SUBJECT = PATIENT_ACCOUNT.account_id
PATIENT_REF = f"patient:{DEV_PATIENT_ID}"

#: Every ``action`` literal the API and the platform write to the chain today
#: (``grep -o 'action="..."'``). A snapshot, not a gate over the tree: the
#: point is that the classifier is total over the vocabulary in use, and that
#: none of it falls through to ``AccessKind.OTHER``.
ACTIONS_IN_USE = (
    "annotation.content_read.refused",
    "annotation.enqueue",
    "annotation.enqueue.refused",
    "annotation.review",
    "annotation.review.refused",
    "api.consent.read",
    "api.csat.record",
    "api.document.create",
    "api.document.download",
    "api.document.ingest",
    "api.document.list",
    "api.experience.wait_times.export",
    "api.experience.wait_times.read",
    "api.note.read",
    "api.note.share",
    "api.note.write",
    "api.notification_prefs.read",
    "api.notification_prefs.update",
    "api.nps.record",
    "api.visit.create",
    "api.visit.list",
    "api.visit.read",
    "audit.worm_copied",
    "auth.account.created",
    "auth.otp.requested",
    "auth.otp.verified",
    "auth.refresh.reuse_detected",
    "consent.cascade",
    "consent.grant",
    "consent.stale",
    "consent.withdraw",
    "dsar.delete.cancel",
    "dsar.delete.request",
    "dsar.delete.shred",
    "dsar.export.issue",
    "dsar.export.request",
    "dsar.rectify",
    "guardian.link",
    "research.extract.served",
)


def _entry(
    seq: int,
    *,
    actor: str = SUBJECT,
    action: str = "api.note.read",
    resource_ref: str = "note:11111111-1111-1111-1111-111111111111",
    consent_scope_ref: str = "scope:core",
) -> AuditEntry:
    """A chain-shaped entry for the pure projection tests. The projection
    never re-hashes, so the hash fields carry the shape and nothing more."""
    return AuditEntry(
        seq=seq,
        timestamp_utc="2026-08-31T09:00:00+00:00",
        actor=actor,
        action=action,
        resource_ref=resource_ref,
        consent_scope_ref=consent_scope_ref,
        prev_hash="0" * 64,
        entry_hash="1" * 64,
    )


# --- the projection: chain entry -> what a patient sees -----------------------------


def test_a_staff_read_of_your_note_projects_to_who_when_what_for() -> None:
    (row,) = project(
        [_entry(1, actor="compliance-officer-7")],
        subject_actor=SUBJECT,
        roles=NoRoleDirectory(),
    )
    assert row.seq == 1
    assert row.occurred_at == "2026-08-31T09:00:00+00:00"
    assert row.actor_kind is ActorKind.OTHER
    assert row.access_kind is AccessKind.VIEW
    assert row.record_kind is RecordKind.NOTE
    assert row.basis_ref == "scope:core"


def test_the_subjects_own_action_is_marked_self() -> None:
    (row,) = project([_entry(1)], subject_actor=SUBJECT, roles=NoRoleDirectory())
    assert row.actor_kind is ActorKind.SELF
    assert row.actor_tr_key == "access_log.actor.self"


def test_no_role_directory_exists_yet_so_the_role_reads_as_unrecorded() -> None:
    """Keycloak and the console role grants arrive with INT-180; until then
    the honest answer is 'no role is recorded for this actor', not a guess
    (the NoAgeRecordSource posture, files/00 rule 2)."""
    (row,) = project(
        [_entry(1, actor="someone-else")], subject_actor=SUBJECT, roles=NoRoleDirectory()
    )
    assert row.actor_role is None
    assert row.actor_tr_key == "access_log.actor.unrecorded"


def test_a_recorded_files_08_role_is_carried_and_keyed() -> None:
    class Directory:
        def role_of(self, actor: str) -> str | None:
            return "compliance_officer"

    (row,) = project([_entry(1, actor="someone-else")], subject_actor=SUBJECT, roles=Directory())
    assert row.actor_role == "compliance_officer"
    assert row.actor_tr_key == "access_log.actor.role.compliance_officer"


def test_a_role_outside_the_files_08_role_set_is_dropped_not_rendered() -> None:
    """A 'role' that is not one of the twelve ids is most plausibly a person's
    name; rendering it would put a staff identity into a patient-facing
    surface, and echoing it into the refusal would put it into a log
    (invariant 6). It is dropped, silently, to unrecorded."""

    class LeakyDirectory:
        def role_of(self, actor: str) -> str | None:
            return "Dr. Ayse Yilmaz"

    (row,) = project(
        [_entry(1, actor="someone-else")], subject_actor=SUBJECT, roles=LeakyDirectory()
    )
    assert row.actor_role is None
    assert row.actor_tr_key == "access_log.actor.unrecorded"


def test_console_role_ids_are_exactly_the_files_08_role_set() -> None:
    assert CONSOLE_ROLE_IDS == frozenset(
        {
            "platform_owner",
            "platform_admin",
            "tenant_admin",
            "tenant_clinical_responsible",
            "clinical_lead",
            "qms_owner",
            "investigator",
            "auditor",
            "sre_oncall",
            "compliance_officer",
            "researcher",
            "support",
        }
    )


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("api.note.read", AccessKind.VIEW),
        ("api.visit.list", AccessKind.VIEW),
        ("api.note.share", AccessKind.SHARE),
        ("api.document.download", AccessKind.EXPORT),
        ("dsar.export.request", AccessKind.EXPORT),
        ("dsar.delete.request", AccessKind.ERASE),
        ("dsar.delete.shred", AccessKind.ERASE),
        ("consent.withdraw", AccessKind.CONSENT),
        ("consent.stale", AccessKind.CONSENT),
        ("api.consent.read", AccessKind.VIEW),
        ("api.visit.create", AccessKind.CHANGE),
        ("annotation.review.refused", AccessKind.REFUSED),
        (SELF_READ_ACTION, AccessKind.ACCESS_LOG),
    ],
)
def test_access_kind_rules(action: str, expected: AccessKind) -> None:
    assert classify_access(action) is expected


def test_every_action_written_today_classifies_to_something_real() -> None:
    unclassified = [a for a in ACTIONS_IN_USE if classify_access(a) is AccessKind.OTHER]
    assert unclassified == []


def test_an_unknown_action_still_yields_a_visible_row() -> None:
    """Fail-open is the right direction for a transparency surface: a row the
    classifier does not recognise must still appear, marked ``other``. Hiding
    it would be the hole this view exists to close."""
    (row,) = project(
        [_entry(1, action="future.thing.happened", actor="x")],
        subject_actor=SUBJECT,
        roles=NoRoleDirectory(),
    )
    assert row.access_kind is AccessKind.OTHER
    assert row.access_tr_key == "access_log.access.other"


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (PATIENT_REF, RecordKind.ACCOUNT),
        ("visit:1", RecordKind.VISIT),
        ("session:1", RecordKind.VISIT),
        ("note:1", RecordKind.NOTE),
        ("doc:1", RecordKind.DOCUMENT),
        ("share:1", RecordKind.SHARE),
        ("consent:1", RecordKind.CONSENT),
        ("dsar-request:1", RecordKind.REQUEST),
        ("dsar-rectification:1", RecordKind.REQUEST),
        ("tenant:1", RecordKind.OTHER),
    ],
)
def test_record_kind_rules(ref: str, expected: RecordKind) -> None:
    assert classify_record(ref) is expected


def test_every_key_a_row_can_carry_is_declared() -> None:
    """``ACCESS_LOG_TR_KEYS`` is the ask handed to the app catalogue: every
    key any row can name must be in it, or the screen renders a blank."""
    for kind in AccessKind:
        assert access_tr_key(kind) in ACCESS_LOG_TR_KEYS
    for record in RecordKind:
        assert record_tr_key(record) in ACCESS_LOG_TR_KEYS
    assert actor_tr_key(ActorKind.SELF, None) in ACCESS_LOG_TR_KEYS
    assert actor_tr_key(ActorKind.OTHER, None) in ACCESS_LOG_TR_KEYS
    for role in CONSOLE_ROLE_IDS:
        assert actor_tr_key(ActorKind.OTHER, role) in ACCESS_LOG_TR_KEYS


#: Letters that only Turkish orthography uses among the languages in this
#: tree. Their absence is what "no Turkish copy was authored here" means; the
#: section sign and em dash of the repo's prose are not evidence of anything.
TURKISH_LETTERS = frozenset("çÇğĞıİöÖşŞüÜ")


def test_the_view_model_and_the_route_author_no_turkish_copy() -> None:
    """Invariant 5: ``tr`` keys are the source of truth and the copy is the
    app catalogue's. A Turkish sentence in either module would be exactly the
    drafted patient copy this project forbids — indistinguishable from
    reviewed copy once merged."""
    import intake_api.access_log as route
    import intake_platform.access_log as view_model

    for module in (view_model, route):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert not (set(source) & TURKISH_LETTERS), module.__name__


def test_a_row_carries_no_free_text() -> None:
    (row,) = project(
        [_entry(1, actor="someone-else")], subject_actor=SUBJECT, roles=NoRoleDirectory()
    )
    for value in (
        row.record_ref,
        row.basis_ref,
        row.actor_tr_key,
        row.access_tr_key,
        row.record_tr_key,
    ):
        assert " " not in value
        assert value.isascii()


# --- the source: suppression and ownership live in the query ------------------------


@pytest.fixture
def audit_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[AuditChainRow.__table__])
    yield engine
    engine.dispose()


def _sources(engine: Engine) -> Iterator[AccessLogSource]:
    """Both implementations of the same protocol run the same contract: the
    SQL one (production wiring) and the store scan (any deployment whose
    AuditStore is not SQLAlchemy)."""
    yield SqlAlchemyAccessLogSource(engine)
    yield StoreScanAccessLogSource(SqlAlchemyAuditStore(engine))


def _seed(engine: Engine) -> None:
    chain = AuditChain(SqlAlchemyAuditStore(engine))
    chain.append(
        actor=SUBJECT,
        action="api.visit.list",
        resource_ref=PATIENT_REF,
        consent_scope_ref="scope:core",
    )
    chain.append(
        actor=SUBJECT,
        action="api.note.read",
        resource_ref="note:99999999-9999-9999-9999-999999999999",
        consent_scope_ref="scope:core",
    )
    for _ in range(5):
        chain.append(
            actor=SUBJECT,
            action=SELF_READ_ACTION,
            resource_ref=PATIENT_REF,
            consent_scope_ref="scope:core",
        )


def test_sources_return_only_the_refs_they_were_given(audit_engine: Engine) -> None:
    _seed(audit_engine)
    for source in _sources(audit_engine):
        found = source.fetch(
            AccessLogQuery(resource_refs=(PATIENT_REF,), subject_actor=SUBJECT, limit=50)
        )
        assert {entry.resource_ref for entry in found} == {PATIENT_REF}


def test_sources_suppress_the_subjects_own_access_log_reads(audit_engine: Engine) -> None:
    _seed(audit_engine)
    for source in _sources(audit_engine):
        found = source.fetch(
            AccessLogQuery(resource_refs=(PATIENT_REF,), subject_actor=SUBJECT, limit=50)
        )
        assert [entry.action for entry in found] == ["api.visit.list"]


def test_suppression_happens_in_the_query_so_a_small_limit_is_not_consumed(
    audit_engine: Engine,
) -> None:
    """Five self-reads sit ON TOP of the one real entry. A post-hoc filter over
    the newest three rows would return an empty view; the in-query rule
    returns the entry that matters."""
    _seed(audit_engine)
    for source in _sources(audit_engine):
        found = source.fetch(
            AccessLogQuery(resource_refs=(PATIENT_REF,), subject_actor=SUBJECT, limit=3)
        )
        assert [entry.action for entry in found] == ["api.visit.list"]


def test_someone_elses_access_log_read_is_not_suppressed(audit_engine: Engine) -> None:
    chain = AuditChain(SqlAlchemyAuditStore(audit_engine))
    chain.append(
        actor="compliance-officer-7",
        action=SELF_READ_ACTION,
        resource_ref=PATIENT_REF,
        consent_scope_ref="basis:KVKK-11/13",
    )
    for source in _sources(audit_engine):
        found = source.fetch(
            AccessLogQuery(resource_refs=(PATIENT_REF,), subject_actor=SUBJECT, limit=50)
        )
        assert [entry.actor for entry in found] == ["compliance-officer-7"]


def test_sources_return_newest_first(audit_engine: Engine) -> None:
    _seed(audit_engine)
    for source in _sources(audit_engine):
        found = source.fetch(
            AccessLogQuery(
                resource_refs=(PATIENT_REF, "note:99999999-9999-9999-9999-999999999999"),
                subject_actor=SUBJECT,
                limit=50,
            )
        )
        assert [entry.seq for entry in found] == [2, 1]


def test_an_empty_ref_set_returns_nothing_rather_than_everything(audit_engine: Engine) -> None:
    """A subject with no records must see an empty log, never an unfiltered
    one — the failure mode of an ``IN ()`` written carelessly."""
    _seed(audit_engine)
    for source in _sources(audit_engine):
        assert source.fetch(AccessLogQuery(resource_refs=(), subject_actor=SUBJECT, limit=50)) == ()


def test_the_in_memory_store_satisfies_the_same_contract() -> None:
    store = InMemoryAuditStore()
    chain = AuditChain(store)
    chain.append(
        actor="x", action="api.note.read", resource_ref="note:1", consent_scope_ref="scope:core"
    )
    chain.append(
        actor="x", action="api.note.read", resource_ref="note:2", consent_scope_ref="scope:core"
    )
    source = StoreScanAccessLogSource(store)
    found = source.fetch(AccessLogQuery(resource_refs=("note:2",), subject_actor="x", limit=50))
    assert [entry.resource_ref for entry in found] == ["note:2"]


# --- the route --------------------------------------------------------------------


def _get(api: ApiHarness, **params: object) -> dict[str, object]:
    response = api.client.get("/v1/me/access-log", params=params, headers=api.patient())
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _rows(api: ApiHarness, **params: object) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = list(_get(api, **params)["entries"])  # type: ignore[arg-type]
    return entries


def test_the_access_log_shows_the_subjects_own_activity(api: ApiHarness) -> None:
    created = api.client.post(
        "/v1/visits",
        json={"hospital": "Hastane", "department": "Bolum", "date": "2026-09-03"},
        headers=api.patient(),
    )
    assert created.status_code == 201, created.text
    rows = _rows(api)
    assert any(row["record_kind"] == "visit" for row in rows), rows
    assert all(row["actor_kind"] == "self" for row in rows), rows


def test_reading_the_access_log_appends_exactly_one_chain_entry(api: ApiHarness) -> None:
    before = len(api.audit_store.entries())
    _get(api)
    after = api.audit_store.entries()
    assert len(after) == before + 1
    assert after[-1].action == SELF_READ_ACTION
    assert after[-1].actor == SUBJECT
    assert after[-1].consent_scope_ref == "scope:core"


def test_the_read_is_audited_write_ahead(api: ApiHarness) -> None:
    """files/10 §2 orders the break-glass audit BEFORE the read. The same
    ordering here means a read that cannot be audited never happens — and,
    because the suppression rule is in the query, the row the read just wrote
    cannot show up in its own answer."""
    body = _get(api)
    written = api.audit_store.entries()[-1]
    assert written.action == SELF_READ_ACTION
    assert all(row["access_kind"] != "access_log" for row in body["entries"])  # type: ignore[union-attr]


def test_reading_the_log_does_not_grow_the_log(api: ApiHarness) -> None:
    first = len(_rows(api))
    second = len(_rows(api))
    third = len(_rows(api))
    assert first == second == third
    # the chain still recorded every one of the three reads
    reads = [e for e in api.audit_store.entries() if e.action == SELF_READ_ACTION]
    assert len(reads) == 3


def test_a_staff_read_of_your_access_log_is_visible_to_you(api: ApiHarness) -> None:
    chain = AuditChain(api.audit_store)
    chain.append(
        actor="compliance-officer-7",
        action=SELF_READ_ACTION,
        resource_ref=PATIENT_REF,
        consent_scope_ref="basis:KVKK-11/13",
    )
    rows = _rows(api)
    assert [row for row in rows if row["access_kind"] == "access_log"] == [
        {
            "seq": 1,
            "occurred_at": rows[0]["occurred_at"],
            "actor_kind": "other",
            "actor_role": None,
            "access_kind": "access_log",
            "record_kind": "account",
            "record_ref": PATIENT_REF,
            "basis_ref": "basis:KVKK-11/13",
            "actor_tr_key": "access_log.actor.unrecorded",
            "access_tr_key": "access_log.access.access_log",
            "record_tr_key": "access_log.record.account",
        }
    ]


def test_another_patients_records_never_appear(api: ApiHarness) -> None:
    foreign_note = f"note:{uuid.uuid4()}"
    chain = AuditChain(api.audit_store)
    chain.append(
        actor="clinician-1",
        action="api.note.read",
        resource_ref=foreign_note,
        consent_scope_ref="scope:core",
    )
    assert all(row["record_ref"] != foreign_note for row in _rows(api))


def test_the_access_log_needs_the_core_consent_scope(api: ApiHarness) -> None:
    api.revoke_consent("core")
    response = api.client.get("/v1/me/access-log", headers=api.patient())
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "core"}


def test_the_access_log_is_patient_only(api: ApiHarness) -> None:
    response = api.client.get("/v1/me/access-log", headers=api.admin())
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}


def test_the_access_log_needs_a_principal(api: ApiHarness) -> None:
    assert api.client.get("/v1/me/access-log").status_code == 401


def test_the_limit_is_bounded_and_reports_truncation(api: ApiHarness) -> None:
    for index in range(4):
        api.client.post(
            "/v1/visits",
            json={"hospital": f"H{index}", "department": "Bolum", "date": "2026-09-03"},
            headers=api.patient(),
        )
    body = _get(api, limit=2)
    assert len(list(body["entries"])) == 2  # type: ignore[arg-type]
    assert body["truncated"] is True
    assert body["limit"] == 2
    assert api.client.get("/v1/me/access-log?limit=0", headers=api.patient()).status_code == 422
    assert api.client.get("/v1/me/access-log?limit=9999", headers=api.patient()).status_code == 422


def test_the_chain_is_still_intact_after_the_view_has_been_read(api: ApiHarness) -> None:
    _get(api)
    _get(api)
    assert verify_entries(api.audit_store.entries()).ok


def test_an_unwired_reader_refuses_instead_of_reporting_an_empty_log(api: ApiHarness) -> None:
    """An empty access log and an unreadable one look identical to a patient,
    and only one of them is true. Fail closed."""
    api.client.app.state.api.access_log = None  # type: ignore[union-attr]
    response = api.client.get("/v1/me/access-log", headers=api.patient())
    assert response.status_code == 503
    assert response.json() == {"error": "access_log_unconfigured"}


def test_the_route_declares_its_consent_scope(api: ApiHarness) -> None:
    """INT-038's scan: a data route that declares nothing fails. The access
    log is clinical metadata, so it declares ``core`` rather than borrowing
    one of the markers (invariant 4)."""
    from intake_api.consent_guard import route_policies, unguarded_data_routes

    assert unguarded_data_routes(api.client.app) == []  # type: ignore[arg-type]
    policy = route_policies(api.client.app)[("GET", "/v1/me/access-log")]  # type: ignore[arg-type]
    assert policy.enforced == ("core",)


def test_the_tr_key_set_is_pinned_so_the_ask_to_the_catalogue_cannot_drift() -> None:
    """docs/evidence/INT-016.md hands this exact list to whoever authors the
    Turkish (apps/** is not this issue's to touch). A key added here without
    the catalogue entry renders a blank on a patient's screen, so the list is
    pinned rather than derived at review time."""
    assert sorted(ACCESS_LOG_TR_KEYS) == [
        "access_log.access.access_log",
        "access_log.access.change",
        "access_log.access.consent",
        "access_log.access.erase",
        "access_log.access.export",
        "access_log.access.other",
        "access_log.access.refused",
        "access_log.access.share",
        "access_log.access.view",
        "access_log.actor.role.auditor",
        "access_log.actor.role.clinical_lead",
        "access_log.actor.role.compliance_officer",
        "access_log.actor.role.investigator",
        "access_log.actor.role.platform_admin",
        "access_log.actor.role.platform_owner",
        "access_log.actor.role.qms_owner",
        "access_log.actor.role.researcher",
        "access_log.actor.role.sre_oncall",
        "access_log.actor.role.support",
        "access_log.actor.role.tenant_admin",
        "access_log.actor.role.tenant_clinical_responsible",
        "access_log.actor.self",
        "access_log.actor.unrecorded",
        "access_log.record.account",
        "access_log.record.consent",
        "access_log.record.document",
        "access_log.record.note",
        "access_log.record.other",
        "access_log.record.request",
        "access_log.record.share",
        "access_log.record.visit",
    ]


def test_the_catalogue_carries_all_of_those_keys_or_none_of_them() -> None:
    """The copy is not authored yet (apps/** is not this issue's to touch), so
    today the catalogue carries none of them. What must never happen is HALF:
    a partly authored key set renders a blank line in the middle of a
    patient's access log, which reads as "nothing happened" — the one wrong
    answer this surface can give. Holds in both directions, so the issue that
    writes the Turkish does not have to edit this test."""
    catalogue = (
        Path(__file__).resolve().parents[2] / "apps" / "mobile" / "src" / "lib" / "i18n" / "tr.ts"
    ).read_text(encoding="utf-8")
    present = {key for key in ACCESS_LOG_TR_KEYS if f'"{key}"' in catalogue}
    assert present in (set(), set(ACCESS_LOG_TR_KEYS)), sorted(ACCESS_LOG_TR_KEYS - present)
