"""INT-038 — consents are free, specific, informed, UNBUNDLED (KVKK-5/6;
files/06 §2: "no pre-ticked boxes, no bundling, no service-conditioning").

What this file pins:
- server-side defaults: every explicit-consent purpose starts OFF (nothing
  is pre-ticked anywhere the server can see); the only default-on purposes
  are the two whose lawful basis is NOT consent, exactly as files/06 §2
  writes them — ``learning:personal`` (performance of the very service the
  patient configured) and ``learning:service_improvement`` (de-identified
  aggregates, opt-out costs no feature);
- the consent-object creation path grants exactly the named purpose and
  nothing else — granting ``core`` implies no other grant;
- core service functions with EVERY optional purpose off, and refusing an
  optional purpose refuses only that purpose's feature, never core;
- structurally: no route bundles an optional purpose into its enforced
  core requirement (the route table proves service-conditioning cannot
  be introduced silently);
- opting out of the default-on purposes costs no feature.
"""

from __future__ import annotations

import dataclasses

from api_harness import ApiHarness, run
from intake_api.consent_guard import route_policies
from intake_api.db import tenant_session
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
from intake_platform.consent import (
    PURPOSES,
    LegalBasis,
    PurposeDef,
    consent_state,
    withdraw_consent,
)
from intake_platform.db.models import Consent
from legal_harness import api_state, grant_bound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

NOTE_BODY_DRAFT = {
    "sections": [{"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Ağrı"]}],
    "scopes": {"chief_complaint": True},
    "status": "draft",
}


# --- defaults: nothing pre-ticked ----------------------------------------------------------


def test_every_explicit_consent_purpose_defaults_off() -> None:
    for purpose in PURPOSES:
        if purpose.legal_basis is LegalBasis.EXPLICIT_CONSENT:
            assert purpose.default_granted is False, purpose.id


def _defaults_on(purposes: tuple[PurposeDef, ...]) -> tuple[str, ...]:
    """Read by purpose ID, never by basis label: a relabelled basis cannot
    hide a pre-tick."""
    return tuple(p.id for p in purposes if p.default_granted)


def test_no_purpose_defaults_on_not_even_the_learning_ones() -> None:
    # INT-603 legal review round 2 (the owner's KVKK approval, D43 pending
    # number): files/06 §2 now says both learning purposes are off until the
    # patient turns them on. KVKK m.6 as amended by Law 7499 leaves no
    # non-consent ground that plainly carries health data for them, and until
    # counsel records one (HB-L27) the answer fails closed.
    assert _defaults_on(PURPOSES) == ()
    by_id = {p.id: p for p in PURPOSES}
    assert by_id["learning:personal"].legal_basis is LegalBasis.SERVICE_PERFORMANCE
    assert by_id["learning:service_improvement"].legal_basis is LegalBasis.DEIDENTIFIED_OPTOUT


def test_near_miss_a_learning_default_flipped_on_fails_the_check() -> None:
    for scope in ("learning:personal", "learning:service_improvement"):
        flipped = tuple(
            dataclasses.replace(p, default_granted=True) if p.id == scope else p for p in PURPOSES
        )
        assert _defaults_on(flipped) == (scope,)
    # and relabelling the basis does not hide it
    relabelled = tuple(
        dataclasses.replace(p, default_granted=True, legal_basis=LegalBasis.SERVICE_PERFORMANCE)
        if p.id == "research"
        else p
        for p in PURPOSES
    )
    assert _defaults_on(relabelled) == ("research",)


def test_server_side_state_matches_the_defaults_for_a_fresh_patient(
    bound_harness: ApiHarness,
) -> None:
    """The dev patient's seeded scopes aside, every other purpose must
    evaluate exactly to its registry default — the server is the place a
    pre-tick would have to live, and there is none."""
    state = api_state(bound_harness)

    async def _decide(scope: str) -> tuple[bool, str]:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            decision = await consent_state(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope=scope,
                catalog=state.consent_catalog,
            )
            return decision.allowed, decision.reason

    for scope in (
        "voice",
        "wellbeing",
        "lane:affect",
        "lane:linguistic",
        "satisfaction",
        "research",
        # INT-603 round 2: a missing grant is not granted, learning included
        "learning:personal",
        "learning:service_improvement",
    ):
        allowed, reason = run(_decide(scope))
        assert (allowed, reason) == (False, "absent"), scope


# --- granting is specific: one purpose, one grant ------------------------------------------


