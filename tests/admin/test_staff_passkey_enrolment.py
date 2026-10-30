"""INT-550 — a new staff user enrols a passkey after the password step (Sec-Row ``platform``).

Found read-only on the synthetic host, 17 Oct 2026: realm ``intake`` refused every new staff
user with "Invalid username or password". The issue blamed the INT-378 provider for not
allowing user setup. It does allow it: ``WebAuthnSessionNotesAuthenticatorFactory`` inherits
the stock ``isUserSetupAllowed() == true`` (the module's own tests hold it outright now). The
cause is the requirement. In Keycloak 26.7.4 (tag ``26.7.4``):

- ``services/.../authentication/DefaultAuthenticationFlow.java:473``: a user the password step
  identified but who holds no credential for an execution is sent to that execution's required
  action (status ``SETUP_REQUIRED``) only when ``factory.isUserSetupAllowed() &&
  model.isRequired() && authenticator.areRequiredActionsEnabled(...)``. An ALTERNATIVE is never
  REQUIRED, so line 480 records ``CREDENTIAL_SETUP_REQUIRED`` instead.
- lines 309-330: in a level of ALTERNATIVEs that exception is only collected. With WebAuthn and
  OTP both ALTERNATIVE and the user holding neither, the subflow, and so the whole browser flow,
  ends unsuccessful with no page.
- ``AuthenticationProcessor.java:1132-1133`` then throws an exception with the top flow's empty
  list, and ``handleBrowserException`` (lines 906-908) answers ``invalid_user_credentials`` and
  ``Messages.INVALID_USER``: "Invalid username or password". The webauthn-register required
  action, which INT-538 sets on every new user, never runs.
- An ``auth-otp-form`` ALTERNATIVE beside WebAuthn is also the way around a passkey for anyone
  holding a TOTP credential.

The fix is in the realms, not the jar: ``intake-webauthn-session-notes`` is REQUIRED in ``staff
second factor``, and ``auth-otp-form`` stays in the subflow, DISABLED, until the owner decides
INT-389 (#644). The console refuses a TOTP token today anyway (INT-378's ``aaguid`` rule). The
per-execution ``userSetupAllowed`` in the realm JSON is an export field that the import never
reads (``DefaultExportImportManager.toModel``, lines 1576-1600), so it is not the switch.

Pinned here, for both committed realms (``infra/keycloak/dev-realm.json`` and
``infra/staging/keycloak/intake-realm.json``):

1. the WebAuthn execution is REQUIRED and nothing else in the subflow is enabled;
2. the subflow is REQUIRED, directly after the REQUIRED password form;
3. ``webauthn-register`` stays enabled: the realms carry no ``requiredActions`` list, so the
   import adds Keycloak's defaults (``DefaultExportImportManager.java:362-373``), which register
   it enabled (``DefaultRequiredActions.java:316-333``). A list that drops or disables it fails;
4. the subflow is the one the provider module's engine test runs
   (``src/test/resources/staff-second-factor.json``, read by ``StaffSecondFactorFlowTest``, which
   drives Keycloak 26.7.4's own ``DefaultAuthenticationFlow``).

The live host's realm was imported once, before this change, so ``deploy.sh`` switches it
(``infra/staging/keycloak/staff_flow.py``, tested in
``tests/infra/test_staging_keycloak_provider.py``).

Each check is a function that returns violations: none for the committed realms, some for
every near-miss.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from intake_platform.admin.principal import principal_from_claims
from intake_platform.admin.second_factor import SecondFactorRequired

REPO = Path(__file__).resolve().parents[2]
REALMS = {
    "dev": REPO / "infra" / "keycloak" / "dev-realm.json",
    "staging": REPO / "infra" / "staging" / "keycloak" / "intake-realm.json",
}
ENGINE_FIXTURE = (
    REPO
    / "infra"
    / "keycloak"
    / "providers"
    / "webauthn-session-notes"
    / "src"
    / "test"
    / "resources"
    / "staff-second-factor.json"
)

SUBFLOW = "staff second factor"
FORMS = "staff browser forms"
PASSWORD = "auth-username-password-form"
PROVIDER = "intake-webauthn-session-notes"
STOCK = "webauthn-authenticator"
OTP = "auth-otp-form"
REGISTER = "webauthn-register"
#: Every requirement under which Keycloak runs an execution (DISABLED never runs).
RUNS = {"REQUIRED", "ALTERNATIVE", "CONDITIONAL"}
#: The fields the engine test reads, and so the ones held equal.
ENGINE_FIELDS = ("authenticator", "authenticatorConfig", "requirement", "priority")


def load(name: str) -> dict[str, Any]:
    realm: dict[str, Any] = json.loads(REALMS[name].read_text(encoding="utf-8"))
    return realm


def flow(realm: Mapping[str, Any], alias: str) -> list[dict[str, Any]]:
    (found,) = [f for f in realm.get("authenticationFlows", []) if f["alias"] == alias]
    executions: list[dict[str, Any]] = sorted(
        found["authenticationExecutions"], key=lambda e: e["priority"]
    )
    return executions


def name(execution: Mapping[str, Any]) -> str:
    return str(execution.get("authenticator") or execution.get("flowAlias"))


def enrolment_violations(realm: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    aliases = {f["alias"] for f in realm.get("authenticationFlows", [])}
    if not {SUBFLOW, FORMS} <= aliases:
        return [f"the realm lacks {sorted({SUBFLOW, FORMS} - aliases)}"]

    forms = [(name(e), e["requirement"]) for e in flow(realm, FORMS)]
    if forms != [(PASSWORD, "REQUIRED"), (SUBFLOW, "REQUIRED")]:
        violations.append(f"{FORMS!r} is {forms}, not the password then the second factor")

    second = flow(realm, SUBFLOW)
    ours = [e for e in second if e.get("authenticator") == PROVIDER]
    if len(ours) != 1:
        violations.append(f"{SUBFLOW!r} runs {PROVIDER} {len(ours)} times")
    elif ours[0]["requirement"] != "REQUIRED":
        violations.append(
            f"{PROVIDER} is {ours[0]['requirement']}: Keycloak sends a user without a passkey to "
            f"{REGISTER} only from a REQUIRED execution"
        )
    for execution in second:
        if execution.get("authenticator") != PROVIDER and execution["requirement"] in RUNS:
            violations.append(
                f"{name(execution)} is {execution['requirement']} beside WebAuthn: it must stay "
                "DISABLED until INT-389"
            )

    actions = realm.get("requiredActions")
    if actions is not None:
        register = [a for a in actions if a.get("alias") == REGISTER]
        if not register or register[0].get("enabled") is not True:
            violations.append(f"{REGISTER} is not an enabled required action of the realm")
    return violations


def engine_view(executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{field: e.get(field) for field in ENGINE_FIELDS} for e in executions]


class TestCommittedRealms:
    @pytest.mark.parametrize("realm", sorted(REALMS))
    def test_no_violation(self, realm: str) -> None:
        assert enrolment_violations(load(realm)) == []

    @pytest.mark.parametrize("realm", sorted(REALMS))
    def test_webauthn_is_required_and_otp_is_kept_disabled(self, realm: str) -> None:
        # the two executions as committed; OTP keeps its amr reference for INT-389
        assert [
            (name(e), e["requirement"], e["authenticatorConfig"])
            for e in flow(load(realm), SUBFLOW)
        ] == [
            (PROVIDER, "REQUIRED", "amr hwk"),
            (OTP, "DISABLED", "amr otp"),
        ]

    @pytest.mark.parametrize("realm", sorted(REALMS))
    def test_the_realm_takes_keycloaks_default_required_actions(self, realm: str) -> None:
        # no list, so the import registers webauthn-register enabled (and UPDATE_PASSWORD,
        # which INT-538's temporary password needs)
        assert "requiredActions" not in load(realm)

    def test_both_realms_carry_the_same_subflow(self) -> None:
        assert engine_view(flow(load("dev"), SUBFLOW)) == engine_view(
            flow(load("staging"), SUBFLOW)
        )

    @pytest.mark.parametrize("realm", sorted(REALMS))
    def test_the_engine_test_runs_the_committed_subflow(self, realm: str) -> None:
        fixture = json.loads(ENGINE_FIXTURE.read_text(encoding="utf-8"))
        assert fixture["alias"] == SUBFLOW
        assert fixture["heldEqualTo"] == [
            str(path.relative_to(REPO)) for _, path in sorted(REALMS.items())
        ]
        assert sorted(fixture["authenticationExecutions"], key=lambda e: e["priority"]) == (
            engine_view(flow(load(realm), SUBFLOW))
        )


def _set(realm: dict[str, Any], alias: str, authenticator: str, requirement: str) -> None:
    for execution in flow(realm, alias):
        if name(execution) == authenticator:
            execution["requirement"] = requirement


def _hosts_state(realm: dict[str, Any]) -> None:
    # the live subflow on 17 Oct 2026
    _set(realm, SUBFLOW, PROVIDER, "ALTERNATIVE")
    _set(realm, SUBFLOW, OTP, "ALTERNATIVE")


def _stock_beside(realm: dict[str, Any]) -> None:
    (found,) = [f for f in realm["authenticationFlows"] if f["alias"] == SUBFLOW]
    found["authenticationExecutions"].append(
        {
            "authenticator": STOCK,
            "authenticatorFlow": False,
            "requirement": "ALTERNATIVE",
            "priority": 30,
        }
    )


def _second_provider(realm: dict[str, Any]) -> None:
    (found,) = [f for f in realm["authenticationFlows"] if f["alias"] == SUBFLOW]
    found["authenticationExecutions"].append(
        {
            "authenticator": PROVIDER,
            "authenticatorFlow": False,
            "requirement": "REQUIRED",
            "priority": 30,
        }
    )


def _second_factor_first(realm: dict[str, Any]) -> None:
    for execution in flow(realm, FORMS):
        execution["priority"] = 30 - execution["priority"]


def _actions_without_register(realm: dict[str, Any]) -> None:
    realm["requiredActions"] = [
        {"alias": "UPDATE_PASSWORD", "providerId": "UPDATE_PASSWORD", "enabled": True}
    ]


def _register_disabled(realm: dict[str, Any]) -> None:
    realm["requiredActions"] = [
        {"alias": "UPDATE_PASSWORD", "providerId": "UPDATE_PASSWORD", "enabled": True},
        {"alias": REGISTER, "providerId": REGISTER, "enabled": False},
    ]


NEAR_MISSES = {
    "the host's two ALTERNATIVEs": _hosts_state,
    "WebAuthn ALTERNATIVE alone": lambda r: _set(r, SUBFLOW, PROVIDER, "ALTERNATIVE"),
    "WebAuthn CONDITIONAL": lambda r: _set(r, SUBFLOW, PROVIDER, "CONDITIONAL"),
    "WebAuthn DISABLED": lambda r: _set(r, SUBFLOW, PROVIDER, "DISABLED"),
    "OTP ALTERNATIVE beside it": lambda r: _set(r, SUBFLOW, OTP, "ALTERNATIVE"),
    "OTP REQUIRED beside it": lambda r: _set(r, SUBFLOW, OTP, "REQUIRED"),
    "OTP CONDITIONAL beside it": lambda r: _set(r, SUBFLOW, OTP, "CONDITIONAL"),
    "the stock authenticator beside it": _stock_beside,
    "the provider twice": _second_provider,
    "the second factor ALTERNATIVE in the forms": lambda r: _set(r, FORMS, SUBFLOW, "ALTERNATIVE"),
    "the second factor before the password": _second_factor_first,
    "a required-action list without webauthn-register": _actions_without_register,
    "webauthn-register disabled": _register_disabled,
}


class TestNearMisses:
    @pytest.mark.parametrize("realm", sorted(REALMS))
    @pytest.mark.parametrize("mutation", sorted(NEAR_MISSES))
    def test_each_is_caught(self, realm: str, mutation: str) -> None:
        mutated = copy.deepcopy(load(realm))
        NEAR_MISSES[mutation](mutated)
        assert enrolment_violations(mutated)

    def test_the_hosts_state_names_the_cause(self) -> None:
        mutated = copy.deepcopy(load("staging"))
        _hosts_state(mutated)
        assert enrolment_violations(mutated) == [
            f"{PROVIDER} is ALTERNATIVE: Keycloak sends a user without a passkey to {REGISTER} "
            "only from a REQUIRED execution",
            f"{OTP} is ALTERNATIVE beside WebAuthn: it must stay DISABLED until INT-389",
        ]

    def test_near_miss_the_engine_fixture_drifting_is_caught(self) -> None:
        fixture = json.loads(ENGINE_FIXTURE.read_text(encoding="utf-8"))
        fixture["authenticationExecutions"][0]["requirement"] = "CONDITIONAL"
        assert fixture["authenticationExecutions"] != engine_view(flow(load("staging"), SUBFLOW))


# --------------------------------------------------------------------------
# the first sign-in after enrolment, as the console sees it
# --------------------------------------------------------------------------

RECORDING = REPO / "tests" / "admin" / "fixtures" / "keycloak_webauthn_login.json"
#: The two roles INT-538's staff-user command creates.
OWNER_ROLES = ["platform_owner", "qms_owner"]


def recorded_passkey_sign_in(role: str) -> dict[str, Any]:
    """INT-378's recorded Keycloak 26.7.4 login through the provider, under ``role``."""
    recording = json.loads(RECORDING.read_text(encoding="utf-8"))
    claims: dict[str, Any] = dict(recording["logins"][PROVIDER]["access_token_claims"])
    claims["realm_access"] = {"roles": [role]}
    return claims


