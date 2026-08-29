"""INT-232 — patient-facing consent routes over the INT-038 service.

What this file pins:
- GET /v1/consents answers the INT-132 client seam shape exactly: a
  ``scopes`` row per non-parameterised files/06 §2 purpose in registry order
  (reason from the pinned INT-038 semantics) plus the versioned, hash-bound
  ``texts`` the catalog can load — and an absent docs/legal tree yields an
  EMPTY texts list, never invented copy (fail closed, invariant 18);
- POST /v1/consents/grant records a hash-bound grant ONLY when the submitted
  {version, text_hash} match the catalog's current text (409 on a moved
  text, 409 on a missing one), and granting one purpose grants nothing else
  (unbundling, files/06 §2);
- POST /v1/consents/withdraw is instant and cascades through the INT-038
  service (voice drags lane:affect, core drags live shares), all audited;
- all three routes are the patient's own surface: the clinic admin gets 403;
- the consent_management() scan marker is accepted ONLY under /v1/consents —
  a data route elsewhere cannot borrow it (negative control), and silence
  still fails the scan;
- refusals carry ids only (invariant 6): unknown purposes — lane:acoustic,
  the bare share family, anything off the closed list — answer 422 with the
  submitted purpose id and nothing else.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "legal"))

import pytest  # noqa: E402
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from intake_api.consent_guard import (  # noqa: E402
    CONSENT_MANAGEMENT_PREFIX,
    consent_management,
    consent_management_routes,
    unguarded_data_routes,
)
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID  # noqa: E402
from intake_platform.consent import PURPOSES, text_filename  # noqa: E402
from intake_platform.db.models import Consent  # noqa: E402
from legal_harness import FIXTURE_VERSION, write_all_consent_texts  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

# The client seam's closed purpose list (apps/mobile consent/purposes.ts):
# every non-parameterised registry purpose, in files/06 §2 order.
SNAPSHOT_PURPOSES = tuple(p.id for p in PURPOSES if not p.parameterised)
DEFAULT_ON = ("learning:personal", "learning:service_improvement")

CLIENT_AT = "2026-08-28T09:00:00.000Z"

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

NOTE_BODY_SENT = {
    "sections": [{"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Ağrı"]}],
    "scopes": {"chief_complaint": True},
    "status": "sent",
}


@pytest.fixture()
def legal_root(tmp_path: Path) -> Path:
    return write_all_consent_texts(tmp_path / "legal" / "consents")


@pytest.fixture()
def texted_harness(tmp_path: Path, legal_root: Path) -> Iterator[ApiHarness]:
    """Texts on disk (the tmp-path catalog fixture), NO grants beyond the
    seeded unbound dev rows — grants in these tests go through the route."""
    yield from build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, legal_root=legal_root
    )


def _delete_all_consents(harness: ApiHarness) -> None:
    """A zero-consent account: even the dev-tier seed rows removed."""

    async def _wipe() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            await session.execute(
                delete(Consent).where(
                    Consent.tenant_id == DEV_TENANT_ID,
                    Consent.patient_id == DEV_PATIENT_ID,
                )
            )

    run(_wipe())


def _consent_rows(harness: ApiHarness, scope: str) -> list[Consent]:
    async def _read() -> list[Consent]:
        async with AsyncSession(harness.engine) as session:
            rows = (
                await session.scalars(
                    select(Consent).where(
                        Consent.tenant_id == DEV_TENANT_ID,
                        Consent.patient_id == DEV_PATIENT_ID,
                        Consent.scope == scope,
                    )
                )
            ).all()
            return list(rows)

    result: list[Consent] = run(_read())
    return result


def _snapshot(harness: ApiHarness) -> dict[str, list[dict[str, object]]]:
    response = harness.client.get("/v1/consents", headers=harness.patient())
    assert response.status_code == 200, response.text
    body: dict[str, list[dict[str, object]]] = response.json()
    return body


def _scope_row(snapshot: dict[str, list[dict[str, object]]], scope: str) -> dict[str, object]:
    rows = [row for row in snapshot["scopes"] if row["scope"] == scope]
    assert len(rows) == 1
    return rows[0]


def _text_row(snapshot: dict[str, list[dict[str, object]]], purpose: str) -> dict[str, object]:
    rows = [row for row in snapshot["texts"] if row["purpose"] == purpose]
    assert len(rows) == 1
    return rows[0]


def _grant(harness: ApiHarness, scope: str) -> None:
    """Grant through the route against the currently served text."""
    snapshot = _snapshot(harness)
    text = _text_row(snapshot, "share" if scope.startswith("share:") else scope)
    response = harness.client.post(
        "/v1/consents/grant",
        json={
            "scope": scope,
            "version": text["version"],
            "text_hash": text["text_hash"],
            "at": CLIENT_AT,
        },
        headers=harness.patient(),
    )
    assert response.status_code == 201, response.text


# --- GET /v1/consents: the snapshot shape ---------------------------------------------


def test_zero_consent_snapshot_is_all_absent_with_no_texts(harness: ApiHarness) -> None:
    """A zero-consent account against the pre-INT-210 world: every açık-rıza
    purpose absent, only the two non-consent-basis purposes default_on, and
    the texts list EMPTY because docs/legal holds nothing (fail closed —
    the route never invents a text)."""
    _delete_all_consents(harness)
    snapshot = _snapshot(harness)
    assert [row["scope"] for row in snapshot["scopes"]] == list(SNAPSHOT_PURPOSES)
    for row in snapshot["scopes"]:
        assert set(row.keys()) == {"scope", "reason", "version", "text_hash"}
        expected = "default_on" if row["scope"] in DEFAULT_ON else "absent"
        assert row["reason"] == expected, row
        assert row["version"] is None
        assert row["text_hash"] is None
    assert snapshot["texts"] == []


def test_snapshot_serves_the_versioned_hash_bound_texts(
    texted_harness: ApiHarness, legal_root: Path
) -> None:
    snapshot = _snapshot(texted_harness)
    served = {row["purpose"] for row in snapshot["texts"]}
    assert served == {p.id for p in PURPOSES}
    voice = _text_row(snapshot, "voice")
    raw = (legal_root / text_filename("voice")).read_bytes()
    assert voice["version"] == FIXTURE_VERSION
    assert voice["text_hash"] == hashlib.sha256(raw).hexdigest()
    body = voice["body"]
    assert isinstance(body, str) and body.strip()


def test_snapshot_reports_the_seeded_unbound_rows_as_unbound(harness: ApiHarness) -> None:
    """No texts on disk: the dev-seed rows (version, NULL hash) are honoured
    as ``unbound`` and their bound version travels to the client."""
    snapshot = _snapshot(harness)
    core = _scope_row(snapshot, "core")
    assert core["reason"] == "unbound"
    assert core["version"] == "int197-dev.1"
    assert core["text_hash"] is None


# --- POST /v1/consents/grant ------------------------------------------------------------


def test_grant_records_a_hash_bound_consent_and_bundles_nothing(
    texted_harness: ApiHarness,
) -> None:
    snapshot = _snapshot(texted_harness)
    text = _text_row(snapshot, "voice")
    response = texted_harness.client.post(
        "/v1/consents/grant",
        json={
            "scope": "voice",
            "version": text["version"],
            "text_hash": text["text_hash"],
            "at": CLIENT_AT,
        },
        headers=texted_harness.patient(),
    )
    assert response.status_code == 201, response.text
    assert response.json() == {
        "scope": "voice",
        "version": text["version"],
        "text_hash": text["text_hash"],
    }
    after = _snapshot(texted_harness)
    voice = _scope_row(after, "voice")
    assert voice["reason"] == "granted"
    assert voice["version"] == text["version"]
    assert voice["text_hash"] == text["text_hash"]
    # unbundling (files/06 §2): granting voice granted NOTHING else
    assert _scope_row(after, "lane:affect")["reason"] == "absent"
    assert _scope_row(after, "wellbeing")["reason"] == "absent"
    rows = _consent_rows(texted_harness, "voice")
    assert len(rows) == 1
    assert rows[0].channel == "app"
    assert rows[0].text_hash == text["text_hash"]
    actions = [e.action for e in texted_harness.audit_store.entries()]
    assert "consent.grant" in actions  # audited (invariant 4)


def test_grant_fails_closed_when_docs_legal_is_absent(harness: ApiHarness) -> None:
    """The real docs/legal tree does not exist yet (INT-210): the grant path
    answers 409 and writes nothing — matching INT-038's no-text-no-grant."""
    _delete_all_consents(harness)
    response = harness.client.post(
        "/v1/consents/grant",
        json={"scope": "voice", "version": "1", "text_hash": "0" * 64, "at": CLIENT_AT},
        headers=harness.patient(),
    )
    assert response.status_code == 409
    assert response.json() == {"error": "text_missing", "scope": "voice"}
    assert _consent_rows(harness, "voice") == []


