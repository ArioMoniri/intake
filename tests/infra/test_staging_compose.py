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
- OpenBao runs in server mode on file storage, never ``-dev``, and its
  config sets no mlock key, which 2.6 refuses at load;
- because OpenBao can no longer lock its memory, init.sh and deploy.sh
  refuse a host whose active swap is not encrypted, before OpenBao starts;
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
  shows why: a file-dev KEK does not survive a process restart;
- INT-352: the API gets the App Attest and SMS keys the operator sets, each
  with no default, and a host-generated tokenization key; deploy.sh refuses
  an Apple team id without all three SMS keys, so a verified device is never
  told a code was sent that nobody sent;
- INT-352 (audit F18): ``/version``'s third stamp, ``sbom_digest``, is the
  sha256 of an SPDX SBOM that syft, pinned by digest, writes of the built api
  image into the host's release directory, never into the image. compose
  requires it to start the api; no SBOM refuses the deploy; smoke.sh fails a
  ``dev`` in any of the three stamps and a digest that is not the sha256 of
  the SBOM on disk. A docker shim stands in for the host to run that logic.

The host-side run (init.sh, deploy.sh, smoke.sh) belongs to the owner and is
recorded in docs/evidence/INT-345.md and INT-352.md when it happens. Nothing
here claims it ran.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
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
#: INT-421: the admin tier (Keycloak, oauth2-proxy, the console image).
ADMIN_DOCKERFILE = STAGING / "Dockerfile.admin-web"
ADMIN_DOCKERIGNORE = STAGING / "Dockerfile.admin-web.dockerignore"
REALM = STAGING / "keycloak" / "intake-realm.json"
OAUTH2_PROXY_CONFIG = STAGING / "oauth2-proxy" / "alpha.yaml"
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
    ADMIN_DOCKERFILE,
    ADMIN_DOCKERIGNORE,
    REALM,
    OAUTH2_PROXY_CONFIG,
)

PROJECT = "intake-staging"
SERVICES = {
    "api",
    "postgres",
    "redis",
    "openbao",
    "minio",
    "caddy",
    # INT-421: the admin tier
    "keycloak",
    "oauth2-proxy",
    "admin-web",
}
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

#: /version's stamps, set by the host scripts, not by the root-only .env: the
#: commit and build time (build args) and the SBOM digest (a runtime variable).
DEPLOY_STAMPED = {"INTAKE_GIT_SHA", "INTAKE_BUILT_AT", "INTAKE_SBOM_DIGEST"}

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

#: The one template key the owner must supply; init.sh refuses to run without it.
OWNER_SUPPLIED = {"STAGING_HOSTNAME"}

#: INT-352: Apple App Attest (INT-344), read from the API once its base carries
#: INT-344; until then these same names.
APP_ATTEST_KEYS = tuple(
    str(getattr(api_settings, constant, name))
    for constant, name in (
        ("ENV_APP_ATTEST_TEAM_ID", "INTAKE_APP_ATTEST_TEAM_ID"),
        ("ENV_APP_ATTEST_BUNDLE_ID", "INTAKE_APP_ATTEST_BUNDLE_ID"),
        ("ENV_APP_ATTEST_ENVIRONMENT", "INTAKE_APP_ATTEST_ENVIRONMENT"),
    )
)
APP_ATTEST_TEAM_ID = APP_ATTEST_KEYS[0]

#: INT-352: the SMS vendor's three keys, the names the API's Twilio adapter reads.
SMS_KEYS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")

#: Template keys the operator sets by hand in the root-only env file. None is
#: generated, and each may stay empty: the API reads empty as unset and fails
#: closed on it.
#: INT-421: the admin console's source ranges (HB-A16). Empty admits nobody.
ADMIN_ALLOWLIST_KEY = "INTAKE_ADMIN_IP_ALLOWLIST"
OPERATOR_SUPPLIED = {*APP_ATTEST_KEYS, *SMS_KEYS, ADMIN_ALLOWLIST_KEY}

#: INT-421: generated as base64url of 32 bytes (oauth2-proxy's key form),
#: not gen_secret's 64 hex.
COOKIE_SECRET_KEYS = {"OAUTH2_PROXY_COOKIE_SECRET"}
COOKIE_SECRET_FORM = re.compile(r"[A-Za-z0-9_-]{43}")

#: The phone-tokenization key: without it the OTP tier answers 503.
TOKENIZATION_KEY = api_settings.ENV_TOKENIZATION_KEY

#: lib.sh's deploy check: an Apple team id needs all three SMS keys.
SMS_GUARD = "require_sms_with_app_attest"

#: The runbook section that tells the operator which keys to set.
ATTEST_SMS_SECTION = "App Attest and SMS"

#: Values an operator might type, for the guard tests. Neither is a real team
#: id or credential; the refusals must echo neither.
TEAM_ID_VALUE = "ABCDE12345"
OPERATOR_VALUE = "operator-typed-value"

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

#: The config key OpenBao 2.6 refuses outright ("OpenBao has dropped support
#: for mlock"), whatever its value.
MLOCK_KEY = "disable_mlock"

#: lib.sh's host check: active swap must be absent, zram, or dm-crypt backed.
SWAP_GUARD = "require_no_unencrypted_swap"

#: The runbook section the guard's refusal points at.
SWAP_SECTION = "Host memory: swap off or encrypted"

#: The first statement that starts OpenBao, in init.sh and in deploy.sh.
OPENBAO_START = "compose up -d postgres redis openbao"

