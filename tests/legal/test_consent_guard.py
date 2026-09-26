"""INT-038 — consent service + consent_guard (files/06 §2; invariants 4, 6, 18).

What this file pins:
- the purpose registry is EXACTLY the closed files/06 §2 list, in order,
  with ``lane:acoustic`` rejected (an investigational-device ICF, not a
  consent purpose — files/06 §2.4);
- text_hash binds the exact docs/legal file bytes; the loader fails closed
  on a missing or malformed text (invariant 18 — no text, no grant);
- the guard refuses with a typed 403 naming the missing purpose id ONLY
  (invariant 6), and a stale grant (text version bumped) is treated as
  absent and audited as ``consent.stale`` — re-granting under the new text
  restores access (re-prompt on change);
- the route-table scan: every data route of the API declares its consent
  scopes; only the invariant-15 meta endpoints are exempt;
- withdrawal cascades dependent grants and live shares in one evaluation
  pass, and the sweep contract proves ≤ 1 min end-to-end on a fake clock.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from api_harness import ApiHarness, run
from intake_api.consent_guard import (
    PRE_AUTH_PREFIX,
    pre_auth,
    pre_auth_routes,
    route_policies,
    unguarded_data_routes,
)
from intake_api.db import tenant_session
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
from intake_platform.consent import (
    CHANNELS,
    PURPOSES,
    SWEEP_INTERVAL,
    WITHDRAWAL_CASCADE_BUDGET,
    ConsentTextCatalog,
    ConsentTextInvalidError,
    ConsentTextMissingError,
    LegalBasis,
    SweepSchedule,
    UnknownPurposeError,
    consent_state,
    dependents_of,
    grant_consent,
    purpose_ids,
    resolve_scope,
    sweep_withdrawals,
    withdraw_consent,
)
from intake_platform.db.models import Consent, Share
from legal_harness import (
    FIXTURE_VERSION,
    api_state,
    grant_bound,
    write_all_consent_texts,
    write_consent_text,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


class RecordingAudit:
    """Unit-lane audit recorder (tests only): same signature as the api's
    AuditWriter.record, so the service cannot skip auditing a change."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str, str]] = []

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        self.entries.append((actor, action, resource_ref, consent_scope))

    def actions(self) -> list[str]:
        return [action for _, action, _, _ in self.entries]


# --- the purpose registry: exactly files/06 §2 -------------------------------------------


def test_purpose_registry_is_exactly_the_06_list_in_order() -> None:
    assert purpose_ids() == (
        "core",
        "voice",
        "wellbeing",
        "lane:affect",
        "lane:linguistic",
        "documents",
        "learning:personal",
        "learning:service_improvement",
        "satisfaction",
        "share",
        "research",
    )
    assert len(PURPOSES) == 11


def test_lane_acoustic_is_not_a_consent_purpose() -> None:
    # files/06 §2.4: an investigational-device ICF, not a toggle.
    with pytest.raises(UnknownPurposeError):
        resolve_scope("lane:acoustic")


def test_unknown_scopes_are_rejected() -> None:
    for scope in ("marketing", "share", "", "core ", "learning:everything"):
        if scope == "share":
            # the bare family id is not grantable: a share is always
            # parameterised (files/06 §2: share:{recipient,visit,sections,expiry})
            with pytest.raises(UnknownPurposeError):
                resolve_scope(scope)
        else:
            with pytest.raises(UnknownPurposeError):
                resolve_scope(scope)


def test_share_family_scopes_resolve_to_the_share_purpose() -> None:
    assert resolve_scope("share:previsit_note").id == "share"


def test_channels_are_the_06_layered_aydinlatma_surfaces() -> None:
    assert CHANNELS == ("app", "kiosk", "clinician", "admin", "web")


def test_cascade_graph_core_reaches_everything_and_voice_reaches_affect() -> None:
    assert set(dependents_of("core")) == set(purpose_ids()) - {"core"}
    assert dependents_of("voice") == ("lane:affect",)
    assert dependents_of("documents") == ()


# --- text_hash binds the shown docs/legal bytes (invariant 18) ----------------------------


def test_text_hash_is_the_sha256_of_the_exact_file_bytes(tmp_path: Path) -> None:
    root = tmp_path / "consents"
    path = write_consent_text(root, "core")
    catalog = ConsentTextCatalog(root)
    entry = catalog.entry("core")
    assert entry.version == FIXTURE_VERSION
    assert entry.text_hash == hashlib.sha256(path.read_bytes()).hexdigest()

    # one changed byte is a different text — the binding must move with it
    path.write_bytes(path.read_bytes() + b"!")
    assert catalog.entry("core").text_hash != entry.text_hash


