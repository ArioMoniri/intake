"""INT-390 — the committed Keycloak realm fits the columns its import writes.

``make obs`` starts Keycloak with ``start-dev --import-realm``, which writes
``infra/keycloak/dev-realm.json`` into Keycloak's JPA schema. A value longer than its column
aborts the import, and the server does not start. INT-365's ``staff browser`` flow description
was 271 characters against an NVARCHAR(255) column, so the realm on ``main`` had never imported
on a real Keycloak (found by INT-378, PR #643).

**Where the limits come from.** They are Keycloak 26.7.4's, the version compose pins. Each was
derived by replaying the Liquibase changelogs in ``model/jpa/src/main/resources/META-INF/`` at
tag 26.7.4 (commit ``aa9fe3fba0c6cd5770f19a49378c55f4378cf544``) in ``jpa-changelog-master.xml``
order. Each limit cites, as ``file:line``, the change that gives the column its final type on a
database with no vendor-specific override (H2, PostgreSQL). The tag's 78 changelog files are
byte-identical to the ones inside the 26.7.4 distribution's
``org.keycloak.keycloak-model-jpa-26.7.4.jar`` (docs/evidence/INT-390.md). One limit is new on
this version: 26.7.0 moved the realm display name out of ``REALM_ATTRIBUTE`` (NCLOB) into
``REALM.DISPLAY_NAME``, which is NVARCHAR(255).

Pinned here:

- every string the realm carries maps to a known column, or is named as never stored as text
  (resolved to an id, stored as an enum ordinal, or hashed). A field nobody classified fails,
  so a new field cannot slip past the limits;
- every mapped value fits its column, measured in UTF-16 code units (Java's ``String.length``,
  never fewer than characters);
- compose runs Keycloak 26.7.4 pinned by index digest, the version these limits are for, and no
  tracked file outside the dated records names another Keycloak image;
- compose mounts the realm into the import directory as ``intake-dev-realm.json``. Since 26.2.0
  the directory import refuses a file not named after the realm inside it, so the old
  ``dev-realm.json`` target stopped the 26.7.4 server before it read a single column.

Each check is a function that returns violations. It runs once on the committed realm, which
must give none, and once on a near-miss, which must give some.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
REALM_PATH = REPO / "infra" / "keycloak" / "dev-realm.json"
COMPOSE_PATH = REPO / "infra" / "docker-compose.obs.yml"

#: GitHub release 26.7.4 (16 Sep 2026), the newest 26.x.
KEYCLOAK_VERSION = "26.7.4"
#: The multi-arch OCI index the registry serves for tag 26.7.4 (amd64, arm64, ppc64le).
KEYCLOAK_INDEX_DIGEST = "sha256:82a77884f3af238beab1e7afd63b5f530e1b5c0590bd7aa60b40a40463e29b2c"
#: Assembled from parts, so the scan below never finds a reference in this file.
KEYCLOAK_REPOSITORY = "/".join(("quay.io", "keycloak", "keycloak"))
KEYCLOAK_IMAGE = f"{KEYCLOAK_REPOSITORY}:{KEYCLOAK_VERSION}@{KEYCLOAK_INDEX_DIGEST}"
IMAGE_SHAPE = re.compile(rf"^{re.escape(KEYCLOAK_REPOSITORY)}:\d+\.\d+\.\d+@sha256:[0-9a-f]{{64}}$")

#: Records, not configuration: dated evidence, the iteration log and the backlog quote
#: versions as history. Nothing pulls from them.
HISTORICAL_PREFIXES = (
    "docs/evidence/",
    "docs/PROGRESS.md",
    "docs/backlog/",
    "files/11_ISSUE_BACKLOG.md",
)
#: A Keycloak image reference: the repository, then a tag or digest, up to whitespace, a
#: quote, a backtick, a comma or a closing bracket.
IMAGE_REFERENCE = re.compile(rf"{re.escape(KEYCLOAK_REPOSITORY)}[:@][^\s\"'`,)\]]*")


@dataclass(frozen=True)
class Column:
    """A column the realm import writes. ``limit`` is None for a CLOB/NCLOB."""

    limit: int | None
    #: The changelog line, at the 26.7.4 tag, that gives the column its final type.
    source: str


COLUMNS: dict[str, Column] = {
    "REALM.NAME": Column(255, "jpa-changelog-1.0.0.Final.xml:164"),
    "REALM.DISPLAY_NAME": Column(255, "jpa-changelog-26.7.0.xml:34"),
    "REALM.SSL_REQUIRED": Column(255, "jpa-changelog-1.0.0.Final.xml:184"),
    "REALM.OTP_POLICY_TYPE": Column(36, "jpa-changelog-1.5.0.xml:62"),
    "REALM.OTP_POLICY_ALG": Column(36, "jpa-changelog-1.5.0.xml:59"),
    "REALM_ATTRIBUTE.VALUE": Column(None, "jpa-changelog-13.0.0.xml:105"),
    "AUTHENTICATION_FLOW.ALIAS": Column(255, "jpa-changelog-1.3.0.xml:55"),
    "AUTHENTICATION_FLOW.DESCRIPTION": Column(255, "jpa-changelog-2.5.0.xml:74"),
    "AUTHENTICATION_FLOW.PROVIDER_ID": Column(36, "jpa-changelog-1.4.0.xml:47"),
    "AUTHENTICATION_EXECUTION.AUTHENTICATOR": Column(36, "jpa-changelog-1.3.0.xml:64"),
    "AUTHENTICATOR_CONFIG.ALIAS": Column(255, "jpa-changelog-1.3.0.xml:47"),
    "AUTHENTICATOR_CONFIG_ENTRY.NAME": Column(255, "jpa-changelog-1.3.0.xml:81"),
    "AUTHENTICATOR_CONFIG_ENTRY.VALUE": Column(None, "jpa-changelog-1.3.0.xml:80"),
    "KEYCLOAK_ROLE.NAME": Column(255, "jpa-changelog-2.5.0.xml:100"),
    "KEYCLOAK_ROLE.DESCRIPTION": Column(255, "jpa-changelog-2.5.0.xml:102"),
    "CLIENT.CLIENT_ID": Column(255, "jpa-changelog-1.2.0.CR1.xml:121"),
    "CLIENT.NAME": Column(255, "jpa-changelog-2.5.0.xml:79"),
    "CLIENT.DESCRIPTION": Column(255, "jpa-changelog-2.5.0.xml:78"),
    "CLIENT.PROTOCOL": Column(255, "jpa-changelog-1.1.0.Beta1.xml:57"),
    "CLIENT.ROOT_URL": Column(255, "jpa-changelog-1.6.1.xml:43"),
    "CLIENT.BASE_URL": Column(255, "jpa-changelog-1.0.0.Final.xml:59"),
    "CLIENT.MANAGEMENT_URL": Column(255, "jpa-changelog-1.0.0.Final.xml:63"),
    "CLIENT.CLIENT_AUTHENTICATOR_TYPE": Column(255, "jpa-changelog-1.5.0.xml:83"),
    "REALM_ENABLED_EVENT_TYPES.VALUE": Column(255, "jpa-changelog-3.4.0.xml:35"),
    "REDIRECT_URIS.VALUE": Column(255, "jpa-changelog-1.0.0.Final.xml:263"),
    "WEB_ORIGINS.VALUE": Column(255, "jpa-changelog-1.0.0.Final.xml:382"),
    "CLIENT_ATTRIBUTES.NAME": Column(255, "jpa-changelog-1.1.0.Beta1.xml:31"),
    "CLIENT_ATTRIBUTES.VALUE": Column(None, "jpa-changelog-20.0.0.xml:93"),
    "PROTOCOL_MAPPER.NAME": Column(255, "jpa-changelog-1.2.0.Beta1.xml:37"),
    "PROTOCOL_MAPPER.PROTOCOL": Column(255, "jpa-changelog-1.2.0.Beta1.xml:40"),
    "PROTOCOL_MAPPER.PROTOCOL_MAPPER_NAME": Column(255, "jpa-changelog-1.2.0.Beta1.xml:43"),
    "PROTOCOL_MAPPER_CONFIG.NAME": Column(255, "jpa-changelog-1.2.0.Beta1.xml:59"),
    "PROTOCOL_MAPPER_CONFIG.VALUE": Column(None, "jpa-changelog-1.2.0.Beta1.xml:58"),
    "COMPONENT.NAME": Column(255, "jpa-changelog-2.1.0.xml:174"),
    "COMPONENT.PROVIDER_ID": Column(36, "jpa-changelog-2.1.0.xml:176"),
    "COMPONENT.PROVIDER_TYPE": Column(255, "jpa-changelog-2.1.0.xml:177"),
    "COMPONENT.SUB_TYPE": Column(255, "jpa-changelog-2.3.0.xml:43"),
    "COMPONENT_CONFIG.NAME": Column(255, "jpa-changelog-2.1.0.xml:165"),
    "COMPONENT_CONFIG.VALUE": Column(None, "jpa-changelog-23.0.0.xml:31"),
    "USER_ENTITY.USERNAME": Column(255, "jpa-changelog-2.5.0.xml:84"),
    "USER_ENTITY.EMAIL": Column(255, "jpa-changelog-1.0.0.Final.xml:298"),
    "USER_ENTITY.FIRST_NAME": Column(255, "jpa-changelog-2.5.0.xml:82"),
    "USER_ENTITY.LAST_NAME": Column(255, "jpa-changelog-2.5.0.xml:83"),
    "USER_ATTRIBUTE.NAME": Column(255, "jpa-changelog-1.0.0.Final.xml:286"),
    # UserAttributeEntity.setValue keeps a value of at most 255 in VALUE (NVARCHAR(255),
    # jpa-changelog-2.5.0.xml:94) and moves a longer one to LONG_VALUE, so no value is refused.
    "USER_ATTRIBUTE.LONG_VALUE": Column(None, "jpa-changelog-24.0.0.xml:24"),
    "CREDENTIAL.TYPE": Column(255, "jpa-changelog-1.0.0.Final.xml:106"),
    "CREDENTIAL.USER_LABEL": Column(255, "jpa-changelog-8.0.0.xml:25"),
}

#: Realm field (list items as ``[]``; a map's keys as ``{}``, its values as ``.*``) -> column.
FIELDS: dict[str, str] = {
    "realm": "REALM.NAME",
    "displayName": "REALM.DISPLAY_NAME",
    "sslRequired": "REALM.SSL_REQUIRED",
    "otpPolicyType": "REALM.OTP_POLICY_TYPE",
    "otpPolicyAlgorithm": "REALM.OTP_POLICY_ALG",
    # INT-366 keeps LOGIN events for the 60-day access hygiene; one row per event type.
    "enabledEventTypes[]": "REALM_ENABLED_EVENT_TYPES.VALUE",
    # RealmAdapter.setWebAuthnPolicy stores each as a realm attribute (lists comma-joined).
    "webAuthnPolicyRpEntityName": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicyRpId": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicyAttestationConveyancePreference": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicyAuthenticatorAttachment": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicyRequireResidentKey": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicyUserVerificationRequirement": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicySignatureAlgorithms[]": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicyAcceptableAaguids[]": "REALM_ATTRIBUTE.VALUE",
    "webAuthnPolicyExtraOrigins[]": "REALM_ATTRIBUTE.VALUE",
    "authenticatorConfig[].alias": "AUTHENTICATOR_CONFIG.ALIAS",
    "authenticatorConfig[].config{}": "AUTHENTICATOR_CONFIG_ENTRY.NAME",
    "authenticatorConfig[].config.*": "AUTHENTICATOR_CONFIG_ENTRY.VALUE",
    "authenticationFlows[].alias": "AUTHENTICATION_FLOW.ALIAS",
    "authenticationFlows[].description": "AUTHENTICATION_FLOW.DESCRIPTION",
    "authenticationFlows[].providerId": "AUTHENTICATION_FLOW.PROVIDER_ID",
    "authenticationFlows[].authenticationExecutions[].authenticator": (
        "AUTHENTICATION_EXECUTION.AUTHENTICATOR"
    ),
    "roles.realm[].name": "KEYCLOAK_ROLE.NAME",
    "roles.realm[].description": "KEYCLOAK_ROLE.DESCRIPTION",
    "clients[].clientId": "CLIENT.CLIENT_ID",
    "clients[].name": "CLIENT.NAME",
    "clients[].description": "CLIENT.DESCRIPTION",
    "clients[].protocol": "CLIENT.PROTOCOL",
    "clients[].rootUrl": "CLIENT.ROOT_URL",
    "clients[].baseUrl": "CLIENT.BASE_URL",
    "clients[].adminUrl": "CLIENT.MANAGEMENT_URL",
    "clients[].clientAuthenticatorType": "CLIENT.CLIENT_AUTHENTICATOR_TYPE",
    "clients[].redirectUris[]": "REDIRECT_URIS.VALUE",
    "clients[].webOrigins[]": "WEB_ORIGINS.VALUE",
    "clients[].attributes{}": "CLIENT_ATTRIBUTES.NAME",
    "clients[].attributes.*": "CLIENT_ATTRIBUTES.VALUE",
    "clients[].protocolMappers[].name": "PROTOCOL_MAPPER.NAME",
    "clients[].protocolMappers[].protocol": "PROTOCOL_MAPPER.PROTOCOL",
    "clients[].protocolMappers[].protocolMapper": "PROTOCOL_MAPPER.PROTOCOL_MAPPER_NAME",
    "clients[].protocolMappers[].config{}": "PROTOCOL_MAPPER_CONFIG.NAME",
    "clients[].protocolMappers[].config.*": "PROTOCOL_MAPPER_CONFIG.VALUE",
    "components{}": "COMPONENT.PROVIDER_TYPE",
    "components.*[].name": "COMPONENT.NAME",
    "components.*[].providerId": "COMPONENT.PROVIDER_ID",
    "components.*[].subType": "COMPONENT.SUB_TYPE",
    "components.*[].config{}": "COMPONENT_CONFIG.NAME",
    "components.*[].config.*[]": "COMPONENT_CONFIG.VALUE",
    "users[].username": "USER_ENTITY.USERNAME",
    "users[].email": "USER_ENTITY.EMAIL",
    "users[].firstName": "USER_ENTITY.FIRST_NAME",
    "users[].lastName": "USER_ENTITY.LAST_NAME",
    "users[].attributes{}": "USER_ATTRIBUTE.NAME",
    "users[].attributes.*[]": "USER_ATTRIBUTE.LONG_VALUE",
    "users[].credentials[].type": "CREDENTIAL.TYPE",
    "users[].credentials[].userLabel": "CREDENTIAL.USER_LABEL",
}

#: Strings the import reads but never writes as text, and what it writes instead.
NOT_STORED: dict[str, str] = {
    "browserFlow": "resolved by alias; REALM.BROWSER_FLOW holds the flow id",
    "authenticationFlows[].authenticationExecutions[].flowAlias": "resolved to the flow id",
    "authenticationFlows[].authenticationExecutions[].authenticatorConfig": (
        "resolved to the AUTHENTICATOR_CONFIG id"
    ),
    "authenticationFlows[].authenticationExecutions[].requirement": "an enum, stored as INT",
    "users[].realmRoles[]": "resolved to the role id",
    # INT-563 review: the step-up client's one default scope, linked by id
    "clients[].defaultClientScopes[]": (
        "resolved by name; CLIENT_SCOPE_CLIENT holds the client scope id"
    ),
    "users[].credentials[].value": "hashed; the hash goes to CREDENTIAL.SECRET_DATA (CLOB)",
}

#: A map whose keys are data rather than field names: its keys land in a NAME column.
_KEYED_MAPS = frozenset({"config", "attributes"})


def load_realm() -> dict[str, Any]:
    realm: dict[str, Any] = json.loads(REALM_PATH.read_text(encoding="utf-8"))
    return realm


def utf16_units(text: str) -> int:
    """Java's ``String.length``: a character outside the BMP counts twice."""
    return len(text.encode("utf-16-le")) // 2


