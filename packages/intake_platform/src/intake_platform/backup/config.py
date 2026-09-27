"""INT-202 — typed readers for the two backup configuration artefacts.

``infra/backup/pgbackrest.conf`` and ``infra/backup/minio-replication.yaml``
are the source of truth for the PITR repository and for what replicates to
the second location. Everything that acts on them goes through this module,
so the plan is stated once and a shell script cannot drift away from it.

Refused at load time rather than trusted:

* an unencrypted repository, and any secret written into the file
  (invariant 14: the passphrase is a host secret, never a committed value);
* TLS verification switched off on any repository. The first version of the
  config pointed an S3 repository at the in-network object store over plain
  HTTP with ``repo1-storage-verify-tls=n``. pgBackRest's S3 driver speaks only
  TLS (pgbackrest/pgbackrest#1590), so that repository could never have been
  written, and ``verify-tls=n`` would have made one that could be
  impersonated. Repository 1 is now a local POSIX repository on its own
  volume; the second location is a second repository once HB-I8(b) names it;
* a count-based or over-long retention. files/06 §1's obligation is a period
  (destruction at most every six months), so the window is in days and
  :func:`~intake_platform.backup.status.validate_retention_days` bounds it.
  No window is set at all until HB-I8(a) is answered;
* a replication rule that would keep erased plaintext (see
  :func:`withheld_rules`).
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from .status import StatusError, validate_retention_days

#: pgBackRest reads every option from the environment as ``PGBACKREST_`` plus
#: the option name upper-cased with dashes as underscores.
CIPHER_PASS_ENV: Final = "PGBACKREST_REPO1_CIPHER_PASS"  # noqa: S105 — a variable name

#: The only repository cipher files/10 §3 accepts.
REQUIRED_CIPHER: Final = "aes-256-cbc"

#: files/06 §1's obligation is a period, so retention is a number of days.
REQUIRED_RETENTION_TYPE: Final = "time"

#: Options that carry a secret, for any repository index.
_SECRET_OPTION = re.compile(
    r"^repo\d+-(?:cipher-pass|s3-key|s3-key-secret|s3-token|azure-key|gcs-key)$"
)
_VERIFY_TLS = re.compile(r"^repo\d+-storage-verify-tls$")


class BackupConfigError(ValueError):
    """A backup artefact is unusable as written."""


@dataclass(frozen=True, slots=True)
class PgBackRestConfig:
    """The subset of ``pgbackrest.conf`` anything downstream needs."""

    stanza: str
    pg_path: str
    pg_user: str
    repo_type: str
    repo_path: str
    repo_cipher_type: str
    archive_async: bool
    retention_type: str
    retention_full: int | None
    log_level_file: str
    cipher_pass_env: str = CIPHER_PASS_ENV

    @property
    def encrypted_at_rest(self) -> bool:
        """The repository — manifests, backups and WAL — is ciphertext."""
        return self.repo_cipher_type == REQUIRED_CIPHER

    @property
    def pitr_capable(self) -> bool:
        """Continuous asynchronous WAL archiving into an encrypted repository
        is what makes a point-in-time restore possible."""
        return self.archive_async and self.encrypted_at_rest and bool(self.pg_path)


@dataclass(frozen=True, slots=True)
class ReplicationRule:
    """One bucket's replication settings."""

    bucket: str
    object_lock: bool
    holds_erasable_plaintext: bool
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
    rules: tuple[ReplicationRule, ...]

    #: files/10 §3 asks for "a second location in Türkiye" and no file names
    #: one (HB-I8(b), HB-I5). An unset endpoint is a refusal.
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
    """Read ``pgbackrest.conf`` and refuse the configurations that are wrong."""
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

    for section in parser.sections():
        for option, value in parser[section].items():
            if _SECRET_OPTION.match(option):
                raise BackupConfigError(
                    f"{path.name} carries {option} — the passphrase and keys are host secrets, "
                    "injected from the root-only env file, never committed (invariant 14; OpenBao "
                    "in the dev tier)"
                )
            if _VERIFY_TLS.match(option) and value.strip().lower() in {"n", "no", "false", "0"}:
                raise BackupConfigError(
                    f"{path.name}: {option}=n — a repository reached without TLS "
                    "verification can be impersonated"
                )

    repo_type = _opt(glob, "repo1-type") or "posix"
    if repo_type != "posix":
        raise BackupConfigError(
            f"{path.name}: repo1-type is {repo_type!r}; repository 1 is the host's own POSIX "
            "repository, and the second location is repository 2 (HB-I8(b))"
        )

    cipher = _opt(glob, "repo1-cipher-type")
    if cipher != REQUIRED_CIPHER:
        raise BackupConfigError(
            f"{path.name}: repo1-cipher-type is {cipher!r}, expected {REQUIRED_CIPHER!r} "
            "— files/10 §3 requires the archive encrypted at rest"
        )

    retention_type = _opt(glob, "repo1-retention-full-type")
    if retention_type != REQUIRED_RETENTION_TYPE:
        raise BackupConfigError(
            f"{path.name}: repo1-retention-full-type is {retention_type!r}, expected 'time' "
            "— files/06 §1 states a period, not a number of backups"
        )
    raw_retention = _opt(glob, "repo1-retention-full")
    try:
        retention = validate_retention_days(raw_retention) if raw_retention else None
    except StatusError as err:
        raise BackupConfigError(f"{path.name}: {err}") from err

    return PgBackRestConfig(
        stanza=stanza,
        pg_path=_opt(parser[stanza], "pg1-path"),
        pg_user=_opt(parser[stanza], "pg1-user"),
        repo_type=repo_type,
        repo_path=_opt(glob, "repo1-path"),
        repo_cipher_type=cipher,
        archive_async=_flag(glob, "archive-async"),
        retention_type=retention_type,
        retention_full=retention,
        log_level_file=_opt(glob, "log-level-file"),
    )


