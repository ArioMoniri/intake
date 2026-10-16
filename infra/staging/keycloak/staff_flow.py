"""Bring the live staff realm's WebAuthn step onto the session-notes provider (INT-378, INT-421).

The admin console refuses a staff token that lacks ``aaguid`` and ``credential_id``. Only the
``intake-webauthn-session-notes`` authenticator writes them (INT-378). The committed realm
(``intake-realm.json``) runs it, but Keycloak imports a realm once: ``start --import-realm``
skips a realm that already exists. So a change to the committed flow never reaches the host,
and this script makes the live ``staff second factor`` subflow match it:

- the WebAuthn alternative is ``intake-webauthn-session-notes``, ALTERNATIVE, with the
  ``amr hwk`` reference the console's second-factor check reads (INT-365);
- the stock ``webauthn-authenticator`` is gone from the subflow;
- WebAuthn comes before the OTP alternative, as committed.

Nothing else is touched. In particular the OTP alternative stays: whether TOTP may sign a
console role in is the owner's decision (INT-389), and the console refuses a TOTP token today.

It is idempotent: each step is taken only when the live flow differs, and the run ends by
checking that the flow is in the committed state, or it fails. ``--check`` only reads. It
runs in a one-off api container (stdlib only) on the internal network, and reads the
bootstrap admin password on stdin, so the secret never reaches an argv, an environment or a
log. It prints execution ids and provider ids, never a value from a credential.

Usage: ``python staff_flow.py [--check] <base-url> <realm> <admin-user>``, password on stdin.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

PROVIDER = "intake-webauthn-session-notes"
STOCK = "webauthn-authenticator"
OTP = "auth-otp-form"
SUBFLOW = "staff second factor"
ALTERNATIVE = "ALTERNATIVE"
#: The committed `amr hwk` reference (intake-realm.json, authenticatorConfig).
HWK_ALIAS = "amr hwk"
HWK_CONFIG = {"default.reference.value": "hwk", "default.reference.maxAge": "28800"}
#: Each pass takes one step, and at most five steps exist; more passes mean a loop.
MAX_PASSES = 8


@dataclass(frozen=True)
class Execution:
    id: str
    provider: str
    requirement: str
    config_alias: str | None
    index: int


@dataclass(frozen=True)
class Step:
    """One change, or ``done``. ``target`` is an execution id when the step names one."""

    action: str
    target: str | None = None


class FlowRefused(Exception):
    """The live flow is in a state this script will not edit: a human looks first."""


def checked_base(base_url: str) -> str:
    """The admin API base, http(s) only: every URL below is built on it (ruff S310)."""
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("the Keycloak base URL must be http(s)://host[:port]")
    return base_url.rstrip("/")


def next_step(executions: Sequence[Execution]) -> Step:
    """The one change that moves the live subflow toward the committed one."""
    providers = [e for e in executions if e.provider == PROVIDER]
    if len(providers) > 1:
        raise FlowRefused("the subflow runs the provider twice")
    if not providers:
        return Step("add_provider")
    provider = providers[0]
    if provider.requirement != ALTERNATIVE:
        return Step("set_alternative", provider.id)
    stock = [e for e in executions if e.provider == STOCK]
    if stock:
        return Step("remove_stock", stock[0].id)
    if provider.config_alias is None:
        return Step("add_hwk_reference", provider.id)
    if provider.config_alias != HWK_ALIAS:
        raise FlowRefused("the provider carries an amr reference other than the committed hwk")
    otp = [e for e in executions if e.provider == OTP]
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
                )
            )
        return found

    def apply(self, step: Step) -> None:
        flow = urllib.parse.quote(SUBFLOW, safe="")
        if step.action == "add_provider":
            self._call(
                "POST", f"/authentication/flows/{flow}/executions/execution", {"provider": PROVIDER}
            )
        elif step.action == "set_alternative":
            self._call(
                "PUT",
                f"/authentication/flows/{flow}/executions",
                {"id": step.target, "requirement": ALTERNATIVE},
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


def run(admin: Admin, *, check_only: bool) -> list[Step]:
    """Apply steps until the subflow is committed-shape; return what was done."""
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
    print(f"staff flow: realm {realm} runs {PROVIDER} with the hwk reference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