#: INT-352 (audit F18): the SBOM generator. syft at v1.51.1, the version CI's
#: anchore/sbom-action v0.24.1 runs, pinned by the index digest resolved from
#: Docker Hub's v2 API on 2026-09-27. Apache-2.0, read from the raw LICENSE
#: blob at the image's revision (docs/evidence/INT-352.md). Assembled from its
#: parts, like the object store's reference.
_SBOM_REPOSITORY = "anchore/syft"
_SBOM_TAG = "v1.51.1"
_SBOM_DIGEST = "sha256:95fe0835e5bebc6f8b1f8acef68d47d63d594ef4c0f25c097ff853b23cbac74c"
APPROVED_SBOM_IMAGE = f"{_SBOM_REPOSITORY}:{_SBOM_TAG}@{_SBOM_DIGEST}"

#: The issue a refusal about the SBOM names.
SBOM_ISSUE = "INT-352"

#: The runtime variable ``VersionInfo`` reads for ``/version``'s sbom_digest.
SBOM_STAMP = "INTAKE_SBOM_DIGEST"

#: The form /version's sbom_digest takes: an OCI-style sha256 digest.
SBOM_DIGEST_FORM = re.compile(r"^sha256:[0-9a-f]{64}$")

#: Where a release's SBOM goes when the state dir is the default one: beside
#: the host's state, outside the build context the image is made from.
DEFAULT_RELEASES_DIR = "/etc/intake-staging/releases"

#: A stamp given a default, or "dev" assigned to it: how F18's live
#: ``"dev"`` would come back.
STAMP_FALLBACK = re.compile(
    r"\$\{INTAKE_(?:GIT_SHA|BUILT_AT|SBOM_DIGEST):?-"
    r"|(?:GIT_SHA|BUILT_AT|SBOM_DIGEST)\s*[:=]\s*[\"']?dev\b"
)

#: The one build statement: its SBOM digest cannot exist yet (see lib.sh).
BUILD_STATEMENT = 'INTAKE_SBOM_DIGEST="$SBOM_DIGEST_DURING_BUILD" compose build api'
#: INT-421: the console image, built from the same commit, with the same
#: build-time value (it is not a digest either).
ADMIN_BUILD_STATEMENT = 'INTAKE_SBOM_DIGEST="$SBOM_DIGEST_DURING_BUILD" compose build admin-web'

#: The docker shim's built image and commit, and the SPDX document its syft
#: prints (the shape syft's spdx-json output takes, trimmed).
SHIM_COMMIT = "0123456789abcdef0123456789abcdef01234567"
SHIM_IMAGE_ID = "sha256:" + "ab" * 32
SHIM_SPDX = json.dumps(
    {
        "spdxVersion": "SPDX-2.3",
        "name": f"intake-staging/api:{SHIM_COMMIT}",
        "packages": [{"SPDXID": "SPDXRef-Package-python-uvicorn", "name": "uvicorn"}],
    }
)


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


def _code(path: Path) -> str:
    """A script's statements, comment lines dropped."""
    return "\n".join(line for line in _text(path).splitlines() if not line.lstrip().startswith("#"))


