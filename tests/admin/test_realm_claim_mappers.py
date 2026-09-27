"""INT-373 — the committed Keycloak realm emits the claims the console parses.

Found by INT-365 (PR #598). The console reads ``aud``, ``org``, ``tenant``,
``aaguid`` and ``credential_id`` from every staff token, but the committed realm
had no mapper for any of them. A real dev-realm token was therefore refused as
malformed, even with a valid ``amr``.

How this is tested without a Keycloak:

- **mapper → claim.** :mod:`keycloak_mappers` applies Keycloak 26.1.4's own
  mapper rules to the realm export. The user attributes and session notes it is
  given are the values of the recorded INT-180 claim set (``keycloak_claims.json``),
  so the minted claims must equal what that suite already drives through the console.
- **claim → console.** The minted claims are signed and sent through the real
  :class:`KeycloakClaimsVerifier` (``aud`` must name ``api``) and
  :func:`principal_from_claims`, with no stand-in for either.
- **a one-field mutation per mapper.** Each is applied to a copy of the realm,
  and the same test first proves the unmutated realm passes, so a mutation
  cannot pass vacuously.
- **who can write the claim.** ``org`` and ``tenant`` come from user attributes,
  so the realm's user profile must let an administrator, and only an
  administrator, set them. If a staff member could edit ``tenant``, the token
  would move them to another tenant.
- **the runbook.** ``docs/runbooks/keycloak-realm.md`` lists the same mappers
  for the owner to apply to the deployed realm, and it cannot drift from the file.

``aaguid`` and ``credential_id`` read user-session notes. No stock Keycloak
26.1.4 authenticator writes those notes, as the evidence cites from the source.
Until the provider the runbook specifies is installed, a real token carries
neither claim and the console refuses it. That is the fail-closed direction.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from admin_harness import recorded_claims
from intake_platform.admin.principal import (
    _ID_SHAPE,
    ClaimsRejected,
    MalformedClaims,
    principal_from_claims,
)
from keycloak_mappers import (
    AUDIENCE_MAPPER,
    NOTE_MAPPER,
    USER_ATTRIBUTE_MAPPER,
    client,
    mint_access_token_claims,
)
from test_oidc_verifier import token, verifier

REPO = Path(__file__).resolve().parents[2]
REALM_PATH = REPO / "infra" / "keycloak" / "dev-realm.json"
RUNBOOK = REPO / "docs" / "runbooks" / "keycloak-realm.md"

CONSOLE_CLIENT = "admin-web"
#: The value INTAKE_ADMIN_OIDC_AUDIENCE takes: the bearer-only resource server.
AUDIENCE = "api"
#: The user-session notes the WebAuthn provider writes (runbook §3).
AAGUID_NOTE = "intake.webauthn.aaguid"
CREDENTIAL_NOTE = "intake.webauthn.credential_id"
#: The five claims this issue owns; everything else comes from built-in scopes.
MAPPED = ("aud", "org", "tenant", "aaguid", "credential_id")
SOURCE_IP = "192.0.2.10"
UP_COMPONENT = "org.keycloak.userprofile.UserProfileProvider"


def _realm() -> dict[str, Any]:
    realm: dict[str, Any] = json.loads(REALM_PATH.read_text(encoding="utf-8"))
    return realm


def _mapper(realm: Mapping[str, Any], claim: str) -> dict[str, Any]:
    """The admin-web mapper that produces ``claim`` — exactly one."""
    found = [
        m
        for m in client(realm, CONSOLE_CLIENT).get("protocolMappers", [])
        if m.get("config", {}).get("claim.name") == claim
        or (claim == "aud" and m.get("protocolMapper") == AUDIENCE_MAPPER)
    ]
    assert len(found) == 1, f"admin-web has {len(found)} mappers for {claim!r}"
    return found[0]


def _inputs(
    account: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, str]]:
    """Split a recorded claim set into what Keycloak is given and what it adds."""
    base = {k: v for k, v in account.items() if k not in MAPPED}
    attributes = {"org": [account["org"]]}
    if account["tenant"] is not None:
        attributes["tenant"] = [account["tenant"]]
    notes = {AAGUID_NOTE: account["aaguid"], CREDENTIAL_NOTE: account["credential_id"]}
    return base, attributes, notes


def _mint(realm: Mapping[str, Any], account: Mapping[str, Any]) -> dict[str, Any]:
    base, attributes, notes = _inputs(account)
    return mint_access_token_claims(
        realm, CONSOLE_CLIENT, base=base, user_attributes=attributes, session_notes=notes
    )


def _admit(claims: Mapping[str, Any]) -> Any:
    """Sign, verify with audience ``api``, and resolve the console principal."""
    verified = verifier().verify(token(claims))
    return principal_from_claims(verified, source_ip=SOURCE_IP)


ACCOUNTS = recorded_claims()
#: One tenant-scoped and one platform-scoped (tenant: null) account.
TENANT_ACCOUNT = "kc:tenant_admin"
PLATFORM_ACCOUNT = "kc:platform_owner"


def _live(account: Mapping[str, Any]) -> dict[str, Any]:
    """A recorded account with a token lifetime around the verifier's clock."""
    fresh = dict(account)
    fresh.update({"exp": 1_800_000_600, "nbf": 1_799_999_990})
    return fresh


