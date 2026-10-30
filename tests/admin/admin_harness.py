"""Harness for the INT-180 admin shell suite.

Two things it owns and nothing else:

- **A recorded Keycloak claim set.** No test dials Keycloak. The fixture in
  ``fixtures/keycloak_claims.json`` carries the claim shape a Keycloak access
  token presents, and ``test_rbac_matrix.py`` holds it against the committed
  realm export (``infra/keycloak/dev-realm.json``) so the two cannot drift.
- **A harness builder** that wires the admin surface onto the services/api
  unit-lane app, with a documentation-range client address so the IP
  allow-list is exercised rather than bypassed.

The client address is ``192.0.2.x`` — RFC 5737 TEST-NET-1, reserved for
documentation and never routable. It lives here, in tests, and never in the
shipped allow-list, which ships empty (invariant 17: an allow-list with no
addresses is the correct shipping state; a plausible address is not).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from access_fakes import seed_signed_sections
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from intake_platform.admin import (
    AdminWiring,
    Deployment,
    FourEyesService,
    IpAllowList,
)
from intake_platform.admin.access import IdentityWiring
from intake_platform.admin.access.review import CONSOLE_SECTIONS, ReviewLedger
from intake_platform.admin.principal import ClaimsRejected
from intake_platform.release_freeze import ReleaseFreezeStore
from intake_platform.safety_inbox import SafetyInbox
from intake_platform.voice_control import VoiceControlStore

#: The tenant deployment map the wiring ships EMPTY (files/08 §2.6): whether
#: INTAKE is processor or controller for a tenant decides whether a lawful
#: basis for staff access exists at all, and no file in the repo states it per
#: tenant. Tests supply their own; production supplies it from the tenant
#: registry once INT-250's gate carries one.
TEST_DEPLOYMENTS = {
    "tenant-a": Deployment.PROCESSOR,
    "tenant-c": Deployment.CONTROLLER,
}

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLAIMS_FIXTURE = FIXTURES / "keycloak_claims.json"

#: TEST-NET-1 (RFC 5737). Documentation-only, never routable.
CLIENT_ADDR = ("192.0.2.10", 51000)
ALLOWED_CIDRS = "192.0.2.0/24"
BLOCKED_ADDR = ("198.51.100.7", 51000)


def recorded_claims() -> Mapping[str, Mapping[str, Any]]:
    payload = json.loads(CLAIMS_FIXTURE.read_text(encoding="utf-8"))
    accounts: Mapping[str, Mapping[str, Any]] = payload["accounts"]
    return accounts


class RecordedClaimsVerifier:
    """Token → recorded claim set. A verifier seam, exercised against a
    committed fixture: the production verifier validates a Keycloak
    signature, and neither it nor this one is allowed to reach a network."""

    def __init__(self, accounts: Mapping[str, Mapping[str, Any]]) -> None:
        self._accounts = dict(accounts)

    def verify(self, token: str) -> Mapping[str, Any]:
        claims = self._accounts.get(token)
        if claims is None:
            raise ClaimsRejected("token is not in the recorded claim set")
        return claims


def token_for(role: str) -> str:
    """The recorded account whose single console role is ``role``."""
    return f"kc:{role}"


def bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(role)}"}


def build_admin_wiring(
    *,
    allowlist: str = ALLOWED_CIDRS,
    deployments: Mapping[str, Deployment] | None = None,
    voice_controls: VoiceControlStore | None = None,
    release_freeze: ReleaseFreezeStore | None = None,
    identity: IdentityWiring | None = None,
    review_clock: Callable[[], datetime] | None = None,
    safety_inbox: SafetyInbox | None = None,
) -> AdminWiring:
    return AdminWiring(
        claims=RecordedClaimsVerifier(recorded_claims()),
        ip_allowlist=IpAllowList.from_spec(allowlist),
        four_eyes=FourEyesService(),
        deployments=dict(TEST_DEPLOYMENTS if deployments is None else deployments),
        voice_controls=voice_controls,
        release_freeze=release_freeze,
        review_ledger=ReviewLedger(clock=review_clock),
        identity=identity,
        safety_inbox=safety_inbox,
    )


def build_admin_harness(
    tmp_path: Path,
    *,
    admin: AdminWiring | None = None,
    client_addr: tuple[str, int] = CLIENT_ADDR,
    signed_sections: tuple[str, ...] = CONSOLE_SECTIONS,
    signed_at: datetime | None = None,
) -> Iterator[ApiHarness]:
    """The console on the unit-lane app.

    INT-366: a console whose access review was never countersigned is
    read-only for ``platform_owner`` and ``tenant_admin`` (files/08 §2.7), so
    by default the harness starts from a review countersigned *now* — suites
    that are not about the review exercise their own routes, not the
    downgrade. ``signed_sections=()`` starts from no review at all, which is
    what the review suite does.
    """
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        admin=admin if admin is not None else build_admin_wiring(),
        client_addr=client_addr,
    ):
        seed_signed_sections(harness.audit_store, signed_sections, at=signed_at)
        yield harness


@dataclass(frozen=True)
class RouteDrive:
    """One reachable admin route, with arguments good enough to drive it.

    The *list* of routes is never written down: both suites derive it from
    ``app.routes`` and fail when a route has no drive case here. Adding a
    route therefore cannot leave either the role matrix or the audit gate
    green by omission.
    """

    method: str
    path_template: str
    url: str
    #: A role the route admits, so the audit suite can drive every route
    #: past its guard and observe what the chain received.
    actor_role: str
    body: dict[str, Any] | None = None


#: A pending-action id that no ceremony ever minted. Role checks must resolve
#: before existence checks, so a denied role sees 403 and an allowed role 404.
ABSENT_ACTION_ID = "01JBQ0000000000000000ADMIN"

BREAK_GLASS_BODY: dict[str, Any] = {
    "session_ref": "session:0f8a1c2d-4b5e-4a6f-9c31-2d4e6f8a1c2d",
    "reason_class": "patient_support_request",
    "justification": "Patient opened a support ticket about a missing note.",
    "controller_instruction_ref": "ci:tenant-a:2026-09-03:01",
}

#: INT-182. The voice module's bodies: a closed reason class and a real
#: explanation (the INT-188 change-reason rule), never patient material.
VOICE_TENANT = "tenant-a"
VOICE_REASON: dict[str, Any] = {
    "reason_class": "incident_mitigation",
    "justification": "Speech lane degraded on the bridge; typed until it recovers.",
}

#: INT-187. The deploy freeze's bodies: the same closed reason class and real
#: explanation as every other governed change (INT-188).
FREEZE_REASON: dict[str, Any] = {
    "reason_class": "incident_mitigation",
    "justification": "Error budget burning on the api; hold every deploy.",
}

#: INT-428. The Model lanes module's bodies: the same closed reason class and
#: real explanation as every other governed change (INT-188).
LANES_REASON: dict[str, Any] = {
    "reason_class": "incident_mitigation",
    "justification": "The GPU lane is down; route the synthetic stress run elsewhere.",
}

ROUTE_DRIVES: tuple[RouteDrive, ...] = (
    RouteDrive("GET", "/admin/whoami", "/admin/whoami", "auditor"),
    RouteDrive("GET", "/admin/access/roles", "/admin/access/roles", "auditor"),
    RouteDrive("GET", "/admin/actions", "/admin/actions", "auditor"),
    RouteDrive("GET", "/admin/models", "/admin/models", "sre_oncall"),
    # INT-351 — the ops console composite (platform scope, read only).
    RouteDrive("GET", "/admin/ops", "/admin/ops", "sre_oncall"),
    # INT-181 — the reliability composite (platform scope, read only).
    RouteDrive("GET", "/admin/reliability", "/admin/reliability", "sre_oncall"),
    RouteDrive(
        "POST",
        "/admin/models/{component}/benchmark",
        "/admin/models/postgres/benchmark",
        "sre_oncall",
        {"kind": "latency"},
    ),
    RouteDrive(
        "POST", "/admin/break-glass", "/admin/break-glass", "clinical_lead", BREAK_GLASS_BODY
    ),
    RouteDrive(
        "GET",
        "/admin/break-glass/{action_id}",
        f"/admin/break-glass/{ABSENT_ACTION_ID}",
        "auditor",
    ),
    RouteDrive(
        "POST",
        "/admin/break-glass/{action_id}/approve",
        f"/admin/break-glass/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-1"},
    ),
    # INT-189 — the compliance module (files/08 §4). All reads, driven by
    # `auditor`, one of the three roles §2.1 admits to these surfaces.
    RouteDrive(
        "GET",
        "/admin/compliance/vendor-register",
        "/admin/compliance/vendor-register",
        "auditor",
    ),
    RouteDrive("GET", "/admin/compliance/consents", "/admin/compliance/consents", "auditor"),
    RouteDrive(
        "GET", "/admin/compliance/audit-search", "/admin/compliance/audit-search", "auditor"
    ),
    RouteDrive("GET", "/admin/compliance/dsar", "/admin/compliance/dsar", "auditor"),
    RouteDrive(
        "GET",
        "/admin/compliance/evidence-export",
        "/admin/compliance/evidence-export",
        "auditor",
    ),
    # INT-182 — the Voice module (files/08 §3 "Voice runtime", §8). The read is
    # platform scope; the kill switch is tier 1 (sre_oncall alone); release,
    # profile and canary are tier-2 ceremonies. The harness wires no voice
    # store, so a permitted role reaches the handler and is answered 503 —
    # past the guard, audited, and never 403.
    RouteDrive("GET", "/admin/voice", "/admin/voice", "sre_oncall"),
    RouteDrive(
        "POST",
        "/admin/voice/kill-switch",
        "/admin/voice/kill-switch",
        "sre_oncall",
        {"tenant": VOICE_TENANT, **VOICE_REASON},
    ),
    RouteDrive(
        "POST",
        "/admin/voice/kill-switch/release",
        "/admin/voice/kill-switch/release",
        "clinical_lead",
        {"tenant": VOICE_TENANT, **VOICE_REASON},
    ),
    RouteDrive(
        "POST",
        "/admin/voice/kill-switch/release/{action_id}/approve",
        f"/admin/voice/kill-switch/release/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-voice-1"},
    ),
    RouteDrive(
        "PUT",
        "/admin/voice/profile/{tenant}",
        f"/admin/voice/profile/{VOICE_TENANT}",
        "clinical_lead",
        {"profile": "residency_tr", **VOICE_REASON},
    ),
    RouteDrive(
        "POST",
        "/admin/voice/profile/pending/{action_id}/approve",
        f"/admin/voice/profile/pending/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-voice-2"},
    ),
    RouteDrive(
        "PUT",
        "/admin/voice/canary/{tenant}",
        f"/admin/voice/canary/{VOICE_TENANT}",
        "clinical_lead",
        {"profile": "residency_tr", "weight": 10, **VOICE_REASON},
    ),
    RouteDrive(
        "POST",
        "/admin/voice/canary/pending/{action_id}/approve",
        f"/admin/voice/canary/pending/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-voice-3"},
    ),
    RouteDrive(
        "GET",
        "/admin/voice/pending/{action_id}",
        f"/admin/voice/pending/{ABSENT_ACTION_ID}",
        "auditor",
    ),
    # INT-187 — the CI/CD & releases module (files/08 §3, §8.2). The read is
    # platform scope; freezing deploys is tier 1 (sre_oncall alone); lifting a
    # freeze is a tier-2 ceremony. The harness wires no freeze store, so a
    # permitted role reaches the handler and is answered 503 — past the guard,
    # audited, and never 403.
    RouteDrive("GET", "/admin/cicd", "/admin/cicd", "sre_oncall"),
    RouteDrive("POST", "/admin/cicd/freeze", "/admin/cicd/freeze", "sre_oncall", FREEZE_REASON),
    RouteDrive(
        "POST",
        "/admin/cicd/freeze/lift",
        "/admin/cicd/freeze/lift",
        "platform_admin",
        FREEZE_REASON,
    ),
    RouteDrive(
        "POST",
        "/admin/cicd/freeze/lift/{action_id}/approve",
        f"/admin/cicd/freeze/lift/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-cicd-1"},
    ),
    RouteDrive(
        "GET",
        "/admin/cicd/pending/{action_id}",
        f"/admin/cicd/pending/{ABSENT_ACTION_ID}",
        "auditor",
    ),
    # INT-428 — the Model lanes module (ADR-035). The harness wires no
    # model-lane store, so every permitted role reaches the handler and is
    # answered 503 (or 404 for an id nothing minted) — past the guard,
    # audited, and never 403.
    RouteDrive("GET", "/admin/model-lanes", "/admin/model-lanes", "sre_oncall"),
    RouteDrive(
        "POST",
        "/admin/model-lanes/hosted/disable",
        "/admin/model-lanes/hosted/disable",
        "sre_oncall",
        LANES_REASON,
    ),
    RouteDrive(
        "POST",
        "/admin/model-lanes/self-hosted",
        "/admin/model-lanes/self-hosted",
        "sre_oncall",
        {**LANES_REASON, "lanes": ["llm"]},
    ),
    RouteDrive(
        "POST",
        "/admin/model-lanes/hosted/release",
        "/admin/model-lanes/hosted/release",
        "platform_admin",
        LANES_REASON,
    ),
    RouteDrive(
        "POST",
        "/admin/model-lanes/hosted/release/{action_id}/approve",
        f"/admin/model-lanes/hosted/release/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-lanes-1"},
    ),
    RouteDrive(
        "PUT",
        "/admin/model-lanes/route/{role}",
        "/admin/model-lanes/route/llm",
        "platform_admin",
        {**LANES_REASON, "route": "self_hosted"},
    ),
    RouteDrive(
        "POST",
        "/admin/model-lanes/route/pending/{action_id}/approve",
        f"/admin/model-lanes/route/pending/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-lanes-2"},
    ),
    RouteDrive(
        "PUT",
        "/admin/model-lanes/keys/{provider}",
        "/admin/model-lanes/keys/openai",
        "platform_admin",
        {**LANES_REASON, "api_key": "unit-lane-not-a-key-0000000000"},
    ),
    RouteDrive(
        "POST",
        "/admin/model-lanes/keys/pending/{action_id}/approve",
        f"/admin/model-lanes/keys/pending/{ABSENT_ACTION_ID}/approve",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-lanes-3"},
    ),
    RouteDrive(
        "GET",
        "/admin/model-lanes/pending/{action_id}",
        f"/admin/model-lanes/pending/{ABSENT_ACTION_ID}",
        "auditor",
    ),
    # INT-366 — Access & identity. With no identity wired (the harness
    # default) the review, the signature and the offboarding answer 503; the
    # countersign and the confirmation name ids nothing ever minted, so they
    # answer 404 — past the role guard either way.
    RouteDrive("GET", "/admin/access/review", "/admin/access/review", "compliance_officer"),
    RouteDrive(
        "POST",
        "/admin/access/review/sign",
        "/admin/access/review/sign",
        "compliance_officer",
        {"section": "console_roles", "review_digest": "0" * 32},
    ),
    RouteDrive(
        "POST",
        "/admin/access/review/sign/{action_id}/countersign",
        f"/admin/access/review/sign/{ABSENT_ACTION_ID}/countersign",
        "qms_owner",
        {"assertion_id": "assn-unit-lane-2"},
    ),
    RouteDrive(
        "POST",
        "/admin/access/offboard",
        "/admin/access/offboard",
        "sre_oncall",
        {"subject": "kc-sub-platform-owner", "reason_class": "departure"},
    ),
    RouteDrive(
        "POST",
        "/admin/access/offboard/{offboarding_id}/confirm",
        f"/admin/access/offboard/{'0' * 32}/confirm",
        "sre_oncall",
        {"system": "grafana"},
    ),
    # INT-406 — the Safety queue. The harness wires no inbox, so a permitted
    # role reaches the handler and is answered 503 — past the guard, audited,
    # and never 403.
    RouteDrive("GET", "/admin/safety-queue", "/admin/safety-queue", "tenant_clinical_responsible"),
    RouteDrive(
        "POST",
        "/admin/safety-queue/{entry_id}/acknowledge",
        f"/admin/safety-queue/sx_{'0' * 32}/acknowledge",
        "tenant_clinical_responsible",
    ),
    # INT-565 — the Protocols, Clinical quality & safety, Security and Cost
    # composites: reads, each answered 200 from the committed sources.
    RouteDrive("GET", "/admin/protocols", "/admin/protocols", "clinical_lead"),
    RouteDrive("GET", "/admin/quality-safety", "/admin/quality-safety", "clinical_lead"),
    RouteDrive("GET", "/admin/security", "/admin/security", "sre_oncall"),
    RouteDrive("GET", "/admin/cost", "/admin/cost", "platform_admin"),
)


def drives_by_route() -> dict[tuple[str, str], RouteDrive]:
    return {(drive.method, drive.path_template): drive for drive in ROUTE_DRIVES}


def _walk_routes(routes: Any) -> Iterator[Any]:
    """Flatten FastAPI's route tree.

    FastAPI >= 0.14 stores an included router as a ``_IncludedRouter`` holding
    ``original_router`` rather than splicing its routes into ``app.routes``,
    so a flat read of ``app.routes`` silently returns nothing for every
    mounted router. A derivation that can return an empty set is a gate that
    passes by accident, which is why the caller also asserts non-emptiness and
    cross-checks against the served OpenAPI document.
    """
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _walk_routes(included.routes)
            continue
        nested = getattr(route, "routes", None)
        if nested is not None and getattr(route, "methods", None) is None:
            yield from _walk_routes(nested)
            continue
        yield route


def reachable_admin_routes(app: Any) -> set[tuple[str, str]]:
    """Every ``/admin`` route the app actually serves.

    Two independent derivations, both read off the running app: the route tree
    and the OpenAPI document. They must agree on everything the document can
    express, so a route that escapes one is caught by the other.
    """
    found: set[tuple[str, str]] = set()
    for route in _walk_routes(app.routes):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not path.startswith("/admin") or methods is None:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            found.add((method, path))
    assert found, (
        "no /admin route was discovered — the route walk has stopped matching "
        "this FastAPI version, and an empty derived list makes every gate that "
        "reads it pass by accident"
    )
    documented = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/admin")
        for method in operations
    }
    assert documented <= found, sorted(documented - found)
    return found


def call(client: Any, drive: RouteDrive, *, role: str, query: str = "") -> Any:
    return client.request(
        drive.method,
        drive.url + query,
        json=drive.body,
        headers=bearer(role),
    )