def _shim(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _swap_host(
    tmp_path: Path,
    swaps: list[tuple[str, str]],
    chains: dict[str, list[str]] | None = None,
    *,
    swapon_rc: int = 0,
) -> Path:
    """A bin dir that stands in for the host's util-linux.

    ``swapon`` answers ``--show`` with one ``NAME TYPE`` line per active swap
    area and refuses any other call. ``lsblk`` answers for a device with its
    own TYPE, or, under ``--inverse``, with its TYPE followed by the TYPE of
    every device beneath it, as the real one does."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    listing = tmp_path / "swaps"
    listing.write_text("".join(f"{name} {kind}\n" for name, kind in swaps), encoding="utf-8")
    _shim(
        bin_dir / "swapon",
        'case "$*" in *--show*) ;; *) exit 99 ;; esac\n'
        f"[ {swapon_rc} -eq 0 ] || exit {swapon_rc}\n"
        f'cat "{listing}"\n',
    )
    chain_dir = tmp_path / "chains"
    chain_dir.mkdir()
    for device, types in (chains or {}).items():
        (chain_dir / Path(device).name).write_text("\n".join(types) + "\n", encoding="utf-8")
    _shim(
        bin_dir / "lsblk",
        "inverse=no\n"
        "for arg; do\n"
        '  [ "$arg" = --inverse ] && inverse=yes\n'
        "  device=$arg\n"
        "done\n"
        f'chain="{chain_dir}/$(basename "$device")"\n'
        '[ -f "$chain" ] || exit 32\n'
        'if [ "$inverse" = yes ]; then cat "$chain"; else head -n 1 "$chain"; fi\n',
    )
    return bin_dir


def _run_swap_guard(bin_dir: Path, *, path: str | None = None) -> subprocess.CompletedProcess[str]:
    """lib.sh's swap guard against the shimmed host, in a clean bash."""
    bash = shutil.which("bash")
    assert bash is not None
    return subprocess.run(
        [bash, "-c", f'source "{LIB}"; {SWAP_GUARD}', "lib-test"],
        capture_output=True,
        text=True,
        cwd=bin_dir.parent,
        env={
            "PATH": path or f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(bin_dir.parent),
        },
        check=False,
    )


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

    def test_openbao_config_is_file_storage_behind_one_listener(self) -> None:
        text = _text(OPENBAO_CONFIG)
        assert re.search(r'storage\s+"file"\s*\{[^}]*path\s*=\s*"/openbao/file"', text, re.S)
        assert re.search(r'listener\s+"tcp"\s*\{[^}]*address\s*=\s*"0\.0\.0\.0:8200"', text, re.S)
        assert not re.search(r"^\s*(dev|-dev)", text, re.M)

    def test_openbao_config_carries_no_mlock_key(self) -> None:
        """OpenBao 2.6 dropped memory locking: a config that sets the key at
        all, even to false, is refused at load and the server restart-loops.
        Swap is the host's job instead (TestSwapGuard)."""
        assert not re.search(r"\b" + MLOCK_KEY + r"\b", _text(OPENBAO_CONFIG))

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
        """A generated secret is a required interpolation. An operator key may
        stay empty, so it is its own plain interpolation, never a literal."""
        secretish = re.compile(r"PASSWORD|TOKEN|SECRET|_AUTH$|_KEY$")
        for name, service in _compose()["services"].items():
            for key, value in _environment(service).items():
                if not secretish.search(key):
                    continue
                if key in OPERATOR_SUPPLIED:
                    assert value == f"${{{key}}}", f"{name}.{key}"
                else:
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
        # INT-352: the up runs the image the SBOM describes, never a rebuild
        assert "compose up -d --no-build" in text
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


# --- host swap: OpenBao 2.6 cannot lock its memory ------------------------------------


class TestSwapGuard:
    """OpenBao 2.6 dropped mlock, so an unsealed server's keys, and the API's
    KEK material, can be paged out. init.sh and deploy.sh therefore refuse a
    host whose active swap could reach a disk in the clear, before OpenBao
    starts. Admitted: no swap, zram (compressed RAM), or a device with
    dm-crypt at or beneath it. Everything else, swap files included, is
    refused, and so is a host where the check itself cannot run."""

    def test_lib_defines_the_guard_on_swapon_show(self) -> None:
        lib = _code(LIB)
        assert re.search(rf"^{SWAP_GUARD}\(\) \{{", lib, re.M)
        assert "swapon --show" in lib

    @pytest.mark.parametrize("script", (INIT, DEPLOY), ids=lambda p: p.name)
    def test_the_guard_runs_before_openbao_starts(self, script: Path) -> None:
        code = _code(script)
        assert re.search(rf"^{SWAP_GUARD}$", code, re.M), f"{script.name} never calls the guard"
        guard = code.index(SWAP_GUARD)
        assert code.index("require_root") < guard, "the root check stays first"
        assert guard < code.index("compose "), "nothing touches docker before the guard"
        assert guard < code.index(OPENBAO_START)

    def test_a_host_without_swap_is_admitted(self, tmp_path: Path) -> None:
        result = _run_swap_guard(_swap_host(tmp_path, []))
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        ("device", "chain"),
        [
            ("/dev/zram0", ["disk"]),
            ("/dev/dm-0", ["crypt", "part", "disk"]),
            ("/dev/dm-2", ["lvm", "crypt", "part", "disk"]),
        ],
        ids=["zram", "dm-crypt", "lvm-on-dm-crypt"],
    )
    def test_encrypted_swap_is_admitted(
        self, tmp_path: Path, device: str, chain: list[str]
    ) -> None:
        """Positive control: the guard is an encryption check, not a refusal
        of all swap. LVM on dm-crypt passes only if the guard walks the
        devices beneath the swap device, not just its own type."""
        bin_dir = _swap_host(tmp_path, [(device, "partition")], {device: chain})
        result = _run_swap_guard(bin_dir)
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        ("device", "kind", "chain"),
        [
            ("/dev/nvme0n1p3", "partition", ["part", "disk"]),
            ("/swapfile", "file", None),
            # a file is refused on its kind alone, whatever lsblk answers
            ("/swapfile", "file", ["crypt", "part", "disk"]),
            ("/dev/dm-1", "partition", ["lvm", "part", "disk"]),
            ("/dev/dm-9", "partition", None),
        ],
        ids=[
            "plain-partition",
            "swap-file",
            "swap-file-on-dm-crypt",
            "plain-lvm",
            "unknown-device",
        ],
    )
    def test_unencrypted_swap_is_refused(
        self, tmp_path: Path, device: str, kind: str, chain: list[str] | None
    ) -> None:
        bin_dir = _swap_host(tmp_path, [(device, kind)], {device: chain} if chain else {})
        result = _run_swap_guard(bin_dir)
        assert result.returncode != 0
        # the guard's own refusal, not bash failing to find it
        assert "not encrypted" in result.stderr, result.stderr
        assert device in result.stderr
        assert "docs/runbooks/staging.md" in result.stderr
        assert SWAP_SECTION in result.stderr

    def test_one_clear_area_among_encrypted_ones_is_refused_by_name(self, tmp_path: Path) -> None:
        swaps = [("/dev/zram0", "partition"), ("/dev/xvdb", "partition")]
        chains = {"/dev/zram0": ["disk"], "/dev/xvdb": ["disk"]}
        result = _run_swap_guard(_swap_host(tmp_path, swaps, chains))
        assert result.returncode != 0
        assert "/dev/xvdb" in result.stderr and "/dev/zram0" not in result.stderr

    def test_a_host_without_swapon_is_refused(self, tmp_path: Path) -> None:
        """Fail closed: a check that cannot run is not a pass."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        dirname = shutil.which("dirname")
        assert dirname is not None
        (bin_dir / "dirname").symlink_to(dirname)
        result = _run_swap_guard(bin_dir, path=str(bin_dir))
        assert result.returncode != 0
        assert "cannot tell whether swap is active" in result.stderr, result.stderr

    def test_a_failing_swapon_is_refused(self, tmp_path: Path) -> None:
        bin_dir = _swap_host(tmp_path, [("/dev/zram0", "partition")], swapon_rc=1)
        result = _run_swap_guard(bin_dir)
        assert result.returncode != 0
        assert "cannot tell whether swap is active" in result.stderr, result.stderr

    def test_the_runbook_section_the_refusal_names_exists(self) -> None:
        assert SWAP_SECTION in _text(LIB)
        runbook = _text(RUNBOOK)
        assert re.search(rf"^## {re.escape(SWAP_SECTION)}$", runbook, re.M)
        section = runbook.split(f"## {SWAP_SECTION}", 1)[1].split("\n## ", 1)[0]
        for needle in ("swapon --show", "swapoff", "zram", "dm-crypt", "no swap"):
            assert needle in section, needle


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
        secrets = {k: v for k, v in generated.items() if k not in OPERATOR_SUPPLIED}
        for key, value in secrets.items():
            form = COOKIE_SECRET_FORM if key in COOKIE_SECRET_KEYS else re.compile(r"[0-9a-f]{64}")
            assert form.fullmatch(value), key
        assert len(set(secrets.values())) == len(secrets), "each secret is its own"
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


# --- INT-352: App Attest and SMS reach the API, and fail closed when unset -------------


def _operator_env(tmp_path: Path, values: dict[str, str]) -> Path:
    """A generated env file, plus the owner's hostname and the given values."""
    env_file = tmp_path / ".env"
    result = _generate_env_file(env_file)
    assert result.returncode == 0, result.stderr
    pairs = {**_read_env_file(env_file), "STAGING_HOSTNAME": "3-91-12-7.sslip.io", **values}
    env_file.write_text("".join(f"{k}={v}\n" for k, v in pairs.items()), encoding="utf-8")
    return env_file