def _rule(raw: dict[str, Any], index: int, name: str) -> ReplicationRule:
    if "bucket" not in raw:
        raise BackupConfigError(f"{name}: replication rule {index} has no bucket")
    if "holds_erasable_plaintext" not in raw:
        raise BackupConfigError(
            f"{name}: rule for {raw['bucket']!r} must state holds_erasable_plaintext — whether a "
            "DSAR erasure deletes these objects in the clear decides whether a copy may exist"
        )
    expiry = raw.get("expiry_days")
    return ReplicationRule(
        bucket=str(raw["bucket"]),
        object_lock=bool(raw.get("object_lock", False)),
        holds_erasable_plaintext=bool(raw["holds_erasable_plaintext"]),
        replicate_existing=bool(raw.get("replicate_existing", False)),
        replicate_delete=bool(raw.get("replicate_delete", False)),
        replicate_delete_marker=bool(raw.get("replicate_delete_marker", False)),
        expiry_days=None if expiry is None else int(expiry),
    )


def load_replication_plan(path: Path) -> ReplicationPlan:
    """Read ``minio-replication.yaml`` and refuse a plan that loses a guarantee."""
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = tuple(_rule(item, i, path.name) for i, item in enumerate(raw.get("rules") or []))
    if not rules:
        raise BackupConfigError(f"{path.name} declares no replication rules")
    for rule in rules:
        if rule.replicate_delete or rule.replicate_delete_marker:
            raise BackupConfigError(
                f"{path.name}: {rule.bucket} replicates deletions — a deletion on the primary "
                "must not reach the copy (files/10 §9 `backups`)"
            )
        if rule.expiry_days is not None:
            raise BackupConfigError(
                f"{path.name}: {rule.bucket} sets expiry_days={rule.expiry_days}; no file in "
                "files/ states a backup retention window (HB-I8)"
            )
    return ReplicationPlan(
        source_alias=str(raw["source_alias"]),
        source_endpoint_env=str(raw["source_endpoint_env"]),
        source_access_key_env=str(raw["source_access_key_env"]),
        source_secret_key_env=str(raw["source_secret_key_env"]),
        target_alias=str(raw["target_alias"]),
        target_endpoint_env=str(raw["target_endpoint_env"]),
        target_access_key_env=str(raw["target_access_key_env"]),
        target_secret_key_env=str(raw["target_secret_key_env"]),
        rules=rules,
    )


def withheld_rules(plan: ReplicationPlan) -> list[tuple[ReplicationRule, str]]:
    """Rules that are declared but never rendered, each with the reason.

    Bucket replication needs versioning on the source, and the copy withholds
    deletes (the ransomware defence). For objects stored in the clear that a
    DSAR erasure deletes, both keep the erased bytes: the noncurrent version
    on the primary and the copy at the second location. So such a bucket is
    neither versioned nor copied until its objects are envelope-encrypted
    (erasure then destroys a key, which a copy cannot undo) or the owner and
    counsel accept a copy that outlives an erasure.
    """
    return [
        (
            rule,
            f"{rule.bucket} holds clear-text objects that a DSAR erasure deletes (files/06 §3); "
            "versioning or copying it would keep erased bytes. Withheld until its objects are "
            "envelope-encrypted or HB-I8 decides otherwise.",
        )
        for rule in plan.rules
        if rule.holds_erasable_plaintext
    ]


def replication_commands(plan: ReplicationPlan) -> list[list[str]]:
    """Render the ``mc`` invocations for every rule that may be replicated.

    Credentials and the endpoint are shell variable references, so no secret
    passes through this process and nothing names the second location.
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
        if rule.holds_erasable_plaintext:
            continue
        make_bucket = ["mc", "mb", "--ignore-existing"]
        if rule.object_lock:
            make_bucket.append("--with-lock")
        commands.append([*make_bucket, f"{dst}/{rule.bucket}"])
        commands.append(["mc", "version", "enable", f"{src}/{rule.bucket}"])
        commands.append(["mc", "version", "enable", f"{dst}/{rule.bucket}"])
        flags = ["metadata-sync"]
        if rule.replicate_existing:
            flags.append("existing-objects")
        commands.append(
            [
                "mc",
                "replicate",
                "add",
                f"{src}/{rule.bucket}",
                "--remote-bucket",
                f"{dst}/{rule.bucket}",
                "--replicate",
                ",".join(flags),
            ]
        )
    return commands