def test_granting_core_grants_nothing_else(bound_harness: ApiHarness) -> None:
    async def _rows() -> dict[str, int]:
        async with AsyncSession(bound_harness.engine) as session:
            rows = (
                await session.scalars(
                    select(Consent).where(
                        Consent.tenant_id == DEV_TENANT_ID,
                        Consent.patient_id == DEV_PATIENT_ID,
                        Consent.text_hash.is_not(None),
                    )
                )
            ).all()
            counts: dict[str, int] = {}
            for row in rows:
                counts[row.scope] = counts.get(row.scope, 0) + 1
            return counts

    before: dict[str, int] = run(_rows())
    grant_bound(bound_harness, "core")
    after: dict[str, int] = run(_rows())
    assert after.get("core", 0) == before.get("core", 0) + 1
    for scope, count in before.items():
        if scope != "core":
            assert after.get(scope, 0) == count, scope
    assert set(after) - set(before) <= {"core"}


# --- core works with every optional purpose off --------------------------------------------


def _strip_to_core(harness: ApiHarness) -> None:
    harness.revoke_consent("documents")
    harness.revoke_consent("share:previsit_note")


def test_core_service_functions_with_every_optional_purpose_off(
    bound_harness: ApiHarness,
) -> None:
    _strip_to_core(bound_harness)
    client, headers = bound_harness.client, bound_harness.patient()

    created = client.post("/v1/visits", json=VISIT_BODY, headers=headers)
    assert created.status_code == 201, created.text
    visit_id = str(created.json()["id"])

    assert client.get("/v1/visits", headers=headers).status_code == 200
    assert client.get(f"/v1/visits/{visit_id}", headers=headers).status_code == 200

    saved = client.put(f"/v1/visits/{visit_id}/note", json=NOTE_BODY_DRAFT, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "draft"
    assert client.get(f"/v1/visits/{visit_id}/note", headers=headers).status_code == 200


def test_refusing_an_optional_purpose_refuses_only_its_own_feature(
    bound_harness: ApiHarness,
) -> None:
    _strip_to_core(bound_harness)
    client, headers = bound_harness.client, bound_harness.patient()
    created = client.post("/v1/visits", json=VISIT_BODY, headers=headers)
    visit_id = str(created.json()["id"])

    # a draft note saves fine under core alone …
    saved = client.put(f"/v1/visits/{visit_id}/note", json=NOTE_BODY_DRAFT, headers=headers)
    assert saved.status_code == 200

    # … the documents feature refuses, naming its own purpose only …
    upload = client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/pdf", "sha256": "ab" * 32},
        headers=headers,
    )
    assert upload.status_code == 403
    assert upload.json() == {"error": "consent_required", "scope": "documents"}

    # … sending a note refuses on the share purpose only …
    sent = client.put(
        f"/v1/visits/{visit_id}/note",
        json={**NOTE_BODY_DRAFT, "status": "sent"},
        headers=headers,
    )
    assert sent.status_code == 403
    assert sent.json() == {"error": "consent_required", "scope": "share:previsit_note"}

    # … and core is untouched afterwards: no penalty beyond the lane itself
    # (files/06 §2.1).
    assert client.get("/v1/visits", headers=headers).status_code == 200
    assert client.get(f"/v1/visits/{visit_id}/note", headers=headers).status_code == 200


def test_no_route_bundles_an_optional_purpose_into_core(harness: ApiHarness) -> None:
    """Service-conditioning would look like a route that enforces core AND
    an optional purpose together. The route table proves there is none —
    and this scan fails the moment one is introduced."""
    for (method, path), policy in route_policies(harness.client.app).items():
        if "core" in policy.enforced:
            assert policy.enforced == ("core",), (method, path)


# --- opting out of the default-on purposes costs no feature --------------------------------


def test_opt_out_of_learning_purposes_costs_no_feature(bound_harness: ApiHarness) -> None:
    state = api_state(bound_harness)

    async def _opt_out() -> None:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            for scope in ("learning:personal", "learning:service_improvement"):
                await withdraw_consent(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    patient_id=DEV_PATIENT_ID,
                    scope=scope,
                    audit=state.audit,
                    actor="dev-patient",
                )

    run(_opt_out())

    async def _decide(scope: str) -> tuple[bool, str]:
        async with tenant_session(bound_harness.engine, DEV_TENANT_ID) as session:
            decision = await consent_state(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                scope=scope,
                catalog=state.consent_catalog,
            )
            return decision.allowed, decision.reason

    # INT-603 round 2: neither was ever granted, so turning them off writes
    # nothing and they stay "absent" — not granted either way
    for scope in ("learning:personal", "learning:service_improvement"):
        assert run(_decide(scope)) == (False, "absent"), scope

    # with both off, the service still works end to end
    client, headers = bound_harness.client, bound_harness.patient()
    created = client.post("/v1/visits", json=VISIT_BODY, headers=headers)
    assert created.status_code == 201
    assert client.get("/v1/visits", headers=headers).status_code == 200