def _run_on_env(env_file: Path, function: str) -> subprocess.CompletedProcess[str]:
    """One lib.sh function against a scratch env file."""
    return _bash(f'ENV_FILE="$1"; {function}', str(env_file), cwd=env_file.parent)


class TestAttestAndSms:
    """INT-352. The deployed API gets the Apple App Attest keys (INT-344), the
    SMS vendor's keys and the phone-tokenization key that turns the OTP tier
    on. The operator sets the first two groups by hand, and either may stay
    empty. init.sh generates the tokenization key like every other secret.

    What keeps this fail-closed:
    - an empty operator key reaches the API as empty, which the API reads as
      unset. With no Apple team id every iOS attestation is refused, and
      Android's is refused until HB-A3, so no request reaches SMS delivery;
    - an Apple team id without all three SMS keys would let a genuine device
      through to a delivery adapter that answers "sent" and sends nothing, so
      deploy.sh refuses that pairing before it touches docker."""

    def test_the_template_lists_every_key_with_no_value(self) -> None:
        template = _env_template()
        for key in (*sorted(OPERATOR_SUPPLIED), TOKENIZATION_KEY):
            assert key in template, key
            assert template[key] == "", key

    @pytest.mark.parametrize("key", sorted(OPERATOR_SUPPLIED))
    def test_compose_passes_each_operator_key_with_no_default(self, key: str) -> None:
        """Exactly `${KEY}`: no default, and not required either, so an empty
        key neither stops compose nor becomes a value the API would trust."""
        assert _environment(_service("api")).get(key) == f"${{{key}}}", key
        for name in SERVICES - {"api"}:
            assert key not in _environment(_service(name)), (name, key)

    def test_compose_passes_the_tokenization_key_as_a_required_secret(self) -> None:
        match = REQUIRED_INTERPOLATION.match(
            _environment(_service("api")).get(TOKENIZATION_KEY, "")
        )
        assert match and match.group(1) == TOKENIZATION_KEY
        generated = set(_env_template()) - OWNER_SUPPLIED - OPERATOR_SUPPLIED
        assert TOKENIZATION_KEY in generated, "generated on the host, never templated"
        for name in SERVICES - {"api"}:
            assert TOKENIZATION_KEY not in _environment(_service(name)), name

    def test_init_generates_the_tokenization_key_and_leaves_operator_keys_empty(
        self, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        result = _generate_env_file(env_file)
        assert result.returncode == 0, result.stderr
        generated = _read_env_file(env_file)
        assert re.fullmatch(r"[0-9a-f]{64}", generated[TOKENIZATION_KEY])
        for key in OPERATOR_SUPPLIED:
            assert generated[key] == "", f"{key} must be the operator's, never generated"

    def test_a_rerun_of_init_keeps_what_the_operator_set(self, tmp_path: Path) -> None:
        env_file = _operator_env(
            tmp_path, {APP_ATTEST_TEAM_ID: TEAM_ID_VALUE, SMS_KEYS[2]: OPERATOR_VALUE}
        )
        before = _read_env_file(env_file)
        result = _generate_env_file(env_file)
        assert result.returncode == 0, result.stderr
        assert _read_env_file(env_file) == before

    def test_load_env_admits_empty_operator_keys(self, tmp_path: Path) -> None:
        result = _run_on_env(_operator_env(tmp_path, {}), "load_env")
        assert result.returncode == 0, result.stderr

    def test_load_env_still_refuses_an_empty_tokenization_key(self, tmp_path: Path) -> None:
        """Negative control: the operator keys are exempt, the secrets are not.
        A host initialised before INT-352 lacks the key and is told to re-run
        init.sh, which fills in only what is missing."""
        result = _run_on_env(_operator_env(tmp_path, {TOKENIZATION_KEY: ""}), "load_env")
        assert result.returncode != 0
        assert f"{TOKENIZATION_KEY} is empty" in result.stderr, result.stderr
        assert "./init.sh" in result.stderr

    def test_deploy_runs_the_sms_guard_after_load_env_and_before_compose(self) -> None:
        assert re.search(rf"^{SMS_GUARD}\(\) \{{", _code(LIB), re.M)
        code = _code(DEPLOY)
        assert re.search(rf"^{SMS_GUARD}$", code, re.M), "deploy.sh never calls the guard"
        assert code.index("load_env") < code.index(SMS_GUARD) < code.index("compose ")

    @pytest.mark.parametrize("sms", [False, True], ids=["no-sms", "sms"])
    def test_no_team_id_is_admitted_either_way(self, tmp_path: Path, sms: bool) -> None:
        values = {key: OPERATOR_VALUE for key in SMS_KEYS} if sms else {}
        result = _run_on_env(_operator_env(tmp_path, values), SMS_GUARD)
        assert result.returncode == 0, result.stderr

    def test_a_team_id_with_all_three_sms_keys_is_admitted(self, tmp_path: Path) -> None:
        """Positive control: the guard is a pairing check, not a refusal of
        App Attest."""
        values = {APP_ATTEST_TEAM_ID: TEAM_ID_VALUE, **{key: OPERATOR_VALUE for key in SMS_KEYS}}
        result = _run_on_env(_operator_env(tmp_path, values), SMS_GUARD)
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        "missing", [*((key,) for key in SMS_KEYS), SMS_KEYS], ids=[*SMS_KEYS, "all"]
    )
    def test_a_team_id_without_every_sms_key_is_refused(
        self, tmp_path: Path, missing: tuple[str, ...]
    ) -> None:
        values = {APP_ATTEST_TEAM_ID: TEAM_ID_VALUE}
        values.update({key: OPERATOR_VALUE for key in SMS_KEYS if key not in missing})
        result = _run_on_env(_operator_env(tmp_path, values), SMS_GUARD)
        assert result.returncode != 0
        for key in missing:
            assert key in result.stderr, (key, result.stderr)
        assert ATTEST_SMS_SECTION in result.stderr
        assert TEAM_ID_VALUE not in result.stderr, "the refusal echoes no value"
        assert OPERATOR_VALUE not in result.stderr, "the refusal echoes no value"

    def test_the_runbook_tells_the_operator_what_to_set(self) -> None:
        runbook = _text(RUNBOOK)
        assert re.search(rf"^## {ATTEST_SMS_SECTION}$", runbook, re.M)
        section = runbook.split(f"## {ATTEST_SMS_SECTION}", 1)[1].split("\n## ", 1)[0]
        needles = (*sorted(OPERATOR_SUPPLIED), TOKENIZATION_KEY, "/etc/intake-staging/.env")
        for needle in (*needles, "./deploy.sh", "./init.sh", "synthetic"):
            assert needle in section, needle


