"""INT-202 — backups: pgBackRest PITR encrypted, object-store replication, drill.

What this file pins without a container runtime (none exists where the unit
lane runs; the real backup → restore → verify cycle is
``tests/infra/test_backup_restore_integration.py`` in the compose CI job):

- the pgBackRest repository is a local POSIX repository, encrypted at rest
  (aes-256-cbc), with its passphrase nowhere in a committed file (invariant
  14). The first version of this file configured an S3 repository against
  the in-network object store over plain HTTP; pgBackRest speaks only TLS to
  S3 (pgbackrest/pgbackrest#1590), so that repository could never have been
  written. A refusal pins it;
- retention is time-based and has NO value: files/10 §3 states RPO 15 min
  and RTO 4 h and no retention, and HB-I8(a) is open. When the owner answers,
  the value is refused above the ceiling files/06 §1 implies;
- the object-store replication plan never versions or copies a bucket whose
  objects are erasable plaintext (``intake-docs``: DSAR erasure deletes the
  bytes, files/06 §3), and names no second location (HB-I8(b));
- the drill never restores into the workspace (INT-315), never projects a
  column, restores from a read-only repository into a network-less scratch
  cluster with archiving off, and stops at a point in time;
- the entry points exist, are strict bash, and the dry run runs here.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
from intake_platform.backup import (
    RESTORE_PGDATA,
    RESTORE_TARGET,
    BackupConfigError,
    PgBackRestConfig,
    ReplicationPlan,
    RestoreTargetInsideWorkspaceError,
    assert_restore_target_outside_workspace,
    load_pgbackrest_config,
    load_replication_plan,
    plan_restore_drill,
    replication_commands,
    withheld_rules,
)
from intake_platform.backup.cli import main as cli_main
from intake_platform.backup.status import RETENTION_CEILING_DAYS

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra"
BACKUP_DIR = INFRA / "backup"
PGBACKREST_CONF = BACKUP_DIR / "pgbackrest.conf"
REPLICATION_PLAN = BACKUP_DIR / "minio-replication.yaml"
SCRIPTS = REPO / "scripts" / "backup"
DRILL_SCRIPT = SCRIPTS / "restore_drill.sh"
DRILL_LIB = SCRIPTS / "drill_lib.sh"
CI_DRILL = SCRIPTS / "ci_drill.sh"
HOST_BACKUP = INFRA / "staging" / "backup.sh"
POSTGRES_DOCKERFILE = INFRA / "staging" / "Dockerfile.postgres"
STAGING_COMPOSE = INFRA / "staging" / "compose.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "restore-drill.md"

#: The buckets the platform actually writes (services/api app defaults +
#: intake_platform.documents).
PLATFORM_BUCKETS = {"intake-docs", "intake-audit-worm"}

#: Created with S3 object-lock in COMPLIANCE mode by DocumentStore.ensure_buckets.
WORM_BUCKETS = {"intake-audit-worm"}

#: Document bytes are stored in the clear (the SSE slot is plumbed, not wired)
#: and a DSAR erasure deletes them (intake_api.dsar.shred). A versioned or
#: replicated copy with deletes withheld would keep an erased document.
ERASABLE_PLAINTEXT_BUCKETS = {"intake-docs"}

#: Anything shaped like a credential in a committed file is invariant 14's
#: failure mode, whatever it is named.
SECRET_SHAPED = re.compile(
    r"(?:pass|passwd|password|secret|key|token|cipher-pass)\s*[:=]\s*(?!\$|\{\{|\"\$)[^\s#]{6,}",
    re.IGNORECASE,
)

#: Every committed file the backup tier consists of.
BACKUP_TIER = (
    PGBACKREST_CONF,
    REPLICATION_PLAN,
    DRILL_SCRIPT,
    DRILL_LIB,
    CI_DRILL,
    HOST_BACKUP,
    POSTGRES_DOCKERFILE,
)


def _config() -> PgBackRestConfig:
    return load_pgbackrest_config(PGBACKREST_CONF)


def _plan() -> ReplicationPlan:
    return load_replication_plan(REPLICATION_PLAN)


def _code(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


# --- pgBackRest: PITR and encryption at rest -------------------------------------------


class TestPgBackRestConfig:
    def test_the_shipped_config_parses(self) -> None:
        config = _config()
        assert config.stanza == "intake"
        assert config.pg_path == "/var/lib/postgresql/data"

    def test_the_repository_is_encrypted_at_rest(self) -> None:
        """files/10 §3: encrypted with separate keys. The repository's own
        cipher, not the volume's: a copied repository is ciphertext."""
        config = _config()
        assert config.repo_cipher_type == "aes-256-cbc"
        assert config.encrypted_at_rest

    def test_the_cipher_passphrase_is_not_in_the_file(self) -> None:
        text = PGBACKREST_CONF.read_text(encoding="utf-8")
        assert not re.search(r"^\s*repo\d-cipher-pass\s*=", text, re.M)
        assert _config().cipher_pass_env == "PGBACKREST_REPO1_CIPHER_PASS"

    def test_no_credential_literal_anywhere_in_the_backup_tier(self) -> None:
        for path in BACKUP_TIER:
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                assert not SECRET_SHAPED.search(line), f"{path.name}:{lineno}: {line!r}"

    def test_the_repository_is_local_posix_on_its_own_volume(self) -> None:
        """Not the object store over plain HTTP: pgBackRest's S3 driver is TLS
        only, so the S3-over-HTTP repository PR #321 committed could never
        have been written. The second location is a second repository (repo2)
        once HB-I8(b) names it, never the first one pointed elsewhere."""
        config = _config()
        assert config.repo_type == "posix"
        assert config.repo_path == "/var/lib/pgbackrest"

    def test_wal_archiving_is_asynchronous_which_is_what_makes_it_pitr(self) -> None:
        config = _config()
        assert config.archive_async
        assert config.pitr_capable

    def test_retention_is_time_based_and_has_no_value(self) -> None:
        """HB-I8(a): nobody has said how long a backup copy lives. pgBackRest
        with no repo1-retention-full expires nothing — the fail-closed
        direction — and the value, when supplied, is a number of days that
        files/06 §1 bounds (tests/infra/test_backup_status.py)."""
        config = _config()
        assert config.retention_type == "time"
        assert config.retention_full is None
        assert not re.search(
            r"^\s*repo1-retention-full\s*=", PGBACKREST_CONF.read_text("utf-8"), re.M
        )

    def test_file_logging_is_warnings_only(self) -> None:
        """The async archiver logs on every segment; `detail` in a long-lived
        container's writable layer grows without bound."""
        assert _config().log_level_file == "warn"