class TestFirstSignInAfterEnrolment:
    """The enrolment login completes through webauthn-register, not through a WebAuthn assertion.

    Keycloak records an execution as completed only on SUCCESS
    (``AuthenticatorUtils.updateCompletedExecutions``, from ``processResult``), and the WebAuthn
    step ends SETUP_REQUIRED. So that login's token has the password's ``amr`` alone and no
    note (``StaffSecondFactorFlowTest`` in the provider module holds both), and the console
    refuses it. An SSO resume keeps that session's ``amr``, so the staff member signs out of
    Keycloak and signs in again. That login asserts the new passkey
    (``theNextSignInAssertsTheNewPasskeyAndCompletesWithBothNotes``) and is admitted, as INT-378's
    recorded login shows.
    """

    @pytest.mark.parametrize("role", OWNER_ROLES)
    def test_the_enrolment_logins_token_is_refused(self, role: str) -> None:
        claims = recorded_passkey_sign_in(role)
        claims["amr"] = ["pwd"]
        del claims["aaguid"], claims["credential_id"]
        with pytest.raises(SecondFactorRequired):
            principal_from_claims(claims, source_ip="127.0.0.1")

    @pytest.mark.parametrize("role", OWNER_ROLES)
    def test_near_miss_the_next_passkey_sign_in_is_admitted(self, role: str) -> None:
        claims = recorded_passkey_sign_in(role)
        assert claims["amr"] == ["pwd", "hwk"]
        principal = principal_from_claims(claims, source_ip="127.0.0.1")
        assert principal.authenticator_aaguid == claims["aaguid"]
        assert principal.credential_id == claims["credential_id"]
        assert [r.value for r in principal.roles] == [role]
