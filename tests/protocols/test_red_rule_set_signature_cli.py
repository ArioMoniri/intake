"""INT-465: the signing helper that runs on both sides of the OpenBao boundary.

Pinned here:
- The committed envelope's payload can be rebuilt byte for byte from the repository,
  so what was signed is exactly what is committed.
- A Transit signature for another key version is refused, and so is anything that is
  not a Transit signature.
- ``verify`` exits 0 for a synthetic tenant and 1 for every other kind (the near miss).
"""

from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from intake_platform.red_signature import (
    COMMITTED_SIGNATURE,
    canonical_payload_bytes,
    load_signature,
)
from intake_platform.red_tenant import TenantKind

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "protocols" / "red_rule_set_signature.py"


def _cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("red_rule_set_signature", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = _cli()


def test_the_committed_payload_is_rebuilt_byte_for_byte_from_the_repository() -> None:
    committed = load_signature(COMMITTED_SIGNATURE)
    assert canonical_payload_bytes(CLI.build_payload()) == canonical_payload_bytes(
        committed.payload
    )


def test_payload_writes_the_canonical_bytes_and_prints_them_as_base64(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "payload.json"
    assert CLI.main(["payload", "--out", str(out)]) == 0
    printed = capsys.readouterr().out.strip()
    assert base64.b64decode(printed) == out.read_bytes()


def test_assemble_rebuilds_the_committed_envelope(tmp_path: Path) -> None:
    committed = load_signature(COMMITTED_SIGNATURE)
    payload = tmp_path / "payload.json"
    payload.write_bytes(canonical_payload_bytes(committed.payload))
    out = tmp_path / "envelope.json"
    transit = f"vault:v1:{committed.signature}"
    args = ["assemble", "--payload", str(payload), "--key-id", committed.key_id]
    assert CLI.main([*args, "--transit", transit, "--out", str(out)]) == 0
    assert load_signature(out) == committed


@pytest.mark.parametrize(
    ("transit", "message"),
    [
        ("vault:v2:" + "A" * 86 + "==", "key version 2"),
        ("not-a-transit-signature", "not a Transit signature"),
    ],
)
def test_a_signature_for_another_version_or_shape_is_refused(transit: str, message: str) -> None:
    committed = load_signature(COMMITTED_SIGNATURE)
    with pytest.raises(ValueError, match=message):
        CLI.envelope_from_transit(committed.payload, key_id=committed.key_id, transit=transit)


def test_verify_accepts_synthetic_and_refuses_every_other_kind(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert CLI.main(["verify", "--tenant-kind", "synthetic"]) == 0
    assert capsys.readouterr().out.strip() == "verified"
    for kind in (kind for kind in TenantKind if kind is not TenantKind.SYNTHETIC):
        assert CLI.main(["verify", "--tenant-kind", kind.value]) == 1
        assert capsys.readouterr().out.strip() == "refused: key_scope_not_admitted_for_tenant"
