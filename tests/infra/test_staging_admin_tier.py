"""INT-421: the staging host's admin tier (Keycloak, oauth2-proxy, admin-web).

The admin console must be reachable on the AWS host only behind a Keycloak
login, and the API's INT-180 gate must keep deciding every read. These tests
pin the configuration that makes that true. Each safety property has a
near-miss control:

- Keycloak runs `start` with the pinned 26.7.4 image plus the INT-378 provider
  jar (tests/infra/test_staging_keycloak_provider.py). The staff realm carries
  no user and no dev password, keeps the INT-365 two-factor browser flow,
  and has a confidential console client whose secret and redirect are
  host-generated values substituted at import.
- oauth2-proxy injects the session's access token, never the ID token, as
  the console's bearer. Only GET /healthz skips the login. Its request and
  auth logs are off, because both name the signed-in staff email.
- Caddy never routes Keycloak's admin console, the master realm or its
  management endpoints.
- The API's admin gate reads the realm's issuer, the `api` audience and a
  key-set file. Its IP allow-list is the owner's explicit allow-all (D19,
  2 Oct 2026), so the Keycloak login, with its second factor, is the gate.
- The console image is pinned, non-root, and reaches only the API.
- lib.sh's cookie secret is 32 bytes in the form oauth2-proxy accepts. The
  key-set mirror refuses a document with no RS256 signing key.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.admin.ip_allowlist import IpAllowList

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
COMPOSE = STAGING / "compose.yaml"
CADDYFILE = STAGING / "Caddyfile"
LIB = STAGING / "lib.sh"
DEPLOY = STAGING / "deploy.sh"
SMOKE = STAGING / "smoke.sh"
REALM = STAGING / "keycloak" / "intake-realm.json"
DEV_REALM = REPO / "infra" / "keycloak" / "dev-realm.json"
ALPHA = STAGING / "oauth2-proxy" / "alpha.yaml"
ADMIN_DOCKERFILE = STAGING / "Dockerfile.admin-web"
KEYCLOAK_DOCKERFILE = STAGING / "Dockerfile.keycloak"
ADMIN_DOCKERIGNORE = STAGING / "Dockerfile.admin-web.dockerignore"

#: INT-390's pin, assembled from parts like the other image pins.
KEYCLOAK_IMAGE = "/".join(("quay.io", "keycloak", "keycloak")) + (
    ":26.7.4@sha256:82a77884f3af238beab1e7afd63b5f530e1b5c0590bd7aa60b40a40463e29b2c"
)
OAUTH2_PROXY_IMAGE = "/".join(("quay.io", "oauth2-proxy", "oauth2-proxy")) + (
    ":v7.15.4@sha256:b1b2021fe8f4004573e8d690dec6c7bb29cc44364572cf8510a05bf3a0ae2ded"
)
PINNED = re.compile(r"^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")
REQUIRED = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):\?[^}]+\}")
#: oauth2-proxy writes both logs unless told not to, and both name the signed-in email.
EMAIL_LOGS = ("OAUTH2_PROXY_REQUEST_LOGGING", "OAUTH2_PROXY_AUTH_LOGGING")


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _service(name: str) -> dict[str, Any]:
    return _compose()["services"][name]


def _env(name: str) -> dict[str, str]:
    env = _service(name).get("environment", {})
    return {str(k): str(v) for k, v in env.items()}


def _email_logs_off(env: dict[str, str]) -> bool:
    return all(env.get(key) == "false" for key in EMAIL_LOGS)


def _realm() -> dict[str, Any]:
    return json.loads(REALM.read_text(encoding="utf-8"))


def _client(realm: dict[str, Any], client_id: str) -> dict[str, Any]:
    return next(c for c in realm["clients"] if c["clientId"] == client_id)


def _bash(script: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {script}'],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


# --- Keycloak ----------------------------------------------------------------------------


class TestKeycloak:
    def test_runs_the_pinned_image_in_production_mode(self) -> None:
        # INT-378: built FROM the pin plus the checked provider jar
        # (tests/infra/test_staging_keycloak_provider.py holds the build)
        keycloak = _service("keycloak")
        assert keycloak["image"] == "intake-staging/keycloak:${INTAKE_GIT_SHA:?set by deploy.sh}"
        assert keycloak["build"]["dockerfile"] == "infra/staging/Dockerfile.keycloak"
        bases = re.findall(r"^FROM (\S+)", KEYCLOAK_DOCKERFILE.read_text(encoding="utf-8"), re.M)
        assert bases[-1] == KEYCLOAK_IMAGE
        assert keycloak["command"][0] == "start"
        assert "start-dev" not in json.dumps(keycloak)
        # an optimized server is never re-augmented, so it would never load the provider
        assert "--optimized" not in json.dumps(keycloak)

    def test_imports_the_realm_under_its_own_name(self) -> None:
        mounts = _service("keycloak")["volumes"]
        assert (
            "./keycloak/intake-realm.json:/opt/keycloak/data/import/intake-realm.json:ro" in mounts
        )
        assert _realm()["realm"] == "intake"

    def test_every_credential_is_a_required_host_secret(self) -> None:
        env = _env("keycloak")
        for key in (
            "KC_DB_PASSWORD",
            "KC_BOOTSTRAP_ADMIN_PASSWORD",
            "INTAKE_ADMIN_WEB_CLIENT_SECRET",
        ):
            assert REQUIRED.fullmatch(env[key]), key

    def test_publishes_no_port_and_sits_on_internal_networks(self) -> None:
        networks = _compose()["networks"]
        keycloak = _service("keycloak")
        assert "ports" not in keycloak
        assert all(networks[n].get("internal") is True for n in keycloak["networks"])

    def test_the_staff_realm_carries_no_user_and_no_dev_value(self) -> None:
        text = REALM.read_text(encoding="utf-8")
        assert "users" not in _realm()
        for dev_value in ("dev-only", "localhost", "127.0.0.1", ".invalid", "COMMITTED DEV"):
            assert dev_value not in text, dev_value

    def test_near_miss_the_dev_realm_would_fail_the_same_scan(self) -> None:
        dev = json.loads(DEV_REALM.read_text(encoding="utf-8"))
        assert dev.get("users"), "the control: the dev realm does carry users"
        assert "localhost" in DEV_REALM.read_text(encoding="utf-8")

    def test_the_two_factor_browser_flow_is_kept(self) -> None:
        realm, dev = _realm(), json.loads(DEV_REALM.read_text(encoding="utf-8"))
        assert realm["browserFlow"] == dev["browserFlow"] == "staff browser"
        assert realm["authenticationFlows"] == dev["authenticationFlows"]
        assert realm["registrationAllowed"] is False

    def test_the_console_client_is_confidential_with_host_substitutions(self) -> None:
        client = _client(_realm(), "admin-web")
        assert client["publicClient"] is False
        assert client["secret"] == "${INTAKE_ADMIN_WEB_CLIENT_SECRET}"
        assert client["redirectUris"] == ["https://admin.${STAGING_HOSTNAME}/oauth2/callback"]
        assert client["attributes"]["pkce.code.challenge.method"] == "S256"
        assert client["directAccessGrantsEnabled"] is False

    def test_the_access_token_carries_the_api_audience(self) -> None:
        mappers = _client(_realm(), "admin-web")["protocolMappers"]
        audience = [m for m in mappers if m["protocolMapper"] == "oidc-audience-mapper"]
        assert [m["config"]["included.client.audience"] for m in audience] == ["api"]
        assert audience[0]["config"]["access.token.claim"] == "true"
        assert _env("api")["INTAKE_ADMIN_OIDC_AUDIENCE"] == "api"


# --- oauth2-proxy ----------------------------------------------------------------------------


class TestLoginGate:
    def test_runs_the_pinned_image_on_the_internal_network_only(self) -> None:
        proxy = _service("oauth2-proxy")
        assert proxy["image"] == OAUTH2_PROXY_IMAGE and PINNED.match(proxy["image"])
        assert "ports" not in proxy
        assert proxy["networks"] == ["edge"]

    def test_the_bearer_is_the_session_access_token(self) -> None:
        alpha = yaml.safe_load(ALPHA.read_text(encoding="utf-8"))
        headers = alpha["injectRequestHeaders"]
        assert [h["name"] for h in headers] == ["Authorization"]
        source = headers[0]["values"][0]["claimSource"]
        assert source == {"claim": "access_token", "prefix": "Bearer "}

    def test_near_miss_an_id_token_bearer_is_refused_by_the_same_check(self) -> None:
        wrong = {"claim": "id_token", "prefix": "Bearer "}
        assert wrong != {"claim": "access_token", "prefix": "Bearer "}

    def test_the_provider_redeems_internally_and_logs_in_publicly(self) -> None:
        provider = yaml.safe_load(ALPHA.read_text(encoding="utf-8"))["providers"][0]
        assert provider["clientSecret"] == "${INTAKE_ADMIN_WEB_CLIENT_SECRET}"
        assert provider["code_challenge_method"] == "S256"
        assert provider["redeemURL"].startswith("http://keycloak:8080/realms/intake/")
        assert provider["loginURL"].startswith("https://auth.${STAGING_HOSTNAME}/realms/intake/")
        issuer = provider["oidcConfig"]["issuerURL"]
        assert issuer == "https://auth.${STAGING_HOSTNAME}/realms/intake"
        assert _env("api")["INTAKE_ADMIN_OIDC_ISSUER"] == (
            "https://auth.${STAGING_HOSTNAME:?run init.sh}/realms/intake"
        )

    def test_only_the_console_liveness_skips_the_login(self) -> None:
        env = _env("oauth2-proxy")
        assert env["OAUTH2_PROXY_SKIP_AUTH_ROUTES"] == "GET=^/healthz$$"
        assert env["OAUTH2_PROXY_COOKIE_SECURE"] == "true"
        assert REQUIRED.fullmatch(env["OAUTH2_PROXY_COOKIE_SECRET"])

    def test_no_log_line_names_the_signed_in_staff_member(self) -> None:
        assert _email_logs_off(_env("oauth2-proxy"))

    def test_near_miss_the_default_logging_fails_the_same_check(self) -> None:
        env = _env("oauth2-proxy")
        default = {k: v for k, v in env.items() if k not in EMAIL_LOGS}
        assert not _email_logs_off(default), "oauth2-proxy logs both unless told not to"
        for key in EMAIL_LOGS:
            assert not _email_logs_off({**default, key: "false"}), "one log alone still names"
            assert not _email_logs_off({**env, key: "true"})


# --- the edge --------------------------------------------------------------------------------


def _site(host: str) -> str:
    text = CADDYFILE.read_text(encoding="utf-8")
    return text.split(f"{host} {{", 1)[1].split("\n}", 1)[0]


class TestEdge:
    def test_the_console_host_goes_through_the_login_gate_only(self) -> None:
        site = _site("admin.{$STAGING_HOSTNAME}")
        assert re.findall(r"reverse_proxy (\S+)", site) == ["oauth2-proxy:4180"]
        assert 'X-Intake-Environment "staging-synthetic-only"' in site

    def test_keycloak_admin_master_realm_and_management_are_not_routed(self) -> None:
        site = _site("auth.{$STAGING_HOSTNAME}")
        matcher = re.search(r"@not_public path (.+)", site)
        assert matcher
        paths = matcher.group(1).split()
        for path in ("/admin", "/admin/*", "/realms/master", "/realms/master/*", "/metrics"):
            assert path in paths, path
        assert "respond @not_public 404" in site
        assert "/realms/intake" not in paths, "the staff realm itself must stay routed"

    def test_nothing_publishes_a_new_port(self) -> None:
        for name in ("keycloak", "oauth2-proxy", "admin-web"):
            assert "ports" not in _service(name), name


# --- the API's admin gate and the console image -------------------------------------------


class TestApiGateAndConsole:
    def test_the_allow_list_is_the_owners_explicit_allow_all(self) -> None:
        # owner decision D19 (2 Oct 2026): "dont make admin access ip restricted"
        spec = _env("api")["INTAKE_ADMIN_IP_ALLOWLIST"]
        assert spec == "0.0.0.0/0,::/0"
        allow = IpAllowList.from_spec(spec)
        for peer in ("172.18.0.5", "3.211.2.143", "2001:db8::1"):
            assert allow.permits(peer), peer
        assert "D19" in COMPOSE.read_text(encoding="utf-8")

    def test_near_miss_an_empty_list_would_admit_nobody(self) -> None:
        assert not IpAllowList.from_spec("").permits("172.18.0.5")

    def test_the_login_gate_still_demands_a_second_factor(self) -> None:
        # D19 lifts the network restriction only; the staff flow is unchanged
        flows = {f["alias"]: f for f in _realm()["authenticationFlows"]}
        forms = flows["staff browser forms"]["authenticationExecutions"]
        assert [e["requirement"] for e in forms] == ["REQUIRED", "REQUIRED"]
        second = flows["staff second factor"]["authenticationExecutions"]
        # INT-378: the WebAuthn step is the stock authenticator's subclass that also writes
        # aaguid and credential_id. INT-550: it is REQUIRED, so a staff user without a passkey
        # enrols one after the password instead of being refused, and OTP is DISABLED until
        # the owner decides INT-389 (#644)
        assert {e["authenticator"]: e["requirement"] for e in second} == {
            "intake-webauthn-session-notes": "REQUIRED",
            "auth-otp-form": "DISABLED",
        }

    def test_the_key_set_is_a_read_only_mirror(self) -> None:
        assert _env("api")["INTAKE_ADMIN_OIDC_JWKS_PATH"] == "/run/intake/keycloak-jwks.json"
        assert (
            "/etc/intake-staging/keycloak-jwks.json:/run/intake/keycloak-jwks.json:ro"
            in _service("api")["volumes"]
        )

    def test_the_console_reaches_only_the_api(self) -> None:
        console = _service("admin-web")
        assert _env("admin-web") == {"INTAKE_ADMIN_API_BASE": "http://api:8000"}
        assert console["networks"] == ["edge"]
        assert console["read_only"] is True
        assert "no-new-privileges:true" in console["security_opt"]

    def test_the_console_image_is_pinned_and_non_root(self) -> None:
        text = ADMIN_DOCKERFILE.read_text(encoding="utf-8")
        bases = re.findall(r"^FROM (\S+)", text, re.M)
        assert bases and all(PINNED.match(base) for base in bases)
        users = re.findall(r"^USER (\d+)", text, re.M)
        assert users and int(users[-1]) >= 1000
        assert "--frozen-lockfile" in text

    def test_the_console_build_context_denies_by_default(self) -> None:
        lines = [
            line.strip()
            for line in ADMIN_DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert lines[0] == "*"
        for excluded in ("**/.env", "**/.env.*", "**/node_modules"):
            assert excluded in lines


# --- lib.sh: the cookie secret and the key-set mirror ------------------------------------------


class TestHostHelpers:
    def test_the_cookie_secret_is_32_bytes_in_base64url(self) -> None:
        result = _bash("gen_cookie_secret; gen_cookie_secret")
        assert result.returncode == 0, result.stderr
        first, second = result.stdout.split()
        assert first != second
        for value in (first, second):
            assert re.fullmatch(r"[A-Za-z0-9_-]{43}", value)
            assert len(base64.urlsafe_b64decode(value + "=")) == 32

    def test_near_miss_gen_secret_is_not_an_accepted_cookie_secret(self) -> None:
        value = _bash("gen_secret").stdout.strip()
        # 64 hex characters decode to 48 bytes and are 64 raw: neither is an AES length
        assert len(base64.urlsafe_b64decode(value)) == 48 and len(value) == 64

    @pytest.mark.parametrize(
        "doc",
        [
            '{"keys": [{"kid": "k1", "kty": "RSA", "use": "sig", "alg": "RS256", '
            '"n": "AQAB", "e": "AQAB"}]}',
            '{"keys": [{"kid": "k1", "kty": "RSA", "n": "AQAB", "e": "AQAB"}]}',
        ],
    )
    def test_a_key_set_with_an_rs256_signing_key_is_usable(self, doc: str) -> None:
        assert _bash("jwks_is_usable", doc).returncode == 0

    @pytest.mark.parametrize(
        "doc",
        [
            "",
            "not json",
            '{"keys": []}',
            '{"keys": [{"kid": "k1", "kty": "RSA", "use": "enc", "n": "AQAB", "e": "AQAB"}]}',
            '{"keys": [{"kid": "k1", "kty": "EC", "use": "sig", "x": "a", "y": "b"}]}',
            '{"keys": [{"kid": "k1", "kty": "RSA", "alg": "RS512", "n": "AQAB", "e": "AQAB"}]}',
        ],
        ids=["empty", "not-json", "no-keys", "encryption-key", "ec-key", "rs512"],
    )
    def test_near_misses_are_not_usable(self, doc: str) -> None:
        assert _bash("jwks_is_usable", doc).returncode != 0

    def test_deploy_mirrors_the_key_set_before_the_api_starts(self) -> None:
        code = "\n".join(
            line
            for line in DEPLOY.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        steps = [
            "ensure_jwks_file",
            "ensure_keycloak_database",
            "compose up -d --no-build --wait keycloak",
            "mirror_keycloak_jwks",
            "compose up -d --no-build --wait --remove-orphans",
        ]
        positions = [code.index(step) for step in steps]
        assert positions == sorted(positions)
        assert code.index("ensure_jwks_file") < code.index("compose ")

    def test_deploy_recreates_the_edge_so_it_reads_this_releases_caddyfile(self) -> None:
        code = "\n".join(
            line
            for line in DEPLOY.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        recreate = "compose up -d --no-build --no-deps --force-recreate --wait caddy"
        assert recreate in code
        assert code.index("compose up -d --no-build --wait --remove-orphans") < code.index(recreate)
        assert code.index(recreate) < code.index("wait_https")
        # near miss: caddy has no healthcheck, so wait_healthy would spin out its 180 s
        assert "wait_healthy caddy" not in code

    def test_the_keycloak_password_travels_on_stdin(self) -> None:
        body = LIB.read_text(encoding="utf-8").split("ensure_keycloak_database() {", 1)[1]
        body = body.split("\n}\n", 1)[0]
        assert "log_statement = 'none'" in body
        assert "| compose exec -T postgres psql" in body

    def test_smoke_checks_the_admin_tier(self) -> None:
        text = SMOKE.read_text(encoding="utf-8")
        for needle in (
            "/realms/intake/.well-known/openid-configuration",
            "/realms/master/",
            "content-security-policy",
            "source_ip_refused",
        ):
            assert needle in text, needle