def test_missing_text_fails_closed(tmp_path: Path) -> None:
    catalog = ConsentTextCatalog(tmp_path / "does-not-exist")
    with pytest.raises(ConsentTextMissingError):
        catalog.entry("core")
    assert catalog.try_entry("core") is None


def test_malformed_text_fails_closed_not_open(tmp_path: Path) -> None:
    root = tmp_path / "consents"
    root.mkdir()
    # no version front matter → invalid, and invalid is an error even on the
    # tolerant lookup: a text we cannot version is a text we cannot bind
    (root / "core.tr.md").write_text("Rıza metni.\n", encoding="utf-8")
    catalog = ConsentTextCatalog(root)
    with pytest.raises(ConsentTextInvalidError):
        catalog.entry("core")
    with pytest.raises(ConsentTextInvalidError):
        catalog.try_entry("core")


def test_grant_refuses_without_a_docs_legal_text(harness: ApiHarness) -> None:
    """docs/legal/consents does not exist yet (INT-210, awaiting-human):
    the grant path must fail closed rather than record an unbound consent."""
    state = api_state(harness)
    audit = RecordingAudit()

    async def _grant() -> None:
        async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
            await grant_consent(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="voice",
                channel="app",
                evidence_ref="evidence:test/voice",
                catalog=state.consent_catalog,
                audit=audit,
                actor="dev-patient",
            )

    with pytest.raises(ConsentTextMissingError):
        run(_grant())
    assert audit.entries == []  # a refused grant is not a consent change


# --- the guard: typed 403, purpose id only (invariant 6) ----------------------------------


def test_guard_refusal_names_the_purpose_id_and_nothing_else(harness: ApiHarness) -> None:
    harness.revoke_consent("core")
    response = harness.client.get("/v1/visits", headers=harness.patient())
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "core"}


def test_guard_runs_on_the_bound_harness_too(bound_harness: ApiHarness) -> None:
    response = bound_harness.client.get("/v1/visits", headers=bound_harness.patient())
    assert response.status_code == 200


# --- route-table scan: every data route declares scopes -----------------------------------


def test_every_data_route_declares_consent_scopes(harness: ApiHarness) -> None:
    app = harness.client.app
    assert unguarded_data_routes(app) == []


def test_pre_auth_declarations_are_exactly_the_auth_bootstrap_routes(
    harness: ApiHarness,
) -> None:
    """INT-131 pre-auth routes have no principal, so they cannot enforce a
    consent scope — but they must DECLARE that, and only under /v1/auth."""
    marked = pre_auth_routes(harness.client.app)
    assert marked == [
        "GET /v1/auth/dev/otp-peek",
        "POST /v1/auth/attest/challenge",
        "POST /v1/auth/attest/key",
        "POST /v1/auth/otp/request",
        "POST /v1/auth/otp/verify",
        "POST /v1/auth/token/refresh",
    ]
    assert all(route.split(" ", 1)[1].startswith(PRE_AUTH_PREFIX) for route in marked)


def test_pre_auth_marker_outside_the_auth_prefix_is_not_a_declaration() -> None:
    """A data route elsewhere cannot borrow the pre-auth marker to dodge the
    scan: outside PRE_AUTH_PREFIX it still counts as unguarded."""
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/v1/sneaky", dependencies=[pre_auth()])
    async def sneaky() -> dict[str, str]:
        return {"ok": "no"}

    assert unguarded_data_routes(app) == ["GET /v1/sneaky"]


def test_route_policy_declarations_cover_the_api_surface(harness: ApiHarness) -> None:
    policies = route_policies(harness.client.app)
    by_route = {
        (method, path): tuple(sorted(policy.enforced + policy.conditional))
        for (method, path), policy in policies.items()
    }
    assert by_route[("GET", "/v1/visits")] == ("core",)
    assert by_route[("POST", "/v1/visits")] == ("core",)
    assert by_route[("GET", "/v1/visits/{visit_id}")] == ("core",)
    assert by_route[("GET", "/v1/visits/{visit_id}/note")] == ("core", "share:previsit_note")
    assert by_route[("PUT", "/v1/visits/{visit_id}/note")] == ("core", "share:previsit_note")
    for method, suffix in (
        ("POST", ""),
        ("GET", ""),
        ("PUT", "/{doc_id}/content"),
        ("GET", "/{doc_id}/url"),
    ):
        assert by_route[(method, f"/v1/visits/{{visit_id}}/documents{suffix}")] == ("documents",)


