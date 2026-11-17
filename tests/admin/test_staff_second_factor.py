"""INT-365 — staff second factor and session bounds (files/08 §2.3; Sec-Row admin-console).

files/08 §2.3: MFA for every console role; phishing-resistant WebAuthn for
anything that reaches patient content; a session of at most 8 h with a
30-minute idle timeout wherever the session can reach PHI.

Four things are pinned, in this order:

1. **Which roles need WebAuthn** is derived from the §2.1 "may reach patient
   content?" column. This file writes the set out AND re-parses the spec
   table, so the registry, the spec and the policy cannot drift apart.
2. **The console refuses** a token whose ``amr`` claim does not show a password
   plus a second factor, and a token without ``hwk`` (the realm's WebAuthn
   reference) for a patient-content role. The claim must be a JSON array of
   exact, case-sensitive strings; every other shape is no evidence. ``acr``
   never admits. The refusal is a 401 with one generic body and an audit row
   that names ids only.
3. **The committed realm** (``infra/keycloak/dev-realm.json``) configures the
   OTP and WebAuthn policies. Every fresh path through its browser flow ends
   with ``pwd`` and a second factor. Its reference values are exactly the ones
   the verifier accepts.
4. **The realm bounds sessions**: 8 h, 30 minutes idle, offline sessions too.

The realm and session checks are functions that return violations. Each one is
run once against the committed realm, which must give none, and once against a
near-miss mutation, which must give some. A checker that cannot fail proves
nothing.

Section 5 (INT-391) pins the ``credential_id`` claim to WebAuthn Level 3's
credential id: unpadded base64url, 16 to 1023 bytes once decoded, one spelling
per credential. It uses property tests over generated ids.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from admin_harness import (
    ALLOWED_CIDRS,
    TEST_DEPLOYMENTS,
    RecordedClaimsVerifier,
    build_admin_harness,
    recorded_claims,
    token_for,
)
from api_harness import ApiHarness
from hypothesis import given, settings
from hypothesis import strategies as st
from intake_platform.admin import ADMIN_ROLES, AdminRole, AdminWiring, IpAllowList
from intake_platform.admin.principal import MalformedClaims, principal_from_claims
from intake_platform.admin.second_factor import (
    AMR_FIRST_FACTOR,
    AMR_OTP,
    AMR_WEBAUTHN,
    SecondFactorRequired,
    accepted_second_factors,
    requires_webauthn,
)

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "files" / "08_ADMIN_CONSOLE_AND_OBSERVABILITY.md"
REALM = REPO / "infra" / "keycloak" / "dev-realm.json"

#: files/08 §2.1, every row whose "may reach patient content?" cell is not
#: "no". Written out on purpose: this is the second opinion against the
#: derivation in ``intake_platform.admin.second_factor``.
PATIENT_CONTENT_ROLES = frozenset(
    {
        AdminRole.PLATFORM_OWNER,
        AdminRole.TENANT_CLINICAL_RESPONSIBLE,
        AdminRole.CLINICAL_LEAD,
        AdminRole.INVESTIGATOR,
        AdminRole.COMPLIANCE_OFFICER,
        AdminRole.SUPPORT,
    }
)
OTHER_ROLES = frozenset(ADMIN_ROLES) - PATIENT_CONTENT_ROLES

PWD_OTP = ["pwd", "otp"]
PWD_HWK = ["pwd", "hwk"]
STEP_UP_BODY = {"error": "insufficient_user_authentication"}
STEP_UP_CHALLENGE = 'Bearer error="insufficient_user_authentication"'

#: files/08 §2.3, in seconds. ``TestSpecAnchor`` fails if the sentence moves.
MAX_SESSION_S = 8 * 3600
IDLE_S = 30 * 60


def account(role: str, *, amr: object = PWD_HWK, **overrides: Any) -> dict[str, Any]:
    """The recorded claim set for ``role`` with ``amr`` replaced (or removed)."""
    claims = copy.deepcopy(dict(recorded_claims()[token_for(role)]))
    if amr is None:
        claims.pop("amr", None)
    else:
        claims["amr"] = amr
    claims.update(overrides)
    return claims


def resolve(claims: Mapping[str, Any]) -> Any:
    return principal_from_claims(claims, source_ip="192.0.2.10")


# --------------------------------------------------------------------------
# 1. which roles need WebAuthn
# --------------------------------------------------------------------------


def spec_patient_content_roles() -> set[str]:
    """Roles whose §2.1 third column does not start with the word "no"."""
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("### 2.1 Role set") : text.index("### 2.2 ")]
    reaching: set[str] = set()
    for line in section.splitlines():
        cells = line.split("|")
        match = re.search(r"`([a-z_]+)`", cells[1]) if len(cells) > 4 else None
        if match and not re.match(r"no\b", cells[3].strip()):
            reaching.add(match.group(1))
    return reaching


class TestRoleMapping:
    def test_webauthn_roles_are_exactly_the_patient_content_rows(self) -> None:
        derived = {role for role in ADMIN_ROLES if requires_webauthn(role)}
        assert derived == PATIENT_CONTENT_ROLES

    def test_the_written_set_matches_the_spec_table(self) -> None:
        assert spec_patient_content_roles() == {role.value for role in PATIENT_CONTENT_ROLES}

    def test_patient_content_roles_accept_only_webauthn(self) -> None:
        for role in PATIENT_CONTENT_ROLES:
            assert accepted_second_factors({role}) == {AMR_WEBAUTHN}, role
        for role in OTHER_ROLES:
            assert accepted_second_factors({role}) == {AMR_OTP, AMR_WEBAUTHN}, role


# --------------------------------------------------------------------------
# 2. the policy, at the principal seam every verifier feeds
# --------------------------------------------------------------------------


class TestPolicy:
    @pytest.mark.parametrize("role", sorted(r.value for r in ADMIN_ROLES))
    def test_a_token_without_amr_is_refused_for_every_role(self, role: str) -> None:
        with pytest.raises(SecondFactorRequired):
            resolve(account(role, amr=None))

    @pytest.mark.parametrize("role", sorted(r.value for r in PATIENT_CONTENT_ROLES))
    def test_otp_for_a_patient_content_role_is_refused(self, role: str) -> None:
        with pytest.raises(SecondFactorRequired):
            resolve(account(role, amr=PWD_OTP))

    @pytest.mark.parametrize("role", sorted(r.value for r in OTHER_ROLES))
    def test_otp_for_a_role_without_patient_content_is_admitted(self, role: str) -> None:
        assert resolve(account(role, amr=PWD_OTP)).roles == {AdminRole(role)}

    @pytest.mark.parametrize("role", sorted(r.value for r in ADMIN_ROLES))
    def test_webauthn_is_admitted_for_every_role(self, role: str) -> None:
        assert resolve(account(role, amr=PWD_HWK)).roles == {AdminRole(role)}
        assert resolve(account(role, amr=["pwd", "otp", "hwk"])).roles == {AdminRole(role)}

    def test_near_miss_only_the_role_differs(self) -> None:
        # The same claim set, amr and all, is admitted for `auditor` and
        # refused for `clinical_lead`. The refusal comes from the role mapping,
        # not from anything wrong with the token.
        admitted = account("auditor", amr=PWD_OTP)
        assert resolve(admitted).subject == "kc-sub-auditor"
        swapped = dict(admitted, realm_access={"roles": ["clinical_lead"]})
        with pytest.raises(SecondFactorRequired):
            resolve(swapped)

    def test_the_strongest_requirement_across_held_roles_wins(self) -> None:
        both = {"roles": ["auditor", "clinical_lead", "offline_access"]}
        with pytest.raises(SecondFactorRequired):
            resolve(account("auditor", amr=PWD_OTP, realm_access=both))
        assert len(resolve(account("auditor", amr=PWD_HWK, realm_access=both)).roles) == 2

    def test_a_role_outside_the_console_set_raises_no_requirement(self) -> None:
        # `clinician` is a realm role, not a console role, so it is dropped
        # before the policy runs and cannot demand anything.
        mixed = {"roles": ["auditor", "clinician"]}
        assert resolve(account("auditor", amr=PWD_OTP, realm_access=mixed))

    @pytest.mark.parametrize(
        "amr",
        [
            [],
            ["pwd"],
            ["hwk"],
            ["otp"],
            ["otp", "hwk"],
            "pwd hwk",
            "hwk",
            "pwd otp",
            ["pwd", "HWK"],
            ["PWD", "hwk"],
            ["pwd", "OTP"],
            ["pwd", " hwk"],
            ["pwd", "hwk "],
            ["pwd", "webauthn"],
            ["pwd", "swk"],
            ["pwd", "mfa"],
            ["pwd", ["hwk"]],
            ["pwd", None, "hwk"],
            ["pwd", 1, "hwk"],
            {"pwd": True, "hwk": True},
            1,
            True,
        ],
        ids=repr,
    )
    @pytest.mark.parametrize("role", ["auditor", "clinical_lead"])
    def test_claim_shape_and_case_are_not_negotiable(self, role: str, amr: object) -> None:
        # OIDC Core §2: amr is a JSON array of case-sensitive strings. A
        # string is refused rather than split; a list with a non-string member
        # is refused rather than filtered.
        with pytest.raises(SecondFactorRequired):
            resolve(account(role, amr=amr))

    @pytest.mark.parametrize("acr", ["0", "1", "2", "gold", "mfa", "urn:mace:incommon:iap:silver"])
    def test_acr_alone_never_admits(self, acr: str) -> None:
        with pytest.raises(SecondFactorRequired):
            resolve(account("auditor", amr=None, acr=acr))
        with pytest.raises(SecondFactorRequired):
            resolve(account("auditor", amr=["pwd"], acr=acr))

    def test_the_refusal_carries_the_verified_subject_and_nothing_else(self) -> None:
        with pytest.raises(SecondFactorRequired) as refused:
            resolve(account("clinical_lead", amr=PWD_OTP))
        assert refused.value.subject == "kc-sub-clinical-lead"
        assert refused.value.code == "insufficient_user_authentication"
        assert "otp" not in str(refused.value)

    def test_an_unshaped_subject_is_not_carried(self) -> None:
        with pytest.raises(SecondFactorRequired) as refused:
            resolve(account("clinical_lead", amr=None, sub="not an id!"))
        assert refused.value.subject is None


# --------------------------------------------------------------------------
# 2b. the refusal as the console serves and audits it
# --------------------------------------------------------------------------

EXTRA_ACCOUNTS: dict[str, dict[str, Any]] = {
    **{f"otp:{role.value}": account(role.value, amr=PWD_OTP) for role in ADMIN_ROLES},
    "noamr:auditor": account("auditor", amr=None),
    "noamr:unshaped_sub": account("auditor", amr=None, sub="not an id!"),
}


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    wiring = AdminWiring(
        claims=RecordedClaimsVerifier({**recorded_claims(), **EXTRA_ACCOUNTS}),
        ip_allowlist=IpAllowList.from_spec(ALLOWED_CIDRS),
        deployments=dict(TEST_DEPLOYMENTS),
    )
    yield from build_admin_harness(tmp_path, admin=wiring)


def whoami(harness: ApiHarness, token: str) -> Any:
    return harness.client.get("/admin/whoami", headers={"Authorization": f"Bearer {token}"})


class TestConsoleRefusal:
    @pytest.mark.parametrize("role", sorted(r.value for r in PATIENT_CONTENT_ROLES))
    def test_otp_for_a_patient_content_role_is_a_generic_401(
        self, harness: ApiHarness, role: str
    ) -> None:
        response = whoami(harness, f"otp:{role}")
        assert response.status_code == 401
        assert response.json() == STEP_UP_BODY
        assert response.headers["www-authenticate"] == STEP_UP_CHALLENGE

    @pytest.mark.parametrize("role", sorted(r.value for r in OTHER_ROLES))
    def test_otp_for_other_roles_reaches_the_console(self, harness: ApiHarness, role: str) -> None:
        assert whoami(harness, f"otp:{role}").status_code == 200

    def test_webauthn_reaches_the_console(self, harness: ApiHarness) -> None:
        assert whoami(harness, token_for("clinical_lead")).status_code == 200

    def test_no_amr_and_wrong_factor_are_indistinguishable(self, harness: ApiHarness) -> None:
        # One body for "no second factor" and "not WebAuthn", so the answer
        # does not reveal whether the account reaches patient content.
        absent = whoami(harness, "noamr:auditor")
        weak = whoami(harness, "otp:clinical_lead")
        assert (absent.status_code, absent.json()) == (weak.status_code, weak.json())
        assert absent.headers["www-authenticate"] == weak.headers["www-authenticate"]

    def test_the_refusal_is_audited_under_the_subject_id(self, harness: ApiHarness) -> None:
        before = len(tuple(harness.audit_store.entries()))
        assert whoami(harness, "otp:clinical_lead").status_code == 401
        appended = tuple(harness.audit_store.entries())[before:]
        assert [entry.action for entry in appended] == [
            "admin.whoami.read.intent",
            "admin.whoami.read.failure",
        ]
        assert {entry.actor for entry in appended} == {"kc-sub-clinical-lead"}
        for entry in appended:
            assert entry.resource_ref.startswith("admin_action:")
            fields = (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref)
            for value in fields:
                # ids only: no claim value, no factor name, no role
                assert not re.search(r"\b(otp|hwk|pwd|amr|clinical_lead)\b", value), value

    def test_an_unshaped_subject_is_audited_as_unresolved(self, harness: ApiHarness) -> None:
        before = len(tuple(harness.audit_store.entries()))
        assert whoami(harness, "noamr:unshaped_sub").status_code == 401
        appended = tuple(harness.audit_store.entries())[before:]
        assert {entry.actor for entry in appended} == {"admin:unresolved"}


# --------------------------------------------------------------------------
# 3. the committed realm: policies, flow, references
# --------------------------------------------------------------------------

RESUMED = "<resumed-sso-session>"


def load_realm() -> dict[str, Any]:
    realm: dict[str, Any] = json.loads(REALM.read_text(encoding="utf-8"))
    return realm


def references(realm: Mapping[str, Any]) -> dict[str, str]:
    """authenticator id -> the amr reference its execution is tagged with."""
    configs = {c["alias"]: c.get("config", {}) for c in realm.get("authenticatorConfig", [])}
    tagged: dict[str, str] = {}
    for flow in realm.get("authenticationFlows", []):
        for execution in flow["authenticationExecutions"]:
            config = configs.get(execution.get("authenticatorConfig", ""), {})
            if "default.reference.value" in config:
                tagged[execution["authenticator"]] = config["default.reference.value"]
    return tagged


def outcomes(realm: Mapping[str, Any], alias: str) -> list[frozenset[str]]:
    """Every set of amr references one successful pass through ``alias`` can
    complete, under Keycloak's requirement rules: REQUIRED all run;
    CONDITIONAL may be skipped; ALTERNATIVE, one of them, and only on a level
    with nothing REQUIRED or CONDITIONAL (Keycloak ignores them otherwise);
    DISABLED never runs. The cookie resumes a session and is marked so."""
    flows = {flow["alias"]: flow for flow in realm.get("authenticationFlows", [])}
    configs = {c["alias"]: c.get("config", {}) for c in realm.get("authenticatorConfig", [])}
    executions = sorted(flows[alias]["authenticationExecutions"], key=lambda e: e["priority"])

    def contributions(execution: Mapping[str, Any]) -> list[frozenset[str]]:
        if execution.get("authenticatorFlow"):
            return outcomes(realm, execution["flowAlias"])
        if execution["authenticator"] == "auth-cookie":
            return [frozenset({RESUMED})]
        config = configs.get(execution.get("authenticatorConfig", ""), {})
        reference = config.get("default.reference.value")
        return [frozenset({reference}) if reference else frozenset()]

    mandatory = [e for e in executions if e["requirement"] in {"REQUIRED", "CONDITIONAL"}]
    if mandatory:
        results = [frozenset[str]()]
        for execution in mandatory:
            options = contributions(execution)
            if execution["requirement"] == "CONDITIONAL":
                options = [*options, frozenset()]
            results = [done | option for done in results for option in options]
        return results
    return [o for e in executions if e["requirement"] == "ALTERNATIVE" for o in contributions(e)]


def second_factor_violations(realm: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    browser = realm.get("browserFlow")
    if browser not in {flow["alias"] for flow in realm.get("authenticationFlows", [])}:
        return [f"browserFlow {browser!r} is not a committed flow"]
    fresh = [o for o in outcomes(realm, browser) if RESUMED not in o]
    if not fresh:
        violations.append("no fresh login path")
    for outcome in fresh:
        if AMR_FIRST_FACTOR not in outcome or not outcome & {AMR_OTP, AMR_WEBAUTHN}:
            violations.append(f"a fresh login completes only {sorted(outcome)}")
    # WebAuthn must stay reachable: without it no patient-content role could
    # ever log in. OTP must not be, until the owner decides INT-389 (#644): the
    # console refuses a TOTP token today (INT-378's aaguid rule), and an OTP
    # ALTERNATIVE beside WebAuthn refused every new staff user (INT-550,
    # tests/admin/test_staff_passkey_enrolment.py). §2.3 is met: WebAuthn is MFA.
    offered = frozenset().union(*fresh) & {AMR_OTP, AMR_WEBAUTHN}
    if offered != {AMR_WEBAUTHN}:
        violations.append(f"the browser flow offers {sorted(offered)} as a second factor")
    expected = {
        "auth-username-password-form": AMR_FIRST_FACTOR,
        "auth-otp-form": AMR_OTP,
        # INT-378: the stock WebAuthn authenticator plus the aaguid/credential_id notes
        "intake-webauthn-session-notes": AMR_WEBAUTHN,
    }
    if references(realm) != expected:
        violations.append(f"references {references(realm)} != {expected}")
    for client in realm.get("clients", []):
        if client.get("directAccessGrantsEnabled") or client.get("implicitFlowEnabled"):
            violations.append(f"{client['clientId']} can obtain a token outside the browser flow")
        if client.get("authenticationFlowBindingOverrides"):
            violations.append(f"{client['clientId']} overrides the browser flow")
    return violations


class TestRealmSecondFactor:
    def test_the_committed_realm_has_no_violation(self) -> None:
        assert second_factor_violations(load_realm()) == []

    def test_otp_policy(self) -> None:
        realm = load_realm()
        assert realm["otpPolicyType"] == "totp"
        assert realm["otpPolicyAlgorithm"] in {"HmacSHA1", "HmacSHA256", "HmacSHA512"}
        assert realm["otpPolicyDigits"] >= 6
        assert 0 < realm["otpPolicyPeriod"] <= 30
        assert realm["otpPolicyLookAheadWindow"] <= 1
        assert realm["otpPolicyCodeReusable"] is False

    def test_webauthn_policy(self) -> None:
        realm = load_realm()
        assert realm["webAuthnPolicyRpEntityName"]
        algorithms = realm["webAuthnPolicySignatureAlgorithms"]
        assert algorithms and "RS1" not in algorithms  # RS1 is RSASSA with SHA-1
        # user verification makes the key a factor of its own, not bare possession
        assert realm["webAuthnPolicyUserVerificationRequirement"] == "required"

    def test_the_console_client_emits_amr_into_the_access_token(self) -> None:
        clients = {client["clientId"]: client for client in load_realm()["clients"]}
        mappers = [
            mapper
            for mapper in clients["admin-web"].get("protocolMappers", [])
            if mapper["protocolMapper"] == "oidc-amr-mapper"
        ]
        assert len(mappers) == 1
        assert mappers[0]["config"]["access.token.claim"] == "true"

    def test_recorded_claims_use_only_the_realm_references(self) -> None:
        issued = set(references(load_realm()).values())
        for token, claims in recorded_claims().items():
            assert set(claims["amr"]) <= issued, token

    @pytest.mark.parametrize(
        ("path", "value"),
        [
            (("staff second factor", 0, "requirement"), "DISABLED"),
            # INT-550: OTP switched on beside WebAuthn (INT-389 not decided)
            (("staff second factor", 1, "requirement"), "REQUIRED"),
            (("staff browser forms", 1, "requirement"), "CONDITIONAL"),
            (("staff browser forms", 1, "requirement"), "DISABLED"),
            (("staff browser forms", 0, "requirement"), "DISABLED"),
            (("staff second factor", 0, "authenticator"), "auth-username-password-form"),
        ],
        ids=repr,
    )
    def test_near_miss_a_bypassed_factor_is_caught(
        self, path: tuple[str, int, str], value: str
    ) -> None:
        realm = load_realm()
        flow_alias, index, field = path
        flow = next(f for f in realm["authenticationFlows"] if f["alias"] == flow_alias)
        ordered = sorted(flow["authenticationExecutions"], key=lambda e: e["priority"])
        ordered[index][field] = value
        assert second_factor_violations(realm)

    def test_near_miss_a_renamed_reference_is_caught(self) -> None:
        realm = load_realm()
        for config in realm["authenticatorConfig"]:
            if config["config"].get("default.reference.value") == AMR_WEBAUTHN:
                config["config"]["default.reference.value"] = "webauthn"
        assert second_factor_violations(realm)

    def test_near_miss_a_direct_grant_client_is_caught(self) -> None:
        realm = load_realm()
        realm["clients"][1]["directAccessGrantsEnabled"] = True
        assert second_factor_violations(realm)


# --------------------------------------------------------------------------
# 4. the committed realm: session bounds
# --------------------------------------------------------------------------


def session_violations(realm: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []

    def bounded(name: str, ceiling: int, *, zero_inherits: bool = False) -> None:
        value = realm.get(name, 0 if zero_inherits else None)
        floor = 0 if zero_inherits else 1
        if not isinstance(value, int) or isinstance(value, bool) or not floor <= value <= ceiling:
            violations.append(f"{name}={value!r} outside [{floor}, {ceiling}]")

    bounded("ssoSessionMaxLifespan", MAX_SESSION_S)
    bounded("ssoSessionIdleTimeout", IDLE_S)
    bounded("offlineSessionMaxLifespan", MAX_SESSION_S)
    bounded("offlineSessionIdleTimeout", IDLE_S)
    bounded("clientSessionMaxLifespan", MAX_SESSION_S, zero_inherits=True)
    bounded("clientSessionIdleTimeout", IDLE_S, zero_inherits=True)
    if realm.get("offlineSessionMaxLifespanEnabled") is not True:
        violations.append("offline sessions carry no max lifespan")
    if realm.get("rememberMe") is not False:
        violations.append("remember-me would stretch the session past the bound")
    ceilings = {
        "client.session.max.lifespan": MAX_SESSION_S,
        "client.offline.session.max.lifespan": MAX_SESSION_S,
        "client.session.idle.timeout": IDLE_S,
        "client.offline.session.idle.timeout": IDLE_S,
    }
    for client in realm.get("clients", []):
        for key, ceiling in ceilings.items():
            raw = client.get("attributes", {}).get(key)
            if raw is not None and not 0 <= int(raw) <= ceiling:
                violations.append(f"{client['clientId']} {key}={raw}")
    sso_max = realm.get("ssoSessionMaxLifespan", 0)
    for config in realm.get("authenticatorConfig", []):
        if "default.reference.value" in config.get("config", {}):
            # 0 would drop the amr value a second after login (Keycloak
            # AmrUtils.isAmrValid); longer than the session would outlive it
            age = int(config["config"].get("default.reference.maxAge", "0"))
            if not 0 < age <= sso_max:
                violations.append(f"{config['alias']} maxAge={age}")
    return violations


class TestRealmSessionBounds:
    def test_the_committed_realm_has_no_violation(self) -> None:
        assert session_violations(load_realm()) == []

    def test_the_values_asserted(self) -> None:
        realm = load_realm()
        assert realm["ssoSessionMaxLifespan"] <= 28800
        assert realm["ssoSessionIdleTimeout"] <= 1800
        assert realm["offlineSessionMaxLifespan"] <= 28800
        assert realm["offlineSessionIdleTimeout"] <= 1800

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("ssoSessionMaxLifespan", MAX_SESSION_S + 1),
            ("ssoSessionIdleTimeout", IDLE_S + 1),
            ("ssoSessionIdleTimeout", 0),
            ("offlineSessionIdleTimeout", 2592000),
            ("offlineSessionMaxLifespanEnabled", False),
            ("clientSessionIdleTimeout", IDLE_S + 1),
            ("rememberMe", True),
        ],
        ids=repr,
    )
    def test_near_miss_one_value_over_is_caught(self, key: str, value: object) -> None:
        realm = load_realm()
        realm[key] = value
        assert session_violations(realm)

    def test_near_miss_a_client_override_is_caught(self) -> None:
        realm = load_realm()
        realm["clients"][1].setdefault("attributes", {})["client.session.idle.timeout"] = "3600"
        assert session_violations(realm)

    def test_near_miss_an_unbounded_amr_age_is_caught(self) -> None:
        realm = load_realm()
        realm["authenticatorConfig"][0]["config"]["default.reference.maxAge"] = "0"
        assert session_violations(realm)


class TestSpecAnchor:
    def test_files_08_still_states_the_bounds_this_file_enforces(self) -> None:
        text = SPEC.read_text(encoding="utf-8")
        section = text[text.index("### 2.3 MFA") : text.index("### 2.4 ")]
        assert "Session ≤ 8 h" in section
        assert "30-minute idle timeout on any session that can reach PHI" in section
        assert "Phishing-resistant WebAuthn is mandatory" in section


# --------------------------------------------------------------------------
# 5. the credential id shape (INT-391)
# --------------------------------------------------------------------------
#
# WebAuthn Level 3 (https://www.w3.org/TR/webauthn-3/): §4 "Credential ID" is a
# byte sequence "at most 1023 bytes long", minted either as at least 16 random
# bytes or as an encrypted credential source; §3 "Base64url Encoding" is the
# RFC 4648 §5 alphabet with every trailing '=' omitted. The INT-378 provider
# writes the claim with Keycloak's Base64Url.encode, which is that encoding.
# RFC 4648 §3.5 has an encoder zero the pad bits, so each credential has one
# spelling, and four-eyes' "distinct credential" check, a string comparison,
# compares credentials.

MIN_ID_BYTES = 16
MAX_ID_BYTES = 1023
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

#: The id in INT-378's recorded Keycloak 26.1.4 login (PR #643), as the
#: provider wrote it.
PROVIDER_RECORDED = "Ts__QVS_6yVp0dtvsiJT9E9-WucmxlSxmy_ha1y4phY"

#: Characters outside RFC 4648 §5: the standard alphabet's two, padding,
#: separators the old id shape allowed, whitespace, and look-alikes.
OUTSIDE = ["+", "/", "=", ".", ":", "@", "~", "%", " ", "\t", "\n", "\x00", "ı", " ", "Ａ", "٣"]


def b64url(raw: bytes) -> str:
    """§3's Base64url Encoding, written out apart from the console's code."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def sample(size: int, lead: int = 0x00) -> bytes:
    """``size`` bytes starting with ``lead``: 0x00 encodes to 'A', 0xF8 to
    '-', 0xFC to '_'."""
    return bytes([lead, *((7 * i + 1) % 256 for i in range(size - 1))])[:size]


