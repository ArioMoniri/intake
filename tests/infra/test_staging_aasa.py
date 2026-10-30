"""INT-580, D34 — the synthetic host serves the apple-app-site-association file.

The owner's decision D34 (files/00_STATE.md, 28 Oct 2026): the app's
``ios.associatedDomains`` is ``webcredentials:3-211-2-143.sslip.io``, and that
host serves ``/.well-known/apple-app-site-association``. iOS honours the
``@<domain> #<code>`` line of an OTP SMS only when both halves agree: the app
declares the domain, and the domain names the app back. Apple fetches the file
over HTTPS, as ``application/json``, and follows no redirect.

The file names the app by its team-prefixed bundle id. The team id is not in
the repository: it is the Apple App ID prefix the operator types into the
host's env file (``INTAKE_APP_ATTEST_TEAM_ID``, ``app_attest_env.sh``, the same
value App Attest verifies against). ``write_aasa`` in ``infra/staging/lib.sh``
renders the file from that value and the bundle id (the env file's, or the
app's committed one), on every deploy. With no team id, or a malformed one, it
writes no file and the route answers 404: fail closed, nothing invented.

Nothing here boots a container: the Caddyfile and compose.yaml are read as
text and YAML, and lib.sh's helpers run in bash against a scratch state dir.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from staging_host_kit import LIB, REPO, STAGING, Host

CADDYFILE = STAGING / "Caddyfile"
COMPOSE = STAGING / "compose.yaml"
DEPLOY = STAGING / "deploy.sh"
APP_JSON = REPO / "apps" / "mobile" / "app.json"
AASA_PATH = "/.well-known/apple-app-site-association"
#: a team id of the right shape for the helpers to render; not anyone's
UNIT_TEAM = "UNITTEAM01"


def _bundle_id() -> str:
    config: dict[str, Any] = json.loads(APP_JSON.read_text(encoding="utf-8"))
    bundle: str = config["expo"]["ios"]["bundleIdentifier"]
    return bundle


def _bash(host: Host, script: str) -> subprocess.CompletedProcess[str]:
    body = f'set -euo pipefail\nsource "{LIB}"\n{script}\n'
    return subprocess.run(  # noqa: S603 — fixed argv, our own script
        ["bash", "-c", body],
        env=host.env(),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _set_env(host: Host, **values: str) -> None:
    lines = [
        line
        for line in host.env_file.read_text(encoding="utf-8").splitlines()
        if line.split("=", 1)[0] not in values
    ]
    lines += [f"{key}={value}" for key, value in values.items()]
    host.env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _aasa_file(host: Host) -> Path:
    return host.state / "well-known" / "apple-app-site-association"


# --- the app declares the domain (D34) ------------------------------------------------------


def test_the_app_declares_the_synthetic_host_for_credentials() -> None:
    config = json.loads(APP_JSON.read_text(encoding="utf-8"))
    assert config["expo"]["ios"]["associatedDomains"] == ["webcredentials:3-211-2-143.sslip.io"]


# --- the document lib.sh renders ------------------------------------------------------------


def test_the_document_names_the_team_prefixed_bundle_id(tmp_path: Path) -> None:
    host = Host(tmp_path)
    result = _bash(host, f'aasa_document "{UNIT_TEAM}" "{_bundle_id()}"')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "webcredentials": {"apps": [f"{UNIT_TEAM}.{_bundle_id()}"]}
    }


@pytest.mark.parametrize(
    ("team", "bundle"),
    [
        ("", "com.ariomoniri.intakemobile"),  # no team id: nothing to name
        ("unitteam01", "com.ariomoniri.intakemobile"),  # Apple's ids are upper case
        ("UNITTEAM0", "com.ariomoniri.intakemobile"),  # nine characters
        ("UNITTEAM01", "intakemobile"),  # a bundle id has a dot
        ("UNITTEAM01", 'com.x"],"y'),  # nothing that could break out of the JSON
    ],
)
def test_a_missing_or_malformed_id_renders_nothing(tmp_path: Path, team: str, bundle: str) -> None:
    host = Host(tmp_path)
    result = _bash(host, f"aasa_document '{team}' '{bundle}'")
    assert result.returncode != 0
    assert result.stdout == ""


# --- write_aasa: on every deploy, from the env file, fail closed -----------------------------


def test_a_host_with_its_team_id_serves_the_file(tmp_path: Path) -> None:
    host = Host(tmp_path)
    _set_env(host, INTAKE_APP_ATTEST_TEAM_ID=UNIT_TEAM)
    result = _bash(host, "write_aasa")
    assert result.returncode == 0, result.stderr
    document = json.loads(_aasa_file(host).read_text(encoding="utf-8"))
    # the bundle id defaults to the app's committed one
    assert document == {"webcredentials": {"apps": [f"{UNIT_TEAM}.{_bundle_id()}"]}}
    assert _aasa_file(host).stat().st_mode & 0o777 == 0o644, "caddy reads it as another user"
    assert UNIT_TEAM not in result.stdout + result.stderr, "the id is not echoed"


def test_the_env_files_bundle_id_wins(tmp_path: Path) -> None:
    host = Host(tmp_path)
    _set_env(
        host,
        INTAKE_APP_ATTEST_TEAM_ID=UNIT_TEAM,
        INTAKE_APP_ATTEST_BUNDLE_ID="com.ariomoniri.intakemobile.staging",
    )
    assert _bash(host, "write_aasa").returncode == 0
    document = json.loads(_aasa_file(host).read_text(encoding="utf-8"))
    assert document["webcredentials"]["apps"] == [
        f"{UNIT_TEAM}.com.ariomoniri.intakemobile.staging"
    ]


@pytest.mark.parametrize("team", ["", "not-a-team-id"])
def test_no_valid_team_id_serves_no_file(tmp_path: Path, team: str) -> None:
    """Fail closed. A stale file from an earlier team id is removed too, so
    the host never names an app it can no longer vouch for."""
    host = Host(tmp_path)
    _set_env(host, INTAKE_APP_ATTEST_TEAM_ID=UNIT_TEAM)
    assert _bash(host, "write_aasa").returncode == 0
    assert _aasa_file(host).exists()
    _set_env(host, INTAKE_APP_ATTEST_TEAM_ID=team)
    result = _bash(host, "write_aasa")
    assert result.returncode == 0, result.stderr
    assert not _aasa_file(host).exists()
    assert "INTAKE_APP_ATTEST_TEAM_ID" in result.stdout + result.stderr, "it says why"
    assert (host.state / "well-known").is_dir(), "the mount source still exists"


def test_every_deploy_renders_it_before_the_edge_starts() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "\nwrite_aasa\n" in deploy
    final_up = deploy.index("compose up -d --no-build --wait --remove-orphans")
    assert deploy.index("\nwrite_aasa\n") < final_up


# --- the route: caddy serves the file, as JSON, with no redirect ----------------------------


def _site_block() -> str:
    text = CADDYFILE.read_text(encoding="utf-8")
    start = text.index("{$STAGING_HOSTNAME} {")
    end = text.index("\n}\n", start)
    return text[start:end]


def test_caddy_serves_the_file_as_json_from_the_mounted_dir() -> None:
    site = _site_block()
    handle = re.search(r"handle " + re.escape(AASA_PATH) + r" \{(.*?)\n\t\}", site, re.S)
    assert handle, "no route for the association file"
    body = handle.group(1)
    assert re.search(r"root \* /srv/well-known\b", body)
    # the one file, whatever else the rendered dir holds
    assert re.search(r"rewrite \* /apple-app-site-association\b", body)
    assert re.search(r"header Content-Type application/json\b", body)
    assert re.search(r"\bfile_server\b", body)
    # Apple follows no redirect, and the API must not answer it instead
    assert "redir" not in body and "reverse_proxy" not in body
    # everything else still goes to the API
    rest = site[handle.end() :]
    assert re.search(r"handle \{\s*reverse_proxy api:8000\s*\}", rest)


def test_compose_mounts_the_rendered_dir_read_only_into_the_edge() -> None:
    compose: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    volumes = compose["services"]["caddy"]["volumes"]
    assert "/etc/intake-staging/well-known:/srv/well-known:ro" in volumes


def test_the_edge_still_reads_only_the_api_for_everything_else() -> None:
    """Near miss: the route is one path. A catch-all file server would expose
    whatever else sits in the state dir."""
    site = _site_block()
    directives = [line.strip() for line in site.splitlines() if not line.strip().startswith("#")]
    assert sum(line.startswith("file_server") for line in directives) == 1
    assert sum(line.startswith("root ") for line in directives) == 1
    assert "/etc/intake-staging" not in site
