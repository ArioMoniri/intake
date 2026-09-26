"""INT-345 — the staging backend artefact (synthetic patients only).

What this file can honestly pin, and what it cannot.

The artefact under ``infra/staging`` runs on one Linux host with Docker: the
AWS box in us-east-1. That host is outside Türkiye, so it carries synthetic
patients only until an in-country host exists (HB-I5, HB-L11). No container
runtime exists where this suite runs (Docker is banned on the development
machine and the GPU server is itself a pod), so nothing here boots a
container. What IS decidable without booting anything:

- the API boots under a non-dev environment: no dev gate anywhere in the
  artefact, the KEK mode is Transit (the OpenBao-backed provider), and
  ``INTAKE_ENV`` is staging;
- OpenBao runs in server mode on file storage, never ``-dev``;
- every image is pinned by digest and nothing secret-shaped is committed;
- only the TLS proxy publishes ports, and only 80/443; the API runs non-root;
- ``/version`` is stamped through build args that the platform's
  ``VersionInfo`` actually reads, and a build without them is refused;
- every role a migration creates with a committed dev password is re-keyed
  on the host;
- the object store runs the owner-approved image pinned by digest (owner
  decision D1, INT-347), publishes no port, and takes its root pair from the
  host-generated env file with no default;
- the restart probe refuses a process-local KEK, and the negative control
  shows why: a file-dev KEK does not survive a process restart.

The host-side run (init.sh, deploy.sh, smoke.sh) belongs to the owner and is
recorded in docs/evidence/INT-345.md when it happens. Nothing here claims it
ran.
"""

from __future__ import annotations

import importlib.util
import inspect
import io
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, get_args

import pytest
import yaml
from intake_api import settings as api_settings
from intake_api.settings import KekMode
from intake_platform.envelope import (
    EnvelopeCipher,
    FileKekProvider,
    TamperError,
    TransitKekProvider,
)
from intake_platform.health import VersionInfo

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
COMPOSE = STAGING / "compose.yaml"
DOCKERFILE = STAGING / "Dockerfile.api"
DOCKERIGNORE = STAGING / "Dockerfile.api.dockerignore"
REQUIREMENTS = STAGING / "requirements-server.txt"
CADDYFILE = STAGING / "Caddyfile"
OPENBAO_CONFIG = STAGING / "openbao" / "openbao.hcl"
API_POLICY = STAGING / "openbao" / "intake-api-policy.hcl"
ENV_TEMPLATE = STAGING / "staging.env.template"
LIB = STAGING / "lib.sh"
INIT = STAGING / "init.sh"
DEPLOY = STAGING / "deploy.sh"
SMOKE = STAGING / "smoke.sh"
PROBE = STAGING / "staging_probe.py"
REVISION = STAGING / "REVISION"
GITATTRIBUTES = STAGING / ".gitattributes"
RUNBOOK = REPO / "docs" / "runbooks" / "staging.md"
MIGRATIONS = REPO / "migrations" / "versions"

SCRIPTS = (LIB, INIT, DEPLOY, SMOKE)
EXECUTABLES = (INIT, DEPLOY, SMOKE)
ARTEFACT = (
    COMPOSE,
    DOCKERFILE,
    DOCKERIGNORE,
    REQUIREMENTS,
    CADDYFILE,
    OPENBAO_CONFIG,
    API_POLICY,
    ENV_TEMPLATE,
    *SCRIPTS,
    PROBE,
    REVISION,
    GITATTRIBUTES,
)

PROJECT = "intake-staging"
SERVICES = {"api", "postgres", "redis", "openbao", "minio", "caddy"}
STAGING_ENV = "staging"

#: The dev-gate prefix, derived from the API's own gate names instead of being
#: spelled here, so a renamed gate moves this guard with it.
DEV_PREFIX = os.path.commonprefix(
    [
        api_settings.ENV_TOKEN_PATIENT,
        api_settings.ENV_TOKEN_ADMIN,
        api_settings.ENV_DEV_OTP_PEEK,
        api_settings.ENV_DEV_ALLOW_UNATTESTED,
    ]
)

#: The KEK mode that keeps keys in process memory; everything else is Transit.
PROCESS_LOCAL_KEK = "file-dev"

#: Build-time stamps set by deploy.sh, not by the root-only .env.
DEPLOY_STAMPED = {"INTAKE_GIT_SHA", "INTAKE_BUILT_AT"}

#: Committed, non-secret values that lib.sh exports for every compose call.
LIB_EXPORTED = {"OBJECT_STORE_IMAGE"}

#: name:tag@sha256:<64 hex> — a tag for humans, a digest for the registry.
PINNED = re.compile(r"^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")

#: Anything shaped like a credential in a committed file is invariant 14's
#: failure mode, whatever it is named (same heuristic as the INT-202 tier).
SECRET_SHAPED = re.compile(
    r"(?:pass|passwd|password|secret|key|token)\s*[:=]\s*(?!\$|\{\{|\"\$)[^\s#]{6,}",
    re.IGNORECASE,
)

#: A credential inside a URL that is not an interpolation.
URL_CREDENTIAL_LITERAL = re.compile(r"://[^:/@\s]+:(?!\$\{)[^@\s]+@")

#: `${NAME:?message}` — required, no default.
REQUIRED_INTERPOLATION = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*):\?[^}]+\}$")

INTERPOLATION = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::?[-?][^}]*)?\}")

MIGRATION_ROLE = re.compile(r"CREATE ROLE (\w+) LOGIN PASSWORD '[^']*'")

#: `${NAME:?message}` anywhere inside a value (a DB URL embeds one).
REQUIRED_INTERPOLATION_IN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):\?[^}]+\}")

#: Any brace interpolation, whatever its operator.
ANY_BRACE_INTERPOLATION = re.compile(r"\$\{[^}]*\}")

