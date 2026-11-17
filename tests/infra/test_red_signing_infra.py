"""INT-465: the OpenBao side of the synthetic-only test key, as committed code.

The key lives in OpenBao Transit on the synthetic AWS host (i-0e489e48739f5de98).
``infra/staging/redset_signer.sh`` is the only thing that touches it:
- ``setup`` uses the OpenBao root token exactly once, inside the host's shell. It
  creates the non-exportable ed25519 Transit key and a policy allowing ``sign`` on
  that key only, and mints a scoped token with that policy into a root-only file.
- ``sign`` uses only the scoped token.
- Neither prints a token. Nothing exports or backs up the key.

The API never signs: its own policy is untouched and grants nothing on the key. It
verifies offline against the committed public half. The image ships the life-threat
set it serves and nothing else from files/.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
SIGNER = STAGING / "redset_signer.sh"
SIGNER_POLICY = STAGING / "openbao" / "redset-synthetic-signer-policy.hcl"
API_POLICY = STAGING / "openbao" / "intake-api-policy.hcl"
DOCKERIGNORE = STAGING / "Dockerfile.api.dockerignore"
REGISTRY = REPO / "packages" / "protocols" / "signing" / "trusted_keys.yaml"
SIGNATURE = REPO / "packages" / "protocols" / "signing" / "red_rule_set.synthetic.json"
COMPOSE = STAGING / "compose.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "red-rule-set-signing.md"
KEY = "redset-synthetic-test"
BLOCK = re.compile(r'path\s+"([^"]+)"\s*\{\s*capabilities\s*=\s*\[([^\]]*)\]\s*\}')


def _blocks(path: Path) -> list[tuple[str, set[str]]]:
    return [
        (route, {c.strip().strip('"') for c in caps.split(",") if c.strip()})
        for route, caps in BLOCK.findall(path.read_text(encoding="utf-8"))
    ]


def test_the_signer_policy_allows_sign_on_the_test_key_only() -> None:
    assert _blocks(SIGNER_POLICY) == [(f"transit/sign/{KEY}", {"update"})]


def test_the_api_policy_grants_nothing_on_the_test_key() -> None:
    """Near miss for the line above: the API's token can wrap tenant KEKs, never sign."""
    assert all(KEY not in route for route, _ in _blocks(API_POLICY))


def test_setup_creates_a_non_exportable_ed25519_key_and_a_scoped_token() -> None:
    script = SIGNER.read_text(encoding="utf-8")
    assert f'REDSET_KEY="{KEY}"' in script
    assert "type=ed25519 exportable=false allow_plaintext_backup=false" in script
    assert 'policy write "$REDSET_POLICY" -' in script
    assert 'auth/token/create-orphan id=- policies="$REDSET_POLICY"' in script
    assert "umask 077" in script and "chmod 600" in script


def test_the_root_token_is_read_once_and_never_printed() -> None:
    script = SIGNER.read_text(encoding="utf-8")
    assert script.count("init_field root_token") == 1
    assert "set -x" not in script
    # A token reaches bao only through the docker CLI environment (lib.sh bao_as).
    # A token is printed only into a pipe to bao_as, which hands it to OpenBao on stdin.
    for line in script.splitlines():
        if re.search(r"\b(echo|printf)\b", line) and re.search(
            r"\$\{?(root|token_id|scoped)\b", line
        ):
            assert "| bao_as" in line, line
    assert not re.search(r"BAO_TOKEN=", script)
    # Nothing exports, backs up, rotates or deletes the key.
    for verb in ("transit/export", "transit/backup", "/rotate", "deletion_allowed"):
        assert verb not in script, verb


def test_sign_uses_the_scoped_token_not_the_root_token() -> None:
    script = SIGNER.read_text(encoding="utf-8")
    sign = script[script.index("sign_payload()") :]
    sign = sign[: sign.index("\n}\n")]
    assert "REDSET_TOKEN_FILE" in sign
    assert "init_field" not in sign and "$root" not in sign
    assert f"transit/sign/{KEY}" in sign or "transit/sign/${REDSET_KEY}" in sign


def test_the_registry_names_this_transit_key() -> None:
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    [key] = doc["keys"]
    assert key["key_id"].startswith(f"{KEY}@")


def test_the_image_ships_the_served_life_threat_set_and_no_other_spec_file() -> None:
    lines = [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert "!files/protocols/base.life_threat.yaml" in lines
    assert not [line for line in lines if line in ("!files/", "!files/**", "!files/protocols/")]


def test_the_runbook_explains_the_custody_and_the_scope() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for needle in ("i-0e489e48739f5de98", "non-exportable", "root token", "synthetic", "INT-058"):
        assert needle in text, needle


def test_only_the_synthetic_api_declares_the_synthetic_tenant_and_its_signed_set() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    api = services["api"]["environment"]
    assert api["INTAKE_ENV"] == "staging"
    assert api["INTAKE_API_TRIAGE_TENANT_KIND"] == "synthetic"
    # The host the signature is bound to (review round 2), and the one it names.
    assert api["INTAKE_API_TRIAGE_DEPLOYMENT"] == "i-0e489e48739f5de98"
    signed = yaml.safe_load(SIGNATURE.read_text(encoding="utf-8"))
    assert signed["payload"]["deployment"] == api["INTAKE_API_TRIAGE_DEPLOYMENT"]
    assert (REPO / api["INTAKE_API_TRIAGE_RULES"]).is_file()
    assert REPO / api["INTAKE_API_TRIAGE_SIGNATURE"] == SIGNATURE
    for name, service in services.items():
        if name != "api":
            assert "INTAKE_API_TRIAGE_TENANT_KIND" not in (service.get("environment") or {}), name
