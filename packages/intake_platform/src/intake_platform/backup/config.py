"""INT-202 — typed readers for the two backup configuration artefacts.

``infra/backup/pgbackrest.conf`` and ``infra/backup/minio-replication.yaml``
are the source of truth for the PITR repository and for what replicates to
the second location. Everything that acts on them — the drill script, the
Makefile targets, CI — goes through this module, so the plan is stated once
and a shell script cannot drift away from it.

Two properties are enforced at load time rather than trusted:

* the repository is encrypted, and its passphrase is **not** in the file
  (invariant 14: secrets come from OpenBao, never from a committed artefact);
* no retention window is invented. files/10 §3 and the INT-202 acceptance
  state RPO 15 min and RTO 4 h and state no retention; the loader reports the
  absence and :mod:`intake_platform.backup.drill` refuses to act on it.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

#: pgBackRest reads every option from the environment as ``PGBACKREST_`` plus
#: the option name upper-cased with dashes as underscores. The passphrase is
#: therefore not configurable to some other name — it is this one.
CIPHER_PASS_ENV: Final = "PGBACKREST_REPO1_CIPHER_PASS"  # noqa: S105 — a variable name

#: The only repository cipher files/10 §3 accepts. AES-256 in CBC is what
#: pgBackRest implements; the option exists to be asserted, not chosen.
REQUIRED_CIPHER: Final = "aes-256-cbc"

#: The env var carrying an operator-supplied retention window. Absent by
#: design; :class:`~intake_platform.backup.drill.RetentionNotConfiguredError`
#: names HB-I8 when it is missing.
RETENTION_FULL_ENV: Final = "PGBACKREST_REPO1_RETENTION_FULL"


class BackupConfigError(ValueError):
    """A backup artefact is unusable as written."""


@dataclass(frozen=True, slots=True)
class PgBackRestConfig:
    """The subset of ``pgbackrest.conf`` anything downstream needs."""

    stanza: str
    pg_path: str
    repo_type: str
    repo_bucket: str
    repo_cipher_type: str
    archive_async: bool
    retention_full: int | None
    cipher_pass_env: str = CIPHER_PASS_ENV

    @property
    def encrypted_at_rest(self) -> bool:
        """The repository — manifests, backups and WAL — is ciphertext."""
        return self.repo_cipher_type == REQUIRED_CIPHER

    @property
    def pitr_capable(self) -> bool:
        """Continuous WAL archiving into an encrypted repository is what
        makes a point-in-time restore possible at all."""
        return self.archive_async and self.encrypted_at_rest and bool(self.pg_path)


@dataclass(frozen=True, slots=True)
class ReplicationRule:
    """One bucket's replication settings."""

    bucket: str
    object_lock: bool
    replicate_existing: bool
    replicate_delete: bool
    replicate_delete_marker: bool
    expiry_days: int | None


@dataclass(frozen=True, slots=True)
class ReplicationPlan:
    """What replicates from the primary object store to the second location."""

    source_alias: str
    source_endpoint_env: str
    source_access_key_env: str
    source_secret_key_env: str
    target_alias: str
    target_endpoint_env: str
    target_access_key_env: str
    target_secret_key_env: str
    repository_bucket: str
    rules: tuple[ReplicationRule, ...]

    #: files/10 §3 asks for "a second location in Türkiye" and no file names
    #: one (HB-I5: no in-country provider is contracted). An unset endpoint is
    #: a refusal, so there is deliberately nothing to fall back to.
    target_endpoint_default: None = None

    @property
    def bucket_names(self) -> set[str]:
        return {rule.bucket for rule in self.rules}

    def rule_for(self, bucket: str) -> ReplicationRule:
        for rule in self.rules:
            if rule.bucket == bucket:
                return rule
        raise BackupConfigError(f"no replication rule for bucket {bucket!r}")


def _opt(section: configparser.SectionProxy, option: str) -> str:
    return str(section.get(option, "")).strip()


def _flag(section: configparser.SectionProxy, option: str) -> bool:
    """pgBackRest booleans are ``y``/``n``, not Python truthiness."""
    return _opt(section, option).lower() in {"y", "yes", "true", "1"}


def load_pgbackrest_config(path: Path) -> PgBackRestConfig:
    """Read ``pgbackrest.conf`` and refuse the configurations that are wrong.

    Raises :class:`BackupConfigError` when the repository is unencrypted or
    when a secret has been written into the file.
    """
    parser = configparser.ConfigParser()
    parser.read_string(path.read_text(encoding="utf-8"))

    if "global" not in parser:
        raise BackupConfigError(f"{path.name} has no [global] section")
    glob = parser["global"]

    stanzas = [name for name in parser.sections() if name != "global" and ":" not in name]
    if len(stanzas) != 1:
        raise BackupConfigError(
            f"{path.name} must declare exactly one stanza; found {stanzas or 'none'}"
        )
    stanza = stanzas[0]

    for forbidden in ("repo1-cipher-pass", "repo1-s3-key", "repo1-s3-key-secret"):
        if forbidden in glob:
            raise BackupConfigError(
                f"{path.name} carries {forbidden} — secrets come from OpenBao (invariant 14)"
            )

    cipher = _opt(glob, "repo1-cipher-type")
    if cipher != REQUIRED_CIPHER:
        raise BackupConfigError(
            f"{path.name}: repo1-cipher-type is {cipher!r}, expected {REQUIRED_CIPHER!r} "
            "— files/10 §3 requires the archive encrypted at rest"
        )

    raw_retention = _opt(glob, "repo1-retention-full")
    retention = int(raw_retention) if raw_retention else None

    return PgBackRestConfig(
        stanza=stanza,
        pg_path=_opt(parser[stanza], "pg1-path"),
        repo_type=_opt(glob, "repo1-type"),
        repo_bucket=_opt(glob, "repo1-s3-bucket"),
        repo_cipher_type=cipher,
        archive_async=_flag(glob, "archive-async"),
        retention_full=retention,
    )


