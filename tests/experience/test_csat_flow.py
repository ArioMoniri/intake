"""INT-240 — CSAT / NPS ingestion (files/08 §4 group F; threat row `experience`).

Acceptance under test, verbatim from docs/backlog/issues.yaml:
  "csat.v1 (1-5 + reason enum + optional text), nps.v1, clinician_pulse.v1;
   POST /sessions/{id}/csat, /feedback/nps; rollups in services/metrics"

The load-bearing property of this suite is the split the free text forces.
Satisfaction feedback is patient-authored: it WILL contain symptoms and names.
So the *scores* are an ``events`` row — operational, PHI-free by construction,
the shape the rollups read — and the *text* is a different row in a different
table, envelope-encrypted like every other clinical payload and joined by
nothing the analytics path touches (invariant 6; threat row `experience`
threat [I], "patient-typed free text carrying identifiers into analytics").

Erasure is structural rather than bolted on: the text row cascades away with
its session (the DSAR m.7/m.11 path deletes sessions) and with its event (the
files/06 §3 ``satisfaction`` retention class destroys events), so no third
sweeper can fall out of step with the two that already exist.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from api_harness import ApiHarness, run, sqlite_ddl_clone
from intake_api.consent_guard import route_policies, unguarded_data_routes
from intake_api.dev_fixture import DEV_TENANT_ID
from intake_platform.db.envelope_json import encrypted_field_from_json
from intake_platform.db.models import CsatText, Event, IntakeSession
from legal_harness import grant_bound
from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

CSAT_PATH = "/v1/sessions/{session_id}/csat"
NPS_PATH = "/v1/feedback/nps"
SATISFACTION_SCOPE = "satisfaction"

#: One patient sentence carrying every shape the threat row names: a symptom
#: narrative, a clinician's name and a reachable phone number.
ADVERSARIAL_TEXT = (
    "Üç gündür göğsümde baskı ve nefes darlığı var, Doktor Ayşe Yılmaz çok "
    "ilgilendi, beni 05321234567 numaralı telefondan arayabilirsiniz."
)


def _create_session(harness: ApiHarness) -> str:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _granted_session(harness: ApiHarness) -> str:
    grant_bound(harness, "core", SATISFACTION_SCOPE)
    return _create_session(harness)


def _post_csat(harness: ApiHarness, session_id: str, **body: Any) -> Any:
    payload: dict[str, Any] = {"score": 4, "reason": "helpful"}
    payload.update(body)
    return harness.client.post(
        CSAT_PATH.format(session_id=session_id), json=payload, headers=harness.patient()
    )


def _events(harness: ApiHarness, event_type: str) -> list[Event]:
    async def _read() -> list[Event]:
        async with AsyncSession(harness.engine) as session:
            rows = await session.scalars(select(Event).where(Event.event_type == event_type))
            return list(rows)

    result: list[Event] = run(_read())
    return result


def _texts(harness: ApiHarness) -> list[CsatText]:
    async def _read() -> list[CsatText]:
        async with AsyncSession(harness.engine) as session:
            rows = await session.scalars(select(CsatText))
            return list(rows)

    result: list[CsatText] = run(_read())
    return result


def _decrypt(harness: ApiHarness, row: CsatText) -> str:
    field = encrypted_field_from_json(row.payload)
    return harness.cipher.decrypt_field(str(DEV_TENANT_ID), field).decode("utf-8")


# --- the two routes the acceptance names ------------------------------------------


def test_csat_records_a_csat_v1_event_carrying_score_and_reason_only(
    harness: ApiHarness,
) -> None:
    session_id = _granted_session(harness)

    response = _post_csat(harness, session_id, score=5, reason="felt_heard")

    assert response.status_code == 201, response.text
    (row,) = _events(harness, "csat.v1")
    assert row.session_id == uuid.UUID(session_id)
    assert row.payload["score"] == 5
    assert row.payload["reason"] == "felt_heard"
    assert row.payload["schema_id"] == "intake.clinical.csat.v1"
    # the operational row cannot carry the patient's words at all
    assert "text" not in row.payload


def test_nps_records_an_nps_v1_event(harness: ApiHarness) -> None:
    grant_bound(harness, SATISFACTION_SCOPE)

    response = harness.client.post(NPS_PATH, json={"score": 9}, headers=harness.patient())

    assert response.status_code == 201, response.text
    (row,) = _events(harness, "nps.v1")
    assert row.payload["score"] == 9
    assert row.payload["schema_id"] == "intake.clinical.nps.v1"
    # NPS is account-level, not session-level: nothing links it to a visit
    assert row.session_id is None


def test_csat_scores_outside_one_to_five_are_refused_without_echoing_the_body(
    harness: ApiHarness,
) -> None:
    session_id = _granted_session(harness)

    response = _post_csat(harness, session_id, score=6, text=ADVERSARIAL_TEXT)

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert ADVERSARIAL_TEXT not in response.text
    assert _events(harness, "csat.v1") == []


def test_csat_reason_is_the_closed_files_08_group_f_enum(harness: ApiHarness) -> None:
    session_id = _granted_session(harness)

    assert _post_csat(harness, session_id, reason="çok_iyiydi").status_code == 422
    for reason in ("too_long", "didnt_understand_me", "felt_rushed", "helpful", "felt_heard"):
        assert _post_csat(harness, session_id, reason=reason).status_code == 201


def test_nps_scores_outside_zero_to_ten_are_refused(harness: ApiHarness) -> None:
    grant_bound(harness, SATISFACTION_SCOPE)

    assert (
        harness.client.post(NPS_PATH, json={"score": 11}, headers=harness.patient()).status_code
        == 422
    )
    assert (
        harness.client.post(NPS_PATH, json={"score": -1}, headers=harness.patient()).status_code
        == 422
    )
    assert _events(harness, "nps.v1") == []


def test_csat_refuses_a_session_that_is_not_the_requesting_patients(
    harness: ApiHarness,
) -> None:
    grant_bound(harness, "core", SATISFACTION_SCOPE)

    response = _post_csat(harness, str(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}
    assert _events(harness, "csat.v1") == []


def test_the_clinic_admin_cannot_rate_on_a_patients_behalf(harness: ApiHarness) -> None:
    session_id = _granted_session(harness)

    response = harness.client.post(
        CSAT_PATH.format(session_id=session_id),
        json={"score": 5, "reason": "helpful"},
        headers=harness.admin(),
    )

    assert response.status_code == 403
    assert _events(harness, "csat.v1") == []


# --- consent (invariant 4) ---------------------------------------------------------


def test_route_table_declares_satisfaction_for_both_new_routes(harness: ApiHarness) -> None:
    app = harness.client.app
    assert unguarded_data_routes(app) == []
    policies = route_policies(app)
    assert policies[("POST", "/v1/sessions/{session_id}/csat")].enforced == (SATISFACTION_SCOPE,)
    assert policies[("POST", NPS_PATH)].enforced == (SATISFACTION_SCOPE,)


def test_csat_is_refused_without_the_satisfaction_consent(harness: ApiHarness) -> None:
    grant_bound(harness, "core")
    session_id = _create_session(harness)

    response = _post_csat(harness, session_id, text=ADVERSARIAL_TEXT)

    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": SATISFACTION_SCOPE}
    assert _events(harness, "csat.v1") == []
    assert _texts(harness) == []


def test_nps_is_refused_without_the_satisfaction_consent(harness: ApiHarness) -> None:
    response = harness.client.post(NPS_PATH, json={"score": 10}, headers=harness.patient())

    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": SATISFACTION_SCOPE}
    assert _events(harness, "nps.v1") == []


def test_withdrawing_satisfaction_closes_both_routes(harness: ApiHarness) -> None:
    session_id = _granted_session(harness)
    assert _post_csat(harness, session_id).status_code == 201

    harness.revoke_consent(SATISFACTION_SCOPE)

    assert _post_csat(harness, session_id).status_code == 403
    assert (
        harness.client.post(NPS_PATH, json={"score": 8}, headers=harness.patient()).status_code
        == 403
    )


def test_both_ingests_are_audited_against_the_satisfaction_scope(harness: ApiHarness) -> None:
    session_id = _granted_session(harness)
    _post_csat(harness, session_id)
    harness.client.post(NPS_PATH, json={"score": 7}, headers=harness.patient())

    actions = {
        (entry.actor, entry.action, entry.consent_scope_ref)
        for entry in harness.audit_store.entries()
    }
    assert ("dev-patient", "api.csat.record", f"scope:{SATISFACTION_SCOPE}") in actions
    assert ("dev-patient", "api.nps.record", f"scope:{SATISFACTION_SCOPE}") in actions


# --- the free text: encrypted, redacted, and out of every other surface -------------


def test_free_text_is_stored_only_as_an_envelope_and_never_as_plaintext(
    harness: ApiHarness,
) -> None:
    session_id = _granted_session(harness)
    _post_csat(harness, session_id, text="Bekleme çok uzundu ama hemşire çok ilgiliydi.")

    (row,) = _texts(harness)
    assert set(row.payload) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}
    assert _decrypt(harness, row) == "Bekleme çok uzundu ama hemşire çok ilgiliydi."
    # and the plaintext is nowhere in the file the database actually wrote
    db_path = Path(harness.settings.app_db_url.split("///", 1)[1])
    assert "hemşire çok ilgiliydi".encode() not in db_path.read_bytes()


def test_free_text_ingestion_applies_the_files_10_redaction_baseline(
    harness: ApiHarness,
) -> None:
    """Threat row `experience` control: "redaction baseline (§3) applied to
    free-text ingestion". The structured identifiers go before the envelope
    closes; names are NER territory, which is why the column is encrypted."""
    session_id = _granted_session(harness)
    _post_csat(harness, session_id, text=ADVERSARIAL_TEXT)

    (row,) = _texts(harness)
    stored = _decrypt(harness, row)
    assert "05321234567" not in stored
    assert "[PHONE]" in stored
    assert "göğsümde baskı" in stored  # the clinically meaningful words survive


def test_the_response_never_echoes_the_patients_words(harness: ApiHarness) -> None:
    session_id = _granted_session(harness)

    response = _post_csat(harness, session_id, text=ADVERSARIAL_TEXT)

    assert response.status_code == 201
    assert "Ayşe" not in response.text
    assert "göğsümde" not in response.text
    assert response.json() == {"session_id": session_id, "recorded": True}


def test_the_audit_entry_references_the_session_and_carries_no_narrative(
    harness: ApiHarness,
) -> None:
    session_id = _granted_session(harness)
    _post_csat(harness, session_id, text=ADVERSARIAL_TEXT)

    entries = [e for e in harness.audit_store.entries() if e.action == "api.csat.record"]
    (entry,) = entries
    assert entry.resource_ref == f"session:{session_id}"
    assert "Ayşe" not in repr(entry)
    assert "göğsümde" not in repr(entry)


def test_omitting_the_text_writes_no_encrypted_row_at_all(harness: ApiHarness) -> None:
    session_id = _granted_session(harness)

    assert _post_csat(harness, session_id).status_code == 201
    assert _post_csat(harness, session_id, text="   ").status_code == 201

    assert _texts(harness) == []
    assert len(_events(harness, "csat.v1")) == 2


def test_nps_carries_no_free_text_field_at_all(harness: ApiHarness) -> None:
    grant_bound(harness, SATISFACTION_SCOPE)

    response = harness.client.post(
        NPS_PATH, json={"score": 9, "text": ADVERSARIAL_TEXT}, headers=harness.patient()
    )

    assert response.status_code == 422
    assert _events(harness, "nps.v1") == []


# --- erasure is structural ----------------------------------------------------------


def test_the_text_column_is_annotated_as_special_category_health() -> None:
    """Invariant 18: the inventory annotation is the field's passport, and a
    patient's satisfaction sentence is health data whatever the survey calls it."""
    annotation = CsatText.__table__.c.payload.info["inventory"]
    assert annotation["category"] == "special_category_health"
    assert "açık rıza" in annotation["basis"]
    assert "with account" in annotation["retention"].lower()