def strings(node: object, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string in ``node`` with its normalised field path."""
    if isinstance(node, dict):
        keyed = path == "components" or path.rsplit(".", 1)[-1] in _KEYED_MAPS
        for key, value in node.items():
            if keyed:
                yield f"{path}{{}}", key
                yield from strings(value, f"{path}.*")
            else:
                yield from strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for item in node:
            yield from strings(item, f"{path}[]")
    elif isinstance(node, str):
        yield path, node


def import_violations(realm: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    for path, text in strings(realm):
        if path in NOT_STORED:
            continue
        column_key = FIELDS.get(path)
        if column_key is None:
            violations.append(f"{path}: no known column; classify it in FIELDS or NOT_STORED")
            continue
        column = COLUMNS[column_key]
        if column.limit is not None and utf16_units(text) > column.limit:
            violations.append(
                f"{path}: {utf16_units(text)} UTF-16 units, but {column_key} holds "
                f"{column.limit} (Keycloak {KEYCLOAK_VERSION} {column.source})"
            )
    return violations


def _flow(realm: dict[str, Any], alias: str) -> dict[str, Any]:
    flow: dict[str, Any] = next(f for f in realm["authenticationFlows"] if f["alias"] == alias)
    return flow


# --------------------------------------------------------------------------
# 1. the committed realm fits
# --------------------------------------------------------------------------


class TestCommittedRealm:
    def test_every_string_fits_its_column(self) -> None:
        assert import_violations(load_realm()) == []

    def test_every_flow_role_and_client_description_is_at_most_255(self) -> None:
        realm = load_realm()
        described = [f.get("description", "") for f in realm["authenticationFlows"]]
        described += [r.get("description", "") for r in realm["roles"]["realm"]]
        described += [c.get("description", "") for c in realm["clients"]]
        assert max(utf16_units(text) for text in described) <= 255

    def test_the_realm_display_name_fits_the_column_26_7_0_added(self) -> None:
        assert COLUMNS["REALM.DISPLAY_NAME"] == Column(255, "jpa-changelog-26.7.0.xml:34")
        assert utf16_units(load_realm()["displayName"]) <= 255


# --------------------------------------------------------------------------
# 2. the checker bites: one value over, one field unclassified
# --------------------------------------------------------------------------


def _set_flow_description(text: str) -> Callable[[dict[str, Any]], None]:
    def mutate(realm: dict[str, Any]) -> None:
        _flow(realm, "staff browser")["description"] = text

    return mutate


def _set(path: tuple[str | int, ...], value: object) -> Callable[[dict[str, Any]], None]:
    def mutate(realm: dict[str, Any]) -> None:
        node: Any = realm
        for step in path[:-1]:
            node = node[step]
        node[path[-1]] = value

    return mutate


def _add_component(provider_id: str) -> Callable[[dict[str, Any]], None]:
    def mutate(realm: dict[str, Any]) -> None:
        realm["components"] = {
            "org.keycloak.userprofile.UserProfileProvider": [
                {"providerId": provider_id, "subComponents": {}, "config": {"k": ["v"]}}
            ]
        }

    return mutate


NEAR_MISSES: dict[str, Callable[[dict[str, Any]], None]] = {
    "flow description 256": _set_flow_description("x" * 256),
    "flow description 128 astral characters (256 UTF-16 units)": _set_flow_description(
        "\U0001d400" * 128
    ),
    "role description 256": _set(("roles", "realm", 0, "description"), "x" * 256),
    "client description 256": _set(("clients", 0, "description"), "x" * 256),
    "client name 256": _set(("clients", 0, "name"), "x" * 256),
    "display name 256": _set(("displayName",), "x" * 256),
    "otp algorithm 37": _set(("otpPolicyAlgorithm",), "x" * 37),
    "flow providerId 37": _set(("authenticationFlows", 0, "providerId"), "x" * 37),
    "execution authenticator 37": _set(
        ("authenticationFlows", 0, "authenticationExecutions", 0, "authenticator"), "x" * 37
    ),
    "redirect uri 256": _set(
        ("clients", 1, "redirectUris", 0), "http://localhost:3000/" + "x" * 234
    ),
    "username 256": _set(("users", 0, "username"), "dev-" + "x" * 252),
    "client attribute name 256": _set(("clients", 1, "attributes", "x" * 256), "v"),
    "component providerId 37": _add_component("x" * 37),
    "unclassified realm field": _set(("unmappedField",), "x"),
    "unclassified client field": _set(("clients", 0, "unmappedField"), "x"),
}


class TestNearMisses:
    @pytest.mark.parametrize("name", sorted(NEAR_MISSES))
    def test_the_mutation_is_caught(self, name: str) -> None:
        realm = copy.deepcopy(load_realm())
        NEAR_MISSES[name](realm)
        assert import_violations(realm), name

    def test_exactly_255_is_admitted_and_256_is_not(self) -> None:
        realm = copy.deepcopy(load_realm())
        _set_flow_description("x" * 255)(realm)
        assert import_violations(realm) == []
        _set_flow_description("x" * 256)(realm)
        assert import_violations(realm) == [
            "authenticationFlows[].description: 256 UTF-16 units, but "
            "AUTHENTICATION_FLOW.DESCRIPTION holds 255 (Keycloak 26.7.4 jpa-changelog-2.5.0.xml:74)"
        ]

    def test_a_long_value_in_an_unbounded_column_is_admitted(self) -> None:
        realm = copy.deepcopy(load_realm())
        _add_component("declarative-user-profile")(realm)
        realm["components"]["org.keycloak.userprofile.UserProfileProvider"][0]["config"]["k"] = [
            "x" * 5000
        ]
        realm["clients"][1].setdefault("attributes", {})["post.logout.redirect.uris"] = "x" * 5000
        assert import_violations(realm) == []

    def test_a_not_stored_string_is_not_measured(self) -> None:
        realm = copy.deepcopy(load_realm())
        realm["users"][0]["credentials"][0]["value"] = "dev-only-" + "x" * 300
        assert import_violations(realm) == []


# --------------------------------------------------------------------------
# 3. the tables are coherent
# --------------------------------------------------------------------------


class TestTables:
    def test_every_field_names_a_known_column(self) -> None:
        assert set(FIELDS.values()) <= set(COLUMNS)

    def test_no_field_is_both_stored_and_not_stored(self) -> None:
        assert not set(FIELDS) & set(NOT_STORED)

    def test_every_source_is_a_changelog_line(self) -> None:
        for key, column in COLUMNS.items():
            assert re.fullmatch(r"jpa-changelog-[0-9A-Za-z.-]+\.xml:\d+", column.source), key

    def test_every_committed_field_is_classified(self) -> None:
        # the walk reaches every string, and each one is either measured or named
        paths = {path for path, _ in strings(load_realm())}
        assert paths <= set(FIELDS) | set(NOT_STORED)
        assert "authenticationFlows[].description" in paths


# --------------------------------------------------------------------------
# 4. the image is the version these limits are for
# --------------------------------------------------------------------------


def compose_keycloak_image() -> str:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return str(compose["services"]["keycloak"]["image"])


@cache
def tracked_image_references() -> tuple[tuple[str, str], ...]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True
    ).stdout.decode("utf-8")
    found: list[tuple[str, str]] = []
    for rel in filter(None, listed.split("\0")):
        path = REPO / rel
        if rel.startswith(HISTORICAL_PREFIXES) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found += [(rel, match) for match in IMAGE_REFERENCE.findall(text)]
    return tuple(found)


class TestImagePin:
    def test_compose_runs_the_pinned_version_by_digest(self) -> None:
        assert compose_keycloak_image() == KEYCLOAK_IMAGE

    def test_the_pin_has_a_tag_for_the_reader_and_a_digest_for_the_runtime(self) -> None:
        assert IMAGE_SHAPE.fullmatch(KEYCLOAK_IMAGE)
        # near-misses: a tag alone can be repointed, and a digest alone hides the version
        assert not IMAGE_SHAPE.fullmatch(f"{KEYCLOAK_REPOSITORY}:{KEYCLOAK_VERSION}")
        assert not IMAGE_SHAPE.fullmatch(f"{KEYCLOAK_REPOSITORY}@{KEYCLOAK_INDEX_DIGEST}")

    def test_no_tracked_file_names_another_keycloak_image(self) -> None:
        references = tracked_image_references()
        assert ("infra/docker-compose.obs.yml", KEYCLOAK_IMAGE) in references
        assert {ref for _, ref in references} == {KEYCLOAK_IMAGE}, references

    def test_near_miss_the_scan_sees_a_stale_tag(self) -> None:
        stale = f"{KEYCLOAK_REPOSITORY}:26.1.4"
        assert IMAGE_REFERENCE.findall(f"    image: {stale}\n") == [stale]


# --------------------------------------------------------------------------
# 5. the import directory picks the committed realm up under the name 26.7.4 requires
# --------------------------------------------------------------------------

IMPORT_DIR = "/opt/keycloak/data/import/"
REALM_SOURCE = "./keycloak/dev-realm.json"


def import_mount_violations(volumes: list[str], realm_name: str) -> list[str]:
    """``DirImportProvider.importRealm`` (26.7.4,
    ``model/storage-services/src/main/java/org/keycloak/exportimport/dir/DirImportProvider.java``
    lines 137 and 146-148) reads ``<name>-realm.json`` and aborts start-up unless the realm
    inside is ``<name>``. 26.1.4 had no such check, so the old ``dev-realm.json`` mount worked
    there and stops the server on 26.7.4."""
    mounts = [str(volume).split(":") for volume in volumes]
    imported = [(source, target) for source, target, *_ in mounts if target.startswith(IMPORT_DIR)]
    expected = [(REALM_SOURCE, f"{IMPORT_DIR}{realm_name}-realm.json")]
    if imported != expected:
        return [f"the import directory holds {imported}, expected {expected}"]
    return []


def compose_keycloak_volumes() -> list[str]:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return [str(volume) for volume in compose["services"]["keycloak"]["volumes"]]


class TestImportMount:
    def test_the_committed_realm_is_mounted_under_its_own_realm_name(self) -> None:
        realm_name = load_realm()["realm"]
        assert import_mount_violations(compose_keycloak_volumes(), realm_name) == []

    def test_near_miss_the_26_1_4_file_name_is_caught(self) -> None:
        old = [f"{REALM_SOURCE}:{IMPORT_DIR}dev-realm.json:ro"]
        assert import_mount_violations(old, "intake-dev")

    def test_near_miss_a_renamed_realm_is_caught(self) -> None:
        assert import_mount_violations(compose_keycloak_volumes(), "intake-prod")

    def test_a_mount_outside_the_import_directory_is_ignored(self) -> None:
        volumes = [
            *compose_keycloak_volumes(),
            "./keycloak/providers/deploy:/opt/keycloak/providers:ro",
        ]
        assert import_mount_violations(volumes, "intake-dev") == []
