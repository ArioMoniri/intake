"""INT-202 — backups: pgBackRest PITR encrypted, MinIO replication, restore drill.

What this file can honestly pin, and what it cannot.

The drill's *execution* half needs a Postgres with WAL archiving, a pgBackRest
repository, two MinIO endpoints and a throwaway restore target. files/10 §3
sizes that at more disk and more Docker memory than this host has — HB-I1
(free 80–100 GB of disk) and HB-I2 (raise Docker's RAM allocation) are both
open. So the drill is scripted, its entry points are wired, and this file
pins the half that is decidable without booting anything:

- the pgBackRest configuration parses, encrypts the repository, and carries
  no credential literal (invariant 14 — secrets come from OpenBao);
- the retention policy is **absent on purpose** and the drill refuses to run
  without it, because files/10 §3 and the backlog state RPO 15 min / RTO 4 h
  and state no retention window. A number nobody supplied is not a default
  (CLAUDE.md: never invent a value to unblock yourself);
- the replication plan targets exactly the buckets the platform writes, and
  preserves object-lock parity on the WORM audit bucket;
- the drill plan never restores into the workspace, never asks for record
  content, and its evidence record carries counts, not rows (invariants 3, 6);
- the compose tier is profile-gated, tag-pinned, loopback-bound and literal-
  free, so the shared dev tier is untouched by its presence;
- the shell drill's ``--dry-run`` path runs here, for real, and exits 0.

The restore itself is exercised by ``make backup-drill`` on a host that meets
the preflight. Nothing in this file claims it ran.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.backup import (
    BackupConfigError,
    DrillBlocked,
    DrillStep,
    PgBackRestConfig,
    ReplicationPlan,
    RestoreTargetInsideWorkspaceError,
    RetentionNotConfiguredError,
    assert_restore_target_outside_workspace,
    drill_evidence_skeleton,
    host_preflight,
    load_pgbackrest_config,
    load_replication_plan,
    plan_restore_drill,
    replication_commands,
)
from intake_platform.backup.cli import main as cli_main
from intake_platform.backup.record import build_record, parse_row_counts
from intake_platform.backup.record import main as record_main

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra"
BACKUP_DIR = INFRA / "backup"
PGBACKREST_CONF = BACKUP_DIR / "pgbackrest.conf"
REPLICATION_PLAN = BACKUP_DIR / "minio-replication.yaml"
COMPOSE_PATH = INFRA / "docker-compose.backup.yml"
DRILL_SCRIPT = REPO / "scripts" / "backup" / "restore_drill.sh"
RUNBOOK = REPO / "docs" / "runbooks" / "restore-drill.md"

#: The buckets the platform actually writes (services/api app defaults +
#: intake_platform.documents). A replication plan that names anything else is
#: replicating a bucket nobody fills, or missing one that holds PHI.
PLATFORM_BUCKETS = {"intake-docs", "intake-audit-worm"}

#: The audit bucket is created with S3 object-lock in COMPLIANCE mode
#: (intake_platform.documents.DocumentStore.ensure_buckets). A replica without
#: the lock silently voids the WORM guarantee files/10 §3 relies on.
WORM_BUCKETS = {"intake-audit-worm"}

#: Anything shaped like a credential in a committed file is invariant 14's
#: failure mode, whatever it is named.
SECRET_SHAPED = re.compile(
    r"(?:pass|passwd|password|secret|key|token|cipher-pass)\s*[:=]\s*(?!\$|\{\{|\"\$)[^\s#]{6,}",
    re.IGNORECASE,
)


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return loaded


def _config() -> PgBackRestConfig:
    return load_pgbackrest_config(PGBACKREST_CONF)


def _plan() -> ReplicationPlan:
    return load_replication_plan(REPLICATION_PLAN)


# --- pgBackRest: PITR and encryption at rest -------------------------------------------


class TestPgBackRestConfig:
    def test_the_shipped_config_parses(self) -> None:
        config = _config()
        assert config.stanza
        assert config.pg_path

    def test_the_repository_is_encrypted_at_rest(self) -> None:
        """files/10 §3: PITR archives encrypted with keys separate from the
        data keys. pgBackRest encrypts the repository, not the volume."""
        config = _config()
        assert config.repo_cipher_type == "aes-256-cbc"
        assert config.encrypted_at_rest is True

    def test_the_cipher_passphrase_is_not_in_the_file(self) -> None:
        """Invariant 14: secrets only from OpenBao. The config declares the
        algorithm; the passphrase arrives as PGBACKREST_REPO1_CIPHER_PASS."""
        config = _config()
        assert config.cipher_pass_env == "PGBACKREST_REPO1_CIPHER_PASS"
        text = PGBACKREST_CONF.read_text(encoding="utf-8")
        assert "repo1-cipher-pass=" not in text
        assert "repo1-s3-key=" not in text
        assert "repo1-s3-key-secret=" not in text

    def test_no_credential_literal_anywhere_in_the_backup_tier(self) -> None:
        for path in (PGBACKREST_CONF, REPLICATION_PLAN, COMPOSE_PATH, DRILL_SCRIPT):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                match = SECRET_SHAPED.search(line)
                assert match is None, f"{path.name}:{lineno} carries a credential literal: {line!r}"

    def test_wal_archiving_is_on_which_is_what_makes_it_pitr(self) -> None:
        config = _config()
        assert config.archive_async is True
        assert config.pitr_capable is True

    def test_retention_is_absent_and_that_is_deliberate(self) -> None:
        """files/10 §3 and the INT-202 acceptance state RPO 15 min and RTO 4 h.
        Neither states how many full backups to keep. The config must not
        guess one, and the loader must report the absence."""
        config = _config()
        assert config.retention_full is None
        text = PGBACKREST_CONF.read_text(encoding="utf-8")
        assert not re.search(r"^\s*repo1-retention-full\s*=", text, re.M)

    def test_planning_a_drill_without_retention_fails_closed(self) -> None:
        config = _config()
        with pytest.raises(RetentionNotConfiguredError) as excinfo:
            plan_restore_drill(config, _plan(), retention_full=None)
        message = str(excinfo.value)
        assert "HB-I8" in message, "the refusal must name the blocker row that unblocks it"

    def test_a_supplied_retention_is_accepted_and_carried(self) -> None:
        steps = plan_restore_drill(_config(), _plan(), retention_full=7)
        assert all(isinstance(step, DrillStep) for step in steps)
        assert any("retention" in step.name for step in steps)

    def test_recovery_target_is_a_time_which_is_what_pitr_means(self) -> None:
        steps = plan_restore_drill(_config(), _plan(), retention_full=7)
        restore = next(s for s in steps if s.name == "restore")
        assert "--type=time" in " ".join(restore.argv)
        assert "--target=" in " ".join(restore.argv)


# --- MinIO replication -----------------------------------------------------------------


class TestReplicationPlan:
    def test_the_plan_parses(self) -> None:
        plan = _plan()
        assert plan.source_alias
        assert plan.target_alias

    def test_it_replicates_exactly_the_buckets_the_platform_writes_plus_the_repo(self) -> None:
        plan = _plan()
        assert PLATFORM_BUCKETS <= plan.bucket_names
        assert plan.repository_bucket in plan.bucket_names
        unexpected = plan.bucket_names - PLATFORM_BUCKETS - {plan.repository_bucket}
        assert unexpected == set(), f"replicating buckets nothing writes: {sorted(unexpected)}"

    def test_the_worm_bucket_keeps_object_lock_on_the_replica(self) -> None:
        plan = _plan()
        for name in WORM_BUCKETS:
            rule = plan.rule_for(name)
            assert rule.object_lock is True, f"{name} replica would lose its WORM guarantee"

    def test_delete_replication_is_off_so_a_deletion_cannot_propagate(self) -> None:
        """Ransomware reaching the primary must not reach the copy. files/10
        §9 `backups`: immutable copies defend against ransomware."""
        for rule in _plan().rules:
            assert rule.replicate_delete is False
            assert rule.replicate_delete_marker is False

    def test_the_second_location_is_named_by_env_not_hardcoded(self) -> None:
        """files/10 §3 requires a second location in Türkiye. No site is named
        anywhere in the blueprint, so the plan takes an endpoint from the
        environment and refuses a default."""
        plan = _plan()
        assert plan.target_endpoint_env == "INTAKE_DR_S3_ENDPOINT"
        assert plan.target_endpoint_default is None

    def test_no_retention_or_expiry_rule_is_invented(self) -> None:
        for rule in _plan().rules:
            assert rule.expiry_days is None


# --- the drill: PHI safety and the plan ------------------------------------------------


class TestDrillPhiSafety:
    def test_a_restore_target_inside_the_workspace_is_refused(self, tmp_path: Path) -> None:
        """Invariant 3 + 6: a restored cluster is PHI on disk. It never lands
        anywhere `git status` can see, and never anywhere a later `make check`
        would scan."""
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(REPO / ".cache" / "restore", REPO)
        outside = tmp_path / "restore"
        assert assert_restore_target_outside_workspace(outside, REPO) is None

    def test_a_relative_target_that_escapes_upward_is_still_checked(self, tmp_path: Path) -> None:
        inside = REPO / "infra" / ".." / ".cache" / "restore"
        with pytest.raises(RestoreTargetInsideWorkspaceError):
            assert_restore_target_outside_workspace(inside, REPO)

    def test_no_step_selects_record_content(self) -> None:
        """The verification queries count rows. They never project a column,
        so there is no path by which a patient's words reach the drill log."""
        joined = " ".join(
            " ".join(step.argv) for step in plan_restore_drill(_config(), _plan(), retention_full=7)
        )
        lowered = joined.lower()
        assert "select *" not in lowered
        assert "pg_dump" not in lowered
        for forbidden in ("transcript", "note_text", "tckn", "phone", "full_name"):
            assert forbidden not in lowered

    def test_the_evidence_skeleton_carries_counts_not_rows(self) -> None:
        skeleton = drill_evidence_skeleton(_config(), retention_full=7)
        assert set(skeleton) == {
            "issue",
            "stanza",
            "started_at",
            "finished_at",
            "rto_budget_s",
            "rpo_budget_s",
            "retention_full",
            "recovery_target_time",
            "restore_seconds",
            "row_counts",
            "verdict",
            "host_preflight",
        }
        assert skeleton["issue"] == "INT-202"
        # the two figures the blueprint DOES state, and no third one
        assert skeleton["rpo_budget_s"] == 900
        assert skeleton["rto_budget_s"] == 14400
        assert skeleton["retention_full"] == 7
        assert skeleton["row_counts"] == {}

    def test_the_evidence_skeleton_has_no_identifier_field(self) -> None:
        skeleton = drill_evidence_skeleton(_config(), retention_full=7)
        blob = repr(skeleton).lower()
        for forbidden in ("patient", "tckn", "phone", "email", "name", "mrn"):
            assert forbidden not in blob


