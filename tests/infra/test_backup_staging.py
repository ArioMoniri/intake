"""INT-202 — backups on the production host stack (``infra/staging``).

The host runs one Postgres. PITR needs that Postgres to archive WAL, so the
primary itself changes: it is built from the same digest-pinned
``postgres:16.15-trixie`` base plus a version-pinned pgBackRest, archives
every segment into an encrypted POSIX repository on a named volume, and
forces a segment switch at least every minute so the 15-minute RPO holds on a
quiet database. The passphrase is a host-generated secret in the root-only
env file, like every other secret in the tier, and reaches the postgres
container only.

``infra/staging/backup.sh`` is the operator's entry point: scheduled backups,
the quarterly drill, the retention setting HB-I8(a) is waiting for, and the
replication HB-I8(b) is waiting for. Nothing here boots a container; the
functions are sourced and run against shims, the way
``tests/infra/test_staging_compose.py`` exercises lib.sh.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.backup.status import RETENTION_CEILING_DAYS, RPO_BUDGET_S

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
COMPOSE = STAGING / "compose.yaml"
LIB = STAGING / "lib.sh"
INIT = STAGING / "init.sh"
DEPLOY = STAGING / "deploy.sh"
BACKUP = STAGING / "backup.sh"
DOCKERFILE = STAGING / "Dockerfile.postgres"
DOCKERIGNORE = STAGING / "Dockerfile.postgres.dockerignore"
TEMPLATE = STAGING / "staging.env.template"
DRILL_LIB = REPO / "scripts" / "backup" / "drill_lib.sh"

#: The base the primary ran before INT-202, unchanged: the backup layer adds a
#: package, never a different server. Assembled from its parts: a complete
#: pinned reference in this file would be one Renovate does not watch
#: (tests/ci/test_dependency_updates.py), while Dockerfile.postgres, which it
#: does watch, holds the real one.
_POSTGRES_REPOSITORY = "postgres"
_POSTGRES_TAG = "16.15-trixie"
_POSTGRES_DIGEST = "sha256:1a6ab3f5345eb6dbe04a1349529caabdb0ab09293a09590fad07b2246bfa4b54"
POSTGRES_BASE = f"{_POSTGRES_REPOSITORY}:{_POSTGRES_TAG}@{_POSTGRES_DIGEST}"
PINNED = re.compile(r"^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")

#: A Debian package version from the PostgreSQL apt archive for trixie.
PGDG_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?-\d+\.pgdg13\+\d+$")

CIPHER_ENV = "PGBACKREST_REPO1_CIPHER_PASS"
REPO_VOLUME = "pgbackrest-repo"
SPOOL_VOLUME = "pgbackrest-spool"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code(path: Path) -> str:
    return "\n".join(line for line in _text(path).splitlines() if not line.lstrip().startswith("#"))


def _compose() -> dict[str, Any]:
    loaded = yaml.safe_load(_text(COMPOSE))
    assert isinstance(loaded, dict)
    return loaded


def _postgres() -> dict[str, Any]:
    service = _compose()["services"]["postgres"]
    assert isinstance(service, dict)
    return service


def _bash(
    script: str, *args: str, cwd: Path | None = None, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd or REPO)}
    env.update(extra_env or {})
    return subprocess.run(  # noqa: S603 — our own scripts, fixed argv
        ["bash", "-c", script, "backup-test", *args],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _source_backup(
    script: str, *args: str, tmp_path: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {"INTAKE_STAGING_STATE_DIR": str(tmp_path / "state")}
    env.update(extra_env or {})
    return _bash(f'source "{BACKUP}"; {script}', *args, cwd=tmp_path, extra_env=env)


def _lib_value(name: str) -> str:
    result = _bash(f'source "{LIB}"; bash -c \'printf "%s" "${{{name}:-}}"\'')
    assert result.returncode == 0, result.stderr
    return result.stdout


def _drill_command() -> list[str]:
    result = _bash(f'source "{DRILL_LIB}"; printf "%s\\n" "${{DRILL_POSTGRES_COMMAND[@]}}"')
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


# --- the image: the same base, plus a pinned pgBackRest --------------------------------


class TestPostgresImage:
    def test_the_base_is_the_digest_pinned_server_the_host_already_runs(self) -> None:
        froms = [
            line.split()[1] for line in _code(DOCKERFILE).splitlines() if line.startswith("FROM ")
        ]
        assert froms == [POSTGRES_BASE]
        assert PINNED.match(froms[0])

    def test_pgbackrest_is_installed_at_a_pinned_version(self) -> None:
        code = _code(DOCKERFILE)
        match = re.search(r"^ARG PGBACKREST_VERSION=(\S+)$", code, re.M)
        assert match, "the package version is an ARG with a pinned default"
        assert PGDG_VERSION.match(match.group(1)), match.group(1)
        assert '"pgbackrest=${PGBACKREST_VERSION}"' in code
        assert "--no-install-recommends" in code

    def test_the_image_tag_names_both_versions(self) -> None:
        version = re.search(
            r"^ARG PGBACKREST_VERSION=(\d+\.\d+(?:\.\d+)?)-", _code(DOCKERFILE), re.M
        )
        assert version
        image = _lib_value("POSTGRES_IMAGE")
        assert image == f"intake-staging/postgres:16.15-pgbackrest-{version.group(1)}"

    def test_the_repository_and_spool_directories_belong_to_postgres(self) -> None:
        code = _code(DOCKERFILE)
        for path in ("/var/lib/pgbackrest", "/var/spool/pgbackrest", "/var/log/pgbackrest"):
            assert re.search(
                rf"install -d -o postgres -g postgres -m 07[05]0 [^\n]*{path}", code
            ), path

    def test_nothing_is_copied_in_and_the_context_sends_nothing(self) -> None:
        """The configuration is mounted at run time; the image holds no file
        of ours, and the build context is filtered to nothing."""
        code = _code(DOCKERFILE)
        assert not re.search(r"^(COPY|ADD) ", code, re.M)
        assert _code(DOCKERIGNORE).strip() == "*"


# --- the primary archives WAL -----------------------------------------------------------


class TestPrimaryArchives:
    def test_the_primary_is_built_from_that_dockerfile_and_tagged_from_lib(self) -> None:
        service = _postgres()
        assert service["build"] == {"context": ".", "dockerfile": "Dockerfile.postgres"}
        assert service["image"] == "${POSTGRES_IMAGE:?set by lib.sh}"

    def test_the_command_is_the_one_the_ci_drill_runs(self) -> None:
        """One statement of the archiving settings: compose's command must be
        the array the CI drill boots its primary with, so the drill proves the
        configuration production runs."""
        assert _postgres()["command"] == _drill_command()

    def test_archiving_is_on_through_pgbackrest(self) -> None:
        command = " ".join(_postgres()["command"])
        assert "archive_mode=on" in command
        assert "archive_command=pgbackrest --stanza=intake archive-push %p" in command

    def test_a_quiet_database_still_switches_segments_well_inside_the_rpo(self) -> None:
        """A WAL segment is archived when it fills. On a quiet database that
        can be hours; archive_timeout forces the switch. PostgreSQL's own
        guidance is "a minute or so", well inside RPO 15 min."""
        setting = next(a for a in _postgres()["command"] if str(a).startswith("archive_timeout="))
        seconds = int(setting.split("=", 1)[1])
        assert 0 < seconds < RPO_BUDGET_S

    def test_the_passphrase_is_a_required_host_secret_for_postgres_only(self) -> None:
        env = _postgres()["environment"]
        assert env[CIPHER_ENV] == f"${{{CIPHER_ENV}:?run init.sh}}"
        for name, service in _compose()["services"].items():
            if name == "postgres":
                continue
            assert CIPHER_ENV not in (service.get("environment") or {}), name

    def test_the_configuration_is_mounted_read_only(self) -> None:
        volumes = [str(v) for v in _postgres()["volumes"]]
        assert "../backup/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro" in volumes
        assert "${PGBACKREST_CONF_D:?set by lib.sh}:/etc/pgbackrest/conf.d:ro" in volumes

    def test_the_repository_and_spool_are_named_volumes(self) -> None:
        volumes = [str(v) for v in _postgres()["volumes"]]
        assert f"{REPO_VOLUME}:/var/lib/pgbackrest" in volumes
        assert f"{SPOOL_VOLUME}:/var/spool/pgbackrest" in volumes
        declared = _compose()["volumes"]
        assert REPO_VOLUME in declared and SPOOL_VOLUME in declared

    def test_the_include_directory_is_under_the_root_only_state_dir(self) -> None:
        assert _lib_value("PGBACKREST_CONF_D") == "/etc/intake-staging/pgbackrest.d"


# --- the host scripts -------------------------------------------------------------------


class TestHostScripts:
    def test_the_template_carries_the_passphrase_key_with_no_value(self) -> None:
        lines = [line for line in _text(TEMPLATE).splitlines() if line.startswith(f"{CIPHER_ENV}=")]
        assert lines == [f"{CIPHER_ENV}="]

    def test_init_generates_it_once_as_256_bit_hex(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        result = _bash(
            f'source "{LIB}"; ENV_FILE="$1"; generate_missing_secrets', str(env_file), cwd=tmp_path
        )
        assert result.returncode == 0, result.stderr
        values = dict(line.split("=", 1) for line in _text(env_file).splitlines())
        first = values[CIPHER_ENV]
        assert re.fullmatch(r"[0-9a-f]{64}", first)
        # a re-run keeps it: a new passphrase cannot open the existing repository
        _bash(
            f'source "{LIB}"; ENV_FILE="$1"; generate_missing_secrets', str(env_file), cwd=tmp_path
        )
        again = dict(line.split("=", 1) for line in _text(env_file).splitlines())
        assert again[CIPHER_ENV] == first

    @pytest.mark.parametrize("script", [INIT, DEPLOY], ids=lambda p: p.name)
    def test_the_image_is_built_after_the_sbom_stamp_and_before_compose(self, script: Path) -> None:
        code = _code(script)
        order = [
            code.index(step)
            for step in ("stamp_sbom", "prepare_backup_dirs", "build_postgres_image")
        ]
        assert order == sorted(order)
        assert order[-1] < code.index("compose "), "compose up needs the image"

    @pytest.mark.parametrize("script", [INIT, DEPLOY], ids=lambda p: p.name)
    def test_the_stanza_is_ensured_after_the_migrations(self, script: Path) -> None:
        code = _code(script)
        assert code.index("rotate_role_passwords") < code.index("ensure_backup_stanza")

    def test_the_stanza_is_created_and_checked_as_the_postgres_user(self) -> None:
        lib = _code(LIB)
        assert re.search(r"compose exec -T -u postgres postgres pgbackrest", lib)
        body = lib[lib.index("ensure_backup_stanza() {") :]
        body = body[: body.index("\n}")]
        assert "stanza-create" in body and "check" in body

    def test_the_postgres_build_is_its_own_statement(self) -> None:
        assert 'INTAKE_SBOM_DIGEST="$SBOM_DIGEST_DURING_BUILD" compose build postgres' in _code(LIB)


class TestBackupScript:
    def test_sourcing_it_runs_nothing(self, tmp_path: Path) -> None:
        result = _source_backup("declare -F cmd_drill >/dev/null", tmp_path=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_an_unknown_command_prints_usage_and_exits_2(self, tmp_path: Path) -> None:
        result = _bash(f'bash "{BACKUP}" restore-everything', cwd=tmp_path)
        assert result.returncode == 2
        assert "usage" in result.stderr

    @pytest.mark.parametrize("kind", ["full", "diff"])
    def test_a_backup_type_is_accepted(self, kind: str, tmp_path: Path) -> None:
        result = _source_backup('backup_type "$1"', kind, tmp_path=tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == kind

    @pytest.mark.parametrize("kind", ["", "incr;rm", "FULL", "snapshot"])
    def test_any_other_backup_type_is_refused(self, kind: str, tmp_path: Path) -> None:
        assert _source_backup('backup_type "$1"', kind, tmp_path=tmp_path).returncode != 0

    def test_set_retention_writes_the_include_file(self, tmp_path: Path) -> None:
        conf_d = tmp_path / "conf.d"
        conf_d.mkdir()
        result = _source_backup(
            'write_retention_conf "$1" "$2"', str(conf_d), "30", tmp_path=tmp_path
        )
        assert result.returncode == 0, result.stderr
        assert _text(conf_d / "retention.conf") == "[global]\nrepo1-retention-full=30\n"

    def test_set_retention_refuses_past_the_ceiling_and_writes_nothing(
        self, tmp_path: Path
    ) -> None:
        conf_d = tmp_path / "conf.d"
        conf_d.mkdir()
        result = _source_backup(
            'write_retention_conf "$1" "$2"',
            str(conf_d),
            str(RETENTION_CEILING_DAYS + 1),
            tmp_path=tmp_path,
        )
        assert result.returncode != 0
        assert "files/06" in result.stderr
        assert not list(conf_d.iterdir())

    def test_replication_refuses_while_the_second_location_is_unnamed(self, tmp_path: Path) -> None:
        result = _source_backup("require_second_location", tmp_path=tmp_path)
        assert result.returncode != 0
        assert "HB-I8(b)" in result.stderr
        assert "INTAKE_DR_S3_ENDPOINT" in result.stderr

    def test_replication_names_every_missing_value_and_no_value(self, tmp_path: Path) -> None:
        result = _source_backup(
            "require_second_location",
            tmp_path=tmp_path,
            extra_env={
                "INTAKE_DR_S3_ENDPOINT": "https://dr.example.test",
                "INTAKE_DR_S3_ACCESS_KEY": "operator-typed",
            },
        )
        assert result.returncode != 0
        assert "INTAKE_DR_S3_SECRET_KEY" in result.stderr
        assert "operator-typed" not in result.stderr

    def test_the_drill_adapters_point_at_the_staging_project(self, tmp_path: Path) -> None:
        code = _code(BACKUP)
        assert "compose exec -T -u postgres postgres" in code
        assert "compose exec -T api python -m" in code
        assert 'DRILL_REPO_VOLUME="intake-staging_pgbackrest-repo"' in code
        assert 'DRILL_IMAGE="$POSTGRES_IMAGE"' in code
        assert 'DRILL_TARGET="staging"' in code

    def test_the_schedule_is_daily_weekly_and_quarterly(self, tmp_path: Path) -> None:
        result = _source_backup("render_units /opt/intake/infra/staging", tmp_path=tmp_path)
        assert result.returncode == 0, result.stderr
        units = result.stdout
        assert "OnCalendar=Mon..Sat *-*-* 01:30:00 UTC" in units
        assert "OnCalendar=Sun *-*-* 01:30:00 UTC" in units
        assert "OnCalendar=*-01,04,07,10-01 03:00:00 UTC" in units
        assert units.count("Persistent=true") == 3
        assert units.count("Type=oneshot") == 3
        assert "ExecStart=/opt/intake/infra/staging/backup.sh backup diff" in units
        assert "ExecStart=/opt/intake/infra/staging/backup.sh backup full" in units
        assert "ExecStart=/opt/intake/infra/staging/backup.sh drill" in units

    def test_the_schedule_refuses_a_relative_path(self, tmp_path: Path) -> None:
        assert _source_backup("render_units infra/staging", tmp_path=tmp_path).returncode != 0