# ----------------------------------------------------------------------- mapper → claim


class TestTheRealmMintsTheConsoleClaims:
    @pytest.mark.parametrize("name", sorted(ACCOUNTS))
    def test_each_recorded_account_is_reproduced_from_the_realm(self, name: str) -> None:
        account = ACCOUNTS[name]
        minted = _mint(_realm(), account)
        for claim in ("aud", "org", "aaguid", "credential_id"):
            assert minted[claim] == account[claim], claim
        # tenant: null in the recording is "no claim" in a token, which the
        # parser reads as the same thing
        assert minted.get("tenant") == account["tenant"]

    @pytest.mark.parametrize("name", [TENANT_ACCOUNT, PLATFORM_ACCOUNT])
    def test_the_minted_token_is_admitted_with_each_claim(self, name: str) -> None:
        account = _live(ACCOUNTS[name])
        principal = _admit(_mint(_realm(), account))
        assert principal.org == account["org"]
        assert principal.tenant == account["tenant"]
        assert principal.authenticator_aaguid == account["aaguid"]
        assert principal.credential_id == account["credential_id"]

    def test_a_realistic_audience_list_is_admitted(self) -> None:
        # the default `roles` scope's "audience resolve" mapper adds `account`
        # for a user holding account-client roles; `aud` is then an array
        claims = _mint(_realm(), _live(ACCOUNTS[TENANT_ACCOUNT]))
        claims["aud"] = [claims["aud"], "account"]
        assert _admit(claims).org == ACCOUNTS[TENANT_ACCOUNT]["org"]

    def test_mapped_claims_reach_the_access_token_only_where_the_console_reads(self) -> None:
        realm = _realm()
        expected_type = {
            "aud": AUDIENCE_MAPPER,
            "org": USER_ATTRIBUTE_MAPPER,
            "tenant": USER_ATTRIBUTE_MAPPER,
            "aaguid": NOTE_MAPPER,
            "credential_id": NOTE_MAPPER,
        }
        for claim in MAPPED:
            mapper = _mapper(realm, claim)
            assert mapper["protocolMapper"] == expected_type[claim], claim
            config = mapper["config"]
            assert config["access.token.claim"] == "true", claim
            # the console reads the access token; the ID token goes to the
            # browser and needs none of these
            assert config.get("id.token.claim", "false") == "false", claim

    def test_the_audience_names_a_client_the_realm_declares(self) -> None:
        realm = _realm()
        config = _mapper(realm, "aud")["config"]
        assert config["included.client.audience"] == AUDIENCE
        assert client(realm, AUDIENCE)["bearerOnly"] is True


# ----------------------------------------------------------- one-field mutations