# --- INT-352 (audit F18): /version's sbom_digest ----------------------------------------


def _sbom_host(tmp_path: Path, mode: str = "ok") -> Path:
    """A bin dir whose ``docker`` stands in for the host's.

    - ``image inspect`` names SHIM_IMAGE_ID, or fails once <tmp>/no-image exists;
    - ``image save --output F`` writes an archive to F;
    - ``run`` plays syft by <tmp>/syft-mode: ok (the SPDX document), fail
      (exit 3), empty (exit 0, no output) or not-spdx (exit 0, another format);
    - ``compose`` records the INTAKE_SBOM_DIGEST it was given.

    Every call is appended to <tmp>/docker.log."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "syft-mode").write_text(mode, encoding="utf-8")
    (tmp_path / "spdx.json").write_text(SHIM_SPDX, encoding="utf-8")
    body = (
        'printf "%s\\n" "$*" >>"@TMP@/docker.log"\n'
        'case "$1" in\n'
        "  compose)\n"
        '    printf "compose-digest=%s\\n" "${INTAKE_SBOM_DIGEST-unset}" >>"@TMP@/docker.log"\n'
        "    exit 0 ;;\n"
        "  image)\n"
        '    case "$2" in\n'
        '      inspect) [ -e "@TMP@/no-image" ] && exit 1; echo "@IMAGE@"; exit 0 ;;\n'
        "      save)\n"
        "        while [ $# -gt 0 ]; do\n"
        '          if [ "$1" = --output ]; then printf archive >"$2"; exit 0; fi\n'
        "          shift\n"
        "        done\n"
        "        exit 2 ;;\n"
        "    esac ;;\n"
        "  run)\n"
        '    case "$(cat "@TMP@/syft-mode")" in\n'
        '      ok) cat "@TMP@/spdx.json"; exit 0 ;;\n'
        '      fail) echo "syft: cannot read the archive" >&2; exit 3 ;;\n'
        "      empty) exit 0 ;;\n"
        '      not-spdx) echo \'{"bomFormat": "CycloneDX"}\'; exit 0 ;;\n'
        "    esac ;;\n"
        "esac\n"
        "exit 97\n"
    )
    _shim(
        bin_dir / "docker", body.replace("@TMP@", str(tmp_path)).replace("@IMAGE@", SHIM_IMAGE_ID)
    )
    return bin_dir


def _run_release(tmp_path: Path, bin_dir: Path, script: str) -> subprocess.CompletedProcess[str]:
    """lib.sh against the shimmed host, with a scratch state dir and a commit."""
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {script}', "lib-test"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(tmp_path),
            "INTAKE_STAGING_STATE_DIR": str(tmp_path / "state"),
            "INTAKE_GIT_SHA": SHIM_COMMIT,
        },
        check=False,
    )


def _docker_calls(tmp_path: Path, verb: str) -> list[str]:
    log = tmp_path / "docker.log"
    lines = _text(log).splitlines() if log.exists() else []
    return [line for line in lines if line.startswith(f"{verb} ")]


def _release_dir(tmp_path: Path) -> Path:
    return tmp_path / "state" / "releases" / SHIM_COMMIT


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


#: A /version body with all three stamps real.
STAMPED_VERSION = {
    "git_sha": SHIM_COMMIT,
    "built_at": "2026-09-27T10:00:00Z",
    "sbom_digest": "sha256:" + "cd" * 32,
}


def _verdict(
    body: str, sha: str = SHIM_COMMIT, sbom: str = STAMPED_VERSION["sbom_digest"]
) -> subprocess.CompletedProcess[str]:
    """smoke.sh's /version check, as lib.sh defines it."""
    return _bash('version_verdict "$1" "$2" <<<"$3"', sha, sbom, body)