def test_every_declared_scope_is_a_registry_scope(harness: ApiHarness) -> None:
    for policy in route_policies(harness.client.app).values():
        for scope in policy.enforced + policy.conditional:
            resolve_scope(scope)  # raises UnknownPurposeError on drift


# --- re-prompt on change: stale grant = absent, audited -----------------------------------


def test_text_version_bump_invalidates_prior_grants(
    bound_harness: ApiHarness, legal_root: Path
) -> None:
    assert (
        bound_harness.client.get("/v1/visits", headers=bound_harness.patient()).status_code == 200
    )

    write_all_consent_texts(legal_root, version="2026-09-01.2")

    response = bound_harness.client.get("/v1/visits", headers=bound_harness.patient())
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "core"}

    stale = [e for e in bound_harness.audit_store.entries() if e.action == "consent.stale"]
    assert stale and stale[-1].consent_scope_ref == "scope:core"
    assert stale[-1].resource_ref == f"patient:{DEV_PATIENT_ID}"


def test_regranting_under_the_new_text_restores_access(
    bound_harness: ApiHarness, legal_root: Path
) -> None:
    write_all_consent_texts(legal_root, version="2026-09-01.2")
    assert (
        bound_harness.client.get("/v1/visits", headers=bound_harness.patient()).status_code == 403
    )

    grant_bound(bound_harness, "core")
    assert (
        bound_harness.client.get("/v1/visits", headers=bound_harness.patient()).status_code == 200
    )


def test_grant_and_withdraw_are_audited_on_the_chain(bound_harness: ApiHarness) -> None:
    state = api_state(bound_harness)

    async def _withdraw() -> None:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            await withdraw_consent(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="documents",
                audit=state.audit,
                actor="dev-patient",
            )

    run(_withdraw())
    actions = [e.action for e in bound_harness.audit_store.entries()]
    assert "consent.grant" in actions
    assert "consent.withdraw" in actions


# --- withdrawal cascade: one pass now, sweep contract ≤ 1 min -----------------------------


def _live_scopes(harness: ApiHarness) -> set[str]:
    async def _read() -> set[str]:
        async with AsyncSession(harness.engine) as session:
            rows = (
                await session.scalars(
                    select(Consent).where(
                        Consent.tenant_id == DEV_TENANT_ID,
                        Consent.patient_id == DEV_PATIENT_ID,
                        Consent.revoked_at.is_(None),
                    )
                )
            ).all()
            return {row.scope for row in rows}

    result: set[str] = run(_read())
    return result


def _live_share_count(harness: ApiHarness) -> int:
    async def _read() -> int:
        async with AsyncSession(harness.engine) as session:
            rows = (await session.scalars(select(Share).where(Share.revoked_at.is_(None)))).all()
            return len(rows)

    count: int = run(_read())
    return count


def _send_note(harness: ApiHarness) -> str:
    created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert created.status_code == 201
    visit_id = str(created.json()["id"])
    sent = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY_SENT, headers=harness.patient()
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    return visit_id


def test_core_withdrawal_cascades_grants_and_live_shares_in_one_pass(
    bound_harness: ApiHarness,
) -> None:
    _send_note(bound_harness)
    assert _live_share_count(bound_harness) == 1
    state = api_state(bound_harness)

    async def _withdraw() -> None:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            report = await withdraw_consent(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="core",
                audit=state.audit,
                actor="dev-patient",
            )
            assert "core" in report.withdrawn_scopes
            assert report.revoked_share_ids  # the live Doctor-Link share fell with core

    run(_withdraw())
    assert _live_scopes(bound_harness) == set()
    assert _live_share_count(bound_harness) == 0
    actions = [e.action for e in bound_harness.audit_store.entries()]
    assert "consent.withdraw" in actions
    assert "consent.cascade" in actions

    # and the guard sees it immediately — the withdrawal is effective now,
    # not at the next sweep
    response = bound_harness.client.get("/v1/visits", headers=bound_harness.patient())
    assert response.status_code == 403