def test_grant_refuses_a_submission_against_a_moved_text(
    texted_harness: ApiHarness, legal_root: Path
) -> None:
    """The client grants against the text it SHOWED. When the served text has
    moved since, the grant is refused (409) and nothing is written — the
    client re-fetches and re-prompts."""
    snapshot = _snapshot(texted_harness)
    shown = _text_row(snapshot, "wellbeing")
    write_all_consent_texts(legal_root, version="2026-09-01.2")
    response = texted_harness.client.post(
        "/v1/consents/grant",
        json={
            "scope": "wellbeing",
            "version": shown["version"],
            "text_hash": shown["text_hash"],
            "at": CLIENT_AT,
        },
        headers=texted_harness.patient(),
    )
    assert response.status_code == 409
    assert response.json() == {"error": "consent_text_changed", "scope": "wellbeing"}
    assert _consent_rows(texted_harness, "wellbeing") == []


def test_grant_is_stale_after_a_text_bump_and_regrant_restores(
    texted_harness: ApiHarness, legal_root: Path
) -> None:
    _grant(texted_harness, "voice")
    before = _scope_row(_snapshot(texted_harness), "voice")
    assert before["reason"] == "granted"

    write_all_consent_texts(legal_root, version="2026-09-01.2")
    stale = _scope_row(_snapshot(texted_harness), "voice")
    assert stale["reason"] == "stale"
    # the row still names the version the patient actually granted against
    assert stale["version"] == FIXTURE_VERSION

    _grant(texted_harness, "voice")  # against the NEW text this time
    regranted = _scope_row(_snapshot(texted_harness), "voice")
    assert regranted["reason"] == "granted"
    assert regranted["version"] == "2026-09-01.2"


