"""INT-016 — the patient-visible access-log view model (files/10 §3; KVKK m.11/m.13).

files/10 §3 states the requirement and the failure it fixes: before this, the
honest answer to *"does the patient ever find out a member of staff read their
intake?"* was *"only if they file a KVKK m.11 request."* The access log is that
answer, rendered from the same hash-chained entries the verifier walks — so a
row the patient sees is a row an auditor can re-verify, and a share that never
reached the chain is a bug in invariant 4, not a gap in this projection.

What the projection must guarantee, and what each test here pins:

1. **Scoped.** Only entries naming one of the patient's own resources appear.
   The scope is passed in and an empty scope yields an empty log — the failure
   direction is "shows nothing", never "shows someone else's".
2. **Role, never identity.** files/10 §3 says *actor role (not name)*. The
   chain records an actor **id**, not a role, so the resolver is an argument;
   an actor nobody resolves renders ``UNKNOWN`` rather than leaking the raw id
   (which can be ``phone:<log-ref>`` or an account id).
3. **Nothing silently dropped.** Every in-scope entry produces exactly one
   row. An action the category table has never seen becomes ``OTHER`` — it is
   never omitted, because an omitted share is the whole thing this log exists
   to prevent.
4. **No PHI** (invariant 6). Rows carry ids, an enum and hashes. The audit
   entry's closed, id-shaped field set is what makes that true by
   construction; this test asserts the projection does not add a carrier.

Not in scope and deliberately absent: reason category and grant duration for
break-glass reads. files/10 §3 names them, and they live in the richer
``admin_audit.v1`` schema (files/08 §8.1) that the break-glass module writes.
No column here invents them.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

import pytest
from intake_platform.access_log import (
    DEFAULT_ROLE_OF,
    AccessCategory,
    AccessLogRow,
    AccessorRole,
    build_access_log,
    classify_action,
)
from intake_platform.audit import AuditChain, InMemoryAuditStore


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 29, 9, 0, 0, tzinfo=UTC)


def _chain(store: InMemoryAuditStore) -> AuditChain:
    return AuditChain(store, clock=_fixed_clock)


def _append(chain: AuditChain, actor: str, action: str, resource_ref: str) -> None:
    chain.append(
        actor=actor,
        action=action,
        resource_ref=resource_ref,
        consent_scope_ref="consent:visit-notes:v1",
    )


# --- scoping ----------------------------------------------------------------------


def test_only_the_patients_own_resources_appear() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _append(chain, "svc-api", "api.note.read", "note:mine")
    _append(chain, "svc-api", "api.note.read", "note:someone-else")
    _append(chain, "svc-api", "api.note.share", "note:mine")

    rows = build_access_log(store.entries(), patient_refs={"note:mine"})

    assert [row.resource_ref for row in rows] == ["note:mine", "note:mine"]
    assert [row.seq for row in rows] == [1, 3]


def test_an_empty_scope_yields_an_empty_log_rather_than_everything() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _append(chain, "svc-api", "api.note.read", "note:mine")
    assert build_access_log(store.entries(), patient_refs=frozenset()) == ()


def test_rows_come_back_in_chain_order() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    for i in range(1, 5):
        _append(chain, "svc-api", "api.note.read", f"note:{i}")
    rows = build_access_log(store.entries(), patient_refs={f"note:{i}" for i in range(1, 5)})
    assert [row.seq for row in rows] == [1, 2, 3, 4]


def test_every_in_scope_entry_produces_exactly_one_row() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    actions = ("api.note.read", "totally.unheard.of.action", "api.note.share")
    for action in actions:
        _append(chain, "svc-api", action, "note:mine")

    rows = build_access_log(store.entries(), patient_refs={"note:mine"})

    assert len(rows) == len(actions)
    assert rows[1].category is AccessCategory.OTHER, "unknown actions surface, never vanish"


# --- role, never identity ---------------------------------------------------------


def test_the_resolver_decides_the_role_and_the_actor_id_never_reaches_the_row() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _append(chain, "clinician:4f2b", "api.note.read", "note:mine")

    def role_of(actor: str) -> AccessorRole:
        return AccessorRole.CLINICIAN if actor.startswith("clinician:") else AccessorRole.UNKNOWN

    (row,) = build_access_log(store.entries(), patient_refs={"note:mine"}, role_of=role_of)

    assert row.accessor_role is AccessorRole.CLINICIAN
    assert "4f2b" not in json.dumps(dataclasses.asdict(row), default=str)


def test_the_default_resolver_names_services_and_refuses_to_guess_anything_else() -> None:
    # The only mapping the chain's own data supports: the `svc-` prefix is a
    # platform convention (svc-api, svc-documents, svc-audit-writer). Every
    # other actor shape is an account id, and guessing a role from an account
    # id is how a display name reaches a patient's screen.
    assert DEFAULT_ROLE_OF("svc-documents") is AccessorRole.SYSTEM
    assert DEFAULT_ROLE_OF("svc-api") is AccessorRole.SYSTEM
    assert DEFAULT_ROLE_OF("patient:0f21") is AccessorRole.UNKNOWN
    assert DEFAULT_ROLE_OF("dev-clinic-admin") is AccessorRole.UNKNOWN
    assert DEFAULT_ROLE_OF("phone:9ab3") is AccessorRole.UNKNOWN


def test_an_unresolvable_actor_is_unknown_not_omitted() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _append(chain, "phone:9ab3", "auth.otp.requested", "patient:mine")
    (row,) = build_access_log(store.entries(), patient_refs={"patient:mine"})
    assert row.accessor_role is AccessorRole.UNKNOWN


# --- categories --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "category"),
    [
        # Reads of clinical content — the m.11 answer.
        ("api.note.read", AccessCategory.RECORD_VIEWED),
        ("api.visit.read", AccessCategory.RECORD_VIEWED),
        ("api.visit.list", AccessCategory.RECORD_VIEWED),
        ("api.document.download", AccessCategory.RECORD_VIEWED),
        ("api.document.list", AccessCategory.RECORD_VIEWED),
        ("api.experience.wait_times.read", AccessCategory.RECORD_VIEWED),
        # Sharing — the category that must never be mistaken for a read.
        ("api.note.share", AccessCategory.RECORD_SHARED),
        # Content the patient (or the clinic) added.
        ("api.note.write", AccessCategory.RECORD_UPDATED),
        ("api.visit.create", AccessCategory.RECORD_UPDATED),
        ("api.document.create", AccessCategory.RECORD_UPDATED),
        ("api.document.ingest", AccessCategory.RECORD_UPDATED),
        # Consent.
        ("api.consent.read", AccessCategory.CONSENT_CHANGED),
        ("consent.grant", AccessCategory.CONSENT_CHANGED),
        ("consent.withdraw", AccessCategory.CONSENT_CHANGED),
        ("consent.cascade", AccessCategory.CONSENT_CHANGED),
        ("consent.stale", AccessCategory.CONSENT_CHANGED),
        # Account and security.
        ("auth.account.created", AccessCategory.ACCOUNT_SECURITY),
        ("auth.otp.requested", AccessCategory.ACCOUNT_SECURITY),
        ("auth.otp.verified", AccessCategory.ACCOUNT_SECURITY),
        ("auth.refresh.reuse_detected", AccessCategory.ACCOUNT_SECURITY),
        ("guardian.link", AccessCategory.ACCOUNT_SECURITY),
        # KVKK data-subject requests.
        ("dsar.export.request", AccessCategory.DATA_REQUEST),
        ("dsar.export.issue", AccessCategory.DATA_REQUEST),
        ("dsar.delete.request", AccessCategory.DATA_REQUEST),
        ("dsar.delete.shred", AccessCategory.DATA_REQUEST),
        # INT-392/INT-393: one erasure entry per removed row, by id. The
        # "share" segment must not turn an erasure into "shared".
        ("dsar.delete.previsit_output", AccessCategory.DATA_REQUEST),
        ("dsar.delete.doctor_link", AccessCategory.DATA_REQUEST),
        ("dsar.delete.share", AccessCategory.DATA_REQUEST),
        ("dsar.delete.cancel", AccessCategory.DATA_REQUEST),
        ("dsar.rectify", AccessCategory.DATA_REQUEST),
        ("api.experience.wait_times.export", AccessCategory.DATA_REQUEST),
        # Preferences and feedback.
        ("api.notification_prefs.read", AccessCategory.PREFERENCES_CHANGED),
        ("api.notification_prefs.update", AccessCategory.PREFERENCES_CHANGED),
        ("api.csat.record", AccessCategory.PREFERENCES_CHANGED),
        ("api.nps.record", AccessCategory.PREFERENCES_CHANGED),
        # Staff review of content (Langfuse annotation queues, INT-175).
        ("annotation.enqueue", AccessCategory.STAFF_REVIEW),
        ("annotation.review", AccessCategory.STAFF_REVIEW),
        ("annotation.content_read.refused", AccessCategory.STAFF_REVIEW),
        ("annotation.enqueue.refused", AccessCategory.STAFF_REVIEW),
        ("annotation.review.refused", AccessCategory.STAFF_REVIEW),
        # Housekeeping the patient may see against their own record.
        ("audit.worm_copied", AccessCategory.SYSTEM_INTEGRITY),
        ("retention.destroyed", AccessCategory.SYSTEM_INTEGRITY),
        ("retention.dsar_run", AccessCategory.SYSTEM_INTEGRITY),
    ],
)
def test_every_action_the_platform_writes_today_classifies(
    action: str, category: AccessCategory
) -> None:
    """Snapshot of the audit actions constructed under packages/ and services/
    as of INT-016. It is a snapshot, not a scan: a new action elsewhere does
    not break this test, but a *renamed* one does, which is the case where a
    share would quietly start rendering as ``OTHER``."""
    assert classify_action(action) is category


def test_anything_that_shares_is_classified_as_sharing() -> None:
    # Rule-shaped rather than snapshot-shaped: this survives new action names.
    for action in ("api.note.share", "share.previsit_note.issue", "doctorlink.share.open"):
        assert classify_action(action) is AccessCategory.RECORD_SHARED


def test_an_unmapped_action_falls_through_to_other() -> None:
    assert classify_action("some.future.thing") is AccessCategory.OTHER


def test_classification_is_case_and_prefix_exact() -> None:
    # `api.notes.read` is not `api.note.read`; near-miss names must not be
    # absorbed by a sloppy prefix rule and rendered as an ordinary view.
    assert classify_action("api.noteworthy.read") is AccessCategory.OTHER
    assert classify_action("API.NOTE.READ") is AccessCategory.OTHER


# --- the row itself ----------------------------------------------------------------


def test_a_row_carries_the_chain_position_so_the_patient_view_is_verifiable() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _append(chain, "svc-api", "api.note.read", "note:mine")
    (entry,) = store.entries()

    (row,) = build_access_log(store.entries(), patient_refs={"note:mine"})

    assert isinstance(row, AccessLogRow)
    assert row.seq == entry.seq
    assert row.entry_hash == entry.entry_hash
    assert row.occurred_at_utc == entry.timestamp_utc
    assert row.consent_scope_ref == "consent:visit-notes:v1"


def test_rows_are_frozen() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _append(chain, "svc-api", "api.note.read", "note:mine")
    (row,) = build_access_log(store.entries(), patient_refs={"note:mine"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.category = AccessCategory.OTHER  # type: ignore[misc]


def test_the_row_field_set_is_closed_and_matches_the_documented_projection() -> None:
    # A field that does not exist cannot accumulate PHI (invariant 6). Adding
    # one is a deliberate act that fails here first.
    assert {f.name for f in dataclasses.fields(AccessLogRow)} == {
        "seq",
        "occurred_at_utc",
        "category",
        "action",
        "accessor_role",
        "resource_ref",
        "consent_scope_ref",
        "entry_hash",
    }
