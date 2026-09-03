"""INT-180 — audit on every admin action, on the one chain (invariant 4).

The list of audited routes is **derived**, never maintained: every test here
starts from FastAPI's own route table. A route added by any means shows up in
``reachable_admin_routes`` and must then carry a declared audit action, a
DangerousAction entry if it mutates, and a drive case — or this suite fails.

The second property is that there is exactly ONE audit path. INT-121 refused
to build a second data-boundary fence because a control implemented twice
diverges; the same argument is stronger here, so the admin surface appends to
``intake_platform.audit`` through the API's existing ``AuditWriter`` and owns
no chain, no store and no head. ``test_console_cannot_reach_the_chain_head``
is the structural proof: HB-I12 exists precisely because an operator who can
rewrite the log can rewrite the evidence of rewriting it, and the console must
not narrow that gap.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from admin_harness import (
    BREAK_GLASS_BODY,
    ROUTE_DRIVES,
    build_admin_harness,
    call,
    drives_by_route,
    reachable_admin_routes,
)
from api_harness import ApiHarness
from intake_api.consent_guard import (
    administrative_action,
    administrative_action_routes,
    unguarded_data_routes,
)
from intake_platform.admin import ADMIN_ROUTES, DANGEROUS_ACTIONS, AdminAuditSink
from intake_platform.audit import AuditEntry, verify_entries

REPO = Path(__file__).resolve().parents[2]
ADMIN_PACKAGE = REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "admin"
ADMIN_ROUTER = REPO / "services" / "api" / "src" / "intake_api" / "admin"

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")

#: Symbols that reach, publish or recompute the chain head. The console must
#: not name any of them (HB-I12: the head is published OUTSIDE the
#: platform_admin blast radius, and this surface sits inside it).
CHAIN_HEAD_SYMBOLS = frozenset(
    {
        "AuditChain",
        "build_worm_bundle",
        "export_worm",
        "verify_entries",
        "verify_worm_export",
        "run_daily_verifier",
        "InMemoryAuditStore",
        "AuditStore",
        "head",
    }
)


@pytest.fixture()
def admin_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def chain(harness: ApiHarness) -> Sequence[AuditEntry]:
    return tuple(harness.audit_store.entries())


def python_sources(*roots: Path) -> list[Path]:
    return sorted(path for root in roots for path in root.rglob("*.py"))


class TestDerivedRouteList:
    def test_every_reachable_route_declares_an_audit_action(
        self, admin_harness: ApiHarness
    ) -> None:
        reachable = reachable_admin_routes(admin_harness.client.app)
        declared = {(route.method, route.path) for route in ADMIN_ROUTES}
        assert reachable == declared, (
            "an /admin route exists that was not built from ADMIN_ROUTES — the "
            "descriptor table is the only way a route may be created, because "
            "it is what carries the audit action"
        )
        for route in ADMIN_ROUTES:
            assert route.audit_action.startswith("admin.")
            assert " " not in route.audit_action

    def test_every_mutating_route_is_a_registered_dangerous_action(self) -> None:
        for route in ADMIN_ROUTES:
            if route.method not in MUTATING:
                continue
            assert route.dangerous_action_id in DANGEROUS_ACTIONS, route.path

    def test_every_reachable_route_has_a_drive_case(self, admin_harness: ApiHarness) -> None:
        assert reachable_admin_routes(admin_harness.client.app) == set(drives_by_route())


class TestAuditOnEveryAction:
    @pytest.mark.parametrize("drive", ROUTE_DRIVES, ids=lambda d: f"{d.method} {d.path_template}")
    def test_driving_a_route_appends_intent_then_outcome(
        self, admin_harness: ApiHarness, drive
    ) -> None:  # type: ignore[no-untyped-def]
        before = len(chain(admin_harness))
        response = call(admin_harness.client, drive, role=drive.actor_role)
        assert response.status_code != 403
        appended = chain(admin_harness)[before:]
        actions = [entry.action for entry in appended]
        assert len(actions) == 2, actions
        assert actions[0].endswith(".intent")
        assert actions[1].startswith(actions[0][: -len(".intent")])
        assert actions[1].endswith((".success", ".failure"))
        # write-ahead: the intent row exists before the outcome is known, and
        # both name the same content-addressed target
        assert appended[0].resource_ref == appended[1].resource_ref
        assert appended[0].seq < appended[1].seq

    def test_a_refused_route_is_still_audited_with_a_failure_outcome(
        self, admin_harness: ApiHarness
    ) -> None:
        drive = drives_by_route()[("GET", "/admin/break-glass/{action_id}")]
        before = len(chain(admin_harness))
        response = call(admin_harness.client, drive, role="auditor")
        assert response.status_code == 404
        appended = chain(admin_harness)[before:]
        assert [entry.action for entry in appended] == [
            "admin.break_glass.brief.read.intent",
            "admin.break_glass.brief.read.failure",
        ]

    def test_a_role_refusal_is_audited_too(self, admin_harness: ApiHarness) -> None:
        drive = drives_by_route()[("POST", "/admin/break-glass")]
        before = len(chain(admin_harness))
        assert call(admin_harness.client, drive, role="researcher").status_code == 403
        appended = chain(admin_harness)[before:]
        assert [entry.action for entry in appended] == [
            "admin.break_glass.open.intent",
            "admin.break_glass.open.failure",
        ]

    def test_admin_entries_share_the_one_chain_and_it_stays_verifiable(
        self, admin_harness: ApiHarness
    ) -> None:
        for drive in ROUTE_DRIVES:
            call(admin_harness.client, drive, role=drive.actor_role)
        entries = chain(admin_harness)
        assert len(entries) >= 2 * len(ROUTE_DRIVES)
        assert verify_entries(entries).ok
        assert [entry.seq for entry in entries] == list(range(1, len(entries) + 1))

    def test_justification_free_text_never_reaches_the_chain(
        self, admin_harness: ApiHarness
    ) -> None:
        drive = drives_by_route()[("POST", "/admin/break-glass")]
        assert call(admin_harness.client, drive, role="clinical_lead").status_code < 400
        needle = BREAK_GLASS_BODY["justification"]
        for entry in chain(admin_harness):
            rendered = " ".join(
                (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref)
            )
            assert needle not in rendered
            for word in ("ticket", "Patient", "note"):
                assert word not in rendered


class TestChainHeadUnreachable:
    def test_console_sources_never_name_a_chain_head_symbol(self) -> None:
        offenders: list[str] = []
        for path in python_sources(ADMIN_PACKAGE, ADMIN_ROUTER):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                name = None
                if isinstance(node, ast.Name):
                    name = node.id
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                elif isinstance(node, ast.alias):
                    name = node.asname or node.name.rsplit(".", 1)[-1]
                if name in CHAIN_HEAD_SYMBOLS:
                    offenders.append(f"{path.relative_to(REPO)}:{name}")
        assert offenders == [], offenders

    def test_the_audit_seam_offers_appending_and_nothing_else(self) -> None:
        public = {name for name in dir(AdminAuditSink) if not name.startswith("_")}
        assert public == {"record"}

    def test_no_admin_response_carries_a_chain_hash(self, admin_harness: ApiHarness) -> None:
        for drive in ROUTE_DRIVES:
            response = call(admin_harness.client, drive, role=drive.actor_role)
            assert not HEX64.search(response.text), drive.path_template

    def test_the_chain_head_moves_but_the_console_never_reads_it(
        self, admin_harness: ApiHarness
    ) -> None:
        # the writer's head advances with every console action; nothing the
        # console hands back exposes it, so an operator inside the
        # platform_admin blast radius cannot check their own forgery against
        # the value HB-I12 publishes outside it
        drive = drives_by_route()[("GET", "/admin/whoami")]
        call(admin_harness.client, drive, role="platform_owner")
        entries = chain(admin_harness)
        assert entries
        head = entries[-1].entry_hash
        response = call(admin_harness.client, drive, role="platform_owner")
        assert head not in response.text
        assert chain(admin_harness)[-1].entry_hash != head


class TestConsentScanDeclaration:
    """INT-038's route-table scan (files/06 §2; invariant 4).

    A console action has no data subject at the door: the principal is staff,
    and files/06 §2 enumerates the patient's purposes and contains nothing
    covering staff access. Naming a scope here would assert a lawful basis the
    repository does not have. So the routes declare WHY they carry none, under
    a marker caged to ``/admin`` — and the cage is what stops a ``/v1`` data
    route borrowing it to dodge a scope.
    """

    def test_the_admin_surface_is_declared_and_nothing_is_unguarded(
        self, admin_harness: ApiHarness
    ) -> None:
        app = admin_harness.client.app
        assert unguarded_data_routes(app) == []
        declared = set(administrative_action_routes(app))
        assert declared == {f"{method} {path}" for method, path in reachable_admin_routes(app)}

    def test_the_marker_outside_the_admin_prefix_is_not_a_declaration(self) -> None:
        """Near-miss negative control, mirroring the pre-auth cage test: a
        data route elsewhere cannot borrow the marker."""
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/v1/borrowed", dependencies=[administrative_action()])
        async def borrowed() -> dict[str, str]:
            return {"ok": "no"}

        assert unguarded_data_routes(app) == ["GET /v1/borrowed"]
        # and a lookalike prefix is not the cage either
        lookalike = FastAPI()

        @lookalike.get("/administration/x", dependencies=[administrative_action()])
        async def lookalike_route() -> dict[str, str]:
            return {"ok": "no"}

        assert unguarded_data_routes(lookalike) == ["GET /administration/x"]