#: A bare `$NAME`, which compose also interpolates (`$$` is a literal dollar).
BARE_INTERPOLATION = re.compile(r"(?<!\$)\$(?=[A-Za-z_])")

#: INT-325 (PR #521): outside dev the API refuses to boot with any of these
#: missing or empty, because each one would otherwise fall back to an in-code
#: dev credential. Read from the API once its base carries #521; until then
#: these same names, each proven below to be a variable the API reads.
INT325_REQUIRED_CREDENTIALS = (
    "INTAKE_API_DB_URL",
    "INTAKE_API_AUDIT_DB_URL",
    "INTAKE_API_BOOTSTRAP_DB_URL",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
)
API_SOURCES = (
    REPO / "services" / "api" / "src" / "intake_api" / "settings.py",
    REPO / "services" / "api" / "src" / "intake_api" / "app.py",
)

#: The one template key the owner supplies; every other one is a generated secret.
OWNER_SUPPLIED = {"STAGING_HOSTNAME"}

#: The issue that records the object-store image and its licence.
OBJECT_STORE_ISSUE = "INT-347"

#: The object-store image the owner chose on 2026-09-26 (owner decision D1:
#: the maintained AGPL-3.0 community fork). INT-347 (PR #554) pins the same
#: reference in observability/registry.yaml, with the licence read from the
#: raw LICENSE blob, and its scan holds every reference in the tree to it.
#: Assembled from its parts: a reference split across string literals would
#: read as an unpinned one to that scan, which stops at a quote.
_OBJECT_STORE_REPOSITORY = "pgsty/minio"
_OBJECT_STORE_TAG = "RELEASE.2026-08-04T00-00-00Z"
_OBJECT_STORE_DIGEST = "sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372"
APPROVED_OBJECT_STORE_IMAGE = (
    f"{_OBJECT_STORE_REPOSITORY}:{_OBJECT_STORE_TAG}@{_OBJECT_STORE_DIGEST}"
)

#: The S3 endpoint the API reads (``services/api/src/intake_api/app.py``).
API_OBJECT_STORE_ENDPOINT = "MINIO_ENDPOINT"


def _withdrawn_upstream_image() -> re.Pattern[str]:
    """The withdrawn upstream server/client images, assembled from parts so
    this file never spells what it forbids (the same shape INT-347 scans)."""
    vendor = "min" + "io"
    return re.compile(
        rf"(?<![\w./-])(?:docker\.io/)?{vendor}/(?:{vendor}|mc)(?![\w-])|quay\.io/{vendor}/"
    )


# --- helpers ---------------------------------------------------------------------------


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compose() -> dict[str, Any]:
    loaded = yaml.safe_load(_text(COMPOSE))
    assert isinstance(loaded, dict)
    return loaded


def _service(name: str) -> dict[str, Any]:
    service = _compose()["services"][name]
    assert isinstance(service, dict)
    return service


def _environment(service: dict[str, Any]) -> dict[str, str]:
    raw = service.get("environment", {})
    if isinstance(raw, list):
        pairs = (str(item).split("=", 1) for item in raw)
        return {pair[0]: pair[1] if len(pair) > 1 else "" for pair in pairs}
    return {str(k): "" if v is None else str(v) for k, v in raw.items()}


def _dockerfile_instructions() -> list[tuple[str, str]]:
    """(INSTRUCTION, arguments) with continuations joined and comments dropped."""
    joined: list[str] = []
    buffer = ""
    for line in _text(DOCKERFILE).splitlines():
        stripped = line.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        joined.append(buffer + stripped)
        buffer = ""
    instructions = []
    for statement in joined:
        head, _, rest = statement.partition(" ")
        instructions.append((head.upper(), rest.strip()))
    return instructions


def _stages() -> list[tuple[str, str | None]]:
    """(image reference, stage alias) per FROM."""
    stages: list[tuple[str, str | None]] = []
    for instruction, args in _dockerfile_instructions():
        if instruction != "FROM":
            continue
        parts = [p for p in args.split() if not p.startswith("--")]
        alias = parts[2] if len(parts) >= 3 and parts[1].lower() == "as" else None
        stages.append((parts[0], alias))
    return stages


