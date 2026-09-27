"""INT-202 — the restore drill's synthetic canary.

A backup is only as good as the restore, and a restore is only as good as
what can be checked in it. The canary gives the drill something exact to
check, written through the platform's own envelope code so the check is about
the real erasure mechanism:

* ``ROWS_PER_RUN`` synthetic rows, whose count and md5 the manifest keeps;
* two synthetic subjects sealed with :class:`~intake_platform.envelope.EnvelopeCipher`
  under the drill's own KEK (Transit key ``tenant-restore-drill`` — never a
  real tenant's): ``retained`` is kept, ``erased`` is crypto-shredded
  (:func:`~intake_platform.envelope.shred_field`, the DSAR erasure's own
  operation) before the recovery target;
* a sentinel row committed after the recovery target.

Everything is written AFTER the newest backup, into a database of its own
(``intake_restore_drill``) on the primary, so it reaches a restore only by WAL
replay. The manifest is PHI-free: counts, hashes and clocks.

:func:`verify_restore` is the pure half and is unit-tested against the file
KEK provider. The database half (:func:`prepare`, :func:`wait_archived`) runs
in the API image on the host and in the CI drill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.envelope import (
    CryptoShredError,
    EncryptedField,
    EnvelopeCipher,
    TamperError,
    TransitKekProvider,
    is_shredded,
    shred_field,
)

from .drill import ROW_COUNT_SQL
from .status import RPO_BUDGET_S

if TYPE_CHECKING:
    import psycopg

CANARY_DATABASE: Final = "intake_restore_drill"
CANARY_TENANT: Final = "restore-drill"
ROWS_PER_RUN: Final = 1000
SUBJECT_RETAINED: Final = "retained"
SUBJECT_ERASED: Final = "erased"
BOOTSTRAP_URL_ENV: Final = "INTAKE_API_BOOTSTRAP_DB_URL"

_AAD_PREFIX: Final = "intake/restore-drill/v1"
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_SEGMENT = re.compile(r"^[0-9A-F]{24}$")
_POLL_S: Final = 2.0

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_REFUSED: Final = 2

SCHEMA_SQL: Final = (
    "CREATE TABLE IF NOT EXISTS drill_rows ("
    "run_id text NOT NULL, seq integer NOT NULL, payload text NOT NULL, "
    "PRIMARY KEY (run_id, seq))",
    "CREATE TABLE IF NOT EXISTS drill_subjects ("
    "run_id text NOT NULL, subject text NOT NULL, envelope jsonb NOT NULL, "
    "PRIMARY KEY (run_id, subject))",
    "CREATE TABLE IF NOT EXISTS drill_sentinel ("
    "run_id text PRIMARY KEY, written_at timestamptz NOT NULL DEFAULT clock_timestamp())",
)
_TABLES: Final = ("drill_rows", "drill_subjects", "drill_sentinel")


class CanaryError(ValueError):
    """The canary cannot be written or read as asked."""


# --- the synthetic data ----------------------------------------------------------------


def new_run_id() -> str:
    return secrets.token_hex(16)


def validate_run_id(run_id: str) -> str:
    """32 lowercase hex characters, and nothing that could reach SQL otherwise."""
    if not _RUN_ID.match(run_id):
        raise CanaryError("a drill run id is 32 lowercase hex characters")
    return run_id


def _digest(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def synthetic_payloads(run_id: str, seed: str, count: int = ROWS_PER_RUN) -> list[str]:
    return [
        f"SYNTHETIC restore-drill row {seq} {_digest(run_id, seed, str(seq))}"
        for seq in range(1, count + 1)
    ]


def rows_checksum(payloads: Sequence[str]) -> str:
    """md5 of ``seq:payload`` lines joined by newlines — what ``dump_sql`` asks
    the restored server for. A checksum of synthetic rows, not a security
    control."""
    joined = "\n".join(f"{seq}:{payload}" for seq, payload in enumerate(payloads, start=1))
    return hashlib.md5(joined.encode("utf-8"), usedforsecurity=False).hexdigest()


def subject_plaintext(run_id: str, subject: str, seed: str) -> bytes:
    return f"SYNTHETIC restore-drill subject {subject} {run_id} {_digest(seed, subject)}".encode()


def subject_aad(run_id: str, subject: str) -> bytes:
    return f"{_AAD_PREFIX}|{run_id}|{subject}".encode()


def seal_subject(
    cipher: EnvelopeCipher, run_id: str, subject: str, plaintext: bytes
) -> EncryptedField:
    return cipher.encrypt_field(CANARY_TENANT, plaintext, subject_aad(run_id, subject))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_sql(run_id: str) -> str:
    """One JSON object from the restored cluster: counts, a checksum, the two
    envelopes and the sentinel count. Only the canary's three tables."""
    # psql runs this inside the scratch container, so there is no driver to
    # bind a parameter; the one interpolated value is validated to exactly 32
    # lowercase hex characters first, which cannot close a quote.
    run = validate_run_id(run_id)
    where = f"WHERE run_id = '{run}'"
    return (  # nosec B608
        "SELECT json_build_object("  # noqa: S608 — run id validated above
        f"'run_id', '{run}', "
        "'rows', (SELECT json_build_object('count', count(*), 'md5', "
        "md5(coalesce(string_agg(seq::text || ':' || payload, E'\\n' ORDER BY seq), ''))) "
        f"FROM drill_rows {where}), "
        "'subjects', (SELECT coalesce(json_object_agg(subject, envelope), '{}'::json) "
        f"FROM drill_subjects {where}), "
        f"'sentinel', (SELECT count(*) FROM drill_sentinel {where}));"
    )


