"""INT-563 (ADR-043): the staging host carries the four-eyes step-up client, through the
deploy path, without touching a flow.

The API approves a four-eyes action only with a grant earned at the realm's public client
``admin-web-stepup``. The committed realm declares it; Keycloak imports a realm once. So
``deploy.sh`` runs ``keycloak/step_up_client.py`` after the staff flow is settled and before
the key set is mirrored, and ``smoke.sh`` re-checks it read-only. What is held here:

- **The script's client is the committed client**, field for field and mapper for mapper,
  for the host's hostname — so the realm file and the deploy path cannot drift.
- **It adds or verifies, nothing else.** An absent client is created once; a present one is
  verified and a difference is refused by name, never edited. Each near miss below is the
  committed client with one thing changed.
- **It never names a flow.** A ``PUT`` on the staff browser flow without each execution's
  priority zeroes them (deploy e19640d2); the script's source carries no flow path and no
  verb but ``GET`` and ``POST``.
- **The secret stays out of argv**, as for ``staff_flow``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
LIB = STAGING / "lib.sh"
DEPLOY = STAGING / "deploy.sh"
SMOKE = STAGING / "smoke.sh"
COMPOSE = STAGING / "compose.yaml"
REALM = STAGING / "keycloak" / "intake-realm.json"
SCRIPT = STAGING / "keycloak" / "step_up_client.py"
HOST = "staging.example.test"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("step_up_client", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["step_up_client"] = module
    spec.loader.exec_module(module)
    return module


SUC = _load()


def _code(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _function(name: str) -> str:
    return LIB.read_text(encoding="utf-8").split(f"\n{name}() {{\n", 1)[1].split("\n}\n", 1)[0]


def _realm_client() -> dict[str, Any]:
    raw = REALM.read_text(encoding="utf-8").replace("${STAGING_HOSTNAME}", HOST)
    (client,) = [c for c in json.loads(raw)["clients"] if c["clientId"] == SUC.CLIENT_ID]
    return dict(client)


class FakeAdmin:
    def __init__(self, clients: list[Mapping[str, Any]]) -> None:
        self.clients = [copy.deepcopy(dict(c)) for c in clients]
        self.created: list[Mapping[str, Any]] = []

    def find(self) -> list[Mapping[str, Any]]:
        return [copy.deepcopy(c) for c in self.clients]

    def create(self, representation: Mapping[str, Any]) -> None:
        self.created.append(representation)
        self.clients.append(copy.deepcopy(dict(representation)))


class TestTheCommittedClient:
    def test_the_script_declares_exactly_the_realm_files_client(self) -> None:
        assert SUC.committed(HOST) == _realm_client()

    def test_the_committed_client_has_no_differences(self) -> None:
        assert SUC.differences(_realm_client(), HOST) == []

    @pytest.mark.parametrize("hostname", ["", "staging", "staging.example.test/evil", "a..b.test"])
    def test_a_hostname_that_is_not_a_dns_name_is_refused(self, hostname: str) -> None:
        with pytest.raises(ValueError):
            SUC.committed(hostname)


def _changed(path: str, value: Any) -> dict[str, Any]:
    client = _realm_client()
    node: Any = client
    *parents, leaf = path.split("/")
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if value is _DROP:
        del node[leaf]
    else:
        node[int(leaf) if isinstance(node, list) else leaf] = value
    return client


_DROP = object()


class TestNearMisses:
    @pytest.mark.parametrize(
        ("path", "value", "named"),
        [
            ("publicClient", False, "publicClient"),
            ("implicitFlowEnabled", True, "implicitFlowEnabled"),
            ("directAccessGrantsEnabled", True, "directAccessGrantsEnabled"),
            ("serviceAccountsEnabled", True, "serviceAccountsEnabled"),
            ("enabled", False, "enabled"),
            ("redirectUris", [f"https://admin.{HOST}/*"], "redirectUris"),
            (
                "redirectUris",
                [f"https://admin.{HOST}/step-up/callback", "https://elsewhere.test/cb"],
                "redirectUris",
            ),
            ("webOrigins", ["+"], "webOrigins"),
            ("attributes", {}, "attributes.pkce.code.challenge.method"),
            ("attributes", {"pkce.code.challenge.method": "plain"}, "attributes.pkce"),
            (
                "protocolMappers/0/config/access.token.claim",
                "true",
                "protocolMappers.aaguid.access.token.claim",
            ),
            (
                "protocolMappers/1/config/user.session.note",
                "intake.webauthn.aaguid",
                "protocolMappers.credential_id.user.session.note",
            ),
            (
                "protocolMappers/2/protocolMapper",
                "oidc-hardcoded-claim-mapper",
                "protocolMappers.amr",
            ),
            ("protocolMappers", [], "protocolMappers"),
        ],
    )
    def test_one_difference_is_named(self, path: str, value: Any, named: str) -> None:
        found = SUC.differences(_changed(path, value), HOST)
        assert found and any(item.startswith(named) for item in found), found

    def test_an_extra_mapper_is_a_difference(self) -> None:
        client = _realm_client()
        client["protocolMappers"].append(
            {"name": "realm roles", "protocolMapper": "oidc-usermodel-realm-role-mapper"}
        )
        assert SUC.differences(client, HOST) == ["protocolMappers"]


class TestRun:
    def test_an_absent_client_is_added_once_and_verified(self) -> None:
        admin = FakeAdmin([{"clientId": "admin-web"}])
        assert SUC.run(admin, HOST, check_only=False) == "added"
        assert admin.created == [SUC.committed(HOST)]
        assert SUC.run(admin, HOST, check_only=False) == "present"
        assert len(admin.created) == 1

    def test_check_never_writes(self) -> None:
        admin = FakeAdmin([])
        with pytest.raises(SUC.ClientRefused, match="no admin-web-stepup"):
            SUC.run(admin, HOST, check_only=True)
        assert admin.created == []

    def test_a_drifted_client_is_refused_and_left_alone(self) -> None:
        admin = FakeAdmin([_changed("publicClient", False)])
        with pytest.raises(SUC.ClientRefused, match="publicClient"):
            SUC.run(admin, HOST, check_only=False)
        assert admin.created == []

    def test_a_duplicated_client_is_refused(self) -> None:
        admin = FakeAdmin([_realm_client(), _realm_client()])
        with pytest.raises(SUC.ClientRefused, match="more than once"):
            SUC.run(admin, HOST, check_only=False)

    def test_a_create_that_does_not_read_back_is_refused(self) -> None:
        class Lost(FakeAdmin):
            def create(self, representation: Mapping[str, Any]) -> None:
                self.created.append(representation)

        admin = Lost([])
        with pytest.raises(SUC.ClientRefused, match="does not read back"):
            SUC.run(admin, HOST, check_only=False)


class TestItNeverTouchesAFlow:
    def test_no_flow_path_and_no_verb_but_get_and_post(self) -> None:
        code = _code(SCRIPT)
        assert "/authentication/" not in code and "executions" not in code.lower().replace(
            "an execution", ""
        )
        verbs = set(re.findall(r'_call\(\s*"([A-Z]+)"', code))
        assert verbs == {"GET", "POST"}


class TestTheDeployPath:
    def test_it_runs_after_the_staff_flow_and_before_the_key_set(self) -> None:
        code = _code(DEPLOY)
        steps = [
            "compose up -d --no-build --wait keycloak",
            "ensure_staff_webauthn_notes",
            "ensure_step_up_client",
            "mirror_keycloak_jwks",
            "compose up -d --no-build --wait --remove-orphans",
        ]
        positions = [code.index(step) for step in steps]
        assert positions == sorted(positions)

    def test_a_client_that_does_not_settle_stops_the_deploy(self) -> None:
        assert "step_up_client apply || die" in _function("ensure_step_up_client")

    def test_the_admin_password_travels_on_stdin(self) -> None:
        body = _function("step_up_client")
        assert 'env_get "$ENV_FILE" KEYCLOAK_ADMIN_PASSWORD' in body
        assert "printf '%s\\n' \"$value\" | compose run --rm --no-deps -T api python -c" in body
        after = body.split("| compose run", 1)[1]
        assert "$value" not in after and " -e " not in after
        assert 'validate_hostname "$hostname"' in body

    def test_smoke_rechecks_it_read_only(self) -> None:
        assert "step_up_client check" in _code(SMOKE)
        assert "step_up_client apply" not in _code(SMOKE)


class TestTheApiIsPointedAtIt:
    def test_the_two_variables_name_the_callback_and_the_internal_token_endpoint(self) -> None:
        env = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["api"]["environment"]
        redirect = env["INTAKE_ADMIN_STEP_UP_REDIRECT_URI"]
        assert redirect == "https://admin.${STAGING_HOSTNAME:?run init.sh}/step-up/callback"
        # the realm's one redirect URI, for the same hostname
        assert [redirect.replace("${STAGING_HOSTNAME:?run init.sh}", HOST)] == _realm_client()[
            "redirectUris"
        ]
        token = env["INTAKE_ADMIN_STEP_UP_EXCHANGE_URL"]
        assert token == "http://keycloak:8080/realms/intake/protocol/openid-connect/token"
        assert env["INTAKE_ADMIN_OIDC_ISSUER"].endswith("/realms/intake")
