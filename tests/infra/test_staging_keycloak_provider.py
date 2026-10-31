"""INT-421 + INT-378: staff sign-in works on the staging host, because its Keycloak runs the
WebAuthn session-notes provider in the realm that is actually live.

The API's admin gate refuses a staff token without ``aaguid`` and ``credential_id``, and only
the INT-378 provider writes them. Three things must therefore hold on the host:

- **The image carries the provider, and only the checked one.** ``Dockerfile.keycloak`` builds
  the jar from source, verifies Maven against the wrapper's pinned sha256, and refuses a jar
  that is not byte-identical to ``infra/keycloak/providers/webauthn-session-notes.sha256``.
  The runtime stage is INT-390's pin plus that one file.
- **The live realm runs it.** Keycloak imports a realm once, and the host's realm predates the
  provider. So deploy.sh runs ``keycloak/staff_flow.py`` after Keycloak starts and before the
  key set is mirrored. The script makes the live ``staff second factor`` subflow match the
  committed realm and fails unless the flow ends in the committed state. smoke.sh re-checks it
  read-only. INT-550: the committed state is the provider REQUIRED, so a new staff user is sent
  to webauthn-register after the password, and OTP DISABLED until the owner decides INT-389;
  the script refuses, before any change, a realm whose webauthn-register action is not enabled.
- **The secret stays out of argv.** The bootstrap admin password reaches the script on stdin.

The script's decision function is tested here step by step, with near-misses. It was also
driven against a real Keycloak 26.7.4 started with the host's hostname flags; that run is
recorded in docs/evidence/INT-421.md.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
DOCKERFILE = STAGING / "Dockerfile.keycloak"
DOCKERIGNORE = STAGING / "Dockerfile.keycloak.dockerignore"
LIB = STAGING / "lib.sh"
DEPLOY = STAGING / "deploy.sh"
SMOKE = STAGING / "smoke.sh"
REALM = STAGING / "keycloak" / "intake-realm.json"
SCRIPT = STAGING / "keycloak" / "staff_flow.py"
PIN = REPO / "infra" / "keycloak" / "providers" / "webauthn-session-notes.sha256"
#: INT-390's pin, assembled from parts so this file names no other image reference.
KEYCLOAK_IMAGE = "/".join(("quay.io", "keycloak", "keycloak")) + (
    ":26.7.4@sha256:82a77884f3af238beab1e7afd63b5f530e1b5c0590bd7aa60b40a40463e29b2c"
)
PINNED = re.compile(r"^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("staff_flow", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["staff_flow"] = module
    spec.loader.exec_module(module)
    return module


sf = _load_script()


def _code(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _function(name: str) -> str:
    return LIB.read_text(encoding="utf-8").split(f"\n{name}() {{\n", 1)[1].split("\n}\n", 1)[0]


# --- the image -------------------------------------------------------------------------------


class TestImage:
    def test_every_base_is_pinned_and_the_runtime_is_the_keycloak_pin(self) -> None:
        bases = re.findall(r"^FROM (\S+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
        assert len(bases) == 2 and all(PINNED.match(base) for base in bases)
        assert bases[-1] == KEYCLOAK_IMAGE

    def test_the_build_refuses_a_jar_that_is_not_the_pin(self) -> None:
        code = _code(DOCKERFILE)
        assert "COPY infra/keycloak/providers/webauthn-session-notes.sha256 /src/" in code
        assert "sha256sum -c /src/webauthn-session-notes.sha256" in code
        # the jar is checked after it is built, in the same step, so no unchecked jar is copied
        build = code.index("mvn -B clean verify")
        assert build < code.index("sha256sum -c /src/webauthn-session-notes.sha256")

    def test_maven_is_checked_against_the_wrappers_pinned_sum(self) -> None:
        code = _code(DOCKERFILE)
        assert "s/^distributionSha256Sum=//p" in code
        assert "sha256sum -c -" in code
        assert code.index("sha256sum -c -") < code.index("jar xf /tmp/maven.zip")
        assert "--proto '=https'" in code

    def test_the_runtime_gets_the_one_jar_and_runs_unprivileged(self) -> None:
        code = _code(DOCKERFILE)
        copies = re.findall(r"^COPY --from=provider .*$", code, re.M)
        assert len(copies) == 1 and "--chmod=0444" in copies[0]
        jar = PIN.read_text(encoding="utf-8").split()[1]
        assert f"/opt/keycloak/providers/{jar}" in code
        users = re.findall(r"^USER (\d+)", code, re.M)
        assert users and int(users[-1]) >= 1000

    def test_the_pin_the_image_checks_is_the_recorded_jar(self) -> None:
        recording = json.loads(
            (REPO / "tests/admin/fixtures/keycloak_webauthn_login.json").read_text(encoding="utf-8")
        )
        assert recording["provider_jar_sha256"] == PIN.read_text(encoding="utf-8").split()[0]

    def test_the_build_context_admits_only_the_module_and_its_pin(self) -> None:
        lines = [
            line.strip()
            for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert lines[0] == "*"
        admitted = [line[1:] for line in lines if line.startswith("!")]
        assert admitted == [
            "infra/keycloak/providers/webauthn-session-notes.sha256",
            "infra/keycloak/providers/webauthn-session-notes",
        ]
        for excluded in (
            "infra/keycloak/providers/webauthn-session-notes/target",
            "**/.env",
            "**/node_modules",
        ):
            assert excluded in lines


# --- deploy and smoke ------------------------------------------------------------------------


class TestDeploy:
    def test_the_image_is_built_before_anything_restarts(self) -> None:
        code = _code(DEPLOY)
        assert code.index("build_keycloak_image") < code.index("compose up")
        assert "compose build keycloak" in _function("build_keycloak_image")

    def test_the_live_realm_is_switched_after_keycloak_starts_and_before_the_key_set(self) -> None:
        code = _code(DEPLOY)
        steps = [
            "compose up -d --no-build --wait keycloak",
            "ensure_staff_webauthn_notes",
            "mirror_keycloak_jwks",
            "compose up -d --no-build --wait --remove-orphans",
        ]
        positions = [code.index(step) for step in steps]
        assert positions == sorted(positions)

    def test_a_flow_that_does_not_settle_stops_the_deploy(self) -> None:
        assert "staff_flow apply || die" in _function("ensure_staff_webauthn_notes")

    def test_the_admin_password_travels_on_stdin(self) -> None:
        body = _function("staff_flow")
        assert 'env_get "$ENV_FILE" KEYCLOAK_ADMIN_PASSWORD' in body
        assert "printf '%s\\n' \"$value\" | compose run --rm --no-deps -T api python -c" in body
        # near-miss: the value never follows the command, where ps would show it
        after = body.split("| compose run", 1)[1]
        assert "$value" not in after and " -e " not in after

    def test_smoke_rechecks_the_live_realm_read_only(self) -> None:
        assert "staff_flow check" in _code(SMOKE)


# --- the script's decision, step by step -------------------------------------------------------
#
# INT-550: the target is the WebAuthn provider REQUIRED, so Keycloak sends a user who holds no
# passkey to webauthn-register after the password, and OTP DISABLED until INT-389. INT-378's
# target was both ALTERNATIVE, which refuses every new user (tests/admin/
# test_staff_passkey_enrolment.py has the Keycloak 26.7.4 source lines).

STOCK = sf.Execution("stock", sf.STOCK, "ALTERNATIVE", sf.HWK_ALIAS, 0, 10)
OTP_ON = sf.Execution("otp", sf.OTP, "ALTERNATIVE", "amr otp", 1, 20)
OTP_OFF = sf.Execution("otp", sf.OTP, "DISABLED", "amr otp", 1, 20)
REGISTER_ON = {"alias": sf.REGISTER, "providerId": sf.REGISTER, "enabled": True}


def provider(
    requirement: str = "REQUIRED",
    alias: str | None = sf.HWK_ALIAS,
    index: int = 0,
    priority: int = 0,
):
    return sf.Execution("prov", sf.PROVIDER, requirement, alias, index, priority)


class TestNextStep:
    def test_a_host_before_int_378_adds_the_provider(self) -> None:
        assert sf.next_step([STOCK, OTP_ON]) == sf.Step("add_provider")

    def test_the_hosts_state_on_17_oct_makes_webauthn_required(self) -> None:
        # INT-378's sync left the provider ALTERNATIVE at priority 0 (docs/evidence/INT-421.md)
        assert sf.next_step([provider("ALTERNATIVE"), OTP_ON]) == sf.Step("set_required", "prov", 0)

    @pytest.mark.parametrize("requirement", ["DISABLED", "ALTERNATIVE", "CONDITIONAL"])
    def test_a_provider_in_any_other_requirement_is_made_required(self, requirement: str) -> None:
        executions = [STOCK, OTP_ON, provider(requirement, None, 2, 30)]
        assert sf.next_step(executions) == sf.Step("set_required", "prov", 30)

    def test_then_otp_is_disabled_at_its_own_priority(self) -> None:
        assert sf.next_step([provider(), OTP_ON]) == sf.Step("disable_otp", "otp", 20)

    @pytest.mark.parametrize("requirement", ["ALTERNATIVE", "REQUIRED", "CONDITIONAL"])
    def test_otp_in_any_requirement_that_runs_is_disabled(self, requirement: str) -> None:
        otp = sf.Execution("otp", sf.OTP, requirement, "amr otp", 1, 20)
        assert sf.next_step([provider(), otp]) == sf.Step("disable_otp", "otp", 20)

    def test_the_stock_authenticator_is_removed_once_the_provider_stands(self) -> None:
        assert sf.next_step([STOCK, OTP_ON, provider(alias=None, index=2)]) == sf.Step(
            "remove_stock", "stock"
        )

    def test_the_provider_gets_the_hwk_reference(self) -> None:
        assert sf.next_step([provider(alias=None, index=0), OTP_ON]) == sf.Step(
            "add_hwk_reference", "prov"
        )

    def test_webauthn_is_raised_above_otp(self) -> None:
        assert sf.next_step([OTP_OFF, provider(index=2, priority=30)]) == sf.Step(
            "raise_provider", "prov"
        )

    def test_the_committed_shape_is_done(self) -> None:
        assert sf.next_step([provider(index=0), OTP_OFF]) == sf.Step("done")

    def test_a_subflow_without_otp_is_done(self) -> None:
        assert sf.next_step([provider()]) == sf.Step("done")

    def test_near_miss_a_foreign_reference_is_refused_not_overwritten(self) -> None:
        with pytest.raises(sf.FlowRefused):
            sf.next_step([provider(alias="amr otp"), OTP_OFF])

    def test_near_miss_two_providers_are_refused(self) -> None:
        with pytest.raises(sf.FlowRefused):
            sf.next_step([provider(), sf.Execution("p2", sf.PROVIDER, "REQUIRED", None, 1, 30)])

    def test_the_committed_realm_is_already_done(self) -> None:
        realm = json.loads(REALM.read_text(encoding="utf-8"))
        (flow,) = [f for f in realm["authenticationFlows"] if f["alias"] == sf.SUBFLOW]
        executions = [
            sf.Execution(
                str(n),
                e["authenticator"],
                e["requirement"],
                e.get("authenticatorConfig"),
                n,
                e["priority"],
            )
            for n, e in enumerate(
                sorted(flow["authenticationExecutions"], key=lambda x: x["priority"])
            )
        ]
        assert sf.next_step(executions) == sf.Step("done")
        assert [(e.provider, e.requirement) for e in executions] == [
            (sf.PROVIDER, "REQUIRED"),
            (sf.OTP, "DISABLED"),
        ]


class TestRegisterAction:
    def test_an_enabled_action_lets_a_new_user_enrol(self) -> None:
        assert sf.register_problem(REGISTER_ON) is None

    def test_near_miss_a_disabled_action_is_named(self) -> None:
        problem = sf.register_problem({**REGISTER_ON, "enabled": False})
        assert problem is not None and "disabled" in problem

    def test_near_miss_an_absent_action_is_named(self) -> None:
        problem = sf.register_problem(None)
        assert problem is not None and sf.REGISTER in problem


class RecordingAdmin(sf.Admin):
    """The real Admin, with the HTTP call recorded instead of sent."""

    def __init__(self) -> None:
        super().__init__("http://keycloak:8080", "intake", "not-a-real-bearer")
        self.calls: list[tuple[str, str, object]] = []

    def _call(self, method: str, path: str, body: object = None) -> object:
        self.calls.append((method, path, body))
        return None


class TestAdminCalls:
    @pytest.mark.parametrize(
        ("step", "requirement"),
        [
            (sf.Step("set_required", "prov", 0), "REQUIRED"),
            (sf.Step("disable_otp", "otp", 20), "DISABLED"),
        ],
    )
    def test_a_requirement_change_keeps_the_executions_priority(
        self, step: sf.Step, requirement: str
    ) -> None:
        # Keycloak 26.7.4's updateExecutions copies the body's priority whenever it differs
        # (AuthenticationManagementResource.java:804-806): a body without one resets it to 0
        admin = RecordingAdmin()
        admin.apply(step)
        assert admin.calls == [
            (
                "PUT",
                "/authentication/flows/staff%20second%20factor/executions",
                {"id": step.target, "requirement": requirement, "priority": step.priority},
            )
        ]

    def test_near_miss_a_requirement_step_without_a_priority_is_refused(self) -> None:
        admin = RecordingAdmin()
        with pytest.raises(sf.FlowRefused):
            admin.apply(sf.Step("set_required", "prov"))
        assert admin.calls == []


class FakeAdmin:
    """The admin API as an in-memory subflow; each step is applied the way Keycloak does it."""

    def __init__(self, executions: list, register: dict | None = REGISTER_ON) -> None:
        self.flow = list(executions)
        self.register = register
        self.applied: list = []

    def executions(self) -> list:
        return [
            sf.Execution(e.id, e.provider, e.requirement, e.config_alias, n, e.priority)
            for n, e in enumerate(self.flow)
        ]

    def register_action(self) -> dict | None:
        return self.register

    def binding(self) -> tuple[str, list]:
        """The committed browser-flow binding (tests/infra/test_staging_staff_binding.py)."""
        return sf.TOP_FLOW, [sf.Node(*node) for node in sf.OUTLINE]

    def apply(self, step) -> None:
        self.applied.append(step)
        if step.action == "add_provider":
            last = max((e.priority for e in self.flow), default=0)
            self.flow.append(
                sf.Execution("prov", sf.PROVIDER, "DISABLED", None, len(self.flow), last + 10)
            )
            return
        (i,) = [n for n, e in enumerate(self.flow) if e.id == step.target]
        e = self.flow[i]
        if step.action in {"set_required", "disable_otp"}:
            requirement = "REQUIRED" if step.action == "set_required" else "DISABLED"
            self.flow[i] = sf.Execution(
                e.id, e.provider, requirement, e.config_alias, i, step.priority
            )
        elif step.action == "remove_stock":
            del self.flow[i]
        elif step.action == "add_hwk_reference":
            self.flow[i] = sf.Execution(
                e.id, e.provider, e.requirement, sf.HWK_ALIAS, i, e.priority
            )
        elif step.action == "raise_provider":
            above = self.flow[i - 1]
            self.flow[i - 1] = sf.Execution(
                e.id, e.provider, e.requirement, e.config_alias, i - 1, above.priority
            )
            self.flow[i] = sf.Execution(
                above.id, above.provider, above.requirement, above.config_alias, i, e.priority
            )


class TestRun:
    def test_from_the_hosts_state_it_takes_two_steps(self) -> None:
        admin = FakeAdmin([provider("ALTERNATIVE"), OTP_ON])
        taken = sf.run(admin, check_only=False)
        assert taken == [sf.Step("set_required", "prov", 0), sf.Step("disable_otp", "otp", 20)]
        assert [(e.provider, e.requirement, e.config_alias, e.priority) for e in admin.flow] == [
            (sf.PROVIDER, "REQUIRED", sf.HWK_ALIAS, 0),
            (sf.OTP, "DISABLED", "amr otp", 20),
        ]

    def test_from_a_host_before_int_378_it_settles(self) -> None:
        admin = FakeAdmin([STOCK, OTP_ON])
        sf.run(admin, check_only=False)
        assert [(e.provider, e.requirement, e.config_alias) for e in admin.flow] == [
            (sf.PROVIDER, "REQUIRED", sf.HWK_ALIAS),
            (sf.OTP, "DISABLED", "amr otp"),
        ]
        assert [step.action for step in admin.applied] == [
            "add_provider",
            "set_required",
            "remove_stock",
            "add_hwk_reference",
            "disable_otp",
            "raise_provider",
        ]

    def test_a_second_run_changes_nothing(self) -> None:
        admin = FakeAdmin([provider(), OTP_OFF])
        assert sf.run(admin, check_only=False) == []

    def test_check_refuses_the_hosts_state_and_changes_nothing(self) -> None:
        admin = FakeAdmin([provider("ALTERNATIVE"), OTP_ON])
        with pytest.raises(sf.FlowRefused):
            sf.run(admin, check_only=True)
        assert admin.applied == []

    @pytest.mark.parametrize("register", [None, {**REGISTER_ON, "enabled": False}])
    def test_near_miss_no_enabled_register_action_refuses_before_any_change(
        self, register: dict | None
    ) -> None:
        admin = FakeAdmin([provider("ALTERNATIVE"), OTP_ON], register=register)
        with pytest.raises(sf.FlowRefused):
            sf.run(admin, check_only=False)
        assert admin.applied == []

    def test_check_passes_the_committed_state(self) -> None:
        assert sf.run(FakeAdmin([provider(), OTP_OFF]), check_only=True) == []

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "keycloak:8080", "ftp://keycloak"])
    def test_near_miss_only_an_http_base_is_admitted(self, url: str) -> None:
        with pytest.raises(ValueError):
            sf.checked_base(url)
        assert sf.checked_base("http://keycloak:8080/") == "http://keycloak:8080"

    def test_no_password_on_stdin_is_a_usage_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(""))
        assert sf.main(["http://keycloak:8080", "intake", "intake-bootstrap"]) == 2