# --- verification ------------------------------------------------------------------------


def _field(raw: object) -> EncryptedField | None:
    if not isinstance(raw, Mapping):
        return None
    try:
        return encrypted_field_from_json(raw)
    except ValueError:
        return None


def _opens_to(
    cipher: EnvelopeCipher, run_id: str, field: EncryptedField, expected_sha256: str
) -> bool:
    try:
        plaintext = cipher.decrypt_field(
            CANARY_TENANT, field, subject_aad(run_id, SUBJECT_RETAINED)
        )
    except (CryptoShredError, TamperError):
        return False
    return sha256_hex(plaintext) == expected_sha256


def _stays_erased(cipher: EnvelopeCipher, run_id: str, field: EncryptedField) -> bool:
    """Erased by key destruction, and still erased: the wrapped DEK is gone and
    the cipher refuses the field as shredded, not as merely broken."""
    if not is_shredded(field):
        return False
    try:
        cipher.decrypt_field(CANARY_TENANT, field, subject_aad(run_id, SUBJECT_ERASED))
    except CryptoShredError:
        return True
    return False


def verify_restore(
    dump: Mapping[str, Any], manifest: Mapping[str, Any], cipher: EnvelopeCipher
) -> dict[str, bool]:
    """Every check the drill makes of the restored canary."""
    run_id = validate_run_id(str(manifest.get("run_id", "")))
    if dump.get("run_id") != run_id:
        raise CanaryError("the dump is for another run than the manifest")
    rows = dump.get("rows") or {}
    expected_rows = manifest.get("rows") or {}
    subjects = dump.get("subjects") or {}
    expected = manifest.get("subjects") or {}
    retained = _field(subjects.get(SUBJECT_RETAINED))
    erased = _field(subjects.get(SUBJECT_ERASED))
    retained_sha = str((expected.get(SUBJECT_RETAINED) or {}).get("plaintext_sha256", ""))
    erased_sha = str((expected.get(SUBJECT_ERASED) or {}).get("ciphertext_sha256", ""))
    return {
        "rows_count": rows.get("count") == expected_rows.get("count"),
        "rows_checksum": rows.get("md5") == expected_rows.get("md5"),
        "retained_readable": retained is not None
        and _opens_to(cipher, run_id, retained, retained_sha),
        "erased_unreadable": erased is not None and _stays_erased(cipher, run_id, erased),
        "erased_same_row": erased is not None and sha256_hex(erased.ciphertext) == erased_sha,
        "sentinel_absent": dump.get("sentinel") == 0,
    }


def erased_subject_state(dump: Mapping[str, Any], cipher: EnvelopeCipher, run_id: str) -> str:
    """``shredded``, ``readable``, ``unreadable`` or ``absent`` — for the
    characterisation restore to a moment before the erasure."""
    field = _field((dump.get("subjects") or {}).get(SUBJECT_ERASED))
    if field is None:
        return "absent"
    if _stays_erased(cipher, run_id, field):
        return "shredded"
    try:
        cipher.decrypt_field(CANARY_TENANT, field, subject_aad(run_id, SUBJECT_ERASED))
    except (CryptoShredError, TamperError):
        return "unreadable"
    return "readable"