def _env_template() -> dict[str, str]:
    pairs: dict[str, str] = {}
    for line in _text(ENV_TEMPLATE).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        assert sep == "=", f"template line is not KEY=VALUE: {line!r}"
        pairs[key] = value
    return pairs


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("staging_probe", PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["staging_probe"] = module
    spec.loader.exec_module(module)
    return module


def _bash(script: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Source lib.sh in a clean bash and run one function — no docker, no host."""
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {script}', "lib-test", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd or REPO)},
        check=False,
    )


def _lib_exported(name: str) -> str:
    """The value a child of a lib.sh-sourcing script sees, i.e. what compose
    interpolates. A variable lib.sh sets but does not export reads empty."""
    result = _bash(f'bash -c \'printf "%s" "${{{name}:-}}"\'')
    assert result.returncode == 0, result.stderr
    return result.stdout


def _object_store_image() -> str:
    """compose's minio image, rendered from lib.sh's exported values."""
    raw = str(_service("minio")["image"])

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        assert name in LIB_EXPORTED, f"the object-store image interpolates {name}"
        return _lib_exported(name)

    return REQUIRED_INTERPOLATION_IN.sub(substitute, raw)


def _required_credentials() -> tuple[str, ...]:
    required = getattr(api_settings, "NON_DEV_REQUIRED_CREDENTIALS", INT325_REQUIRED_CREDENTIALS)
    return tuple(str(name) for name in required)


def _read_env_file(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for line in _text(path).splitlines():
        key, sep, value = line.partition("=")
        assert sep == "=", f"env file line is not KEY=VALUE: {line!r}"
        pairs[key] = value
    return pairs


def _generate_env_file(env_file: Path) -> subprocess.CompletedProcess[str]:
    """init.sh's secret generation, pointed at a scratch env file."""
    return _bash('ENV_FILE="$1"; generate_missing_secrets', str(env_file), cwd=env_file.parent)


def _render(value: str, env: dict[str, str]) -> str:
    """Compose's `${NAME:?message}` substitution from an env file's values."""

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        assert env.get(name), f"compose would stop: {name} is empty"
        return env[name]

    return REQUIRED_INTERPOLATION_IN.sub(substitute, value)


def _run_deploy(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """deploy.sh itself, with a scratch state dir so nothing reaches /etc."""
    return subprocess.run(
        ["bash", str(DEPLOY)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(tmp_path),
            "INTAKE_STAGING_STATE_DIR": str(tmp_path / "state"),
        },
        check=False,
    )


def _role_password_keys() -> dict[str, str]:
    """lib.sh's role → .env key table (``"role:KEY"`` entries)."""
    match = re.search(r"ROLE_PASSWORD_KEYS=\((.*?)\)", _text(LIB), re.S)
    assert match, "lib.sh declares no ROLE_PASSWORD_KEYS table"
    entries = re.findall(r'"(\w+):([A-Z_][A-Z0-9_]*)"', match.group(1))
    return dict(entries)


# --- the artefact exists and is runnable -----------------------------------------------


class TestArtefactShape:
    def test_every_artefact_file_exists(self) -> None:
        missing = [str(p.relative_to(REPO)) for p in (*ARTEFACT, RUNBOOK) if not p.is_file()]
        assert not missing, f"missing: {missing}"

    def test_host_scripts_are_executable(self) -> None:
        for script in EXECUTABLES:
            assert script.stat().st_mode & stat.S_IXUSR, f"{script.name} is not executable"

    @pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
    def test_scripts_are_strict_bash_and_parse(self, script: Path) -> None:
        text = _text(script)
        assert text.startswith("#!/usr/bin/env bash\n")
        assert "set -euo pipefail" in text
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    def test_the_compose_project_is_intake_staging(self) -> None:
        assert _compose()["name"] == PROJECT
        assert f"-p {PROJECT}" in _text(LIB), "every compose call goes through one project"

    def test_the_services_are_exactly_the_staging_backend(self) -> None:
        assert set(_compose()["services"]) == SERVICES


# --- non-dev boot: no dev gate, Transit KEK, staging environment ------------------------


class TestNonDevBoot:
    def test_the_dev_prefix_was_derived_from_the_api(self) -> None:
        assert DEV_PREFIX.startswith("INTAKE_") and DEV_PREFIX.endswith("_")
        assert len(DEV_PREFIX) > len("INTAKE_")

    @pytest.mark.parametrize("path", ARTEFACT, ids=lambda p: p.name)
    def test_no_dev_gate_anywhere_in_the_artefact(self, path: Path) -> None:
        assert DEV_PREFIX not in _text(path), f"{path.name} names a dev gate"

    def test_no_service_environment_carries_a_dev_gate(self) -> None:
        for name in SERVICES:
            env = _environment(_service(name))
            assert not [k for k in env if k.startswith(DEV_PREFIX)], name
            assert not [k for k in env if "_DEV_" in k or k.startswith("DEV_")], name

    def test_intake_env_is_staging(self) -> None:
        assert _environment(_service("api"))["INTAKE_ENV"] == STAGING_ENV

    def test_the_kek_mode_is_transit(self) -> None:
        modes = set(get_args(KekMode))
        assert PROCESS_LOCAL_KEK in modes, "the negative control names a real mode"
        mode = _environment(_service("api"))["INTAKE_API_KEK_MODE"]
        assert mode in modes
        assert mode != PROCESS_LOCAL_KEK
        assert mode == "transit"

    @pytest.mark.parametrize("path", ARTEFACT, ids=lambda p: p.name)
    def test_the_process_local_kek_is_never_named(self, path: Path) -> None:
        assert PROCESS_LOCAL_KEK not in _text(path), f"{path.name} names the file-dev KEK"

    def test_the_api_reaches_openbao_with_a_host_generated_token(self) -> None:
        env = _environment(_service("api"))
        assert env["OPENBAO_ADDR"] == "http://openbao:8200"
        match = REQUIRED_INTERPOLATION.match(env["OPENBAO_TOKEN"])
        assert match and match.group(1) == "OPENBAO_TOKEN"

    def test_the_api_database_urls_are_least_privilege_roles_with_host_passwords(self) -> None:
        env = _environment(_service("api"))
        assert env["INTAKE_API_DB_URL"].startswith("postgresql+psycopg://app_rw:${")
        assert env["INTAKE_API_AUDIT_DB_URL"].startswith("postgresql+psycopg://svc_audit_writer:${")
        for key in ("INTAKE_API_DB_URL", "INTAKE_API_AUDIT_DB_URL", "INTAKE_API_BOOTSTRAP_DB_URL"):
            assert "@postgres:5432/" in env[key], key
            assert not URL_CREDENTIAL_LITERAL.search(env[key]), key

    def test_the_otp_tier_is_left_unconfigured(self) -> None:
        """No tokenization key → no OTP tier (503). Wiring it here would wire the
        dev delivery logger, which answers 'sent' and sends nothing."""
        assert api_settings.ENV_TOKENIZATION_KEY not in _environment(_service("api"))


# --- OpenBao: server mode, file storage, transit, least-privilege policy ----------------


class TestOpenBao:
    def test_openbao_runs_server_mode_never_dev(self) -> None:
        """The image's default CMD is ``server -dev``, and its entrypoint's
        ``server`` branch appends ``-dev-*`` flags — so the command is explicit
        and starts with ``bao``, which bypasses that branch entirely."""
        command = _service("openbao")["command"]
        assert isinstance(command, list)
        assert command[:2] == ["bao", "server"]
        assert "-config=/openbao/config/openbao.hcl" in command
        assert not [arg for arg in command if str(arg).startswith("-dev")]
        assert "entrypoint" not in _service("openbao"), "keep dumb-init and core dumps off"
        env = _environment(_service("openbao"))
        assert not [k for k in env if "DEV" in k]

    def test_openbao_config_is_file_storage_with_mlock(self) -> None:
        text = _text(OPENBAO_CONFIG)
        assert re.search(r'storage\s+"file"\s*\{[^}]*path\s*=\s*"/openbao/file"', text, re.S)
        assert re.search(r"disable_mlock\s*=\s*false", text)
        assert not re.search(r"^\s*(dev|-dev)", text, re.M)

    def test_openbao_state_lives_on_a_named_volume(self) -> None:
        compose = _compose()
        volumes = _service("openbao")["volumes"]
        data = [v for v in volumes if str(v).endswith(":/openbao/file")]
        assert data, "file storage must persist across restarts or the KEK dies with it"
        assert data[0].split(":")[0] in compose["volumes"]
        config = [v for v in volumes if "openbao.hcl" in str(v)]
        assert config and str(config[0]).endswith(":ro")

    def test_openbao_can_lock_memory_as_its_non_root_user(self) -> None:
        memlock = _service("openbao")["ulimits"]["memlock"]
        assert memlock in (-1, {"soft": -1, "hard": -1})

    def test_the_api_policy_grants_only_tenant_transit_keys(self) -> None:
        prefix = inspect.signature(TransitKekProvider.__init__).parameters["key_prefix"].default
        blocks = re.findall(
            r'path\s+"([^"]+)"\s*\{\s*capabilities\s*=\s*\[([^\]]*)\]\s*\}', _text(API_POLICY)
        )
        assert blocks
        for path, caps in blocks:
            assert path.startswith("transit/"), path
            assert f"/{prefix}-" in path, path
            granted = {c.strip().strip('"') for c in caps.split(",") if c.strip()}
            assert granted <= {"create", "update", "read"}, (path, granted)

    def test_init_enables_transit_and_creates_the_probe_kek(self) -> None:
        probe = _load_probe()
        # the provider's own default prefix, as the API constructs it
        key_name = TransitKekProvider(secrets=None)._key_name(probe.PROBE_TENANT)
        lib = _text(LIB) + _text(INIT)
        assert "secrets enable transit" in lib
        assert f'PROBE_KEK="{key_name}"' in _text(LIB)
        assert "transit/keys/${PROBE_KEK}" in lib
        assert "policy write intake-api -" in lib

    def test_init_uses_key_shares_and_writes_them_root_only(self) -> None:
        text = _text(INIT) + _text(LIB)
        assert re.search(r"operator init -key-shares=\d+ -key-threshold=\d+ -format=json", text)
        assert "umask 077" in text
        assert "chmod 600" in text and "chmod 700" in text

    def test_unseal_keys_and_tokens_never_travel_in_argv(self) -> None:
        text = _text(LIB) + _text(INIT) + _text(DEPLOY) + _text(SMOKE)
        assert "write -format=json sys/unseal key=-" in text, "unseal key goes via stdin"
        assert not re.search(r"operator unseal\s+\S", text)
        assert "-e BAO_TOKEN " in text or '-e BAO_TOKEN"' in text
        assert not re.search(r"-e BAO_TOKEN=", text)


# --- images, secrets, ports, users ----------------------------------------------------


class TestSupplyChainAndExposure:
    def test_every_pulled_image_is_pinned_by_digest(self) -> None:
        for name, service in _compose()["services"].items():
            if "build" in service:
                continue
            image = _object_store_image() if name == "minio" else service["image"]
            assert PINNED.match(image), f"{name}: {image}"

    def test_every_dockerfile_base_is_pinned_by_digest(self) -> None:
        aliases = {alias for _, alias in _stages() if alias}
        for ref, _ in _stages():
            if ref in aliases:
                continue
            assert PINNED.match(ref), ref
        for instruction, args in _dockerfile_instructions():
            if instruction != "COPY":
                continue
            source = re.search(r"--from=(\S+)", args)
            if source and source.group(1) not in aliases:
                assert PINNED.match(source.group(1)), source.group(1)

    def test_the_server_process_is_hash_pinned(self) -> None:
        requirements = [
            line
            for line in _text(REQUIREMENTS).replace("\\\n", " ").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert any(line.startswith("uvicorn==") for line in requirements)
        for line in requirements:
            assert "==" in line and "--hash=sha256:" in line, line
        assert "--require-hashes" in _text(DOCKERFILE)

    @pytest.mark.parametrize("path", ARTEFACT, ids=lambda p: p.name)
    def test_no_secret_literal_is_committed(self, path: Path) -> None:
        for lineno, line in enumerate(_text(path).splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            assert not SECRET_SHAPED.search(line), f"{path.name}:{lineno}: {line!r}"
            assert not URL_CREDENTIAL_LITERAL.search(line), f"{path.name}:{lineno}: {line!r}"

    def test_secret_environment_values_are_interpolated(self) -> None:
        secretish = re.compile(r"PASSWORD|TOKEN|SECRET|_AUTH$|_KEY$")
        for name, service in _compose()["services"].items():
            for key, value in _environment(service).items():
                if secretish.search(key):
                    assert REQUIRED_INTERPOLATION.match(value), f"{name}.{key}"

    def test_the_env_template_holds_keys_only(self) -> None:
        template = _env_template()
        assert template
        assert all(value == "" for value in template.values()), "values are generated on host"

    def test_every_compose_interpolation_is_a_template_key_or_a_deploy_stamp(self) -> None:
        referenced = set(INTERPOLATION.findall(_text(COMPOSE)))
        assert referenced - set(_env_template()) - DEPLOY_STAMPED - LIB_EXPORTED == set()
        assert DEPLOY_STAMPED <= referenced
        assert LIB_EXPORTED <= referenced
        assert not LIB_EXPORTED & set(_env_template()), "committed values, not host secrets"

    def test_only_the_proxy_publishes_ports_and_only_80_and_443(self) -> None:
        for name, service in _compose()["services"].items():
            assert service.get("network_mode") != "host", name
            if name != "caddy":
                assert "ports" not in service, f"{name} must not publish a port"
        published = set()
        for mapping in _service("caddy")["ports"]:
            if isinstance(mapping, dict):
                published.add((int(mapping["published"]), int(mapping["target"])))
                assert mapping.get("protocol", "tcp") == "tcp"
            else:
                text = str(mapping)
                assert "/udp" not in text
                host, _, target = text.rpartition(":")
                published.add((int(host.split(":")[-1]), int(target.split("/")[0])))
        assert published == {(80, 80), (443, 443)}

    def test_data_services_sit_on_internal_networks_only(self) -> None:
        networks = _compose()["networks"]
        for name in ("postgres", "redis", "openbao", "minio", "api"):
            attached = _service(name)["networks"]
            for network in attached:
                assert networks[network].get("internal") is True, (name, network)
        caddy = _service("caddy")["networks"]
        assert any(not networks[n].get("internal") for n in caddy), "ACME needs egress"
        assert set(caddy) & set(_service("api")["networks"]), "caddy must reach the api"

    def test_the_api_runs_as_non_root(self) -> None:
        final_stage_users: list[str] = []
        for instruction, args in _dockerfile_instructions():
            if instruction == "FROM":
                final_stage_users = []
            if instruction == "USER":
                final_stage_users.append(args)
        assert final_stage_users, "the runtime stage sets no USER"
        user = final_stage_users[-1].split(":")[0]
        assert user.isdigit(), "a numeric uid cannot be remapped to root by a passwd edit"
        assert int(user) >= 1000
        api = _service("api")
        assert str(api.get("user", user)).split(":")[0] not in {"root", "0"}
        assert api.get("read_only") is True
        assert "no-new-privileges:true" in api.get("security_opt", [])


# --- the API image: uv sync --frozen, uvicorn factory, stamped /version ----------------


class TestApiImage:
    def test_dependencies_come_from_the_frozen_lock(self) -> None:
        runs = [args for instr, args in _dockerfile_instructions() if instr == "RUN"]
        assert any("uv sync" in r and "--frozen" in r and "--no-dev" in r for r in runs)
        assert any("--package intake-api" in r for r in runs)

    def test_the_process_is_the_uvicorn_factory(self) -> None:
        cmd = [args for instr, args in _dockerfile_instructions() if instr == "CMD"][-1]
        assert "uvicorn" in cmd and "intake_api.app:create_app" in cmd and "--factory" in cmd
        from intake_api.app import create_app

        assert callable(create_app)

    def test_the_proxy_targets_the_port_uvicorn_listens_on(self) -> None:
        cmd = [args for instr, args in _dockerfile_instructions() if instr == "CMD"][-1]
        port = re.search(r'"--port",\s*"(\d+)"', cmd)
        assert port
        assert re.search(rf"reverse_proxy\s+api:{port.group(1)}\b", _text(CADDYFILE))

    def test_version_stamps_are_the_names_versioninfo_reads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        envs: dict[str, str] = {}
        for instruction, args in _dockerfile_instructions():
            if instruction == "ENV":
                for key, value in re.findall(r"(\w+)=(\S+)", args):
                    envs[key] = value
        by_arg = {
            arg: key
            for key, value in envs.items()
            for arg in ("GIT_SHA", "BUILT_AT")
            if value in (f"${{{arg}}}", f"${arg}")
        }
        assert set(by_arg) == {"GIT_SHA", "BUILT_AT"}
        monkeypatch.setenv(by_arg["GIT_SHA"], "4f1c2e0")
        monkeypatch.setenv(by_arg["BUILT_AT"], "2026-09-26T12:00:00Z")
        version = VersionInfo.from_env()
        assert version.git_sha == "4f1c2e0"
        assert version.built_at == "2026-09-26T12:00:00Z"

    def test_a_build_without_real_stamps_is_refused(self) -> None:
        instructions = _dockerfile_instructions()
        declared = {a for i, a in instructions if i == "ARG"}
        # declared bare: an ARG default would be a stamp nobody supplied
        assert {"GIT_SHA", "BUILT_AT"} <= declared
        guards = [a for i, a in instructions if i == "RUN" and "GIT_SHA" in a and "BUILT_AT" in a]
        assert guards and '"dev"' in guards[0]
        build_args = _service("api")["build"]["args"]
        for arg in ("GIT_SHA", "BUILT_AT"):
            assert REQUIRED_INTERPOLATION.match(str(build_args[arg])), arg

    def test_the_build_context_is_filtered(self) -> None:
        lines = [
            line.strip()
            for line in _text(DOCKERIGNORE).splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert lines[0] == "*", "deny by default, re-include what the image needs"
        for excluded in ("**/.env", "**/.env.*", "**/node_modules", "**/.venv"):
            assert excluded in lines, excluded
        assert "!docs/legal/" in lines

    def test_the_revision_is_stamped_by_git_archive(self) -> None:
        assert _text(REVISION).strip() == "$Format:%H$"
        assert re.search(r"^REVISION\s+export-subst$", _text(GITATTRIBUTES), re.M)


# --- host scripts: behaviour that runs without docker ----------------------------------


class TestHostScripts:
    def test_revision_sha_reads_a_stamped_file(self, tmp_path: Path) -> None:
        stamped = tmp_path / "REVISION"
        stamped.write_text("0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8")
        result = _bash('revision_sha_from_file "$1"', str(stamped), cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "0123456789abcdef0123456789abcdef01234567"

    def test_revision_sha_refuses_an_unstamped_file(self, tmp_path: Path) -> None:
        unstamped = tmp_path / "REVISION"
        unstamped.write_text("$Format:%H$\n", encoding="utf-8")
        result = _bash('revision_sha_from_file "$1"', str(unstamped), cwd=tmp_path)
        assert result.returncode != 0
        assert result.stdout.strip() == ""
        # the function's own refusal, not bash failing to find it
        assert "not stamped" in result.stderr

    @pytest.mark.parametrize("hostname", ["3-91-12-7.sslip.io", "staging.example.org"])
    def test_a_real_hostname_is_accepted(self, hostname: str) -> None:
        assert _bash('validate_hostname "$1"', hostname).returncode == 0

    @pytest.mark.parametrize("hostname", ["", "localhost", "bad_host.sslip.io", "-a.sslip.io"])
    def test_a_bad_hostname_is_refused(self, hostname: str) -> None:
        result = _bash('validate_hostname "$1"', hostname)
        assert result.returncode != 0
        assert "not a public hostname" in result.stderr

    def test_generated_secrets_are_256_bit_hex(self) -> None:
        result = _bash("gen_secret; gen_secret")
        first, second = result.stdout.split()
        assert re.fullmatch(r"[0-9a-f]{64}", first) and first != second

    def test_env_set_upserts_root_only(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        steps = 'env_set "$1" A one; env_set "$1" B two; env_set "$1" A three; env_get "$1" A'
        result = _bash(steps, str(env_file), cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "three"
        assert _text(env_file).splitlines() == ["B=two", "A=three"]
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    def test_every_dev_password_role_is_rekeyed(self) -> None:
        created = set()
        for migration in MIGRATIONS.glob("*.py"):
            created |= set(MIGRATION_ROLE.findall(_text(migration)))
        assert created, "the migrations create login roles; the parser found none"
        table = _role_password_keys()
        assert set(table) == created, "a role would keep its committed dev password"
        assert set(table.values()) <= set(_env_template())
        assert "ALTER ROLE" in _text(LIB)

    def test_init_and_deploy_migrate_and_rekey(self) -> None:
        assert "alembic upgrade head" in _text(LIB)
        for script in (INIT, DEPLOY):
            text = _text(script)
            assert "run_migrations" in text and "rotate_role_passwords" in text, script.name
            code = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("#")
            )
            # nothing touches docker before the root check
            assert code.index("require_root") < code.index("compose "), script.name

    def test_deploy_is_the_idempotent_compose_up_then_probes(self) -> None:
        text = _text(DEPLOY)
        assert "compose up -d --build" in text
        assert "unseal_openbao" in text
        assert "https://" in text

    def test_smoke_probes_the_public_endpoints_and_restarts(self) -> None:
        text = _text(SMOKE)
        for endpoint in ("/healthz", "/readyz", "/metrics", "/version"):
            assert endpoint in text, endpoint
        assert "https://${STAGING_HOSTNAME}" in text
        assert "compose restart api" in text
        assert "compose restart openbao" in text
        for mode in ("env", "write", "read"):
            assert f"staging_probe.py {mode}" in text, mode


# --- the restart probe ------------------------------------------------------------------


class TestStagingProbe:
    def test_the_probe_derives_the_same_dev_prefix(self) -> None:
        assert _load_probe().dev_prefix() == DEV_PREFIX

    def test_the_staging_posture_passes(self) -> None:
        probe = _load_probe()
        assert probe.environment_offences({"INTAKE_ENV": STAGING_ENV}, "transit") == []

    def test_a_dev_gate_a_dev_env_or_a_local_kek_is_an_offence(self) -> None:
        probe = _load_probe()
        gate = api_settings.ENV_DEV_OTP_PEEK
        offences = probe.environment_offences({"INTAKE_ENV": "dev", gate: ""}, PROCESS_LOCAL_KEK)
        assert len(offences) == 3
        assert any(gate in o for o in offences)

    def test_a_record_roundtrips_within_one_process(self) -> None:
        probe = _load_probe()
        cipher = EnvelopeCipher(FileKekProvider())
        probe.read_record(cipher, probe.write_record(cipher))

    def test_negative_control_a_process_local_kek_fails_the_restart(self) -> None:
        """What the restart test exists to catch: a new process with a new
        FileKekProvider cannot open what the old one wrote."""
        probe = _load_probe()
        packed = probe.write_record(EnvelopeCipher(FileKekProvider()))
        with pytest.raises(TamperError):
            probe.read_record(EnvelopeCipher(FileKekProvider()), packed)

    def test_main_refuses_before_building_a_cipher(self) -> None:
        probe = _load_probe()

        def forbidden() -> EnvelopeCipher:
            raise AssertionError("a cipher was built under a refused posture")

        err = io.StringIO()
        code = probe.main(
            ["write"],
            environ={"INTAKE_ENV": STAGING_ENV},
            kek_mode=lambda: PROCESS_LOCAL_KEK,
            cipher_factory=forbidden,
            stdin=io.StringIO(),
            stdout=io.StringIO(),
            stderr=err,
        )
        assert code == 2
        assert "transit" in err.getvalue()

    def test_main_write_then_read_across_one_cipher(self) -> None:
        probe = _load_probe()
        cipher = EnvelopeCipher(FileKekProvider())
        common: dict[str, Any] = {
            "environ": {"INTAKE_ENV": STAGING_ENV},
            "kek_mode": lambda: "transit",
            "cipher_factory": lambda: cipher,
            "stderr": io.StringIO(),
        }
        written = io.StringIO()
        assert probe.main(["write"], stdin=io.StringIO(), stdout=written, **common) == 0
        read_out = io.StringIO()
        code = probe.main(
            ["read"], stdin=io.StringIO(written.getvalue()), stdout=read_out, **common
        )
        assert code == 0
        assert read_out.getvalue().strip() == "restart-probe: decrypted"

    def test_main_read_reports_a_failure_without_content(self) -> None:
        probe = _load_probe()
        err = io.StringIO()
        code = probe.main(
            ["read"],
            environ={"INTAKE_ENV": STAGING_ENV},
            kek_mode=lambda: "transit",
            cipher_factory=lambda: EnvelopeCipher(FileKekProvider()),
            stdin=io.StringIO(probe.write_record(EnvelopeCipher(FileKekProvider()))),
            stdout=io.StringIO(),
            stderr=err,
        )
        assert code == 1
        assert "TamperError" in err.getvalue()

    def test_main_write_reports_an_unreachable_kek_by_class_only(self) -> None:
        """A sealed or unreachable OpenBao surfaces as a class name, not a
        traceback carrying addresses or key names."""
        probe = _load_probe()

        def unreachable() -> EnvelopeCipher:
            raise ConnectionError("openbao at http://openbao:8200 refused")

        err, out = io.StringIO(), io.StringIO()
        code = probe.main(
            ["write"],
            environ={"INTAKE_ENV": STAGING_ENV},
            kek_mode=lambda: "transit",
            cipher_factory=unreachable,
            stdin=io.StringIO(),
            stdout=out,
            stderr=err,
        )
        assert code == 1
        assert err.getvalue().strip() == "restart-probe: encrypt failed (ConnectionError)"
        assert out.getvalue() == ""


# --- INT-325: every credential the API requires outside dev ----------------------------


class TestNonDevCredentials:
    """Outside dev the API refuses to boot when a DB or object-store credential
    variable is missing or empty (INT-325, PR #521). Each one must be a
    host-generated secret in the root-only env file and reach the api with no
    default, or the staging API never starts."""

    def test_the_required_credentials_are_variables_the_api_reads(self) -> None:
        source = "".join(_text(path) for path in API_SOURCES)
        required = _required_credentials()
        assert required
        for name in required:
            assert f'"{name}"' in source, f"the API reads no {name}"

    @pytest.mark.parametrize("variable", _required_credentials())
    def test_compose_passes_each_credential_to_the_api_with_no_default(self, variable: str) -> None:
        env = _environment(_service("api"))
        assert variable in env, f"the api would refuse to boot: {variable} is not passed"
        value = env[variable]
        interpolations = ANY_BRACE_INTERPOLATION.findall(value)
        assert interpolations, f"{variable} is a literal, not a host-generated secret"
        for whole in interpolations:
            assert REQUIRED_INTERPOLATION.match(whole), f"{variable}: {whole} is not required"
        assert not BARE_INTERPOLATION.search(value.replace("$$", "")), variable
        keys = set(REQUIRED_INTERPOLATION_IN.findall(value))
        assert keys <= set(_env_template()) - OWNER_SUPPLIED - DEPLOY_STAMPED, (variable, keys)

    def test_init_generates_every_secret_root_only_and_once(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        first = _generate_env_file(env_file)
        assert first.returncode == 0, first.stderr
        generated = _read_env_file(env_file)
        assert set(generated) == set(_env_template()) - OWNER_SUPPLIED
        for key, value in generated.items():
            assert re.fullmatch(r"[0-9a-f]{64}", value), key
        assert len(set(generated.values())) == len(generated), "each secret is its own"
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
        second = _generate_env_file(env_file)
        assert second.returncode == 0, second.stderr
        assert _read_env_file(env_file) == generated, "a re-run must re-key nothing"

    def test_init_generates_through_the_tested_function(self) -> None:
        code = "\n".join(
            line for line in _text(INIT).splitlines() if not line.lstrip().startswith("#")
        )
        assert "generate_missing_secrets" in code
        assert code.index("prepare_state_dir") < code.index("generate_missing_secrets")
        assert code.index("generate_missing_secrets") < code.index("load_env")

    def test_every_credential_renders_non_empty_from_a_generated_env_file(
        self, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        assert _generate_env_file(env_file).returncode == 0
        values = {**_read_env_file(env_file), "STAGING_HOSTNAME": "3-91-12-7.sslip.io"}
        api_env = _environment(_service("api"))
        for variable in _required_credentials():
            rendered = _render(api_env[variable], values)
            assert rendered, variable
            assert "$" not in rendered, variable
        user = _render(api_env["MINIO_ROOT_USER"], values)
        password = _render(api_env["MINIO_ROOT_PASSWORD"], values)
        assert user != password


# --- the object store: owner decision D1, recorded by INT-347 ---------------------------


class TestObjectStore:
    """The API's documents and WORM audit copies need an S3-compatible store.
    The owner chose its image on 2026-09-26 (owner decision D1), and INT-347
    records it with the licence read from the raw LICENSE blob. lib.sh holds
    the one staging copy of the reference and exports it; compose's ``minio``
    service interpolates it; deploy.sh's first statement refuses an empty or
    unpinned value. The gate therefore checks exactly what compose pulls."""

    def test_lib_exports_the_owner_approved_pin(self) -> None:
        image = _lib_exported("OBJECT_STORE_IMAGE")
        assert image == APPROVED_OBJECT_STORE_IMAGE
        assert PINNED.match(image)

    def test_the_minio_service_runs_exactly_that_image(self) -> None:
        raw = str(_service("minio")["image"])
        match = REQUIRED_INTERPOLATION.match(raw)
        assert match and match.group(1) == "OBJECT_STORE_IMAGE", raw
        assert _object_store_image() == APPROVED_OBJECT_STORE_IMAGE

    def test_the_store_publishes_no_port_and_sits_on_the_internal_network(self) -> None:
        minio = _service("minio")
        assert "ports" not in minio, "the store is reachable from the api only"
        assert "network_mode" not in minio
        assert minio["networks"] == ["backend"]
        assert _compose()["networks"]["backend"].get("internal") is True
        assert "backend" in _service("api")["networks"]

    def test_the_root_pair_is_a_required_host_secret_shared_with_the_api(self) -> None:
        store = _environment(_service("minio"))
        api = _environment(_service("api"))
        secrets = set(_env_template()) - OWNER_SUPPLIED
        for name in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"):
            match = REQUIRED_INTERPOLATION.match(store.get(name, ""))
            assert match and match.group(1) == name, f"minio.{name} is defaulted or literal"
            assert name in secrets
            assert api[name] == store[name], f"the api and the store disagree on {name}"

    def test_the_store_keeps_its_data_on_a_named_volume(self) -> None:
        minio = _service("minio")
        assert minio["command"] == ["server", "/data"]
        data = [v for v in minio["volumes"] if str(v).endswith(":/data")]
        assert data, "the documents and the WORM audit copies must survive a restart"
        assert str(data[0]).split(":")[0] in _compose()["volumes"]

    def test_the_web_console_is_off(self) -> None:
        assert _environment(_service("minio"))["MINIO_BROWSER"] == "off"

    def test_the_api_waits_for_a_healthy_store_and_reaches_it_internally(self) -> None:
        assert _service("minio")["healthcheck"]["test"] == ["CMD", "mc", "ready", "local"]
        assert _service("api")["depends_on"]["minio"] == {"condition": "service_healthy"}
        assert _environment(_service("api"))[API_OBJECT_STORE_ENDPOINT] == "minio:9000"
        source = "".join(_text(path) for path in API_SOURCES)
        assert f'"{API_OBJECT_STORE_ENDPOINT}"' in source, "the API reads no such variable"

    def test_no_bucket_is_pre_created(self) -> None:
        """The API creates both buckets on first use
        (``DocumentStore.ensure_buckets``), the audit bucket with object lock.
        The store enables the lock only at creation, so a bucket pre-created
        here without it would make the API fail closed on WORM."""
        from intake_platform.documents import DocumentStore

        assert "object_lock=True" in inspect.getsource(DocumentStore.ensure_buckets)
        for path in (*SCRIPTS, COMPOSE):
            assert not re.search(r"\bmc\s+mb\b|make_bucket", _text(path)), path.name

    def test_deploy_no_longer_refuses_on_the_object_store(self, tmp_path: Path) -> None:
        result = _run_deploy(tmp_path)
        # it still stops, later and for a host reason: not root, no docker, no env file
        assert result.returncode != 0
        assert "object-store image" not in result.stderr
        assert OBJECT_STORE_ISSUE not in result.stderr
        assert any(
            reason in result.stderr for reason in ("run as root", "missing", "run ./init.sh first")
        ), result.stderr
        assert not (tmp_path / "state").exists()

    def test_the_gate_runs_before_anything_touches_the_host(self) -> None:
        code = "\n".join(
            line for line in _text(DEPLOY).splitlines() if not line.lstrip().startswith("#")
        )
        gate = code.index('require_object_store_image "$OBJECT_STORE_IMAGE"')
        assert gate < code.index("require_root") < code.index("compose ")

    @pytest.mark.parametrize(
        "image",
        [
            "",
            "registry.invalid/object-store:1.0",
            "registry.invalid/object-store@sha256:" + "0" * 64,
            "registry.invalid/object-store:1.0@sha256:" + "0" * 63,
        ],
        ids=["unset", "tag-only", "no-tag", "short-digest"],
    )
    def test_the_gate_refuses_an_unset_or_unpinned_image(self, image: str) -> None:
        result = _bash('require_object_store_image "$1"', image)
        assert result.returncode != 0
        assert OBJECT_STORE_ISSUE in result.stderr

    def test_the_gate_admits_a_digest_pinned_image(self) -> None:
        """Positive control: the gate is a pin check, not a constant refusal."""
        image = "registry.invalid/object-store:1.0@sha256:" + "0" * 64
        assert PINNED.match(image)
        result = _bash('require_object_store_image "$1"', image)
        assert result.returncode == 0, result.stderr

    def test_the_withdrawn_name_scan_recognises_what_it_forbids(self) -> None:
        vendor = "min" + "io"
        pattern = _withdrawn_upstream_image()
        assert pattern.search(f"the upstream {vendor}/{vendor} image is withdrawn")
        assert pattern.search(f"image: {vendor}/mc:RELEASE.x")
        assert not pattern.search(f"https://github.com/{vendor}/{vendor}")
        assert not pattern.search(APPROVED_OBJECT_STORE_IMAGE)

    @pytest.mark.parametrize("path", (*ARTEFACT, RUNBOOK), ids=lambda p: p.name)
    def test_no_staging_file_names_the_withdrawn_image(self, path: Path) -> None:
        """INT-347's tree-wide scan forbids the withdrawn name outside dated
        records, so the artefact stays clean for when both have landed."""
        pattern = _withdrawn_upstream_image()
        hits = [line.strip() for line in _text(path).splitlines() if pattern.search(line)]
        assert not hits, f"{path.name}: {hits}"

    def test_the_runbook_names_the_store_and_the_owner_decision(self) -> None:
        text = _text(RUNBOOK)
        assert "owner decision D1" in text
        assert OBJECT_STORE_ISSUE in text
        assert "depends on INT-347" not in text, "the deploy no longer waits on INT-347"


# --- the runbook -----------------------------------------------------------------------


class TestRunbook:
    def test_the_runbook_carries_the_synthetic_only_warning_and_the_owner_steps(self) -> None:
        text = _text(RUNBOOK)
        for needle in (
            "synthetic",
            "HB-I5",
            "HB-L11",
            "us-east-1",
            "intake-staging-web",
            "sslip.io",
            "allocate-address",
            "aws ssm start-session",
            "git archive",
            "./init.sh",
            "./deploy.sh",
            "./smoke.sh",
        ):
            assert needle in text, needle