def test_voice_withdrawal_cascades_exactly_its_dependent_lane(
    bound_harness: ApiHarness,
) -> None:
    grant_bound(bound_harness, "voice", "lane:affect", "lane:linguistic")
    state = api_state(bound_harness)

    async def _withdraw() -> None:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            await withdraw_consent(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="voice",
                audit=state.audit,
                actor="dev-patient",
            )

    run(_withdraw())
    live = _live_scopes(bound_harness)
    assert "voice" not in live
    assert "lane:affect" not in live  # rides the voice stream (files/06 §2.1)
    assert "lane:linguistic" in live  # text-only lane is independent (files/06 §2.1)
    assert "core" in live  # withdrawal never over-reaches


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance_to(self, instant: datetime) -> None:
        assert instant >= self._now
        self._now = instant


def test_sweep_schedule_contract_bounds_end_to_end_at_one_minute() -> None:
    """The synchronous pass already cascades immediately; the sweep is the
    crash-recovery bound. Contract: for ANY withdrawal instant, the next
    scheduled sweep runs within one interval, and interval + pass budget
    stays inside the one-minute acceptance budget."""
    schedule = SweepSchedule()
    epoch = datetime(2026, 8, 27, 12, 0, 0, tzinfo=UTC)
    assert schedule.interval + schedule.pass_budget <= WITHDRAWAL_CASCADE_BUDGET
    assert schedule.interval == SWEEP_INTERVAL
    for offset_ms in (0, 1, 999, 15_000, 29_999, 30_000, 31_337, 59_999, 60_000, 61_000):
        withdrawal_at = epoch + timedelta(milliseconds=offset_ms)
        next_run = schedule.next_run_after(withdrawal_at, epoch=epoch)
        assert next_run > withdrawal_at
        assert next_run - withdrawal_at <= schedule.interval
        completes_by = next_run + schedule.pass_budget
        assert completes_by - withdrawal_at <= WITHDRAWAL_CASCADE_BUDGET


def test_sweep_completes_a_crash_interrupted_cascade_within_the_budget(
    bound_harness: ApiHarness,
) -> None:
    """Fake clock, no sleeps: mark core revoked WITHOUT its cascade (as a
    crash between the mark and the cascade would leave it), then run the
    next scheduled sweep and prove full revocation within ≤ 1 min."""
    _send_note(bound_harness)
    state = api_state(bound_harness)
    schedule = SweepSchedule()
    # the fake clock starts at wall-now so the already-written grants sit
    # BEFORE the simulated withdrawal instant; time only ever moves by
    # advance_to — no sleeps anywhere
    epoch = datetime.now(UTC)
    withdrawal_at = epoch + timedelta(seconds=17, milliseconds=250)
    clock = FakeClock(epoch)

    async def _mark_without_cascade() -> None:
        async with AsyncSession(bound_harness.engine) as session, session.begin():
            rows = (
                await session.scalars(
                    select(Consent).where(
                        Consent.tenant_id == DEV_TENANT_ID,
                        Consent.patient_id == DEV_PATIENT_ID,
                        Consent.scope == "core",
                        Consent.revoked_at.is_(None),
                    )
                )
            ).all()
            assert rows
            for row in rows:
                row.revoked_at = withdrawal_at

    run(_mark_without_cascade())
    clock.advance_to(withdrawal_at)
    assert _live_share_count(bound_harness) == 1  # the crash left the share standing

    clock.advance_to(schedule.next_run_after(withdrawal_at, epoch=epoch))

    async def _sweep() -> int:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            return await sweep_withdrawals(
                session,
                tenant_id=DEV_TENANT_ID,
                audit=state.audit,
                actor="consent-sweep",
                now=clock.now(),
            )

    repaired: int = run(_sweep())
    assert repaired > 0
    assert _live_scopes(bound_harness) == set()
    assert _live_share_count(bound_harness) == 0
    assert clock.now() - withdrawal_at <= schedule.interval
    assert clock.now() + schedule.pass_budget - withdrawal_at <= WITHDRAWAL_CASCADE_BUDGET
    cascade = [e for e in bound_harness.audit_store.entries() if e.action == "consent.cascade"]
    assert cascade and all(e.actor == "consent-sweep" for e in cascade[-repaired:])