class TestHostPreflight:
    def test_this_host_is_blocked_and_says_which_row_unblocks_it(self) -> None:
        """Not a skip and not a shrunken drill: a typed refusal naming the
        open blockers. HB-I1 is disk, HB-I2 is Docker memory."""
        outcome = host_preflight(free_disk_bytes=13 * 1024**3, docker_memory_bytes=15 * 1024**3)
        assert isinstance(outcome, DrillBlocked)
        assert "HB-I1" in outcome.reason
        assert "HB-I2" in outcome.reason

    def test_a_host_that_meets_both_bounds_is_not_blocked(self) -> None:
        assert (
            host_preflight(free_disk_bytes=200 * 1024**3, docker_memory_bytes=32 * 1024**3) is None
        )

    def test_disk_alone_blocks_and_names_only_disk(self) -> None:
        outcome = host_preflight(free_disk_bytes=13 * 1024**3, docker_memory_bytes=32 * 1024**3)
        assert isinstance(outcome, DrillBlocked)
        assert "HB-I1" in outcome.reason
        assert "HB-I2" not in outcome.reason

    def test_memory_alone_blocks_and_names_only_memory(self) -> None:
        outcome = host_preflight(free_disk_bytes=200 * 1024**3, docker_memory_bytes=15 * 1024**3)
        assert isinstance(outcome, DrillBlocked)
        assert "HB-I2" in outcome.reason
        assert "HB-I1" not in outcome.reason


