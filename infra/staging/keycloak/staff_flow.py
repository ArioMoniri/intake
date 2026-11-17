"""Bring the live staff realm's second factor onto the committed shape (INT-378, INT-421, INT-550).

The admin console refuses a staff token that lacks ``aaguid`` and ``credential_id``. Only the
``intake-webauthn-session-notes`` authenticator writes them (INT-378). The committed realm
(``intake-realm.json``) runs it, but Keycloak imports a realm once: ``start --import-realm``
skips a realm that already exists. So a change to the committed flow never reaches the host,
and this script makes the live ``staff second factor`` subflow match it:

- the WebAuthn step is ``intake-webauthn-session-notes``, REQUIRED, with the ``amr hwk``
  reference the console's second-factor check reads (INT-365). REQUIRED is what lets a new
  staff user in: Keycloak 26.7.4 sends a user without a passkey to the ``webauthn-register``
  required action only from a REQUIRED execution, and refuses them from an ALTERNATIVE with
  "Invalid username or password" (INT-550, ``tests/admin/test_staff_passkey_enrolment.py``);
- the stock ``webauthn-authenticator`` is gone from the subflow;
- the OTP step is DISABLED and stays in place, after WebAuthn, until the owner decides
  INT-389 (#644). The console refuses a TOTP token today, and an OTP ALTERNATIVE beside
  WebAuthn was both the dead end for new users and a way around a passkey.

Before any change it reads the realm's ``webauthn-register`` required action and refuses, with
the reason, unless it exists and is enabled: without it a new user still cannot enrol. A
requirement change always sends the execution's current priority, because Keycloak's
``updateExecutions`` copies whatever priority the body carries (an absent one is 0).

Nothing else is touched. It is idempotent: each step is taken only when the live flow differs,
and the run ends by checking that the flow is in the committed state, or it fails. ``--check``
only reads. It runs in a one-off api container (stdlib only) on the internal network, and reads
the bootstrap admin password on stdin, so the secret never reaches an argv, an environment or a
log. It prints execution ids and provider ids, never a value from a credential.

Usage: ``python staff_flow.py [--check] <base-url> <realm> <admin-user>``, password on stdin.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

PROVIDER = "intake-webauthn-session-notes"
STOCK = "webauthn-authenticator"
OTP = "auth-otp-form"
SUBFLOW = "staff second factor"
REQUIRED = "REQUIRED"
DISABLED = "DISABLED"
#: The required action a REQUIRED WebAuthn execution sends a user without a passkey to.
REGISTER = "webauthn-register"
#: The committed `amr hwk` reference (intake-realm.json, authenticatorConfig).
HWK_ALIAS = "amr hwk"
HWK_CONFIG = {"default.reference.value": "hwk", "default.reference.maxAge": "28800"}
#: Each pass takes one step, and at most six steps exist; more passes mean a loop.
MAX_PASSES = 8
#: The steps that change a requirement, and the requirement each one sets.
REQUIREMENT_STEPS = {"set_required": REQUIRED, "disable_otp": DISABLED}


@dataclass(frozen=True)
class Execution:
    id: str
    provider: str
    requirement: str
    config_alias: str | None
    index: int
    priority: int


@dataclass(frozen=True)
class Step:
    """One change, or ``done``. ``target`` is an execution id when the step names one, and
    ``priority`` is that execution's current priority when the step changes its requirement."""

    action: str
    target: str | None = None
    priority: int | None = None


class FlowRefused(Exception):
    """The live realm is in a state this script will not edit: a human looks first."""


class FlowAdmin(Protocol):
    def executions(self) -> list[Execution]: ...

    def register_action(self) -> Mapping[str, Any] | None: ...

    def apply(self, step: Step) -> None: ...


def checked_base(base_url: str) -> str:
    """The admin API base, http(s) only: every URL below is built on it (ruff S310)."""
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("the Keycloak base URL must be http(s)://host[:port]")
    return base_url.rstrip("/")


def register_problem(action: Mapping[str, Any] | None) -> str | None:
    """Why a new staff user could not enrol a passkey, or None when they can."""
    if action is None:
        return f"the realm has no {REGISTER} required action: a new staff user cannot enrol"
    if action.get("enabled") is not True:
        return f"the realm's {REGISTER} required action is disabled: a new staff user cannot enrol"
    return None


def next_step(executions: Sequence[Execution]) -> Step:
    """The one change that moves the live subflow toward the committed one."""
    providers = [e for e in executions if e.provider == PROVIDER]
    if len(providers) > 1:
        raise FlowRefused("the subflow runs the provider twice")
    if not providers:
        return Step("add_provider")
    provider = providers[0]
    if provider.requirement != REQUIRED:
        return Step("set_required", provider.id, provider.priority)
    stock = [e for e in executions if e.provider == STOCK]
    if stock:
        return Step("remove_stock", stock[0].id)
    if provider.config_alias is None:
        return Step("add_hwk_reference", provider.id)
    if provider.config_alias != HWK_ALIAS:
        raise FlowRefused("the provider carries an amr reference other than the committed hwk")
    otp = [e for e in executions if e.provider == OTP]
    if otp and otp[0].requirement != DISABLED:
        return Step("disable_otp", otp[0].id, otp[0].priority)
    if otp and provider.index > otp[0].index:
        return Step("raise_provider", provider.id)
    return Step("done")