def test_sweep_spares_grants_made_after_the_withdrawal(bound_harness: ApiHarness) -> None:
    """A re-grant after a withdrawal is a NEW consent; the sweep must never
    kill it while repairing the old cascade."""
    state = api_state(bound_harness)
    withdrawal_at = datetime.now(UTC) + timedelta(seconds=17)

    async def _mark_core_revoked() -> None:
        async with AsyncSession(bound_harness.engine) as session, session.begin():
            rows = (
                await session.scalars(
                    select(Consent).where(
                        Consent.tenant_id == DEV_TENANT_ID,
                        Consent.patient_id == DEV_PATIENT_ID,
                        Consent.scope == "core",
                        Consent.revoked_at.is_(None),
                    )
                )
            ).all()
            for row in rows:
                row.revoked_at = withdrawal_at

    run(_mark_core_revoked())

    async def _regrant_documents_later() -> None:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            await grant_consent(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="documents",
                channel="app",
                evidence_ref="evidence:test/documents.regrant",
                catalog=state.consent_catalog,
                audit=state.audit,
                actor="dev-patient",
                now=withdrawal_at + timedelta(seconds=5),
            )

    run(_regrant_documents_later())

    async def _sweep() -> int:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            return await sweep_withdrawals(
                session,
                tenant_id=DEV_TENANT_ID,
                audit=state.audit,
                actor="consent-sweep",
                now=withdrawal_at + timedelta(seconds=30),
            )

    run(_sweep())
    live = _live_scopes(bound_harness)
    assert "documents" in live  # granted after the withdrawal instant — spared
    assert "share:previsit_note" not in live  # granted before it — swept


# --- service-level decision semantics ------------------------------------------------------


def test_consent_state_reports_stale_against_the_current_text(
    bound_harness: ApiHarness, legal_root: Path
) -> None:
    state = api_state(bound_harness)

    async def _decide() -> tuple[str, str]:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            before = await consent_state(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="core",
                catalog=state.consent_catalog,
            )
            write_all_consent_texts(legal_root, version="2026-09-02.3")
            after = await consent_state(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="core",
                catalog=state.consent_catalog,
            )
            return before.reason, after.reason

    before_reason, after_reason = run(_decide())
    assert before_reason == "granted"
    assert after_reason == "stale"


def test_purpose_definitions_carry_their_lawful_basis() -> None:
    by_id = {p.id: p for p in PURPOSES}
    assert by_id["core"].legal_basis is LegalBasis.EXPLICIT_CONSENT
    assert by_id["learning:personal"].legal_basis is LegalBasis.SERVICE_PERFORMANCE
    assert by_id["learning:service_improvement"].legal_basis is LegalBasis.DEIDENTIFIED_OPTOUT
    assert by_id["share"].parameterised is True


def test_grant_validates_channel_and_evidence_shape(bound_harness: ApiHarness) -> None:
    state = api_state(bound_harness)

    async def _grant(channel: str, evidence_ref: str) -> None:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            await grant_consent(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope="wellbeing",
                channel=channel,
                evidence_ref=evidence_ref,
                catalog=state.consent_catalog,
                audit=state.audit,
                actor="dev-patient",
            )

    with pytest.raises(ValueError, match="channel"):
        run(_grant("postcard", "evidence:test/wellbeing"))
    with pytest.raises(ValueError, match="evidence_ref"):
        run(_grant("app", "hasta Ayşe Yılmaz onayladı"))  # narrative shapes are refused


def test_grant_rows_carry_the_full_06_record(bound_harness: ApiHarness) -> None:
    """files/06 §2: each consent stores {version, text_hash, ts, channel,
    evidence}. The dev-tier seed rows predate binding; rows written by the
    service must carry all five."""

    async def _read() -> list[Consent]:
        async with AsyncSession(bound_harness.engine) as session:
            rows = (
                await session.scalars(
                    select(Consent).where(
                        Consent.tenant_id == DEV_TENANT_ID,
                        Consent.patient_id == DEV_PATIENT_ID,
                        Consent.scope == "core",
                        Consent.text_hash.is_not(None),
                    )
                )
            ).all()
            return list(rows)

    rows: list[Consent] = run(_read())
    assert rows
    for row in rows:
        assert row.version == FIXTURE_VERSION
        assert row.text_hash and len(row.text_hash) == 64
        assert row.granted_at is not None
        assert row.channel == "app"
        assert row.evidence_ref == "evidence:test/core"


def test_unknown_patient_defaults_are_fail_closed(bound_harness: ApiHarness) -> None:
    state = api_state(bound_harness)
    stranger = uuid.uuid4()

    async def _decide(scope: str) -> bool:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            decision = await consent_state(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=stranger,
                scope=scope,
                catalog=state.consent_catalog,
            )
            return decision.allowed

    for scope in ("core", "voice", "documents", "share:previsit_note", "research"):
        assert run(_decide(scope)) is False