class TestSbomStamp:
    """INT-352, audit F18: the live API reported ``sbom_digest: "dev"``.

    deploy.sh (and init.sh, which builds too) builds the api image, has syft
    write an SPDX SBOM of it into the host's release directory, outside the
    build context, and passes the file's sha256 to the api container as
    ``INTAKE_SBOM_DIGEST``, beside the git_sha and built_at build stamps.
    compose requires it, so no api container starts without one. syft runs
    from a digest-pinned image, offline, on a saved archive of the image,
    never on the docker socket. If it fails, or writes anything but an SPDX
    document, the deploy stops. smoke.sh reads the SBOM on disk and fails a
    ``dev`` in any stamp, a digest that is not that file's sha256, and an api
    container that runs another image."""

    # --- the pinned generator ---

    def test_lib_pins_syft_by_digest(self) -> None:
        result = _bash('printf "%s" "$SBOM_IMAGE"')
        assert result.stdout == APPROVED_SBOM_IMAGE
        assert PINNED.match(result.stdout)

    @pytest.mark.parametrize(
        "image",
        [
            "",
            f"{_SBOM_REPOSITORY}:{_SBOM_TAG}",
            f"{_SBOM_REPOSITORY}@{_SBOM_DIGEST}",
            f"{_SBOM_REPOSITORY}:{_SBOM_TAG}@{_SBOM_DIGEST[:-1]}",
        ],
        ids=["unset", "tag-only", "no-tag", "short-digest"],
    )
    def test_the_syft_gate_refuses_an_unset_or_unpinned_image(self, image: str) -> None:
        result = _bash('require_sbom_image "$1"', image)
        assert result.returncode != 0
        assert SBOM_ISSUE in result.stderr

    def test_the_syft_gate_admits_a_digest_pinned_image(self) -> None:
        """Positive control: the gate is a pin check, not a constant refusal."""
        result = _bash('require_sbom_image "$1"', APPROVED_SBOM_IMAGE)
        assert result.returncode == 0, result.stderr

    def test_deploy_checks_the_syft_pin_before_it_touches_the_host(self) -> None:
        code = _code(DEPLOY)
        gate = code.index('require_sbom_image "$SBOM_IMAGE"')
        assert code.index("require_object_store_image") < gate < code.index("require_root")

    def test_an_unpinned_syft_never_runs(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        result = _run_release(
            tmp_path, bin_dir, f'SBOM_IMAGE="{_SBOM_REPOSITORY}:latest"; stamp_sbom'
        )
        assert result.returncode != 0
        assert SBOM_ISSUE in result.stderr
        assert not _docker_calls(tmp_path, "run")

    # --- compose and the image ---

    def test_compose_passes_the_digest_to_the_api_as_a_required_stamp(self) -> None:
        match = REQUIRED_INTERPOLATION.match(_environment(_service("api")).get(SBOM_STAMP, ""))
        assert match and match.group(1) == SBOM_STAMP
        for name in SERVICES - {"api"}:
            assert SBOM_STAMP not in _environment(_service(name)), name
        assert SBOM_STAMP not in _env_template(), "a release stamp, not a host secret"

    def test_the_stamp_is_the_name_versioninfo_reads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        digest = STAMPED_VERSION["sbom_digest"]
        monkeypatch.setenv(SBOM_STAMP, digest)
        assert VersionInfo.from_env().sbom_digest == digest
        monkeypatch.delenv(SBOM_STAMP)
        # what F18 saw live: nothing passed it, so compose must require it
        assert VersionInfo.from_env().sbom_digest == "dev"

    def test_the_sbom_never_enters_the_image(self) -> None:
        """The SBOM describes the image, so the image cannot carry it: no
        build arg, no ENV or LABEL, and the file lands outside the context."""
        assert "SBOM" not in str(_service("api")["build"]).upper()
        for instruction, args in _dockerfile_instructions():
            assert "SBOM" not in args.upper(), (instruction, args)
        releases = _bash('printf "%s" "$RELEASES_DIR"').stdout
        assert releases == DEFAULT_RELEASES_DIR
        assert not Path(releases).is_relative_to(REPO)

    @pytest.mark.parametrize("path", (*SCRIPTS, COMPOSE, DOCKERFILE), ids=lambda p: p.name)
    def test_no_stamp_falls_back_to_dev(self, path: Path) -> None:
        hits = [line.strip() for line in _text(path).splitlines() if STAMP_FALLBACK.search(line)]
        assert not hits, f"{path.name}: {hits}"

    @pytest.mark.parametrize(
        "line",
        [
            "INTAKE_SBOM_DIGEST: ${INTAKE_SBOM_DIGEST:-dev}",
            "INTAKE_SBOM_DIGEST: ${INTAKE_SBOM_DIGEST-}",
            'export INTAKE_SBOM_DIGEST="dev"',
            "INTAKE_SBOM_DIGEST: dev",
            "ENV INTAKE_GIT_SHA=dev",
        ],
    )
    def test_the_fallback_scan_recognises_what_it_forbids(self, line: str) -> None:
        assert STAMP_FALLBACK.search(line)

    def test_the_fallback_scan_passes_the_required_form(self) -> None:
        """Near-miss control: the required interpolation is not a fallback."""
        assert not STAMP_FALLBACK.search(f"{SBOM_STAMP}: ${{{SBOM_STAMP}:?set by deploy.sh}}")
        assert not STAMP_FALLBACK.search(f"{SBOM_STAMP}=development-tier")

    # --- the scripts' order ---

    @pytest.mark.parametrize("script", (INIT, DEPLOY), ids=lambda p: p.name)
    def test_the_image_is_built_and_stamped_before_any_compose_call(self, script: Path) -> None:
        code = _code(script)
        assert re.search(r"^build_api_image$", code, re.M), script.name
        assert re.search(r"^stamp_sbom$", code, re.M), script.name
        order = [code.index(step) for step in ("stamp_revision", "build_api_image", "stamp_sbom")]
        assert order == sorted(order)
        assert order[-1] < code.index("compose "), "compose needs the digest to load"

    def test_the_only_build_is_build_api_image(self) -> None:
        builds = [
            line.strip()
            for path in SCRIPTS
            for line in _code(path).splitlines()
            if re.search(r"\bcompose build\b", line)
        ]
        assert builds == [BUILD_STATEMENT, ADMIN_BUILD_STATEMENT]

    def test_deploy_runs_exactly_the_image_the_sbom_describes(self) -> None:
        ups = re.findall(r"^compose up .*$", _code(DEPLOY), re.M)
        assert "--no-build" in ups[-1].split()
        assert not [up for up in ups if "--build" in up.split()], (
            "a rebuild is not the SBOM's image"
        )

    def test_smoke_reads_the_stamp_from_disk_and_checks_it(self) -> None:
        code = _code(SMOKE)
        assert re.search(r"^stamp_sbom_from_disk$", code, re.M)
        assert code.index("stamp_sbom_from_disk") < code.index("compose ")
        for writer in ("build_api_image", "generate_sbom"):
            assert writer not in code, f"smoke.sh never writes: {writer}"
        assert not re.search(r"^stamp_sbom$", code, re.M)
        assert re.search(r'version_verdict "\$INTAKE_GIT_SHA" "\$\w+"', code)
        assert 'sha256_of "$SBOM_FILE"' in code, "the file on disk, hashed at check time"
        assert "{{.Image}}" in code and '"$API_IMAGE_ID"' in code

    # --- the stamp, run against the shimmed host ---

    def test_the_build_value_reaches_only_the_build_call(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        result = _run_release(
            tmp_path, bin_dir, 'build_api_image; printf "[%s]" "${INTAKE_SBOM_DIGEST-unset}"'
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "[unset]", "bound to the build, never exported"
        builds = _docker_calls(tmp_path, "compose")
        assert len(builds) == 1 and builds[0].endswith(" build api")
        seen = [line for line in _text(tmp_path / "docker.log").splitlines() if "digest=" in line]
        value = seen[0].split("=", 1)[1]
        assert value not in ("", "dev", "unset")
        assert not SBOM_DIGEST_FORM.match(value), "no container could mistake it for a digest"
        assert _verdict(json.dumps({**STAMPED_VERSION, "sbom_digest": value})).returncode != 0

    def test_stamp_writes_the_sbom_beside_the_release_and_exports_its_sha256(
        self, tmp_path: Path
    ) -> None:
        bin_dir = _sbom_host(tmp_path)
        result = _run_release(
            tmp_path, bin_dir, 'stamp_sbom; printf "%s\\n%s\\n" "$INTAKE_SBOM_DIGEST" "$SBOM_FILE"'
        )
        assert result.returncode == 0, result.stderr
        digest, sbom_file = result.stdout.split()
        sbom = Path(sbom_file)
        hex_id = SHIM_IMAGE_ID.removeprefix("sha256:")
        assert sbom == _release_dir(tmp_path) / f"api-{hex_id}.spdx.json"
        assert sbom.read_text(encoding="utf-8") == SHIM_SPDX
        assert digest == _sha256(sbom)
        assert SBOM_DIGEST_FORM.match(digest)
        assert [p.name for p in _release_dir(tmp_path).iterdir()] == [sbom.name], "work removed"
        assert stat.S_IMODE(_release_dir(tmp_path).stat().st_mode) == 0o700

    def test_syft_runs_offline_on_a_read_only_archive_never_the_socket(
        self, tmp_path: Path
    ) -> None:
        bin_dir = _sbom_host(tmp_path)
        assert _run_release(tmp_path, bin_dir, "stamp_sbom").returncode == 0
        saves = _docker_calls(tmp_path, "image")
        assert [s for s in saves if s.startswith("image save ")], saves
        assert saves[-1].endswith(f"intake-staging/api:{SHIM_COMMIT}")
        (run,) = _docker_calls(tmp_path, "run")
        args = run.split()
        assert APPROVED_SBOM_IMAGE in args
        assert "--network none" in run and "--cap-drop ALL" in run
        assert re.search(r"image\.tar:/in/image\.tar:ro(\s|$)", run)
        assert "docker-archive:/in/image.tar" in args
        assert "spdx-json" in args
        assert "docker.sock" not in _text(tmp_path / "docker.log")

    @pytest.mark.parametrize("mode", ["fail", "empty", "not-spdx"])
    def test_no_sbom_refuses_the_release_and_leaves_nothing(
        self, tmp_path: Path, mode: str
    ) -> None:
        """syft failing refuses the deploy; the near-misses, a syft that
        exits 0 with nothing or with another format, refuse it too."""
        bin_dir = _sbom_host(tmp_path, mode)
        result = _run_release(
            tmp_path, bin_dir, 'stamp_sbom; printf "stamped %s\\n" "$INTAKE_SBOM_DIGEST"'
        )
        assert result.returncode != 0
        assert "stamped" not in result.stdout
        assert "refusing" in result.stderr and SBOM_ISSUE in result.stderr
        assert list(_release_dir(tmp_path).iterdir()) == [], "no SBOM and no work dir left"

    def test_a_rerun_on_the_same_image_keeps_its_sbom(self, tmp_path: Path) -> None:
        """deploy.sh is idempotent: the same image keeps its SBOM, so the
        digest, and with it the api container, stay as they are. syft would
        fail on the second run here; it is never called."""
        bin_dir = _sbom_host(tmp_path)
        first = _run_release(tmp_path, bin_dir, 'stamp_sbom; printf "%s" "$INTAKE_SBOM_DIGEST"')
        assert first.returncode == 0, first.stderr
        (tmp_path / "syft-mode").write_text("fail", encoding="utf-8")
        second = _run_release(tmp_path, bin_dir, 'stamp_sbom; printf "%s" "$INTAKE_SBOM_DIGEST"')
        assert second.returncode == 0, second.stderr
        assert second.stdout == first.stdout
        assert len(_docker_calls(tmp_path, "run")) == 1

    @pytest.mark.parametrize("function", ["stamp_sbom", "stamp_sbom_from_disk"])
    def test_no_built_image_is_refused(self, tmp_path: Path, function: str) -> None:
        bin_dir = _sbom_host(tmp_path)
        (tmp_path / "no-image").touch()
        result = _run_release(tmp_path, bin_dir, function)
        assert result.returncode != 0
        assert "no api image" in result.stderr
        assert not _docker_calls(tmp_path, "run")

    def test_smoke_reads_the_sbom_deploy_wrote_and_never_writes_one(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        missing = _run_release(tmp_path, bin_dir, "stamp_sbom_from_disk")
        assert missing.returncode != 0
        assert "./deploy.sh" in missing.stderr
        assert not _docker_calls(tmp_path, "run"), "smoke never generates an SBOM"
        stamped = _run_release(tmp_path, bin_dir, 'stamp_sbom; printf "%s" "$INTAKE_SBOM_DIGEST"')
        read = _run_release(
            tmp_path, bin_dir, 'stamp_sbom_from_disk; printf "%s" "$INTAKE_SBOM_DIGEST"'
        )
        assert read.returncode == 0, read.stderr
        assert read.stdout == stamped.stdout

    # --- smoke's /version verdict ---

    def test_a_fully_stamped_version_passes(self) -> None:
        result = _verdict(json.dumps(STAMPED_VERSION))
        assert result.returncode == 0, result.stdout
        for value in STAMPED_VERSION.values():
            assert value in result.stdout

    @pytest.mark.parametrize("field", sorted(STAMPED_VERSION))
    @pytest.mark.parametrize("value", ["dev", "", None], ids=["dev", "empty", "null"])
    def test_an_unstamped_field_fails(self, field: str, value: str | None) -> None:
        result = _verdict(json.dumps({**STAMPED_VERSION, field: value}))
        assert result.returncode != 0
        assert field in result.stdout

    @pytest.mark.parametrize("field", sorted(STAMPED_VERSION))
    def test_a_missing_field_fails(self, field: str) -> None:
        body = {key: value for key, value in STAMPED_VERSION.items() if key != field}
        result = _verdict(json.dumps(body))
        assert result.returncode != 0
        assert field in result.stdout

    def test_a_digest_one_character_off_the_sbom_on_disk_fails(self) -> None:
        """Near-miss: a well-formed digest that is not the file's sha256."""
        near = STAMPED_VERSION["sbom_digest"][:-1] + "e"
        assert SBOM_DIGEST_FORM.match(near)
        result = _verdict(json.dumps({**STAMPED_VERSION, "sbom_digest": near}))
        assert result.returncode != 0
        assert "SBOM on disk" in result.stdout

    def test_another_commit_fails(self) -> None:
        result = _verdict(json.dumps({**STAMPED_VERSION, "git_sha": "f" * 40}))
        assert result.returncode != 0
        assert "git_sha" in result.stdout

    @pytest.mark.parametrize("body", ["", "<html>502</html>", "[]"], ids=["empty", "html", "list"])
    def test_a_body_that_is_not_a_version_object_fails(self, body: str) -> None:
        assert _verdict(body).returncode != 0

    def test_the_runbook_says_where_the_sbom_is_and_what_smoke_checks(self) -> None:
        text = _text(RUNBOOK)
        assert "`sbom_digest` stays `dev`" not in text
        for needle in ("sbom_digest", DEFAULT_RELEASES_DIR, _SBOM_REPOSITORY, "--no-build"):
            assert needle in text, needle


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