class Admin:
    """The Keycloak admin REST API, over the internal network, with one bearer."""

    def __init__(self, base_url: str, realm: str, bearer: str) -> None:
        self._base = checked_base(base_url)
        self._realm = urllib.parse.quote(realm, safe="")
        self._bearer = bearer

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 — checked_base admits http(s) only
            f"{self._base}/admin/realms/{self._realm}{path}", data=data, method=method
        )
        request.add_header("Authorization", f"Bearer {self._bearer}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else None

    def executions(self) -> list[Execution]:
        flow = urllib.parse.quote(SUBFLOW, safe="")
        found: list[Execution] = []
        for item in self._call("GET", f"/authentication/flows/{flow}/executions"):
            if item.get("level", 0) != 0:
                continue
            config_id = item.get("authenticationConfig")
            alias = None
            if config_id:
                # 26.7.4 masks every config value in this answer; the alias is what
                # can be read, and only the committed realm and this script write it
                alias = self._call("GET", f"/authentication/config/{config_id}").get("alias")
            found.append(
                Execution(
                    id=item["id"],
                    provider=item.get("providerId", ""),
                    requirement=item.get("requirement", ""),
                    config_alias=alias,
                    index=int(item.get("index", 0)),
                    priority=int(item.get("priority", 0)),
                )
            )
        return found

    def register_action(self) -> Mapping[str, Any] | None:
        try:
            action: Mapping[str, Any] = self._call(
                "GET", f"/authentication/required-actions/{REGISTER}"
            )
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise
        return action

    def apply(self, step: Step) -> None:
        flow = urllib.parse.quote(SUBFLOW, safe="")
        if step.action == "add_provider":
            self._call(
                "POST", f"/authentication/flows/{flow}/executions/execution", {"provider": PROVIDER}
            )
        elif step.action in REQUIREMENT_STEPS:
            if step.priority is None:
                # the PUT copies the body's priority; without the current one it would be 0
                raise FlowRefused(f"{step.action} without the execution's priority")
            self._call(
                "PUT",
                f"/authentication/flows/{flow}/executions",
                {
                    "id": step.target,
                    "requirement": REQUIREMENT_STEPS[step.action],
                    "priority": step.priority,
                },
            )
        elif step.action == "remove_stock":
            self._call("DELETE", f"/authentication/executions/{step.target}")
        elif step.action == "add_hwk_reference":
            self._call(
                "POST",
                f"/authentication/executions/{step.target}/config",
                {"alias": HWK_ALIAS, "config": HWK_CONFIG},
            )
        elif step.action == "raise_provider":
            self._call("POST", f"/authentication/executions/{step.target}/raise-priority")
        else:
            raise FlowRefused(f"unknown step {step.action}")


def admin_bearer(base_url: str, user: str, password: str) -> str:
    form = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "admin-cli", "username": user, "password": password}
    ).encode("ascii")
    request = urllib.request.Request(  # noqa: S310 — checked_base admits http(s) only
        f"{checked_base(base_url)}/realms/master/protocol/openid-connect/token",
        data=form,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        token: str = json.loads(response.read())["access_token"]
    return token


def run(admin: FlowAdmin, *, check_only: bool) -> list[Step]:
    """Apply steps until the subflow is committed-shape; return what was done."""
    problem = register_problem(admin.register_action())
    if problem is not None:
        raise FlowRefused(problem)
    taken: list[Step] = []
    for _ in range(MAX_PASSES):
        step = next_step(admin.executions())
        if step.action == "done":
            return taken
        if check_only:
            raise FlowRefused(
                f"the live subflow is not in the committed state (next: {step.action})"
            )
        admin.apply(step)
        taken.append(step)
    raise FlowRefused("the subflow did not settle")


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    check_only = "--check" in args
    if check_only:
        args.remove("--check")
    if len(args) != 3:
        print("usage: staff_flow.py [--check] <base-url> <realm> <admin-user>", file=sys.stderr)
        return 2
    base_url, realm, user = args
    password = sys.stdin.readline().rstrip("\n")
    if not password:
        print("staff flow: no admin password on stdin", file=sys.stderr)
        return 2
    try:
        admin = Admin(base_url, realm, admin_bearer(base_url, user, password))
        taken = run(admin, check_only=check_only)
    except urllib.error.HTTPError as err:
        # a status and a reason only: a response body is never printed
        print(f"staff flow: the admin API answered {err.code} {err.reason}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"staff flow: Keycloak unreachable ({type(err).__name__})", file=sys.stderr)
        return 1
    except FlowRefused as refused:
        print(f"staff flow: refused: {refused}", file=sys.stderr)
        return 3
    for step in taken:
        print(f"staff flow: {step.action} {step.target or PROVIDER}")
    print(
        f"staff flow: realm {realm} runs {PROVIDER} REQUIRED with the hwk reference, "
        f"OTP disabled, and {REGISTER} enabled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