# --- the database half ---------------------------------------------------------------------


def dsn_from_env(env: Mapping[str, str], database: str | None = None) -> str:
    """The libpq URL for the bootstrap role, optionally on another database."""
    url = env.get(BOOTSTRAP_URL_ENV, "").strip()
    scheme, separator, rest = url.partition("://")
    if not separator or not scheme.startswith("postgresql"):
        raise CanaryError(f"{BOOTSTRAP_URL_ENV} is not set to a postgresql URL")
    dsn = f"postgresql://{rest}"
    if database is None:
        return dsn
    base, slash, _old = dsn.rpartition("/")
    if not slash or "@" not in base:
        raise CanaryError(f"{BOOTSTRAP_URL_ENV} names no database to replace")
    return f"{base}/{database}"


def _connect(dsn: str) -> psycopg.Connection[Any]:
    import psycopg  # local import: only the drill needs the driver

    return psycopg.connect(dsn, autocommit=True)


def _target(moment: datetime) -> str:
    """The recovery_target_time form pgBackRest passes through."""
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f+00")


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _row(row: tuple[Any, ...] | None, what: str) -> tuple[Any, ...]:
    if row is None:
        raise CanaryError(f"the primary returned no row for {what}")
    return row


def _clock(conn: psycopg.Connection[Any]) -> datetime:
    moment: datetime = _row(conn.execute("SELECT clock_timestamp()").fetchone(), "the clock")[0]
    return moment


def prepare(
    env: Mapping[str, str], cipher: EnvelopeCipher, run_id: str | None = None
) -> dict[str, Any]:
    """Seed, erase one subject, write the sentinel; return the manifest."""
    from psycopg import sql

    run = validate_run_id(run_id or new_run_id())
    seed = secrets.token_hex(16)
    with _connect(dsn_from_env(env)) as admin:
        found = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (CANARY_DATABASE,)
        ).fetchone()
        if found is None:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(CANARY_DATABASE)))

    payloads = synthetic_payloads(run, seed)
    retained_plain = subject_plaintext(run, SUBJECT_RETAINED, seed)
    retained = seal_subject(cipher, run, SUBJECT_RETAINED, retained_plain)
    erased = seal_subject(cipher, run, SUBJECT_ERASED, subject_plaintext(run, SUBJECT_ERASED, seed))
    with _connect(dsn_from_env(env, CANARY_DATABASE)) as conn:
        for statement in SCHEMA_SQL:
            conn.execute(statement)
        for table in _TABLES:
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE run_id <> %s").format(sql.Identifier(table)), (run,)
            )
        with conn.transaction(), conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO drill_rows (run_id, seq, payload) VALUES (%s, %s, %s)",
                [(run, seq, payload) for seq, payload in enumerate(payloads, start=1)],
            )
            for subject, field in ((SUBJECT_RETAINED, retained), (SUBJECT_ERASED, erased)):
                cursor.execute(
                    "INSERT INTO drill_subjects (run_id, subject, envelope) "
                    "VALUES (%s, %s, %s::jsonb)",
                    (run, subject, json.dumps(encrypted_field_to_json(field))),
                )
        before_erasure = _clock(conn)
        with conn.transaction():
            conn.execute(
                "UPDATE drill_subjects SET envelope = %s::jsonb WHERE run_id = %s AND subject = %s",
                (json.dumps(encrypted_field_to_json(shred_field(erased))), run, SUBJECT_ERASED),
            )
        recovery_target = _clock(conn)
        with conn.transaction():
            conn.execute("INSERT INTO drill_sentinel (run_id) VALUES (%s)", (run,))
        sentinel_at = _clock(conn)
        position = _row(
            conn.execute(
                "SELECT pg_current_wal_lsn()::text, pg_walfile_name(pg_current_wal_lsn())"
            ).fetchone(),
            "the WAL position",
        )
    return {
        "run_id": run,
        "rows": {"count": len(payloads), "md5": rows_checksum(payloads)},
        "subjects": {
            SUBJECT_RETAINED: {
                "plaintext_sha256": sha256_hex(retained_plain),
                "ciphertext_sha256": sha256_hex(retained.ciphertext),
            },
            SUBJECT_ERASED: {"ciphertext_sha256": sha256_hex(erased.ciphertext)},
        },
        "before_erasure": _target(before_erasure),
        "recovery_target": _target(recovery_target),
        "sentinel_at": _iso(sentinel_at),
        "wal_lsn": str(position[0]),
        "walfile": str(position[1]),
    }