def _set(claim: str, key: str, value: str) -> Callable[[dict[str, Any]], None]:
    def mutate(realm: dict[str, Any]) -> None:
        _mapper(realm, claim)["config"][key] = value

    return mutate


#: (mutation, the refusal it must cause). Two per mapper.
MUTATIONS: dict[str, tuple[Callable[[dict[str, Any]], None], type[Exception]]] = {
    "aud-names-the-console-client": (
        _set("aud", "included.client.audience", CONSOLE_CLIENT),
        ClaimsRejected,
    ),
    "aud-off-the-access-token": (_set("aud", "access.token.claim", "false"), ClaimsRejected),
    "org-renamed-claim": (_set("org", "claim.name", "organisation"), MalformedClaims),
    "org-wrong-attribute": (_set("org", "user.attribute", "organisation"), MalformedClaims),
    "org-multivalued": (_set("org", "multivalued", "true"), MalformedClaims),
    "tenant-multivalued": (_set("tenant", "multivalued", "true"), MalformedClaims),
    "aaguid-wrong-note": (_set("aaguid", "user.session.note", "webauthn.aaguid"), MalformedClaims),
    "aaguid-nested-claim": (_set("aaguid", "claim.name", "webauthn.aaguid"), MalformedClaims),
    "credential-id-wrong-note": (
        _set("credential_id", "user.session.note", "credential_id"),
        MalformedClaims,
    ),
    "credential-id-off-the-access-token": (
        _set("credential_id", "access.token.claim", "false"),
        MalformedClaims,
    ),
}


class TestOneFieldMutations:
    @pytest.mark.parametrize("name", sorted(MUTATIONS))
    def test_each_mutation_is_refused_and_the_realm_is_not(self, name: str) -> None:
        account = _live(ACCOUNTS[TENANT_ACCOUNT])
        realm = _realm()
        # near-miss control first: the committed realm is admitted
        assert _admit(_mint(realm, account)).org == account["org"]
        mutate, refusal = MUTATIONS[name]
        mutated = copy.deepcopy(realm)
        mutate(mutated)
        with pytest.raises(refusal):
            _admit(_mint(mutated, account))

    @pytest.mark.parametrize(
        "mutation",
        [
            _set("tenant", "claim.name", "tenant_id"),
            _set("tenant", "user.attribute", "tenant_id"),
        ],
        ids=["tenant-renamed-claim", "tenant-wrong-attribute"],
    )
    def test_a_lost_tenant_claim_is_caught_before_it_widens_scope(
        self, mutation: Callable[[dict[str, Any]], None]
    ) -> None:
        # `tenant` is optional to the parser (platform roles carry none), so a
        # lost claim is admitted with no tenant. That is why the test pins the
        # value rather than a refusal.
        account = _live(ACCOUNTS[TENANT_ACCOUNT])
        assert _admit(_mint(_realm(), account)).tenant == account["tenant"]
        mutated = _realm()
        mutation(mutated)
        assert _admit(_mint(mutated, account)).tenant is None

    def test_without_the_webauthn_notes_the_token_is_refused(self) -> None:
        """What a stock Keycloak issues today: no provider writes the notes."""
        account = _live(ACCOUNTS[TENANT_ACCOUNT])
        base, attributes, _ = _inputs(account)
        claims = mint_access_token_claims(
            _realm(), CONSOLE_CLIENT, base=base, user_attributes=attributes, session_notes={}
        )
        assert "aaguid" not in claims and "credential_id" not in claims
        with pytest.raises(MalformedClaims):
            _admit(claims)


# ------------------------------------------------------------ who writes org/tenant


def _user_profile(realm: Mapping[str, Any]) -> dict[str, Any]:
    components = realm.get("components", {}).get(UP_COMPONENT, [])
    assert len(components) == 1, "the realm must declare exactly one user profile"
    raw = components[0]["config"]["kc.user.profile.config"]
    assert isinstance(raw, list) and len(raw) == 1
    profile: dict[str, Any] = json.loads(raw[0])
    return profile