def with_id(value: object) -> dict[str, Any]:
    return account("clinical_lead", credential_id=value)


def refused(value: object) -> None:
    with pytest.raises(MalformedClaims):
        resolve(with_id(value))


def webauthn_ids(
    min_size: int = MIN_ID_BYTES, max_size: int = MAX_ID_BYTES
) -> st.SearchStrategy[bytes]:
    return st.binary(min_size=min_size, max_size=max_size)


class TestCredentialIdShape:
    @given(raw=webauthn_ids())
    @settings(max_examples=300, deadline=None)
    def test_every_webauthn_credential_id_is_admitted(self, raw: bytes) -> None:
        value = b64url(raw)
        assert resolve(with_id(value)).credential_id == value

    @given(first=st.integers(0xF8, 0xFF), rest=webauthn_ids(min_size=15, max_size=1022))
    @settings(max_examples=200, deadline=None)
    def test_an_id_starting_with_dash_or_underscore_is_admitted(
        self, first: int, rest: bytes
    ) -> None:
        # the old shape wanted a letter or digit first, so about 2 random ids
        # in 64 were refused
        value = b64url(bytes([first]) + rest)
        assert value[0] in "-_"
        assert resolve(with_id(value)).credential_id == value

    @pytest.mark.parametrize("lead", [0x00, 0xF8, 0xFC], ids=["A", "dash", "underscore"])
    @pytest.mark.parametrize("size", [16, 17, 18, 95, 96, 97, 98, 1021, 1022, 1023])
    def test_the_boundaries_are_admitted(self, size: int, lead: int) -> None:
        # 96 bytes (128 characters) was the old ceiling; 97 was refused
        value = b64url(sample(size, lead))
        assert resolve(with_id(value)).credential_id == value

    def test_the_provider_recorded_id_is_admitted(self) -> None:
        assert len(base64.urlsafe_b64decode(PROVIDER_RECORDED + "=")) == 32
        assert resolve(with_id(PROVIDER_RECORDED)).credential_id == PROVIDER_RECORDED

    def test_every_recorded_account_carries_a_webauthn_credential_id(self) -> None:
        for token, claims in recorded_claims().items():
            value = claims["credential_id"]
            raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            assert b64url(raw) == value, token
            assert MIN_ID_BYTES <= len(raw) <= MAX_ID_BYTES, token

    @given(raw=webauthn_ids().filter(lambda raw: len(raw) % 3 != 0))
    @settings(deadline=None)
    def test_near_miss_padding_is_refused(self, raw: bytes) -> None:
        padded = base64.urlsafe_b64encode(raw).decode("ascii")
        assert padded.endswith("=")
        refused(padded)

    @given(raw=webauthn_ids(), data=st.data())
    @settings(max_examples=300, deadline=None)
    def test_near_miss_one_character_outside_base64url_is_refused(
        self, raw: bytes, data: st.DataObject
    ) -> None:
        value = b64url(raw)
        at = data.draw(st.integers(0, len(value) - 1))
        refused(value[:at] + data.draw(st.sampled_from(OUTSIDE)) + value[at + 1 :])

    @given(first=st.integers(0xF8, 0xFF), rest=webauthn_ids(min_size=15, max_size=1022))
    @settings(deadline=None)
    def test_near_miss_the_standard_alphabet_is_refused(self, first: int, rest: bytes) -> None:
        # the ids that start with '-' or '_' in §3's alphabet start with '+'
        # or '/' in RFC 4648 §4's: the same bytes, spelled the other way
        standard = base64.b64encode(bytes([first]) + rest).decode("ascii").rstrip("=")
        assert standard[0] in "+/"
        refused(standard)

    @given(raw=webauthn_ids(min_size=0, max_size=MIN_ID_BYTES - 1))
    @settings(deadline=None)
    def test_near_miss_fewer_than_16_bytes_is_refused(self, raw: bytes) -> None:
        refused(b64url(raw))

    @given(raw=webauthn_ids(min_size=MAX_ID_BYTES + 1, max_size=MAX_ID_BYTES + 96))
    @settings(max_examples=50, deadline=None)
    def test_near_miss_more_than_1023_bytes_is_refused(self, raw: bytes) -> None:
        refused(b64url(raw))

    @pytest.mark.parametrize("size", [0, 15, 1024])
    @pytest.mark.parametrize("lead", [0x00, 0xFC], ids=["A", "underscore"])
    def test_near_miss_the_named_sizes_are_refused(self, size: int, lead: int) -> None:
        refused(b64url(sample(size, lead)))

    @given(raw=webauthn_ids().filter(lambda raw: len(raw) % 3 != 0), data=st.data())
    @settings(deadline=None)
    def test_near_miss_a_second_spelling_of_the_same_bytes_is_refused(
        self, raw: bytes, data: st.DataObject
    ) -> None:
        # the last character carries 2 or 4 pad bits; a lenient decoder
        # ignores them, so setting one spells the same credential again
        value = b64url(raw)
        pad_bits = 4 if len(raw) % 3 == 1 else 2
        flip = data.draw(st.integers(1, 2**pad_bits - 1))
        twin = value[:-1] + ALPHABET[ALPHABET.index(value[-1]) | flip]
        assert base64.urlsafe_b64decode(twin + "=" * (-len(twin) % 4)) == raw
        refused(twin)

    @given(
        raw=webauthn_ids().filter(lambda raw: len(raw) % 3 == 0),
        extra=st.sampled_from(ALPHABET),
    )
    @settings(deadline=None)
    def test_near_miss_a_dangling_character_is_refused(self, raw: bytes, extra: str) -> None:
        # 4n+1 characters decode to no byte sequence at all
        refused(b64url(raw) + extra)

    @pytest.mark.parametrize("value", [None, 0, 12345, True, b"A" * 22, ["A" * 22], {}], ids=repr)
    def test_near_miss_a_value_that_is_not_a_string_is_refused(self, value: object) -> None:
        refused(value)

    def test_near_miss_an_absent_claim_is_refused(self) -> None:
        claims = with_id(None)
        del claims["credential_id"]
        with pytest.raises(MalformedClaims):
            resolve(claims)

    def test_the_refusal_names_the_claim_and_never_the_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        value = base64.urlsafe_b64encode(sample(1024, 0xFC)).decode("ascii")
        with pytest.raises(MalformedClaims) as refusal:
            resolve(with_id(value))
        assert "credential_id" in str(refusal.value)
        for text in (str(refusal.value), repr(refusal.value), caplog.text):
            assert value[:22] not in text

    @given(uuid=st.uuids())
    @settings(deadline=None)
    def test_the_aaguid_the_provider_writes_is_still_admitted(self, uuid: Any) -> None:
        # INT-378: the provider writes the stored AAGUID as UUID text
        # (webauthn4j's AAGUID.toString()). INT-391 leaves its shape alone.
        text = str(uuid)
        assert resolve(account("clinical_lead", aaguid=text)).authenticator_aaguid == text


