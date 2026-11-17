"""Fakes for the INT-366 access-review and offboarding suites.

No test dials Keycloak or OpenBao (CLAUDE.md: never a live call in tests;
mocks live in tests only). The two classes below answer the handful of admin
REST calls the production adapters make, from the recorded realm in
``fixtures/keycloak_admin_realm.json``, through ``httpx.MockTransport``. The
production adapters therefore run unchanged: what is faked is the server, not
the client.

Timestamps in the fixture are anchored at ``recorded_at_ms``; each fake shifts
them to the ``now`` it is given, so "88 days since the last login" stays 88
days whatever day the suite runs on.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
from intake_platform.admin.access import (
    ConsoleAccountSystem,
    IdentityWiring,
    KeycloakAdminDirectory,
    OpenBaoLeaseRevoker,
    load_console_systems,
)
from intake_platform.admin.access.review import SIGNED_ACTION, signed_resource_ref
from intake_platform.admin.audit import ADMIN_BASIS_REF
from intake_platform.audit import AuditChain, AuditStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REALM_FIXTURE = FIXTURES / "keycloak_admin_realm.json"
REPO = Path(__file__).resolve().parents[2]
CONSOLE_ACCOUNTS = REPO / "infra" / "admin" / "console-accounts.yaml"

KEYCLOAK_BASE = "https://keycloak.test"
OPENBAO_BASE = "https://openbao.test"
ADMIN_CLIENT_ID = "intake-access-admin"
#: A test value, never a secret: the fake compares against it and nothing else.
ADMIN_CLIENT_SECRET = "unit-lane-client-secret"
OPENBAO_TOKEN = "unit-lane-offboarding-token"


def recorded_realm() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(REALM_FIXTURE.read_text(encoding="utf-8"))
    return payload


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


class FakeKeycloak:
    """The Keycloak admin REST endpoints INT-366 calls, over the recorded realm."""

    def __init__(self, now: datetime, fixture: Mapping[str, Any] | None = None) -> None:
        data = copy.deepcopy(dict(fixture if fixture is not None else recorded_realm()))
        shift = _ms(now) - int(data["recorded_at_ms"])
        self.realm: str = data["realm"]
        self.events_config: dict[str, Any] = data["events_config"]
        self.users: dict[str, dict[str, Any]] = {}
        self.roles: dict[str, list[str]] = {}
        self.logins: dict[str, list[int]] = {}
        for raw in data["users"]:
            user = dict(raw)
            self.roles[user["id"]] = list(user.pop("realm_roles"))
            self.logins[user["id"]] = sorted(
                (stamp + shift for stamp in user.pop("logins_ms")), reverse=True
            )
            user["createdTimestamp"] = int(user["createdTimestamp"]) + shift
            self.users[user["id"]] = user
        self.sessions: dict[str, int] = {subject: 1 for subject in self.users}
        self.calls: list[tuple[str, str]] = []
        #: operation names that answer 500: "users", "disable", "logout",
        #: "events", "events_config", "token"
        self.fail: set[str] = set()
        self.tokens: set[str] = set()

    # -- the transport -------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def directory(self) -> KeycloakAdminDirectory:
        return KeycloakAdminDirectory(
            httpx.Client(base_url=KEYCLOAK_BASE, transport=self.transport()),
            realm=self.realm,
            client_id=ADMIN_CLIENT_ID,
            client_secret=ADMIN_CLIENT_SECRET,
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        token_path = f"/realms/{self.realm}/protocol/openid-connect/token"
        if path == token_path:
            return self._token(request)
        if request.headers.get("authorization", "").removeprefix("Bearer ") not in self.tokens:
            return httpx.Response(401, json={"error": "HTTP 401 Unauthorized"})
        prefix = f"/admin/realms/{self.realm}"
        if not path.startswith(prefix):
            return httpx.Response(404)
        rest = path[len(prefix) :].strip("/").split("/")
        return self._admin(request, rest)

    def _token(self, request: httpx.Request) -> httpx.Response:
        if "token" in self.fail:
            return httpx.Response(500)
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if (
            form.get("grant_type") != "client_credentials"
            or form.get("client_id") != ADMIN_CLIENT_ID
            or form.get("client_secret") != ADMIN_CLIENT_SECRET
        ):
            return httpx.Response(401, json={"error": "unauthorized_client"})
        token = f"kc-admin-token-{len(self.tokens) + 1}"
        self.tokens.add(token)
        return httpx.Response(
            200, json={"access_token": token, "expires_in": 60, "token_type": "Bearer"}
        )

    def _admin(self, request: httpx.Request, rest: list[str]) -> httpx.Response:
        method = request.method
        if rest == ["events", "config"] and method == "GET":
            if "events_config" in self.fail:
                return httpx.Response(500)
            return httpx.Response(200, json=self.events_config)
        if rest == ["events"] and method == "GET":
            return self._events(request)
        if rest == ["users"] and method == "GET":
            if "users" in self.fail:
                return httpx.Response(500)
            first = int(request.url.params.get("first", "0"))
            size = int(request.url.params.get("max", "100"))
            page = list(self.users.values())[first : first + size]
            return httpx.Response(200, json=page)
        if len(rest) >= 2 and rest[0] == "users":
            subject = rest[1]
            if subject not in self.users:
                return httpx.Response(404, json={"error": "User not found"})
            tail = rest[2:]
            if not tail and method == "GET":
                return httpx.Response(200, json=self.users[subject])
            if not tail and method == "PUT":
                if "disable" in self.fail:
                    return httpx.Response(500)
                body = json.loads(request.content or b"{}")
                if set(body) != {"enabled"}:
                    return httpx.Response(400, json={"error": "unexpected representation"})
                self.users[subject]["enabled"] = bool(body["enabled"])
                return httpx.Response(204)
            if tail == ["logout"] and method == "POST":
                if "logout" in self.fail:
                    return httpx.Response(500)
                self.sessions[subject] = 0
                return httpx.Response(204)
            if tail == ["role-mappings", "realm", "composite"] and method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {"id": f"role-{name}", "name": name, "composite": False}
                        for name in self.roles[subject]
                    ],
                )
        return httpx.Response(405)

    def _events(self, request: httpx.Request) -> httpx.Response:
        if "events" in self.fail:
            return httpx.Response(500)
        params = request.url.params
        if params.get("type") != "LOGIN":
            return httpx.Response(200, json=[])
        subject = params.get("user", "")
        size = int(params.get("max", "100"))
        rows = [
            {
                "time": stamp,
                "type": "LOGIN",
                "realmId": self.realm,
                "clientId": "admin-web",
                "userId": subject,
                "ipAddress": "192.0.2.44",
            }
            for stamp in self.logins.get(subject, [])
        ]
        return httpx.Response(200, json=rows[:size])


class FakeOpenBao:
    """The OpenBao identity and token-accessor endpoints the lease revoker calls."""

    def __init__(self, fixture: Mapping[str, Any] | None = None) -> None:
        data = copy.deepcopy(dict((fixture or recorded_realm())["openbao"]))
        self.mount_accessor: str = data["alias_mount_accessor"]
        self.entities: dict[str, str] = data["entities"]
        self.accessors: dict[str, str | None] = data["token_accessors"]
        self.disabled_entities: set[str] = set()
        self.revoked: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self.fail: set[str] = set()

    def revoker(self) -> OpenBaoLeaseRevoker:
        client = httpx.Client(
            base_url=OPENBAO_BASE,
            headers={"X-Vault-Token": OPENBAO_TOKEN},
            transport=httpx.MockTransport(self.handler),
        )
        return OpenBaoLeaseRevoker(client, alias_mount_accessor=self.mount_accessor)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        if request.headers.get("x-vault-token") != OPENBAO_TOKEN:
            return httpx.Response(403, json={"errors": ["permission denied"]})
        if "all" in self.fail:
            return httpx.Response(503, json={"errors": ["sealed"]})
        body = json.loads(request.content or b"{}") if request.method == "POST" else {}
        if path == "/v1/identity/lookup/entity" and request.method == "POST":
            if body.get("alias_mount_accessor") != self.mount_accessor:
                return httpx.Response(204)
            entity = self.entities.get(body.get("alias_name", ""))
            if entity is None:
                return httpx.Response(204)
            return httpx.Response(
                200, json={"data": {"id": entity, "name": f"entity_{entity}", "disabled": False}}
            )
        if path.startswith("/v1/identity/entity/id/") and request.method == "POST":
            if body != {"disabled": True}:
                return httpx.Response(400, json={"errors": ["unexpected update"]})
            self.disabled_entities.add(path.rsplit("/", 1)[-1])
            return httpx.Response(204)
        if path == "/v1/auth/token/accessors" and request.method == "GET":
            if request.url.params.get("list") != "true":
                return httpx.Response(405)
            return httpx.Response(200, json={"data": {"keys": sorted(self.accessors)}})
        if path == "/v1/auth/token/lookup-accessor" and request.method == "POST":
            accessor = body.get("accessor", "")
            if accessor not in self.accessors or self.accessors[accessor] is None:
                return httpx.Response(400, json={"errors": ["invalid accessor"]})
            return httpx.Response(
                200, json={"data": {"accessor": accessor, "entity_id": self.accessors[accessor]}}
            )
        if path == "/v1/auth/token/revoke-accessor" and request.method == "POST":
            if "revoke" in self.fail:
                return httpx.Response(500, json={"errors": ["internal error"]})
            accessor = body.get("accessor", "")
            self.accessors.pop(accessor, None)
            self.revoked.append(accessor)
            return httpx.Response(204)
        return httpx.Response(405)


def committed_systems() -> tuple[ConsoleAccountSystem, ...]:
    return load_console_systems(CONSOLE_ACCOUNTS)


def identity_wiring(keycloak: FakeKeycloak, openbao: FakeOpenBao) -> IdentityWiring:
    return IdentityWiring(
        directory=keycloak.directory(),
        leases=openbao.revoker(),
        systems=committed_systems(),
    )


def seed_signed_sections(
    store: AuditStore,
    sections: tuple[str, ...],
    *,
    at: datetime | None = None,
    actor: str = "kc-sub-qms-owner",
) -> None:
    """Write countersigned-review rows straight onto the chain.

    The harness uses this so that suites which are not about the review start
    from a current one; the review suite drives the real ceremony instead.
    Writing through ``AuditChain`` keeps the chain verifiable: it resumes from
    the store's tail exactly as the API's writer will on its first append.
    """
    stamp = at if at is not None else datetime.now(UTC)
    writer = AuditChain(store, clock=lambda: stamp)
    for section in sections:
        writer.append(
            actor=actor,
            action=SIGNED_ACTION,
            resource_ref=signed_resource_ref(section, "0" * 32),
            consent_scope_ref=ADMIN_BASIS_REF,
        )


def iter_actions(store: AuditStore) -> Iterator[str]:
    for entry in store.entries():
        yield entry.action