# --- the compose tier ------------------------------------------------------------------


class TestBackupComposeTier:
    def test_it_is_its_own_file_and_the_shared_dev_tier_is_untouched(self) -> None:
        assert COMPOSE_PATH.is_file()
        dev = (INFRA / "docker-compose.dev.yml").read_text(encoding="utf-8")
        assert "pgbackrest" not in dev
        assert "minio-dr" not in dev

    def test_every_service_is_gated_behind_the_backup_profile(self) -> None:
        for name, service in _compose()["services"].items():
            assert service.get("profiles") == ["backup"], (
                f"{name} would start with the plain dev tier"
            )

    def test_every_image_is_tag_pinned(self) -> None:
        for name, service in _compose()["services"].items():
            refs: list[str] = []
            if "image" in service:
                refs.append(str(service["image"]))
            inline = str(service.get("build", {}).get("dockerfile_inline", ""))
            refs.extend(
                line.split()[1]
                for line in inline.splitlines()
                if line.strip().upper().startswith("FROM ")
            )
            assert refs, f"{name} pulls no image and builds nothing"
            for ref in refs:
                assert ":" in ref, f"{name}: unpinned image reference {ref}"
                assert ref.rsplit(":", 1)[1] not in {"latest", ""}, f"{name}: floating tag {ref}"

    def test_every_published_port_binds_loopback(self) -> None:
        for name, service in _compose()["services"].items():
            for published in service.get("ports", []):
                assert str(published).startswith("127.0.0.1:"), (
                    f"{name} publishes {published} on every interface"
                )

    def test_long_running_services_have_a_healthcheck_and_one_shots_say_so(self) -> None:
        for name, service in _compose()["services"].items():
            if "healthcheck" in service:
                continue
            assert service.get("restart") == "no", (
                f'{name} has neither a healthcheck nor an explicit `restart: "no"`'
            )

    def test_the_repository_passphrase_reaches_the_container_from_the_environment(self) -> None:
        env = _compose()["services"]["pgbackrest"]["environment"]
        raw = env if isinstance(env, list) else [f"{k}={v}" for k, v in env.items()]
        joined = "\n".join(str(item) for item in raw)
        assert "PGBACKREST_REPO1_CIPHER_PASS" in joined
        assert "${PGBACKREST_REPO1_CIPHER_PASS" in joined, "must interpolate, never inline"

    def test_every_bind_mount_source_exists(self) -> None:
        for name, service in _compose()["services"].items():
            for volume in service.get("volumes", []):
                source = str(volume).split(":", 1)[0]
                if not source.startswith("."):
                    continue
                assert (INFRA / source).exists(), f"{name} mounts a missing path: {source}"