@pytest.mark.parametrize("cascade_from", ["session", "event"])
def test_the_text_row_cascades_away_with_its_session_and_with_its_event(
    tmp_path: Any, cascade_from: str
) -> None:
    """DSAR erasure deletes sessions; the files/06 §3 ``satisfaction`` class
    destroys events. Either one must take the patient's words with it, and the
    DDL — not a sweeper somebody has to remember — is what guarantees it."""
    db = tmp_path / "cascade.db"
    engine = create_engine(f"sqlite+pysqlite:///{db}")

    @sa_event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    sqlite_ddl_clone().create_all(engine)

    tenant_id, patient_id, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenants (id, display_name, kvkk_role) VALUES (:i, :d, :r)"),
            {"i": tenant_id.hex, "d": "cascade", "r": "controller"},
        )
        conn.execute(
            text("INSERT INTO patients (id, tenant_id, pseudonym) VALUES (:i, :t, :p)"),
            {"i": patient_id.hex, "t": tenant_id.hex, "p": "dev." + "0" * 128},
        )
        conn.execute(
            text(
                "INSERT INTO sessions (id, tenant_id, patient_id, protocol_id,"
                " protocol_version, status, started_at)"
                " VALUES (:i, :t, :p, 'x', 'y', 'created', CURRENT_TIMESTAMP)"
            ),
            {"i": session_id.hex, "t": tenant_id.hex, "p": patient_id.hex},
        )
        conn.execute(
            text(
                "INSERT INTO events (id, tenant_id, session_id, event_type, payload)"
                " VALUES (1, :t, :s, 'csat.v1', '{}')"
            ),
            {"t": tenant_id.hex, "s": session_id.hex},
        )
        conn.execute(
            text(
                "INSERT INTO csat_texts (id, tenant_id, session_id, event_id, payload)"
                " VALUES (:i, :t, :s, 1, '{}')"
            ),
            {"i": uuid.uuid4().hex, "t": tenant_id.hex, "s": session_id.hex},
        )

    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM csat_texts")).scalar_one() == 1
        if cascade_from == "session":
            # exactly the order intake_api.dsar.shred uses: telemetry is
            # de-linked first (events.session_id has no ON DELETE clause, so
            # the session cannot go while an event points at it), THEN the
            # session is deleted — and the comment goes with it
            conn.execute(
                update(Event).where(Event.session_id == session_id).values(session_id=None)
            )
            conn.execute(delete(IntakeSession).where(IntakeSession.id == session_id))
        else:
            # and the files/06 §3 satisfaction clock: destroy_events deletes
            # the event row, which takes the comment with it too
            conn.execute(delete(Event).where(Event.id == 1))
        assert conn.execute(text("SELECT count(*) FROM csat_texts")).scalar_one() == 0
    engine.dispose()