# --- POST /v1/consents/withdraw ----------------------------------------------------------


def test_withdraw_cascades_and_the_snapshot_shows_it(texted_harness: ApiHarness) -> None:
    for scope in ("voice", "lane:affect", "lane:linguistic"):
        _grant(texted_harness, scope)
    response = texted_harness.client.post(
        "/v1/consents/withdraw",
        json={"scope": "voice", "at": CLIENT_AT},
        headers=texted_harness.patient(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "voice"
    assert body["withdrawn_scopes"] == ["lane:affect", "voice"]
    assert body["revoked_share_ids"] == []

    snapshot = _snapshot(texted_harness)
    assert _scope_row(snapshot, "voice")["reason"] == "withdrawn"
    assert _scope_row(snapshot, "lane:affect")["reason"] == "withdrawn"
    # the text-only lane survives a voice withdrawal (files/06 §2.1)
    assert _scope_row(snapshot, "lane:linguistic")["reason"] == "granted"

    actions = [e.action for e in texted_harness.audit_store.entries()]
    assert "consent.withdraw" in actions
    assert "consent.cascade" in actions


def test_core_withdrawal_revokes_live_shares_through_the_service(
    texted_harness: ApiHarness,
) -> None:
    """Wire, don't duplicate: the route rides the INT-038 cascade, so a core
    withdrawal drops the delivered Doctor-Link share and reports its id."""
    for scope in ("core", "documents", "share:previsit_note"):
        _grant(texted_harness, scope)
    created = texted_harness.client.post(
        "/v1/visits", json=VISIT_BODY, headers=texted_harness.patient()
    )
    assert created.status_code == 201, created.text
    visit_id = created.json()["id"]
    sent = texted_harness.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY_SENT, headers=texted_harness.patient()
    )
    assert sent.status_code == 200, sent.text

    response = texted_harness.client.post(
        "/v1/consents/withdraw",
        json={"scope": "core", "at": CLIENT_AT},
        headers=texted_harness.patient(),
    )
    assert response.status_code == 200
    body = response.json()
    assert "core" in body["withdrawn_scopes"]
    assert len(body["revoked_share_ids"]) == 1

    snapshot_refused = texted_harness.client.get("/v1/visits", headers=texted_harness.patient())
    assert snapshot_refused.status_code == 403  # the guard sees it immediately


def test_withdrawing_a_default_on_purpose_materialises_the_opt_out(
    harness: ApiHarness,
) -> None:
    response = harness.client.post(
        "/v1/consents/withdraw",
        json={"scope": "learning:personal", "at": CLIENT_AT},
        headers=harness.patient(),
    )
    assert response.status_code == 200
    assert response.json()["withdrawn_scopes"] == ["learning:personal"]
    row = _scope_row(_snapshot(harness), "learning:personal")
    assert row["reason"] == "withdrawn"


# --- patient-only (403 for the clinic admin) ----------------------------------------------


def test_admin_is_refused_on_all_three_routes(harness: ApiHarness) -> None:
    assert harness.client.get("/v1/consents", headers=harness.admin()).status_code == 403
    grant = harness.client.post(
        "/v1/consents/grant",
        json={"scope": "voice", "version": "1", "text_hash": "0" * 64, "at": CLIENT_AT},
        headers=harness.admin(),
    )
    assert grant.status_code == 403
    assert grant.json() == {"error": "forbidden"}
    withdraw = harness.client.post(
        "/v1/consents/withdraw",
        json={"scope": "voice", "at": CLIENT_AT},
        headers=harness.admin(),
    )
    assert withdraw.status_code == 403


# --- the closed list: 422 with the purpose id only (invariant 6) --------------------------


def test_unknown_purposes_answer_422_with_the_id_only(texted_harness: ApiHarness) -> None:
    for scope in ("lane:acoustic", "share", "marketing"):
        grant = texted_harness.client.post(
            "/v1/consents/grant",
            json={"scope": scope, "version": "1", "text_hash": "0" * 64, "at": CLIENT_AT},
            headers=texted_harness.patient(),
        )
        assert grant.status_code == 422, scope
        assert grant.json() == {"error": "purpose_unknown", "scope": scope}
        withdraw = texted_harness.client.post(
            "/v1/consents/withdraw",
            json={"scope": scope, "at": CLIENT_AT},
            headers=texted_harness.patient(),
        )
        assert withdraw.status_code == 422, scope
        assert withdraw.json() == {"error": "purpose_unknown", "scope": scope}


# --- the scan: consent_management is a declaration, not an exemption ----------------------


def test_consent_routes_declare_the_management_marker(harness: ApiHarness) -> None:
    marked = consent_management_routes(harness.client.app)
    assert marked == [
        "GET /v1/consents",
        "POST /v1/consents/grant",
        "POST /v1/consents/withdraw",
    ]
    for route in marked:
        path = route.split(" ", 1)[1]
        assert path == CONSENT_MANAGEMENT_PREFIX or path.startswith(CONSENT_MANAGEMENT_PREFIX + "/")
    # with the marker accepted, the whole surface still scans clean
    assert unguarded_data_routes(harness.client.app) == []


def test_consent_management_marker_outside_the_prefix_is_not_a_declaration() -> None:
    """Negative control (the pre_auth pattern): a data route elsewhere cannot
    borrow the marker to dodge the scan — and a lookalike prefix does not
    count either (the boundary is a path segment, not a substring)."""
    app = FastAPI()

    @app.get("/v1/sneaky", dependencies=[consent_management()])
    async def sneaky() -> dict[str, str]:
        return {"ok": "no"}

    @app.get("/v1/consentsish", dependencies=[consent_management()])
    async def lookalike() -> dict[str, str]:
        return {"ok": "no"}

    assert sorted(unguarded_data_routes(app)) == ["GET /v1/consentsish", "GET /v1/sneaky"]


def test_snapshot_read_is_audited(harness: ApiHarness) -> None:
    _snapshot(harness)
    entries = [e for e in harness.audit_store.entries() if e.action == "api.consent.read"]
    assert entries
    assert entries[-1].resource_ref == f"patient:{DEV_PATIENT_ID}"