# --- the entry points ------------------------------------------------------------------


class TestEntryPoints:
    def test_the_drill_script_exists_and_is_executable(self) -> None:
        assert DRILL_SCRIPT.is_file()
        assert DRILL_SCRIPT.stat().st_mode & stat.S_IXUSR

    def test_the_script_is_strict_bash(self) -> None:
        text = DRILL_SCRIPT.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in text

    def test_the_dry_run_path_runs_here_and_exits_zero(self) -> None:
        proc = subprocess.run(  # noqa: S603
            [str(DRILL_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=REPO,
            env={**os.environ, "PGBACKREST_REPO1_RETENTION_FULL": "7"},
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert "restore" in proc.stdout
        assert "INT-202" in proc.stdout

    def test_the_dry_run_touches_no_container_runtime(self) -> None:
        """A dry run that shells out to docker is not a dry run."""
        proc = subprocess.run(  # noqa: S603
            [shutil.which("bash") or "/bin/bash", "-n", str(DRILL_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        body = DRILL_SCRIPT.read_text(encoding="utf-8").split("run_drill()", 1)
        assert len(body) == 2, "the script must separate planning from execution"
        assert "docker" not in body[0], "the dry-run half reaches a container runtime"

    def test_the_real_run_refuses_without_a_retention_window(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "PGBACKREST_REPO1_RETENTION_FULL"}
        proc = subprocess.run(  # noqa: S603
            [str(DRILL_SCRIPT), "--run"],
            capture_output=True,
            text=True,
            cwd=REPO,
            env=env,
            check=False,
        )
        assert proc.returncode != 0
        assert "HB-I8" in (proc.stdout + proc.stderr)

    def test_make_carries_the_manual_entry_point_and_the_ci_hook(self) -> None:
        makefile = (REPO / "Makefile").read_text(encoding="utf-8")
        for target in ("backup-drill:", "backup-drill-dry:", "backup-drill-ci:"):
            assert re.search(rf"^{re.escape(target)}", makefile, re.M), f"no {target} target"

    def test_the_runbook_states_the_quarterly_schedule(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8").lower()
        assert "quarterly" in text
        assert "make backup-drill" in text

    def test_env_example_documents_the_knobs_without_adding_a_key(self) -> None:
        """tests/security/test_openbao_wiring.py allows exactly seven
        uncommented keys. Backup knobs are documented, never assigned."""
        env = (REPO / "env.example").read_text(encoding="utf-8")
        assert "PGBACKREST_REPO1_CIPHER_PASS" in env
        assert "INTAKE_DR_S3_ENDPOINT" in env
        keys = {
            line.split("=", 1)[0]
            for line in env.splitlines()
            if "=" in line and not line.startswith("#")
        }
        assert "PGBACKREST_REPO1_CIPHER_PASS" not in keys
        assert "INTAKE_DR_S3_ENDPOINT" not in keys


def test_the_blocker_row_that_gates_retention_is_recorded() -> None:
    """CLAUDE.md: never invent a value; write the ask, name the human, cross-
    reference the HUMAN_BLOCKERS.md row, and continue."""
    text = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
    assert "HB-I8" in text
    row = next(line for line in text.splitlines() if "HB-I8" in line)
    assert "retention" in row.lower()


# --- negative controls: every refusal, exercised ---------------------------------------


def _conf(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pgbackrest.conf"
    path.write_text(body, encoding="utf-8")
    return path


GOOD_CONF = """
[global]
repo1-type=s3
repo1-s3-bucket=intake-pgbackrest
repo1-cipher-type=aes-256-cbc
archive-async=y

[intake]
pg1-path=/var/lib/postgresql/data
"""


class TestConfigRefusals:
    def test_the_near_miss_control_loads(self, tmp_path: Path) -> None:
        """The fixture the negatives are mutations of must itself be valid,
        or every negative below passes for the wrong reason."""
        config = load_pgbackrest_config(_conf(tmp_path, GOOD_CONF))
        assert config.encrypted_at_rest and config.pitr_capable

    def test_an_unencrypted_repository_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("repo1-cipher-type=aes-256-cbc", "repo1-cipher-type=none")
        with pytest.raises(BackupConfigError, match="encrypted at rest"):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_a_passphrase_written_into_the_file_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace(
            "archive-async=y", "archive-async=y\nrepo1-cipher-pass=whatever-it-says"
        )
        with pytest.raises(BackupConfigError, match="OpenBao"):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_an_access_key_written_into_the_file_is_refused(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("archive-async=y", "archive-async=y\nrepo1-s3-key=whatever")
        with pytest.raises(BackupConfigError, match="OpenBao"):
            load_pgbackrest_config(_conf(tmp_path, body))

    def test_no_global_section_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BackupConfigError, match="global"):
            load_pgbackrest_config(_conf(tmp_path, "[intake]\npg1-path=/x\n"))

    def test_two_stanzas_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BackupConfigError, match="exactly one stanza"):
            load_pgbackrest_config(_conf(tmp_path, GOOD_CONF + "\n[other]\npg1-path=/y\n"))

    def test_a_supplied_retention_in_the_file_is_read_not_ignored(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("archive-async=y", "archive-async=y\nrepo1-retention-full=9")
        assert load_pgbackrest_config(_conf(tmp_path, body)).retention_full == 9

    def test_a_config_without_archiving_is_not_pitr_capable(self, tmp_path: Path) -> None:
        body = GOOD_CONF.replace("archive-async=y", "archive-async=n")
        config = load_pgbackrest_config(_conf(tmp_path, body))
        assert config.pitr_capable is False
        with pytest.raises(ValueError, match="PITR-capable"):
            plan_restore_drill(config, _plan(), retention_full=7)

    def test_a_retention_of_zero_keeps_nothing_and_is_refused(self) -> None:
        with pytest.raises(RetentionNotConfiguredError, match="keeps no full backup"):
            plan_restore_drill(_config(), _plan(), retention_full=0)


def _plan_file(tmp_path: Path, mutate: dict[str, Any] | None = None) -> Path:
    raw: dict[str, Any] = yaml.safe_load(REPLICATION_PLAN.read_text(encoding="utf-8"))
    if mutate:
        raw.update(mutate)
    path = tmp_path / "minio-replication.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


class TestReplicationRefusals:
    def test_the_near_miss_control_loads(self, tmp_path: Path) -> None:
        assert load_replication_plan(_plan_file(tmp_path)).rules

    def test_a_plan_that_replicates_deletions_is_refused(self, tmp_path: Path) -> None:
        raw: dict[str, Any] = yaml.safe_load(REPLICATION_PLAN.read_text(encoding="utf-8"))
        raw["rules"][0]["replicate_delete"] = True
        with pytest.raises(BackupConfigError, match="replicates deletions"):
            load_replication_plan(_plan_file(tmp_path, {"rules": raw["rules"]}))

    def test_a_plan_that_replicates_delete_markers_is_refused(self, tmp_path: Path) -> None:
        raw: dict[str, Any] = yaml.safe_load(REPLICATION_PLAN.read_text(encoding="utf-8"))
        raw["rules"][0]["replicate_delete_marker"] = True
        with pytest.raises(BackupConfigError, match="replicates deletions"):
            load_replication_plan(_plan_file(tmp_path, {"rules": raw["rules"]}))

    def test_an_invented_expiry_window_is_refused(self, tmp_path: Path) -> None:
        raw: dict[str, Any] = yaml.safe_load(REPLICATION_PLAN.read_text(encoding="utf-8"))
        raw["rules"][0]["expiry_days"] = 30
        with pytest.raises(BackupConfigError, match="HB-I8"):
            load_replication_plan(_plan_file(tmp_path, {"rules": raw["rules"]}))

    def test_an_empty_plan_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BackupConfigError, match="no replication rules"):
            load_replication_plan(_plan_file(tmp_path, {"rules": []}))

    def test_an_unreplicated_repository_bucket_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(BackupConfigError, match="is not replicated"):
            load_replication_plan(_plan_file(tmp_path, {"repository_bucket": "somewhere-else"}))

    def test_asking_for_an_unknown_bucket_raises(self) -> None:
        with pytest.raises(BackupConfigError, match="no replication rule"):
            _plan().rule_for("intake-nothing")

    def test_the_rendered_commands_never_ask_for_delete_replication(self) -> None:
        rendered = [" ".join(command) for command in replication_commands(_plan())]
        joined = " ".join(rendered)
        assert "delete-marker" not in joined
        assert ",delete" not in joined
        # object-locked buckets are created locked; the lock cannot be added later
        assert any("--with-lock intake-dr/intake-audit-worm" in line for line in rendered)
        assert any("intake-dr/intake-docs" in line for line in rendered)

    def test_the_rendered_commands_carry_variable_names_not_values(self) -> None:
        for command in replication_commands(_plan()):
            for token in command:
                if token.startswith("${"):
                    assert token.endswith("}")


# --- the CLI and the evidence writer ---------------------------------------------------


class TestPlanCli:
    def _argv(self, *extra: str) -> list[str]:
        return ["--infra", str(BACKUP_DIR), "--repo-root", str(REPO), *extra]

    def test_it_renders_the_plan_and_reports_a_blocked_host(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main(
            self._argv("--free-disk-bytes", str(13 * 1024**3)),
            env={"PGBACKREST_REPO1_RETENTION_FULL": "7"},
        )
        out = capsys.readouterr().out
        assert code == 0, "a dry render is not a failure, whatever the host looks like"
        assert "BLOCKED" in out and "HB-I1" in out

    def test_enforce_host_turns_the_verdict_into_an_exit_code(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main(
            self._argv("--free-disk-bytes", str(13 * 1024**3), "--enforce-host"),
            env={"PGBACKREST_REPO1_RETENTION_FULL": "7"},
        )
        capsys.readouterr()
        assert code == 3

    def test_a_ready_host_renders_and_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = cli_main(
            self._argv(
                "--free-disk-bytes",
                str(500 * 1024**3),
                "--container-memory-bytes",
                str(64 * 1024**3),
                "--enforce-host",
                "--show-replication",
            ),
            env={"PGBACKREST_REPO1_RETENTION_FULL": "7"},
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "host              ready" in out
        assert "mc replicate add" in out

    def test_it_refuses_without_retention(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = cli_main(self._argv(), env={})
        assert code == 2
        assert "HB-I8" in capsys.readouterr().out

    def test_a_non_numeric_retention_is_refused_not_coerced(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main(self._argv(), env={"PGBACKREST_REPO1_RETENTION_FULL": "forever"})
        assert code == 2
        capsys.readouterr()

    def test_emit_replication_prints_commands_only(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main(self._argv("--emit-replication"), env={})
        out = capsys.readouterr().out
        assert code == 0
        assert out.splitlines()
        for line in out.splitlines():
            assert line.startswith("mc ")

    def test_a_missing_config_is_refused_not_crashed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main(["--infra", str(tmp_path), "--repo-root", str(REPO)], env={})
        assert code == 2
        assert "refused" in capsys.readouterr().out

    def test_it_reads_the_process_environment_when_none_is_passed(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("PGBACKREST_REPO1_RETENTION_FULL", "3")
        code = cli_main(self._argv())
        assert code == 0
        assert "retention 3 full" in capsys.readouterr().out


class TestEvidenceRecord:
    def test_counts_parse_and_anything_else_is_dropped(self) -> None:
        raw = "\n".join(
            [
                " visits:12",
                " notes:0",
                'ERROR:  column "tckn" does not exist',
                "psql: could not connect",
                " weird name:3",
                " overflowing:not-a-number",
                "",
            ]
        )
        assert parse_row_counts(raw) == {"visits": 12, "notes": 0}

    def test_a_relname_longer_than_postgres_allows_is_dropped(self) -> None:
        assert parse_row_counts(f"{'a' * 64}:1") == {}

    def test_the_record_is_counts_clocks_and_a_verdict(self) -> None:
        record = build_record(
            PGBACKREST_CONF,
            {
                "PGBACKREST_REPO1_RETENTION_FULL": "7",
                "DRILL_STARTED_AT": "2026-08-29T03:00:00Z",
                "DRILL_RECOVERY_TARGET": "2026-08-29 02:45:00+00",
                "DRILL_RESTORE_SECONDS": "412",
                "DRILL_ROW_COUNTS": " visits:12\n notes:4\n",
            },
        )
        assert record["verdict"] == "pass"
        assert record["restore_seconds"] == 412
        assert record["row_counts"] == {"visits": 12, "notes": 4}
        assert set(record) == set(drill_evidence_skeleton(_config(), 7))

    def test_a_restore_past_the_rto_is_recorded_not_hidden(self) -> None:
        record = build_record(
            PGBACKREST_CONF,
            {"PGBACKREST_REPO1_RETENTION_FULL": "7", "DRILL_RESTORE_SECONDS": "14401"},
        )
        assert record["verdict"] == "rto_exceeded"

    def test_writing_the_record_lands_a_json_file_with_no_identifier(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = record_main(
            {
                "INTAKE_REPO_ROOT": str(REPO),
                "DRILL_EVIDENCE_DIR": str(tmp_path),
                "PGBACKREST_REPO1_RETENTION_FULL": "7",
                "DRILL_RESTORE_SECONDS": "10",
                "DRILL_ROW_COUNTS": " visits:1\n",
            }
        )
        assert code == 0
        capsys.readouterr()
        written = list(tmp_path.glob("restore-drill-*.json"))
        assert len(written) == 1
        blob = written[0].read_text(encoding="utf-8")
        assert '"visits": 1' in blob
        for forbidden in ("tckn", "phone", "patient", "transcript"):
            assert forbidden not in blob.lower()


def test_the_module_entry_point_is_the_same_cli() -> None:
    """`python -m intake_platform.backup` is what the drill script calls; if
    it ever pointed at a second implementation the plan and the run would
    diverge silently."""
    import intake_platform.backup.__main__ as entry

    assert entry.main is cli_main