def _rule(raw: dict[str, Any], index: int) -> ReplicationRule:
    try:
        bucket = str(raw["bucket"])
    except KeyError as err:  # pragma: no cover - defended by the schema test
        raise BackupConfigError(f"replication rule {index} has no bucket") from err
    expiry = raw.get("expiry_days")
    return ReplicationRule(
        bucket=bucket,
        object_lock=bool(raw.get("object_lock", False)),
        replicate_existing=bool(raw.get("replicate_existing", False)),
        replicate_delete=bool(raw.get("replicate_delete", False)),
        replicate_delete_marker=bool(raw.get("replicate_delete_marker", False)),
        expiry_days=None if expiry is None else int(expiry),
    )


def load_replication_plan(path: Path) -> ReplicationPlan:
    """Read ``minio-replication.yaml`` and refuse a plan that loses a guarantee.

    Two refusals matter. A rule that replicates deletes turns the copy into a
    second victim of the same ransomware; a rule that invents an expiry window
    answers a retention question nobody has answered (HB-I8).
    """
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = tuple(_rule(item, i) for i, item in enumerate(raw.get("rules", [])))
    if not rules:
        raise BackupConfigError(f"{path.name} declares no replication rules")

    for rule in rules:
        if rule.replicate_delete or rule.replicate_delete_marker:
            raise BackupConfigError(
                f"{path.name}: {rule.bucket} replicates deletions — a deletion on the "
                "primary must not reach the copy (files/10 §9 `backups`)"
            )
        if rule.expiry_days is not None:
            raise BackupConfigError(
                f"{path.name}: {rule.bucket} sets expiry_days={rule.expiry_days}; no file "
                "in files/ states a backup retention window (HB-I8)"
            )

    plan = ReplicationPlan(
        source_alias=str(raw["source_alias"]),
        source_endpoint_env=str(raw["source_endpoint_env"]),
        source_access_key_env=str(raw["source_access_key_env"]),
        source_secret_key_env=str(raw["source_secret_key_env"]),
        target_alias=str(raw["target_alias"]),
        target_endpoint_env=str(raw["target_endpoint_env"]),
        target_access_key_env=str(raw["target_access_key_env"]),
        target_secret_key_env=str(raw["target_secret_key_env"]),
        repository_bucket=str(raw["repository_bucket"]),
        rules=rules,
    )
    if plan.repository_bucket not in plan.bucket_names:
        raise BackupConfigError(
            f"{path.name}: the pgBackRest repository bucket {plan.repository_bucket!r} "
            "is not replicated — the PITR archive would exist in one place only"
        )
    return plan


def replication_commands(plan: ReplicationPlan) -> list[list[str]]:
    """Render the ``mc`` invocations that realise *plan*.

    Rendered, not written down twice: the YAML is the only statement of what
    replicates where. Credentials are referenced as shell variables so no
    secret ever passes through this process.
    """
    src, dst = plan.source_alias, plan.target_alias
    commands: list[list[str]] = [
        [
            "mc",
            "alias",
            "set",
            src,
            f"${{{plan.source_endpoint_env}}}",
            f"${{{plan.source_access_key_env}}}",
            f"${{{plan.source_secret_key_env}}}",
        ],
        [
            "mc",
            "alias",
            "set",
            dst,
            f"${{{plan.target_endpoint_env}}}",
            f"${{{plan.target_access_key_env}}}",
            f"${{{plan.target_secret_key_env}}}",
        ],
    ]
    for rule in plan.rules:
        make_bucket = ["mc", "mb", "--ignore-existing"]
        if rule.object_lock:
            make_bucket.append("--with-lock")
        commands.append([*make_bucket, f"{dst}/{rule.bucket}"])
        commands.append(["mc", "version", "enable", f"{src}/{rule.bucket}"])
        commands.append(["mc", "version", "enable", f"{dst}/{rule.bucket}"])
        commands.append(
            [
                "mc",
                "replicate",
                "add",
                f"{src}/{rule.bucket}",
                "--remote-bucket",
                f"{dst}/{rule.bucket}",
                "--replicate",
                _replicate_flags(rule),
            ]
        )
    return commands


def _replicate_flags(rule: ReplicationRule) -> str:
    """The ``--replicate`` value: what a change on the primary propagates.

    ``delete`` and ``delete-marker`` are never included — that omission is
    the ransomware defence, and :func:`load_replication_plan` refuses a plan
    that would ask for them.
    """
    flags = ["metadata-sync"]
    if rule.replicate_existing:
        flags.append("existing-objects")
    return ",".join(flags)
