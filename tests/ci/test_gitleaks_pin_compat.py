"""INT-426: .gitleaks.toml must be readable by the gitleaks that CI pins.

The first aws-ci run on main (2 Oct 2026, run 20261002t202525z) failed
`make security` at step [1/12], where gitleaks scans the full history. Under
the pinned gitleaks 8.24.3 it reported 6 findings. That is the version
security.yml's gitleaks-action v2.3.9 runs and that infra/ci/Dockerfile.runner
installs. Four of the 6 are the false positives .gitleaks.toml already
allowlists. The other 2 are a JWT-shaped test fixture with no allowlist row.

The cause is the table name. `[[allowlists]]` (plural) arrived in gitleaks
8.25.0, and 8.24.3 ignores it silently: the same scan under 8.30.1 reports
only the 2 fixture findings. The global `[allowlist]` table is read by both
versions. So the rows move into it unchanged. No pattern is added, widened or
removed, and the near-miss in scripts/ci/gate_selftest.sh still plants a real
literal beside each one.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GITLEAKS_TOML = REPO / ".gitleaks.toml"

# The three reviewed rows, verbatim (INT-019, INT-002). The set may not grow here.
REVIEWED_ROWS = {
    r"deid-tr-ner-v1-[0-9a-f]{8}",
    r"^[A-Za-z0-9_.-]+:\$\$?\{[A-Za-z_][A-Za-z0-9_]*\}$",
    r"^WAF/CrowdSec$",
}


def _pinned_gitleaks_version() -> str:
    dockerfile = (REPO / "infra/ci/Dockerfile.runner").read_text(encoding="utf-8")
    match = re.search(r"^ARG GITLEAKS_VERSION=(\S+)$", dockerfile, re.M)
    assert match, "the runner image must pin gitleaks"
    return match.group(1)


def test_the_pinned_gitleaks_predates_plural_allowlists() -> None:
    # If the pin ever reaches 8.25, the plural form becomes readable. This
    # test then says so, rather than going stale.
    major, minor, _ = (int(p) for p in _pinned_gitleaks_version().split("."))
    assert (major, minor) < (8, 25)


def test_the_allowlist_is_in_the_table_the_pinned_gitleaks_reads() -> None:
    config = tomllib.loads(GITLEAKS_TOML.read_text(encoding="utf-8"))
    assert "allowlists" not in config, (
        "[[allowlists]] needs gitleaks >= 8.25; the pinned 8.24.3 ignores it and every "
        "row in it (measured on main: 6 findings instead of 2)"
    )
    assert config["extend"] == {"useDefault": True}
    assert set(config["allowlist"]["regexes"]) == REVIEWED_ROWS


def test_every_row_is_still_anchored_or_artefact_shaped() -> None:
    # The move must not loosen a row: the two prose and reference rows stay
    # anchored end to end, which is the only scoping that cannot silence a
    # neighbour.
    for row in REVIEWED_ROWS - {r"deid-tr-ner-v1-[0-9a-f]{8}"}:
        assert row.startswith("^") and row.endswith("$"), row
