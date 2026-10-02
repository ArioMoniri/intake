"""INT-202 — the restore drill, run for real: backup → restore → verify.

``scripts/backup/ci_drill.sh`` builds the production host's Postgres image
(``infra/staging/Dockerfile.postgres``: the pinned server plus the pinned
pgBackRest), boots a primary with the exact archiving command the host runs,
takes an encrypted full backup into a POSIX repository, and then runs the
same drill engine (``scripts/backup/drill_lib.sh``) the host's quarterly
timer runs:

1. a synthetic canary is written AFTER the backup, so only WAL replay can
   bring it back; one synthetic subject is crypto-shredded; a sentinel row is
   written after the recovery target;
2. the drill waits for the sentinel's WAL segment to reach the repository on
   the primary's own ``archive_timeout`` — that wait is the observed RPO;
3. every file in the repository must begin with the OpenSSL salted-cipher
   header — the repository is ciphertext;
4. a point-in-time restore from the read-only repository into a scratch
   volume, a network-less scratch cluster with archiving off, promotion —
   the restore time is the observed RTO;
5. counts and checksums of the synthetic rows, the kept subject decrypts,
   the erased subject stays unreadable, the sentinel is absent.

Then a second restore, to the moment BEFORE the erasure, characterises the
window HB-I8 and INT-037's second ask are about: the erased subject is
readable there. That is recorded as a fact, not a pass.

It is marked ``integration`` and runs in the compose CI job
(``make check-integration``), which has Docker and the dev OpenBao with
Transit enabled. It never skips: a restore drill that quietly does not run is
the threat files/10 §9 names for this row — "restores never exercised".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
CI_DRILL = REPO / "scripts" / "backup" / "ci_drill.sh"

#: Building the image and two restores on a CI runner; generous, but bounded.
TIMEOUT_S = 1800


@pytest.fixture(scope="module")
def drill(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    evidence = tmp_path_factory.mktemp("drill-evidence")
    result = subprocess.run(  # noqa: S603 — our own script, fixed argv
        ["bash", str(CI_DRILL), "--evidence-dir", str(evidence), "--characterise-erasure-window"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        env={**os.environ, "DRILL_PYTHON": sys.executable},
        check=False,
    )
    return result, evidence


def test_the_transcript_reaches_the_ci_log(
    drill: tuple[subprocess.CompletedProcess[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """The drill's own output is its evidence of record: printed past pytest's
    capture so the CI log carries it whether the drill passed or not. It holds
    clocks, labels, counts and the evidence JSON — no secret and no row."""
    result, _ = drill
    with capsys.disabled():
        print("\n----- restore drill transcript (stderr) -----")
        print(result.stderr)
        print("----- restore drill transcript (stdout) -----")
        print(result.stdout)
    assert result.stdout or result.stderr


def _record(evidence: Path) -> dict[str, object]:
    records = sorted(evidence.glob("restore-drill-*.json"))
    assert len(records) == 1, [p.name for p in evidence.iterdir()]
    loaded: dict[str, object] = json.loads(records[0].read_text(encoding="utf-8"))
    return loaded


def test_the_drill_script_exits_zero(drill: tuple[subprocess.CompletedProcess[str], Path]) -> None:
    result, _ = drill
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]


def test_the_evidence_record_passes_every_check(
    drill: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    record = _record(drill[1])
    assert record["verdict"] == "pass", record
    assert record["failures"] == []
    checks = record["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values()), checks
    assert record["target"] == "ci"


def test_the_rpo_and_rto_were_measured_inside_their_budgets(
    drill: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    record = _record(drill[1])
    rpo = record["rpo_observed_s"]
    rto = record["restore_seconds"]
    assert isinstance(rpo, int | float) and 0 <= rpo <= 900
    assert isinstance(rto, int) and 0 < rto <= 14400


def test_the_second_location_is_reported_unconfigured(
    drill: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    assert _record(drill[1])["second_location"] == "unconfigured"


def test_a_restore_to_before_the_erasure_resurrects_the_subject(
    drill: tuple[subprocess.CompletedProcess[str], Path],
) -> None:
    """The characterisation, not a pass: with per-field DEKs in the database
    and a per-tenant KEK in OpenBao, a backup taken before an erasure opens
    the erased field when restored to before it. HB-I8 (how long backups
    live) and INT-037's second ask (a per-subject key) are what close it."""
    result, _ = drill
    assert "erasure window: before the erasure the erased subject is readable" in result.stdout