def profile_violations(profile: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    if profile.get("unmanagedAttributePolicy", "DISABLED") == "ENABLED":
        found.append("unmanaged attributes are user-editable")
    attributes = {a["name"]: a for a in profile.get("attributes", [])}
    for name in ("org", "tenant"):
        attribute = attributes.get(name)
        if attribute is None:
            found.append(f"{name}: not declared")
            continue
        permissions = attribute.get("permissions", {})
        if permissions.get("edit") != ["admin"]:
            found.append(f"{name}: edit is not admin-only")
        if permissions.get("view") != ["admin"]:
            found.append(f"{name}: view is not admin-only")
        if attribute.get("multivalued", False):
            found.append(f"{name}: multivalued")
        pattern = attribute.get("validations", {}).get("pattern", {}).get("pattern")
        if pattern != f"^{_ID_SHAPE.pattern}$":
            found.append(f"{name}: pattern is not the console's id shape")
    return found


class TestOnlyAnAdministratorWritesOrgAndTenant:
    def test_the_committed_profile_has_no_violation(self) -> None:
        assert profile_violations(_user_profile(_realm())) == []

    def test_the_default_attributes_survive(self) -> None:
        names = {a["name"] for a in _user_profile(_realm())["attributes"]}
        assert {"username", "email", "firstName", "lastName"} <= names

    @pytest.mark.parametrize(
        ("mutate", "expected"),
        [
            (lambda p: p.update(unmanagedAttributePolicy="ENABLED"), "unmanaged"),
            (lambda p: _attr(p, "tenant")["permissions"].update(edit=["admin", "user"]), "tenant"),
            (lambda p: _attr(p, "org")["permissions"].update(view=["admin", "user"]), "org"),
            (lambda p: _attr(p, "org").update(multivalued=True), "org: multivalued"),
            (
                lambda p: _attr(p, "tenant")["validations"]["pattern"].update(pattern="^.*$"),
                "tenant: pattern",
            ),
            (lambda p: p["attributes"].remove(_attr(p, "org")), "org: not declared"),
        ],
        ids=["unmanaged", "tenant-self-edit", "org-self-view", "org-multi", "tenant-any", "no-org"],
    )
    def test_each_near_miss_is_a_violation(
        self, mutate: Callable[[dict[str, Any]], None], expected: str
    ) -> None:
        profile = _user_profile(_realm())
        mutate(profile)
        assert any(expected in v for v in profile_violations(profile))


def _attr(profile: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(a for a in profile["attributes"] if a["name"] == name)
    return found


# ----------------------------------------------------------------------- the runbook


def _row_for(text: str, mapper: Mapping[str, Any]) -> str | None:
    config = mapper["config"]
    source = (
        config.get("included.client.audience")
        or config.get("user.attribute")
        or config.get("user.session.note")
    )
    for line in text.splitlines():
        cells = [c.strip().strip("`") for c in line.split("|")]
        if mapper["name"] in cells and mapper["protocolMapper"] in cells and source in cells:
            return line
    return None


class TestTheRunbookListsTheSameMappers:
    @pytest.mark.parametrize("claim", MAPPED)
    def test_every_mapper_has_a_row(self, claim: str) -> None:
        mapper = _mapper(_realm(), claim)
        assert _row_for(RUNBOOK.read_text(encoding="utf-8"), mapper), (
            f"docs/runbooks/keycloak-realm.md has no row for the {mapper['name']!r} mapper"
        )

    def test_a_renamed_note_is_drift(self) -> None:
        mapper = copy.deepcopy(_mapper(_realm(), "aaguid"))
        mapper["config"]["user.session.note"] = "webauthn.aaguid"
        assert _row_for(RUNBOOK.read_text(encoding="utf-8"), mapper) is None

    def test_the_runbook_names_the_provider_contract(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        for note in (AAGUID_NOTE, CREDENTIAL_NOTE):
            assert re.search(rf"`{re.escape(note)}`", text), note
        assert _ID_SHAPE.pattern in text