def _conf(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pgbackrest.conf"
    path.write_text(body, encoding="utf-8")
    return path


GOOD_CONF = """
[global]
repo1-type=posix
repo1-path=/var/lib/pgbackrest
repo1-cipher-type=aes-256-cbc
repo1-retention-full-type=time
archive-async=y
log-level-file=warn

[intake]
pg1-path=/var/lib/postgresql/data
pg1-user=intake
"""


class TestConfigRefusals:
    def test_the_near_miss_control_loads(self, tmp_path: Path) -> None:
        assert load_pgbackrest_config(_conf(tmp_path, GOOD_CONF)).pitr_capable

    def test_an_unencrypted_repository_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("repo1-cipher-type=aes-256-cbc", "repo1-cipher-type=none")
        with pytest.raises(BackupConfigError, match="aes-256-cbc"):
            load_pgbackrest_config(_conf(tmp_path, body))

    @pytest.mark.parametrize(
        "line",
        [
            "repo1-cipher-pass=aVeryLongPassphrase",
            "repo2-cipher-pass=aVeryLongPassphrase",
            "repo1-s3-key=AKIAEXAMPLEKEY",
            "repo2-s3-key-secret=someSecretValue",
        ],
    )
    def test_a_secret_written_into_the_file_is_refused(self, tmp_path: Path, line: str) -> None:
        body = GOOD_CONF.replace("archive-async=y", f"archive-async=y\n{line}")
        with pytest.raises(BackupConfigError, match="OpenBao|host"):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_the_s3_over_plain_http_shape_is_refused(self, tmp_path: Path) -> None:
        """The regression: an S3 repository with TLS verification off."""
        body = GOOD_CONF.replace(
            "repo1-type=posix", "repo1-type=s3\nrepo1-s3-endpoint=minio\nrepo1-storage-verify-tls=n"
        )
        with pytest.raises(BackupConfigError):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_tls_verification_off_is_refused_on_any_repository(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("archive-async=y", "archive-async=y\nrepo2-storage-verify-tls=n")
        with pytest.raises(BackupConfigError, match="verify-tls"):
            load_pgbackrest_config(_conf(tmp_path, body))

    @pytest.mark.parametrize("option", ["repo1-bundle", "repo1-block", "repo2-bundle"])
    def test_a_packed_repository_layout_is_refused(self, tmp_path: Path, option: str) -> None:
        """Measured, not assumed: with bundling and block incremental on, the
        first CI drill found the bundle files did not begin with the cipher
        header every other repository file carries, so the drill could not
        prove the repository is ciphertext file by file."""
        body = GOOD_CONF.replace("archive-async=y", f"archive-async=y\n{option}=y")
        with pytest.raises(BackupConfigError, match="cipher header"):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_a_packed_layout_switched_off_explicitly_is_accepted(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace(
            "archive-async=y", "archive-async=y\nrepo1-bundle=n\nrepo1-block=n"
        )
        assert load_pgbackrest_config(_conf(tmp_path, body)).pitr_capable

    def test_no_global_section_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BackupConfigError, match="global"):
            load_pgbackrest_config(_conf(tmp_path, "[intake]\npg1-path=/x\n"))

    def test_two_stanzas_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BackupConfigError, match="exactly one stanza"):
            load_pgbackrest_config(_conf(tmp_path, GOOD_CONF + "\n[other]\npg1-path=/y\n"))

    def test_count_based_retention_is_refused(self, tmp_path: Path) -> None:
        """A count of backups is not a period. files/06 §1's obligation is a
        period (≤ 6 months), so the window is stated in days."""
        body = GOOD_CONF.replace(
            "repo1-retention-full-type=time", "repo1-retention-full-type=count"
        )
        with pytest.raises(BackupConfigError, match="time"):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_a_retention_within_the_ceiling_is_read_not_ignored(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("archive-async=y", "archive-async=y\nrepo1-retention-full=30")
        assert load_pgbackrest_config(_conf(tmp_path, body)).retention_full == 30

    def test_a_retention_past_the_ceiling_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace(
            "archive-async=y", f"archive-async=y\nrepo1-retention-full={RETENTION_CEILING_DAYS + 1}"
        )
        with pytest.raises(BackupConfigError, match="files/06"):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_a_config_without_async_archiving_is_not_pitr_capable(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("archive-async=y", "archive-async=n")
        config = load_pgbackrest_config(_conf(tmp_path, body))
        assert not config.pitr_capable
        with pytest.raises(BackupConfigError, match="PITR"):
            plan_restore_drill(config)


# --- replication to the second location --------------------------------------------------


class TestReplicationPlan:
    def test_the_plan_parses(self) -> None:
        plan = _plan()
        assert plan.source_alias and plan.target_alias

    def test_it_covers_exactly_the_buckets_the_platform_writes(self) -> None:
        assert _plan().bucket_names == PLATFORM_BUCKETS

    def test_the_worm_bucket_keeps_object_lock_on_the_replica(self) -> None:
        for bucket in WORM_BUCKETS:
            assert _plan().rule_for(bucket).object_lock
        rendered = [" ".join(c) for c in replication_commands(_plan())]
        assert any("--with-lock" in c and "intake-audit-worm" in c for c in rendered)

    def test_delete_replication_is_off_so_a_deletion_cannot_propagate(self) -> None:
        for rule in _plan().rules:
            assert not rule.replicate_delete and not rule.replicate_delete_marker
        rendered = " ".join(" ".join(c) for c in replication_commands(_plan()))
        assert "delete" not in rendered

    def test_an_erasable_plaintext_bucket_is_withheld_not_replicated(self) -> None:
        """Replication needs versioning on the source, and a replica keeps what
        a delete removes. For a bucket of clear-text documents that a DSAR
        erasure deletes (files/06 §3), both would keep the erased bytes. So
        the bucket is withheld — not versioned, not copied — and the refusal
        names why and who decides (HB-I8)."""
        plan = _plan()
        withheld = {rule.bucket for rule, _reason in withheld_rules(plan)}
        assert withheld == ERASABLE_PLAINTEXT_BUCKETS
        for _rule, reason in withheld_rules(plan):
            assert "files/06" in reason and "HB-I8" in reason
        rendered = " ".join(" ".join(c) for c in replication_commands(plan))
        for bucket in ERASABLE_PLAINTEXT_BUCKETS:
            assert bucket not in rendered

    def test_the_pitr_archive_is_not_an_object_store_bucket(self) -> None:
        """The repository is POSIX now; its second copy is a pgBackRest repo2."""
        text = REPLICATION_PLAN.read_text(encoding="utf-8")
        assert "intake-pgbackrest" not in text
        assert "repository_bucket" not in text

    def test_the_second_location_is_named_by_env_with_no_default(self) -> None:
        plan = _plan()
        assert plan.target_endpoint_env == "INTAKE_DR_S3_ENDPOINT"
        assert plan.target_endpoint_default is None
        rendered = " ".join(" ".join(c) for c in replication_commands(plan))
        assert "${INTAKE_DR_S3_ENDPOINT}" in rendered
        assert "http" not in rendered

    def test_no_expiry_is_invented(self) -> None:
        for rule in _plan().rules:
            assert rule.expiry_days is None

    def test_the_rendered_commands_carry_variable_names_not_values(self) -> None:
        for command in replication_commands(_plan()):
            if command[:3] == ["mc", "alias", "set"]:
                assert all(part.startswith("${") for part in command[4:])


def _plan_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "minio-replication.yaml"
    path.write_text(body, encoding="utf-8")
    return path


GOOD_PLAN = """
version: 1
source_alias: a
source_endpoint_env: A
source_access_key_env: B
source_secret_key_env: C
target_alias: d
target_endpoint_env: D
target_access_key_env: E
target_secret_key_env: F
rules:
  - bucket: intake-audit-worm
    object_lock: true
    holds_erasable_plaintext: false
    replicate_existing: true
    replicate_delete: false
    replicate_delete_marker: false
    expiry_days: null
"""


class TestReplicationRefusals:
    def test_the_near_miss_control_loads(self, tmp_path: Path) -> None:
        assert load_replication_plan(_plan_file(tmp_path, GOOD_PLAN)).bucket_names == {
            "intake-audit-worm"
        }

    def test_a_plan_that_replicates_deletions_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_PLAN.replace("replicate_delete: false", "replicate_delete: true")
        with pytest.raises(BackupConfigError, match="deletion"):
            load_replication_plan(_plan_file(tmp_path, body))

    def test_a_plan_that_replicates_delete_markers_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_PLAN.replace("replicate_delete_marker: false", "replicate_delete_marker: true")
        with pytest.raises(BackupConfigError, match="deletion"):
            load_replication_plan(_plan_file(tmp_path, body))

    def test_an_invented_expiry_window_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_PLAN.replace("expiry_days: null", "expiry_days: 30")
        with pytest.raises(BackupConfigError, match="HB-I8"):
            load_replication_plan(_plan_file(tmp_path, body))

    def test_a_rule_that_does_not_say_whether_it_holds_erasable_plaintext_is_refused(
        self, tmp_path: Path
    ) -> None:
        body = GOOD_PLAN.replace("    holds_erasable_plaintext: false\n", "")
        with pytest.raises(BackupConfigError, match="holds_erasable_plaintext"):
            load_replication_plan(_plan_file(tmp_path, body))

    def test_an_empty_plan_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BackupConfigError, match="no replication rules"):
            load_replication_plan(
                _plan_file(tmp_path, GOOD_PLAN.split("rules:")[0] + "rules: []\n")
            )

    def test_asking_for_an_unknown_bucket_raises(self) -> None:
        with pytest.raises(BackupConfigError):
            _plan().rule_for("intake-nothing")


# --- the drill: PHI safety (INT-315) and the plan ---------------------------------------


def _symlinked_cache_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A checkout whose `.cache` is a symlink out of it, and the store it
    points at. INT-315's fixture is the real fresh-worktree deid-model
    workflow rather than an invented one."""
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    model_store = tmp_path / "intake-model-cache"
    model_store.mkdir()
    (workspace / ".cache").symlink_to(model_store, target_is_directory=True)
    return workspace, model_store


class TestDrillPhiSafety:
    def test_a_restore_target_inside_the_workspace_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(REPO / ".cache" / "restore", REPO)
        assert assert_restore_target_outside_workspace(tmp_path / "restore", REPO) is None

    def test_a_relative_target_that_escapes_upward_is_still_checked(self) -> None:
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(
                REPO / "infra" / ".." / ".cache" / "restore", REPO
            )

    def test_a_symlinked_cache_inside_the_worktree_is_still_inside(self, tmp_path: Path) -> None:
        """INT-315: `git status` sees the path, not the link's destination."""
        workspace, model_store = _symlinked_cache_worktree(tmp_path)
        target = workspace / ".cache" / "restore"
        assert target.resolve() == model_store / "restore"
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(target, workspace)

    def test_any_symlinked_directory_inside_the_workspace_is_refused(self, tmp_path: Path) -> None:
        workspace = tmp_path / "worktree"
        (workspace / "infra").mkdir(parents=True)
        elsewhere = tmp_path / "scratch"
        elsewhere.mkdir()
        (workspace / "infra" / "volumes").symlink_to(elsewhere, target_is_directory=True)
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(
                workspace / "infra" / "volumes" / "restore", workspace
            )

    def test_the_workspace_side_is_resolved_too(self, tmp_path: Path) -> None:
        workspace, _ = _symlinked_cache_worktree(tmp_path)
        linked_workspace = tmp_path / "worktree-link"
        linked_workspace.symlink_to(workspace, target_is_directory=True)
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(
                workspace / ".cache" / "restore", linked_workspace
            )
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(workspace / "restore", linked_workspace)
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(linked_workspace / "restore", workspace)

    def test_near_miss_a_genuinely_external_target_is_still_accepted(self, tmp_path: Path) -> None:
        workspace, model_store = _symlinked_cache_worktree(tmp_path)
        sibling = tmp_path / "restore"
        sibling.mkdir()
        assert assert_restore_target_outside_workspace(sibling, workspace) is None
        assert assert_restore_target_outside_workspace(model_store / "restore", workspace) is None
        prefix_sibling = tmp_path / "worktree-restores"
        prefix_sibling.mkdir()
        assert assert_restore_target_outside_workspace(prefix_sibling, workspace) is None
        assert assert_restore_target_outside_workspace(Path(RESTORE_TARGET), workspace) is None

    def test_near_miss_an_upward_escape_that_genuinely_leaves_is_accepted(
        self, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "worktree"
        (workspace / "infra").mkdir(parents=True)
        escapes = workspace / "infra" / ".." / ".." / "restore"
        assert assert_restore_target_outside_workspace(escapes, workspace) is None

    def test_no_restore_writes_patient_data_inside_the_repository(self, tmp_path: Path) -> None:
        workspace, _ = _symlinked_cache_worktree(tmp_path)
        (workspace / "infra").mkdir()
        for candidate in (
            workspace,
            workspace / "restore",
            workspace / ".cache" / "restore",
            workspace / "infra" / ".." / ".cache" / "restore",
            workspace / ".cache" / ".." / "restore",
        ):
            with pytest.raises(RestoreTargetInsideWorkspaceError):
                assert_restore_target_outside_workspace(candidate, workspace)
        for step in plan_restore_drill(_config()):
            for word in step.argv:
                assert str(workspace) not in word
                assert str(REPO) not in word
        assert assert_restore_target_outside_workspace(Path(RESTORE_TARGET), REPO) is None


class TestDrillPlan:
    def _joined(self) -> str:
        return " ".join(" ".join(step.argv) for step in plan_restore_drill(_config()))

    def test_no_step_selects_record_content(self) -> None:
        lowered = self._joined().lower()
        assert "select *" not in lowered
        assert "pg_dump" not in lowered
        for forbidden in ("transcript", "note_text", "tckn", "phone", "full_name"):
            assert forbidden not in lowered

    def test_the_restore_is_to_a_point_in_time_and_promotes(self) -> None:
        restore = next(s for s in plan_restore_drill(_config()) if s.name == "restore")
        assert "--type=time" in restore.argv
        assert "--target-action=promote" in restore.argv
        assert f"--pg1-path={RESTORE_PGDATA}" in restore.argv
        assert RESTORE_PGDATA.startswith(RESTORE_TARGET + "/")

    def test_the_scratch_cluster_never_archives_and_has_no_network(self) -> None:
        """A restored cluster that archived would push a second timeline into
        the production stanza. Archiving off, no listener, no network."""
        scratch = next(s for s in plan_restore_drill(_config()) if s.name == "start_scratch")
        assert "archive_mode=off" in scratch.argv
        assert "listen_addresses=" in scratch.argv
        assert scratch.where == "scratch container, --network none, repository read-only"

    def test_the_order_is_backup_canary_archive_restore_verify_teardown(self) -> None:
        names = [step.name for step in plan_restore_drill(_config())]
        assert names == [
            "newest_backup",
            "headroom",
            "prepare_canary",
            "wait_archived",
            "repository_encrypted",
            "restore",
            "start_scratch",
            "wait_promoted",
            "row_counts",
            "verify_canary",
            "teardown",
            "evidence",
        ]


# --- the entry points --------------------------------------------------------------------


class TestEntryPoints:
    @pytest.mark.parametrize("script", [DRILL_SCRIPT, CI_DRILL, HOST_BACKUP], ids=lambda p: p.name)
    def test_the_scripts_are_executable(self, script: Path) -> None:
        assert script.stat().st_mode & stat.S_IXUSR

    @pytest.mark.parametrize(
        "script", [DRILL_SCRIPT, DRILL_LIB, CI_DRILL, HOST_BACKUP], ids=lambda p: p.name
    )
    def test_the_scripts_are_strict_bash_and_parse(self, script: Path) -> None:
        text = script.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash\n")
        assert "set -euo pipefail" in text
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    def test_the_dry_run_path_runs_here_and_exits_zero(self) -> None:
        result = subprocess.run(
            ["bash", str(DRILL_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=REPO,
            env={**os.environ},
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "restore" in result.stdout
        assert "second location" in result.stdout
        assert "HB-I8" in result.stdout

    def test_the_dry_run_touches_no_container_runtime(self) -> None:
        assert "docker" not in _code(DRILL_SCRIPT)

    def test_sourcing_the_engine_touches_nothing(self) -> None:
        """drill_lib.sh defines functions and one array; every docker call
        sits inside a function, so sourcing it is inert."""
        result = subprocess.run(
            ["bash", "-c", f'source "{DRILL_LIB}"; declare -F run_restore_drill >/dev/null'],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_the_engine_refuses_without_its_adapters(self) -> None:
        result = subprocess.run(
            ["bash", "-c", f'source "{DRILL_LIB}"; run_restore_drill'],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert result.returncode != 0
        assert "drill_primary_exec" in result.stderr

    def test_make_carries_the_config_gate_the_dry_run_and_the_ci_drill(self) -> None:
        makefile = (REPO / "Makefile").read_text(encoding="utf-8")
        for target in ("backup-config-check:", "backup-drill-dry:", "backup-drill-ci:"):
            assert target in makefile
        assert "scripts/backup/ci_drill.sh" in makefile

    def test_the_runbook_states_the_schedule_and_the_owner_steps(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        for needle in (
            "quarterly",
            "backup.sh drill",
            "backup.sh install-schedule",
            "HB-I8",
            "## Backup stale",
            "## Restore drill overdue",
            "escrow",
            "erasure",
        ):
            assert needle in text, needle

    def test_env_example_documents_the_knobs_without_adding_a_key(self) -> None:
        env = (REPO / "env.example").read_text(encoding="utf-8")
        keys = {
            line.split("=", 1)[0]
            for line in env.splitlines()
            if "=" in line and not line.startswith("#")
        }
        assert "PGBACKREST_REPO1_CIPHER_PASS" not in keys
        assert "INTAKE_DR_S3_ENDPOINT" not in keys
        assert "docker-compose.backup.yml" not in env


class TestPlanCli:
    def _run(self, *extra: str, env: dict[str, str] | None = None) -> int:
        return cli_main(
            ["--infra", str(BACKUP_DIR), "--repo-root", str(REPO), *extra], env=env or {}
        )

    def test_it_renders_the_plan_and_the_blocked_second_location(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run() == 0
        out = capsys.readouterr().out
        assert "aes-256-cbc" in out
        assert "posix" in out
        assert "second location   NOT CONFIGURED" in out and "HB-I8(b)" in out
        assert "retention         not set" in out and "HB-I8(a)" in out
        assert "withheld" in out and "intake-docs" in out

    def test_show_replication_renders_only_the_replicable_buckets(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run("--show-replication") == 0
        out = capsys.readouterr().out
        assert "mc replicate add intake-primary/intake-audit-worm" in out
        assert "replicate add intake-primary/intake-docs" not in out

    def test_emit_replication_prints_commands_only(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run("--emit-replication") == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert lines and all(line.startswith("mc ") for line in lines)

    def test_a_missing_config_is_refused_not_crashed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli_main(["--infra", str(tmp_path), "--repo-root", str(REPO)], env={}) == 2
        assert "refused" in capsys.readouterr().out

    def test_it_reads_the_process_environment_when_none_is_passed(self) -> None:
        assert cli_main(["--infra", str(BACKUP_DIR), "--repo-root", str(REPO)]) == 0


def test_the_blocker_row_carries_both_asks_and_the_erasure_finding() -> None:
    """CLAUDE.md: never invent a value; write the ask, name the human, cross-
    reference the HUMAN_BLOCKERS.md row, and continue."""
    text = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| **HB-I8**"))
    lowered = row.lower()
    assert "retention" in lowered
    assert "second location" in lowered
    assert str(RETENTION_CEILING_DAYS) in row
    assert "intake-docs" in row


def test_the_module_entry_point_is_the_same_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    argv = ["intake_platform.backup", "--infra", str(BACKUP_DIR), "--repo-root", str(REPO)]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("intake_platform.backup", run_name="__main__")
    assert exc.value.code == 0


def test_the_dev_compose_overlay_is_gone() -> None:
    """The laptop overlay could run nowhere (Docker is banned on the laptop
    and absent on the GPU server) and stood a local object store up as the
    'second location' — a fake bucket. The drill runs on the host and in CI."""
    assert not (INFRA / "docker-compose.backup.yml").exists()