# --------------------------------------------------------------------------
# 5b. the credential id shape as the console serves and audits it
# --------------------------------------------------------------------------

LONGEST_DASH = b64url(sample(MAX_ID_BYTES, 0xF8))
MALFORMED_IDS: dict[str, object] = {
    "padded": base64.urlsafe_b64encode(sample(MIN_ID_BYTES, 0xFC)).decode("ascii"),
    "standard_alphabet": base64.b64encode(sample(MAX_ID_BYTES, 0xFC)).decode("ascii"),
    "too_long": b64url(sample(MAX_ID_BYTES + 1, 0xF8)),
    "too_short": b64url(sample(MIN_ID_BYTES - 1, 0xF8)),
    "not_a_string": 1023,
}
ID_ACCOUNTS: dict[str, dict[str, Any]] = {
    "id:longest_dash": account("clinical_lead", credential_id=LONGEST_DASH),
    **{
        f"id:{name}": account("clinical_lead", credential_id=v) for name, v in MALFORMED_IDS.items()
    },
}


@pytest.fixture()
def id_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    wiring = AdminWiring(
        claims=RecordedClaimsVerifier({**recorded_claims(), **ID_ACCOUNTS}),
        ip_allowlist=IpAllowList.from_spec(ALLOWED_CIDRS),
        deployments=dict(TEST_DEPLOYMENTS),
    )
    yield from build_admin_harness(tmp_path, admin=wiring)


class TestConsoleCredentialId:
    def test_a_1023_byte_id_starting_with_dash_reaches_the_console(
        self, id_harness: ApiHarness
    ) -> None:
        assert LONGEST_DASH.startswith("-") and len(LONGEST_DASH) == 1364
        response = whoami(id_harness, "id:longest_dash")
        assert response.status_code == 200
        assert response.json()["subject"] == "kc-sub-clinical-lead"

    def test_a_malformed_id_is_one_generic_403_that_never_echoes_it(
        self, id_harness: ApiHarness, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        before = len(tuple(id_harness.audit_store.entries()))
        answers = {name: whoami(id_harness, f"id:{name}") for name in MALFORMED_IDS}
        appended = tuple(id_harness.audit_store.entries())[before:]
        for name, response in answers.items():
            assert (response.status_code, response.json()) == (403, {"error": "forbidden"}), name
        assert {entry.actor for entry in appended} == {"admin:unresolved"}
        audited = " ".join(
            " ".join((e.actor, e.action, e.resource_ref, e.consent_scope_ref)) for e in appended
        )
        for value in MALFORMED_IDS.values():
            if not isinstance(value, str):
                continue
            for text in (caplog.text, audited, *(r.text for r in answers.values())):
                assert value[:16] not in text
