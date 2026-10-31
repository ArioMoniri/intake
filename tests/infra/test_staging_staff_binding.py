"""INT-563 review: `staff_flow check` also holds the flow *around* the second factor.

ADR-043's step-up proves the WebAuthn step ran in the fresh login only while that step is
REQUIRED on the path every staff login takes. The INT-378/INT-550 script held the
`staff second factor` subflow itself. That is necessary and not sufficient: a realm whose
browser flow is rebound to another flow, a third ALTERNATIVE beside the cookie and the forms
(an identity-provider redirect, a password-only subflow), or a second factor no longer REQUIRED
inside the forms would each let a password-only login through while the subflow still looks
committed. So the script reads the realm's browser-flow binding and the outline of
`staff browser`, refuses anything but the committed shape — before any change, in both modes —
and edits neither (a PUT on a flow without each execution's priority zeroes them: deploy
e19640d2).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "infra" / "staging" / "keycloak" / "staff_flow.py"
REALM = REPO / "infra" / "staging" / "keycloak" / "intake-realm.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("staff_flow_binding", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["staff_flow_binding"] = module
    spec.loader.exec_module(module)
    return module


sf = _load()


def _realm_outline() -> tuple[str | None, list]:
    """What Keycloak's executions listing of `staff browser` reads for the committed realm."""
    realm = json.loads(REALM.read_text(encoding="utf-8"))
    flows = {flow["alias"]: flow for flow in realm["authenticationFlows"]}

    def walk(alias: str, level: int) -> list:
        nodes = []
        for e in sorted(flows[alias]["authenticationExecutions"], key=lambda x: x["priority"]):
            if e.get("authenticatorFlow"):
                nodes.append(sf.Node(level, e["flowAlias"], e["requirement"]))
                nodes.extend(walk(e["flowAlias"], level + 1))
            else:
                nodes.append(sf.Node(level, e["authenticator"], e["requirement"]))
        return nodes

    return realm.get("browserFlow"), walk(sf.TOP_FLOW, 0)


COMMITTED = _realm_outline()


def _with(nodes: list, index: int, **changes: object) -> list:
    out = list(nodes)
    node = out[index]
    out[index] = sf.Node(
        changes.get("level", node.level),  # type: ignore[arg-type]
        changes.get("name", node.name),  # type: ignore[arg-type]
        changes.get("requirement", node.requirement),  # type: ignore[arg-type]
    )
    return out


class TestTheCommittedRealm:
    def test_it_is_the_outline_the_script_requires(self) -> None:
        assert sf.binding_problem(*COMMITTED) is None

    def test_the_outline_is_cookie_or_password_then_second_factor(self) -> None:
        _, nodes = COMMITTED
        shallow = [(n.level, n.name, n.requirement) for n in nodes if n.level <= 1]
        assert shallow == list(sf.OUTLINE)


class TestNearMisses:
    @pytest.mark.parametrize("flow", ["browser", "staff browser copy", None])
    def test_a_rebound_browser_flow_is_refused(self, flow: str | None) -> None:
        assert sf.binding_problem(flow, COMMITTED[1]) is not None

    def test_a_third_way_in_beside_the_cookie_and_the_forms_is_refused(self) -> None:
        flow, nodes = COMMITTED
        extra = [*nodes[:2], sf.Node(0, "identity-provider-redirector", "ALTERNATIVE"), *nodes[2:]]
        assert sf.binding_problem(flow, extra) is not None

    def test_a_disabled_extra_is_no_way_in(self) -> None:
        # near miss to the case above: present but DISABLED runs nothing
        flow, nodes = COMMITTED
        extra = [*nodes[:2], sf.Node(0, "identity-provider-redirector", "DISABLED"), *nodes[2:]]
        assert sf.binding_problem(flow, extra) is None

    @pytest.mark.parametrize(
        ("index", "requirement"),
        [
            (1, "DISABLED"),  # the forms subflow off: cookie-only
            (2, "ALTERNATIVE"),  # the password optional
            (3, "ALTERNATIVE"),  # the second factor optional
            (3, "DISABLED"),  # the second factor off: password-only
            (3, "CONDITIONAL"),
        ],
    )
    def test_a_weakened_step_is_refused(self, index: int, requirement: str) -> None:
        flow, nodes = COMMITTED
        assert sf.binding_problem(flow, _with(nodes, index, requirement=requirement)) is not None

    def test_a_password_only_sibling_inside_the_forms_is_refused(self) -> None:
        flow, nodes = COMMITTED
        sibling = [*nodes[:4], sf.Node(1, "auth-otp-form", "ALTERNATIVE"), *nodes[4:]]
        assert sf.binding_problem(flow, sibling) is not None


class FakeAdmin:
    """The committed subflow; the binding is the case under test."""

    def __init__(self, binding: tuple[str | None, list]) -> None:
        self._binding = binding
        self.applied: list = []

    def executions(self) -> list:
        return [
            sf.Execution("prov", sf.PROVIDER, "REQUIRED", sf.HWK_ALIAS, 0, 10),
            sf.Execution("otp", sf.OTP, "DISABLED", "amr otp", 1, 20),
        ]

    def register_action(self) -> dict:
        return {"alias": sf.REGISTER, "providerId": sf.REGISTER, "enabled": True}

    def binding(self) -> tuple[str | None, list]:
        return self._binding

    def apply(self, step: object) -> None:
        self.applied.append(step)


class TestRun:
    def test_the_committed_binding_passes_check(self) -> None:
        assert sf.run(FakeAdmin(COMMITTED), check_only=True) == []

    @pytest.mark.parametrize("check_only", [True, False])
    def test_a_rebound_realm_is_refused_before_any_change(self, check_only: bool) -> None:
        admin = FakeAdmin(("browser", COMMITTED[1]))
        with pytest.raises(sf.FlowRefused, match="browser flow"):
            sf.run(admin, check_only=check_only)
        assert admin.applied == []


class RecordingAdmin(sf.Admin):
    def __init__(self) -> None:
        super().__init__("http://keycloak:8080", "intake", "not-a-real-bearer")
        self.calls: list[tuple[str, str]] = []

    def _call(self, method: str, path: str, body: object = None) -> object:
        self.calls.append((method, path))
        if path == "":
            return {"browserFlow": sf.TOP_FLOW}
        return [
            {"level": 0, "providerId": "auth-cookie", "requirement": "ALTERNATIVE"},
            {
                "level": 0,
                "authenticationFlow": True,
                "displayName": "staff browser forms",
                "providerId": "basic-flow",
                "requirement": "ALTERNATIVE",
            },
        ]


class TestTheReads:
    def test_two_gets_and_nothing_else(self) -> None:
        admin = RecordingAdmin()
        flow, nodes = admin.binding()
        assert flow == sf.TOP_FLOW
        assert [(n.level, n.name, n.requirement) for n in nodes] == [
            (0, "auth-cookie", "ALTERNATIVE"),
            (0, "staff browser forms", "ALTERNATIVE"),
        ]
        assert admin.calls == [
            ("GET", ""),
            ("GET", "/authentication/flows/staff%20browser/executions"),
        ]