def archived_covers(last_archived: str | None, walfile: str) -> bool:
    """The archiver has pushed *walfile* or a later segment of its timeline.
    History and ``.backup`` files are not segments and never count."""
    if not last_archived or not _SEGMENT.match(last_archived) or not _SEGMENT.match(walfile):
        return False
    return last_archived[:8] == walfile[:8] and last_archived >= walfile


def wait_archived(
    env: Mapping[str, str],
    walfile: str,
    since: datetime,
    timeout_s: float = RPO_BUDGET_S,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Wait for *walfile* to reach the repository on the primary's own
    ``archive_timeout``; the lag from *since* is the observed RPO."""
    deadline = clock() + timeout_s
    with _connect(dsn_from_env(env)) as conn:
        while True:
            row = conn.execute(
                "SELECT last_archived_wal, last_archived_time FROM pg_stat_archiver"
            ).fetchone()
            if row is not None and archived_covers(row[0], walfile) and row[1] is not None:
                archived_at: datetime = row[1]
                return {
                    "archived": True,
                    "archived_at": _iso(archived_at),
                    "rpo_observed_s": round(max(0.0, (archived_at - since).total_seconds()), 3),
                }
            if clock() >= deadline:
                return {"archived": False, "rpo_observed_s": None, "waited_s": timeout_s}
            sleep(_POLL_S)


def cleanup(env: Mapping[str, str], run_id: str) -> None:
    from psycopg import sql

    run = validate_run_id(run_id)
    with _connect(dsn_from_env(env, CANARY_DATABASE)) as conn:
        for table in _TABLES:
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE run_id = %s").format(sql.Identifier(table)), (run,)
            )


# --- CLI -----------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="restore-drill-canary")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="seed, erase, sentinel; print the manifest")
    wait = sub.add_parser("wait-archived")
    wait.add_argument("--walfile", required=True)
    wait.add_argument("--since", required=True, help="ISO time of the sentinel commit")
    wait.add_argument("--timeout", type=float, default=float(RPO_BUDGET_S))
    dump = sub.add_parser("dump-sql")
    dump.add_argument("--run-id", required=True)
    sub.add_parser("row-count-sql")
    verify = sub.add_parser("verify", help="stdin: the restored dump")
    verify.add_argument("--manifest", required=True)
    state = sub.add_parser("erased-state", help="stdin: the restored dump")
    state.add_argument("--run-id", required=True)
    clean = sub.add_parser("cleanup")
    clean.add_argument("--run-id", required=True)
    return parser


def _default_cipher() -> EnvelopeCipher:
    from intake_platform.secrets import SecretsProvider

    return EnvelopeCipher(TransitKekProvider(SecretsProvider.from_env()))


def _json(raw: str) -> dict[str, Any]:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as err:
        raise CanaryError(f"not JSON: {err.msg}") from err
    if not isinstance(loaded, dict):
        raise CanaryError("expected a JSON object")
    return loaded


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: str | None = None,
    cipher: EnvelopeCipher | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    environ = os.environ if env is None else env
    try:
        if args.command == "dump-sql":
            print(dump_sql(args.run_id))
            return EXIT_OK
        if args.command == "row-count-sql":
            print(ROW_COUNT_SQL + ";")
            return EXIT_OK
        if args.command == "cleanup":
            cleanup(environ, args.run_id)
            return EXIT_OK
        if args.command == "wait-archived":
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
            result = wait_archived(environ, args.walfile, since, args.timeout)
            print(json.dumps(result, sort_keys=True))
            return EXIT_OK if result["archived"] else EXIT_FAILED
        active = cipher or _default_cipher()
        if args.command == "prepare":
            print(json.dumps(prepare(environ, active), sort_keys=True))
            return EXIT_OK
        dump = _json(sys.stdin.read() if stdin is None else stdin)
        if args.command == "erased-state":
            print(erased_subject_state(dump, active, validate_run_id(args.run_id)))
            return EXIT_OK
        checks = verify_restore(dump, _json(args.manifest), active)
        print(json.dumps(checks, sort_keys=True))
        return EXIT_OK if all(checks.values()) else EXIT_FAILED
    except CanaryError as err:
        print(f"restore drill canary: refused — {err}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":  # pragma: no cover - exercised through the drill engine
    raise SystemExit(main())
