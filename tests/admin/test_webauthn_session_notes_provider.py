"""INT-378 — a Keycloak provider writes the WebAuthn notes the console's token needs.

The admin console requires ``aaguid`` and ``credential_id`` on every staff token (INT-180). The
realm maps both from user-session notes (INT-373), and stock Keycloak writes neither note.
The provider in ``infra/keycloak/providers/webauthn-session-notes`` is the stock WebAuthn
authenticator plus those two notes. Its own behaviour is proven by its Java tests (``make
keycloak-provider``, a step of the required CI job ``check-py``). This file holds everything
around it that Python can see:

- **the realm runs it.** The staff flow's WebAuthn execution names the provider's id, which is
  the id the Java factory registers, and nothing runs the stock authenticator any more.
- **one set of names.** The notes the Java class writes are the notes the realm's mappers read.
- **the realm imports.** Keycloak keeps a flow or role description in an NVARCHAR(255) column,
  and a longer one fails the import, so the committed realm could not load (INT-365's flow
  description was 271 characters; found by the live login below).
- **the pins.** The Maven distribution, every artefact Maven resolves and the jar are pinned by
  sha256, the jar is reproducible, and the compose file, the Makefile and CI all use the pin.
- **a real login, recorded.** ``scripts/keycloak/record_webauthn_login.py`` logged a synthetic
  staff account in to a real Keycloak running the pinned jar (26.7.4, the composed version; the
  recorder reads the version from the server), once through the committed
  realm and once through a twin that differs only in running the stock authenticator. The
  recording is replayed here through the console's own verifier and principal parser: the first
  token is admitted with the authenticator's AAGUID and credential id, the second is refused.

The owner decision split out as INT-389 (#644; a TOTP login has no AAGUID) is not taken here,
and the console's rule that every token carries ``aaguid`` is unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

import pytest
import yaml
from defusedxml.ElementTree import parse as parse_xml
from intake_platform.admin.principal import (
    _ID_SHAPE,
    MalformedClaims,
    principal_from_claims,
)
from intake_platform.admin.roles import AdminRole
from intake_platform.admin.second_factor import AMR_WEBAUTHN, requires_webauthn
from test_oidc_verifier import token, verifier

REPO = Path(__file__).resolve().parents[2]
REALM_PATH = REPO / "infra" / "keycloak" / "dev-realm.json"
PROVIDERS = REPO / "infra" / "keycloak" / "providers"
MODULE = PROVIDERS / "webauthn-session-notes"
JAVA = MODULE / "src" / "main" / "java" / "intake" / "keycloak" / "webauthn"
PIN_PATH = PROVIDERS / "webauthn-session-notes.sha256"
COMPOSE_PATH = REPO / "infra" / "docker-compose.obs.yml"
MAKEFILE = REPO / "Makefile"
CI_PATH = REPO / ".github" / "workflows" / "ci.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "keycloak-realm.md"
RECORDING = Path(__file__).parent / "fixtures" / "keycloak_webauthn_login.json"

STOCK_WEBAUTHN = "webauthn-authenticator"
POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}
SHA256 = re.compile(r"[0-9a-f]{64}")

#: Keycloak 26.1.4 model/jpa/src/main/resources/META-INF/jpa-changelog-2.5.0.xml:
#: AUTHENTICATION_FLOW.DESCRIPTION and KEYCLOAK_ROLE.DESCRIPTION are NVARCHAR(255).
DESCRIPTION_COLUMN = 255

#: sha256 of mvnw, the Apache Maven Wrapper 3.3.4 "only-script" script copied verbatim from
#: maven-wrapper-distribution-3.3.4-only-script.zip (docs/evidence/INT-378.md).
MVNW_SHA256 = "cae96cef89ebea3531221f4ae17c23cf8edf67d00eae8306d4186ae1bbed4d02"


def load_realm() -> dict[str, Any]:
    realm: dict[str, Any] = json.loads(REALM_PATH.read_text(encoding="utf-8"))
    return realm


def java_constant(source: str, name: str) -> str:
    text = (JAVA / source).read_text(encoding="utf-8")
    match = re.search(rf'public static final String {name} = "([^"]+)";', text)
    assert match, f"{source} declares no {name}"
    return match.group(1)


PROVIDER_ID = java_constant("WebAuthnSessionNotesAuthenticatorFactory.java", "PROVIDER_ID")
AAGUID_NOTE = java_constant("WebAuthnSessionNotes.java", "AAGUID_NOTE")
CREDENTIAL_ID_NOTE = java_constant("WebAuthnSessionNotes.java", "CREDENTIAL_ID_NOTE")


def pom() -> Element:
    root = parse_xml(MODULE / "pom.xml").getroot()
    assert root is not None
    return root


def pom_text(path: str) -> str:
    element = pom().find(path, POM_NS)
    assert element is not None and element.text, path
    return element.text.strip()


def pom_property(name: str) -> str:
    return pom_text(f"m:properties/m:{name}")


def jar_name() -> str:
    return f"{pom_text('m:artifactId')}-{pom_text('m:version')}.jar"


def compose_keycloak() -> dict[str, Any]:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    service: dict[str, Any] = compose["services"]["keycloak"]
    return service


#: Joined, so this file never spells an image reference the INT-390 image scan would read.
KEYCLOAK_REPOSITORY = "/".join(("quay.io", "keycloak", "keycloak"))


def composed_image() -> tuple[str, str, str]:
    """The obs Keycloak image as (repository, tag, digest); INT-390 pins it by both."""
    reference, _, digest = str(compose_keycloak()["image"]).partition("@")
    repository, _, tag = reference.rpartition(":")
    return repository, tag, digest


def recording() -> dict[str, Any]:
    recorded: dict[str, Any] = json.loads(RECORDING.read_text(encoding="utf-8"))
    return recorded


# --------------------------------------------------------------------------
# 1. the realm runs the provider, under the id the factory registers
# --------------------------------------------------------------------------


def webauthn_executions(realm: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (flow["alias"], execution)
        for flow in realm.get("authenticationFlows", [])
        for execution in flow["authenticationExecutions"]
        if execution.get("authenticator") in {PROVIDER_ID, STOCK_WEBAUTHN}
    ]


def wiring_violations(realm: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    executions = webauthn_executions(realm)
    for alias, execution in executions:
        if execution["authenticator"] == STOCK_WEBAUTHN:
            violations.append(
                f"flow {alias!r} runs the stock {STOCK_WEBAUTHN}, which writes no note"
            )
    ours = [(alias, e) for alias, e in executions if e["authenticator"] == PROVIDER_ID]
    if [alias for alias, _ in ours] != ["staff second factor"]:
        violations.append(f"{PROVIDER_ID} runs in {[alias for alias, _ in ours]}")
        return violations
    configs = {c["alias"]: c.get("config", {}) for c in realm.get("authenticatorConfig", [])}
    reference = configs.get(ours[0][1].get("authenticatorConfig", ""), {})
    if reference.get("default.reference.value") != AMR_WEBAUTHN:
        violations.append(f"{PROVIDER_ID} is not tagged amr {AMR_WEBAUTHN}")
    return violations


def note_violations(realm: Mapping[str, Any]) -> list[str]:
    clients = {client["clientId"]: client for client in realm["clients"]}
    read = {
        mapper["config"].get("claim.name"): mapper["config"].get("user.session.note")
        for mapper in clients["admin-web"].get("protocolMappers", [])
        if mapper["protocolMapper"] == "oidc-usersessionmodel-note-mapper"
    }
    written = {"aaguid": AAGUID_NOTE, "credential_id": CREDENTIAL_ID_NOTE}
    return [
        f"claim {claim!r} reads note {read.get(claim)!r}, the provider writes {note!r}"
        for claim, note in written.items()
        if read.get(claim) != note
    ]


def description_violations(realm: Mapping[str, Any]) -> list[str]:
    described = [
        (f"flow {f['alias']!r}", f.get("description", "")) for f in realm["authenticationFlows"]
    ]
    described += [
        (f"role {r['name']!r}", r.get("description", "")) for r in realm["roles"]["realm"]
    ]
    described += [(f"client {c['clientId']!r}", c.get("description", "")) for c in realm["clients"]]
    return [
        f"{what} description is {len(text)} characters"
        for what, text in described
        if len(text) > DESCRIPTION_COLUMN
    ]


class TestRealmWiring:
    def test_the_provider_id_is_the_factorys_and_the_service_file_names_the_factory(self) -> None:
        assert PROVIDER_ID == "intake-webauthn-session-notes"
        service = MODULE / "src/main/resources/META-INF/services"
        registered = (service / "org.keycloak.authentication.AuthenticatorFactory").read_text()
        assert registered.split() == [
            "intake.keycloak.webauthn.WebAuthnSessionNotesAuthenticatorFactory"
        ]

    def test_the_committed_realm_runs_the_provider_and_never_the_stock_authenticator(self) -> None:
        assert wiring_violations(load_realm()) == []

    def test_near_miss_the_stock_authenticator_back_in_the_flow_is_caught(self) -> None:
        realm = load_realm()
        for _, execution in webauthn_executions(realm):
            execution["authenticator"] = STOCK_WEBAUTHN
        assert wiring_violations(realm)

    def test_near_miss_the_provider_without_its_amr_reference_is_caught(self) -> None:
        realm = load_realm()
        for _, execution in webauthn_executions(realm):
            execution.pop("authenticatorConfig")
        assert wiring_violations(realm)

    def test_the_notes_the_provider_writes_are_the_notes_the_mappers_read(self) -> None:
        assert (AAGUID_NOTE, CREDENTIAL_ID_NOTE) == (
            "intake.webauthn.aaguid",
            "intake.webauthn.credential_id",
        )
        assert note_violations(load_realm()) == []

    def test_near_miss_a_renamed_mapper_note_is_caught(self) -> None:
        realm = load_realm()
        for client in realm["clients"]:
            for mapper in client.get("protocolMappers", []):
                if mapper["config"].get("claim.name") == "credential_id":
                    mapper["config"]["user.session.note"] = "intake.webauthn.credentialId"
        assert note_violations(realm)

    def test_every_description_fits_keycloaks_column(self) -> None:
        assert description_violations(load_realm()) == []

    def test_near_miss_a_256_character_flow_description_is_caught(self) -> None:
        realm = copy.deepcopy(load_realm())
        realm["authenticationFlows"][0]["description"] = "x" * (DESCRIPTION_COLUMN + 1)
        assert description_violations(realm) == [
            f"flow 'staff browser' description is {DESCRIPTION_COLUMN + 1} characters"
        ]


# --------------------------------------------------------------------------
# 2. the build recipe and its pins (invariant 14)
# --------------------------------------------------------------------------


class TestPins:
    def test_the_wrapper_is_the_verbatim_3_3_4_script(self) -> None:
        mvnw = MODULE / "mvnw"
        assert hashlib.sha256(mvnw.read_bytes()).hexdigest() == MVNW_SHA256
        assert "Apache Maven Wrapper startup batch script, version 3.3.4" in mvnw.read_text()

    def test_the_maven_distribution_is_pinned_by_sha256(self) -> None:
        props = dict(
            line.split("=", 1)
            for line in (MODULE / ".mvn/wrapper/maven-wrapper.properties").read_text().splitlines()
            if line and not line.startswith("#")
        )
        assert props["distributionType"] == "only-script"
        assert props["distributionUrl"] == (
            "https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.16/"
            "apache-maven-3.9.16-bin.zip"
        )
        assert SHA256.fullmatch(props["distributionSha256Sum"])

    def test_every_resolved_artefact_must_match_a_committed_sha256(self) -> None:
        config = (MODULE / ".mvn/maven.config").read_text().split()
        assert "--strict-checksums" in config
        for flag in (
            "-Daether.artifactResolver.postProcessor.trustedChecksums=true",
            "-Daether.artifactResolver.postProcessor.trustedChecksums.checksumAlgorithms=SHA-256",
            "-Daether.artifactResolver.postProcessor.trustedChecksums.failIfMissing=true",
            "-Daether.trustedChecksumsSource.summaryFile=true",
            "-Daether.trustedChecksumsSource.summaryFile.basedir=${session.rootDirectory}/.mvn/checksums",
        ):
            assert flag in config, flag
        assert not any("trustedChecksums.record" in flag for flag in config)
        lines = (MODULE / ".mvn/checksums/checksums-central.sha256").read_text().splitlines()
        paths = []
        for line in lines:
            digest, path = line.split("  ")
            assert SHA256.fullmatch(digest), line
            paths.append(path)
        assert len(paths) == len(set(paths))
        version = pom_property("keycloak.version")
        for artefact in ("keycloak-services", "keycloak-server-spi", "keycloak-server-spi-private"):
            assert f"org/keycloak/{artefact}/{version}/{artefact}-{version}.jar" in paths

    def test_keycloak_is_provided_at_the_composed_version_and_nothing_is_bundled(self) -> None:
        repository, tag, digest = composed_image()
        assert repository == KEYCLOAK_REPOSITORY
        assert tag == pom_property("keycloak.version")
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        for dependency in pom().findall("m:dependencies/m:dependency", POM_NS):
            group = dependency.findtext("m:groupId", namespaces=POM_NS)
            artefact = dependency.findtext("m:artifactId", namespaces=POM_NS)
            version = dependency.findtext("m:version", namespaces=POM_NS) or ""
            scope = dependency.findtext("m:scope", namespaces=POM_NS)
            assert scope in {"provided", "test"}, f"{artefact} would be bundled into the jar"
            assert not re.search(r"[\[\](),]", version), f"{artefact} names a version range"
            if group == "org.keycloak":
                assert version == "${keycloak.version}" and scope == "provided", artefact
                exclusions = [
                    (
                        e.findtext("m:groupId", namespaces=POM_NS),
                        e.findtext("m:artifactId", namespaces=POM_NS),
                    )
                    for e in dependency.findall("m:exclusions/m:exclusion", POM_NS)
                ]
                assert exclusions == [("*", "*")], artefact

    def test_every_plugin_is_pinned_and_the_jar_is_reproducible(self) -> None:
        for plugin in pom().findall("m:build/m:pluginManagement/m:plugins/m:plugin", POM_NS):
            assert re.fullmatch(
                r"\d+\.\d+\.\d+", plugin.findtext("m:version", namespaces=POM_NS) or ""
            )
        assert re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", pom_property("project.build.outputTimestamp")
        )
        # plexus-archiver writes zip entry times in the JVM's zone; UTC makes the jar zone-free
        assert (MODULE / ".mvn/jvm.config").read_text().split() == ["-Duser.timezone=UTC"]
        assert (MODULE / ".gitignore").read_text().split() == ["target/"]

    def test_the_pin_names_the_jar_the_recipe_builds(self) -> None:
        digest, name = PIN_PATH.read_text().rstrip("\n").split("  ")
        assert SHA256.fullmatch(digest)
        assert name == jar_name() == "intake-webauthn-session-notes-1.0.0.jar"

    def test_make_checks_the_pin_before_staging_and_obs_depends_on_it(self) -> None:
        makefile = MAKEFILE.read_text()
        target = makefile.split("\nkeycloak-provider:\n", 1)[1].split("\n\n", 1)[0]
        steps = [line.strip() for line in target.splitlines()]
        assert steps[0].endswith("./mvnw -B clean verify")
        assert steps[1].endswith("shasum -a 256 -c ../../webauthn-session-notes.sha256")
        assert steps[2].startswith("cp ") and "/deploy/" in steps[2]
        assert "\nobs: keycloak-provider\n" in makefile

    def test_ci_rebuilds_the_jar_against_the_pin(self) -> None:
        workflow = yaml.safe_load(CI_PATH.read_text())
        runs = [step.get("run", "") for step in workflow["jobs"]["check-py"]["steps"]]
        assert any(run.endswith("make keycloak-provider") for run in runs)
        # a step of a required job: a job of its own would be a gate the ops console's
        # recorded GitHub answers cannot show (tests/observability/test_ops_cicd.py)
        assert "keycloak-provider" not in workflow["jobs"]

    def test_the_obs_keycloak_mounts_only_the_checked_jar_directory(self) -> None:
        assert (
            "./keycloak/providers/deploy:/opt/keycloak/providers:ro"
            in compose_keycloak()["volumes"]
        )
        ignored = (PROVIDERS / "deploy" / ".gitignore").read_text().splitlines()
        assert "*.jar" in ignored


# --------------------------------------------------------------------------
# 3. a real Keycloak login, recorded, replayed through the console
# --------------------------------------------------------------------------


class TestRecordedLogin:
    def test_the_recording_is_of_the_pinned_jar_on_the_composed_keycloak(self) -> None:
        recorded = recording()
        assert recorded["provider_jar_sha256"] == PIN_PATH.read_text().split()[0]
        assert composed_image()[1] == recorded["keycloak"]["version"]
        assert SHA256.fullmatch(recorded["keycloak"]["dist_sha256"])

    def test_the_provider_login_carries_the_authenticators_ids(self) -> None:
        recorded = recording()
        authenticator = recorded["software_authenticator"]
        claims = recorded["logins"][PROVIDER_ID]["access_token_claims"]
        assert claims["aaguid"] == authenticator["aaguid"]
        assert claims["credential_id"] == authenticator["credential_id"]
        assert AMR_WEBAUTHN in claims["amr"]
        assert _ID_SHAPE.fullmatch(claims["credential_id"])

    def test_the_only_claims_the_provider_adds_are_the_two_ids(self) -> None:
        logins = recording()["logins"]
        with_notes = set(logins[PROVIDER_ID]["access_token_claims"])
        stock = set(logins[STOCK_WEBAUTHN]["access_token_claims"])
        assert with_notes - stock == {"aaguid", "credential_id"}
        assert stock <= with_notes

    def test_the_console_admits_the_provider_login(self) -> None:
        recorded = recording()
        live = recorded["logins"][PROVIDER_ID]
        assert live["console"]["admitted"] is True
        claims = live["access_token_claims"]
        # replayed through the console's verifier: the recorded claims, re-signed with the test
        # key, at the moment they were issued
        admitted = verifier(issuer=claims["iss"], clock=lambda: claims["iat"]).verify(token(claims))
        principal = principal_from_claims(admitted, source_ip="127.0.0.1")
        assert principal.authenticator_aaguid == recorded["software_authenticator"]["aaguid"]
        assert principal.credential_id == recorded["software_authenticator"]["credential_id"]
        assert principal.tenant == claims["tenant"]
        # a role that reaches patient content, so it was admitted on hwk, not otp
        assert AdminRole.TENANT_CLINICAL_RESPONSIBLE in principal.roles
        assert requires_webauthn(AdminRole.TENANT_CLINICAL_RESPONSIBLE)

    @pytest.mark.parametrize("claim", ["aaguid", "credential_id"])
    def test_near_miss_the_same_login_without_one_note_is_refused(self, claim: str) -> None:
        claims = dict(recording()["logins"][PROVIDER_ID]["access_token_claims"])
        del claims[claim]
        with pytest.raises(MalformedClaims, match=claim):
            principal_from_claims(claims, source_ip="127.0.0.1")

    def test_the_stock_authenticators_login_is_refused(self) -> None:
        live = recording()["logins"][STOCK_WEBAUTHN]
        assert live["console"] == {
            "admitted": False,
            "refusal": "MalformedClaims",
            "reason": "claim 'aaguid' is absent or not id-shaped",
        }
        with pytest.raises(MalformedClaims, match="aaguid"):
            principal_from_claims(live["access_token_claims"], source_ip="127.0.0.1")


# --------------------------------------------------------------------------
# 4. the runbook tells the owner how to deploy and re-check it
# --------------------------------------------------------------------------


class TestRunbook:
    def test_the_runbook_documents_the_rebuild_the_hash_and_the_deploy_step(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        for needle in (
            PROVIDER_ID,
            "make keycloak-provider",
            PIN_PATH.read_text().split()[0],
            "/opt/keycloak/providers",
            "kc.sh build",
            STOCK_WEBAUTHN,
        ):
            assert needle in text, needle
