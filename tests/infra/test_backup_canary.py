"""INT-202 — the restore drill's synthetic canary, and the erasure question.

The drill writes a small synthetic data set into its own database on the
primary, after the newest backup, so the only way it can reappear in a restore
is WAL replay. Two synthetic subjects are sealed with the platform's real
envelope code (``intake_platform.envelope``): one is kept, one is
crypto-shredded before the recovery target (its wrapped DEK destroyed, exactly
what a DSAR erasure does — ``services/api/src/intake_api/dsar/shred.py``). A
sentinel row is written after the target.

A restore passes only when all of these hold in the RESTORED cluster:

* the synthetic rows are all there, byte-for-byte (count + md5);
* the kept subject decrypts to the plaintext whose sha256 the manifest holds;
* the erased subject is the same row (same ciphertext) and still cannot be
  opened — erased-by-key-destruction stays erased;
* the sentinel is absent, which is what proves the restore stopped at the
  requested moment rather than replaying everything it had.

This file pins the pure half against the file KEK provider. The database half
runs in ``tests/infra/test_backup_restore_integration.py`` against a real
pgBackRest restore.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from intake_platform.backup import canary
from intake_platform.backup.canary import (
    CANARY_DATABASE,
    CANARY_TENANT,
    ROWS_PER_RUN,
    SUBJECT_ERASED,
    SUBJECT_RETAINED,
    CanaryError,
    dump_sql,
    new_run_id,
    rows_checksum,
    seal_subject,
    sha256_hex,
    subject_aad,
    subject_plaintext,
    synthetic_payloads,
    validate_run_id,
    verify_restore,
)
from intake_platform.db.envelope_json import encrypted_field_to_json
from intake_platform.envelope import EnvelopeCipher, FileKekProvider, is_shredded, shred_field

RUN_ID = "fedcba9876543210fedcba9876543210"
SEED = "00112233445566778899aabbccddeeff"


def _cipher() -> EnvelopeCipher:
    return EnvelopeCipher(FileKekProvider())


def _world(cipher: EnvelopeCipher) -> tuple[dict[str, Any], dict[str, Any]]:
    """A manifest and the dump a correct restore-after-erasure would produce."""
    payloads = synthetic_payloads(RUN_ID, SEED)
    retained_plain = subject_plaintext(RUN_ID, SUBJECT_RETAINED, SEED)
    erased_plain = subject_plaintext(RUN_ID, SUBJECT_ERASED, SEED)
    retained = seal_subject(cipher, RUN_ID, SUBJECT_RETAINED, retained_plain)
    erased = shred_field(seal_subject(cipher, RUN_ID, SUBJECT_ERASED, erased_plain))
    manifest = {
        "run_id": RUN_ID,
        "rows": {"count": len(payloads), "md5": rows_checksum(payloads)},
        "subjects": {
            SUBJECT_RETAINED: {
                "plaintext_sha256": sha256_hex(retained_plain),
                "ciphertext_sha256": sha256_hex(retained.ciphertext),
            },
            SUBJECT_ERASED: {"ciphertext_sha256": sha256_hex(erased.ciphertext)},
        },
    }
    dump = {
        "run_id": RUN_ID,
        "rows": {"count": len(payloads), "md5": rows_checksum(payloads)},
        "subjects": {
            SUBJECT_RETAINED: encrypted_field_to_json(retained),
            SUBJECT_ERASED: encrypted_field_to_json(erased),
        },
        "sentinel": 0,
    }
    return manifest, dump


class TestSyntheticData:
    def test_the_run_id_is_128_bits_of_hex(self) -> None:
        run_id = new_run_id()
        assert validate_run_id(run_id) == run_id
        assert new_run_id() != run_id

    @pytest.mark.parametrize(
        "bad", ["", "ABCDEF0123456789ABCDEF0123456789", "x" * 32, "0" * 31, "'; drop"]
    )
    def test_a_malformed_run_id_is_refused(self, bad: str) -> None:
        with pytest.raises(CanaryError):
            validate_run_id(bad)

    def test_payloads_are_deterministic_synthetic_and_sized(self) -> None:
        first = synthetic_payloads(RUN_ID, SEED)
        assert first == synthetic_payloads(RUN_ID, SEED)
        assert len(first) == ROWS_PER_RUN
        assert all(p.startswith("SYNTHETIC restore-drill row") for p in first)
        assert synthetic_payloads(RUN_ID, "ff" * 16) != first

    def test_the_checksum_is_the_one_postgres_computes(self) -> None:
        """``dump_sql`` asks the server for md5(string_agg(seq || ':' ||
        payload, E'\\n' ORDER BY seq)); this is the same string, built here."""
        payloads = ["a", "b", "c"]
        expected = hashlib.md5(b"1:a\n2:b\n3:c", usedforsecurity=False).hexdigest()
        assert rows_checksum(payloads) == expected
        assert "string_agg" in dump_sql(RUN_ID) and "ORDER BY seq" in dump_sql(RUN_ID)

    def test_subject_plaintext_is_labelled_synthetic(self) -> None:
        plain = subject_plaintext(RUN_ID, SUBJECT_RETAINED, SEED)
        assert plain.startswith(b"SYNTHETIC restore-drill subject")

    def test_the_aad_binds_run_and_subject(self) -> None:
        assert subject_aad(RUN_ID, SUBJECT_RETAINED) != subject_aad(RUN_ID, SUBJECT_ERASED)

    def test_the_canary_has_its_own_tenant_key_and_database(self) -> None:
        """Never a real tenant's KEK and never the application database: the
        drill's writes live in a database of their own on the same cluster,
        and its KEK is the Transit key tenant-restore-drill."""
        assert CANARY_TENANT == "restore-drill"
        assert CANARY_DATABASE == "intake_restore_drill"
        assert CANARY_DATABASE != "intake"


class TestDumpSql:
    def test_the_dump_reads_only_the_canary_tables(self) -> None:
        sql = dump_sql(RUN_ID)
        lowered = sql.lower()
        assert "select *" not in lowered
        for table in ("drill_rows", "drill_subjects", "drill_sentinel"):
            assert table in lowered
        for word in ("patients", "sessions", "notes", "slots", "documents"):
            assert f" {word}" not in lowered

    def test_the_run_id_is_validated_before_it_reaches_sql(self) -> None:
        with pytest.raises(CanaryError):
            dump_sql("0' OR '1'='1")


class TestVerifyRestore:
    def test_a_correct_restore_after_the_erasure_passes_every_check(self) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        checks = verify_restore(dump, manifest, cipher)
        assert checks == {
            "rows_count": True,
            "rows_checksum": True,
            "retained_readable": True,
            "erased_unreadable": True,
            "erased_same_row": True,
            "sentinel_absent": True,
        }

    def test_negative_control_an_erased_subject_whose_dek_came_back_fails(self) -> None:
        """The resurrection a restore must not produce: the same row, with its
        wrapped DEK present again. Near-miss of the passing case — only the
        DEK differs."""
        cipher = _cipher()
        manifest, dump = _world(cipher)
        resurrected = seal_subject(
            cipher, RUN_ID, SUBJECT_ERASED, subject_plaintext(RUN_ID, SUBJECT_ERASED, SEED)
        )
        dump["subjects"][SUBJECT_ERASED] = encrypted_field_to_json(resurrected)
        checks = verify_restore(dump, manifest, cipher)
        assert checks["erased_unreadable"] is False
        assert checks["retained_readable"] is True

    def test_a_missing_row_fails_count_and_checksum(self) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        payloads = synthetic_payloads(RUN_ID, SEED)[:-1]
        dump["rows"] = {"count": len(payloads), "md5": rows_checksum(payloads)}
        checks = verify_restore(dump, manifest, cipher)
        assert checks["rows_count"] is False and checks["rows_checksum"] is False

    def test_an_altered_row_fails_the_checksum_only(self) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        payloads = synthetic_payloads(RUN_ID, SEED)
        payloads[5] = payloads[5] + "!"
        dump["rows"]["md5"] = rows_checksum(payloads)
        checks = verify_restore(dump, manifest, cipher)
        assert checks["rows_count"] is True and checks["rows_checksum"] is False

    def test_a_present_sentinel_means_the_restore_ignored_the_target(self) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        dump["sentinel"] = 1
        assert verify_restore(dump, manifest, cipher)["sentinel_absent"] is False

    def test_a_retained_subject_that_will_not_open_fails(self) -> None:
        manifest, dump = _world(_cipher())
        # a different process's KEK: the wrapped DEK cannot be unwrapped
        assert verify_restore(dump, manifest, _cipher())["retained_readable"] is False

    def test_an_absent_subject_fails_rather_than_passing_vacuously(self) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        del dump["subjects"][SUBJECT_ERASED]
        checks = verify_restore(dump, manifest, cipher)
        assert checks["erased_unreadable"] is False
        assert checks["erased_same_row"] is False

    def test_a_different_row_with_no_dek_is_not_the_erased_subject(self) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        other = shred_field(seal_subject(cipher, RUN_ID, SUBJECT_ERASED, b"another row"))
        dump["subjects"][SUBJECT_ERASED] = encrypted_field_to_json(other)
        checks = verify_restore(dump, manifest, cipher)
        assert checks["erased_unreadable"] is True
        assert checks["erased_same_row"] is False

    def test_a_dump_for_another_run_is_refused(self) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        dump["run_id"] = "0" * 32
        with pytest.raises(CanaryError, match="run"):
            verify_restore(dump, manifest, cipher)


class TestCharacterisation:
    def test_a_restore_to_before_the_erasure_reports_the_subject_readable(self) -> None:
        """What HB-I8 and INT-037's second ask are about, stated as a
        measurement: restored to a moment before the erasure, the erased
        subject's wrapped DEK is back and the tenant KEK still opens it."""
        cipher = _cipher()
        manifest, dump = _world(cipher)
        before = seal_subject(
            cipher, RUN_ID, SUBJECT_ERASED, subject_plaintext(RUN_ID, SUBJECT_ERASED, SEED)
        )
        dump["subjects"][SUBJECT_ERASED] = encrypted_field_to_json(before)
        assert not is_shredded(before)
        assert canary.erased_subject_state(dump, cipher, RUN_ID) == "readable"

    def test_after_the_erasure_the_state_is_shredded(self) -> None:
        cipher = _cipher()
        _manifest, dump = _world(cipher)
        assert canary.erased_subject_state(dump, cipher, RUN_ID) == "shredded"


class TestCli:
    def test_dump_sql_and_row_count_sql_print(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert canary.main(["dump-sql", "--run-id", RUN_ID]) == 0
        assert "drill_rows" in capsys.readouterr().out
        assert canary.main(["row-count-sql"]) == 0
        assert "count(*)" in capsys.readouterr().out

    def test_verify_reads_the_dump_on_stdin_and_prints_checks(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        code = canary.main(
            ["verify", "--manifest", json.dumps(manifest)], stdin=json.dumps(dump), cipher=cipher
        )
        assert code == 0
        assert json.loads(capsys.readouterr().out)["erased_unreadable"] is True

    def test_verify_exits_1_on_a_failed_check(self, capsys: pytest.CaptureFixture[str]) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        dump["sentinel"] = 1
        code = canary.main(
            ["verify", "--manifest", json.dumps(manifest)], stdin=json.dumps(dump), cipher=cipher
        )
        assert code == 1
        assert json.loads(capsys.readouterr().out)["sentinel_absent"] is False

    def test_erased_state_subcommand(self, capsys: pytest.CaptureFixture[str]) -> None:
        cipher = _cipher()
        _manifest, dump = _world(cipher)
        assert (
            canary.main(["erased-state", "--run-id", RUN_ID], stdin=json.dumps(dump), cipher=cipher)
            == 0
        )
        assert capsys.readouterr().out.strip() == "shredded"

    def test_the_dsn_comes_from_the_bootstrap_url_and_drops_the_driver(self) -> None:
        env = {"INTAKE_API_BOOTSTRAP_DB_URL": "postgresql+psycopg://intake:pw@postgres:5432/intake"}
        assert canary.dsn_from_env(env) == "postgresql://intake:pw@postgres:5432/intake"
        assert (
            canary.dsn_from_env(env, database=CANARY_DATABASE)
            == "postgresql://intake:pw@postgres:5432/intake_restore_drill"
        )

    def test_no_bootstrap_url_is_a_refusal(self) -> None:
        with pytest.raises(CanaryError, match="INTAKE_API_BOOTSTRAP_DB_URL"):
            canary.dsn_from_env({})

    @pytest.mark.parametrize(
        "url", ["mysql://intake:pw@db/intake", "postgresql+psycopg://postgres"]
    )
    def test_a_url_that_is_not_a_postgres_database_url_is_refused(self, url: str) -> None:
        with pytest.raises(CanaryError):
            canary.dsn_from_env({canary.BOOTSTRAP_URL_ENV: url}, database=CANARY_DATABASE)

    def test_the_refusal_never_echoes_the_url(self) -> None:
        env = {canary.BOOTSTRAP_URL_ENV: "mysql://intake:s3cret-value@db/intake"}
        with pytest.raises(CanaryError) as caught:
            canary.dsn_from_env(env)
        assert "s3cret-value" not in str(caught.value)

    def test_bad_json_on_stdin_is_a_refusal(self, capsys: pytest.CaptureFixture[str]) -> None:
        manifest, _dump = _world(_cipher())
        code = canary.main(
            ["verify", "--manifest", json.dumps(manifest)], stdin="not json", cipher=_cipher()
        )
        assert code == 2
        assert "refused" in capsys.readouterr().err

    def test_a_json_array_is_not_a_dump(self) -> None:
        manifest, _dump = _world(_cipher())
        code = canary.main(
            ["verify", "--manifest", json.dumps(manifest)], stdin="[]", cipher=_cipher()
        )
        assert code == 2

    def test_without_an_injected_cipher_the_transit_one_is_built(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cipher = _cipher()
        manifest, dump = _world(cipher)
        monkeypatch.setattr(canary, "_default_cipher", lambda: cipher)
        assert (
            canary.main(["verify", "--manifest", json.dumps(manifest)], stdin=json.dumps(dump)) == 0
        )
        assert json.loads(capsys.readouterr().out)["retained_readable"] is True


# --- the database half, against a recording fake -----------------------------------------

NOW = datetime(2026, 9, 27, 11, 0, tzinfo=UTC)
BOOTSTRAP = {canary.BOOTSTRAP_URL_ENV: "postgresql+psycopg://intake:pw@postgres:5432/intake"}


class _Result:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeConnection:
    """Records every statement and answers the few queries the canary asks."""

    def __init__(
        self,
        *,
        database_exists: bool = False,
        archiver: list[tuple[str | None, datetime | None]] | None = None,
    ) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.database_exists = database_exists
        self.archiver = archiver or []
        self.clock = NOW

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, query: object, params: Sequence[Any] = ()) -> _Result:
        text = str(query)
        self.statements.append((text, tuple(params)))
        if "pg_database" in text:
            return _Result((1,) if self.database_exists else None)
        if "clock_timestamp" in text:
            self.clock += timedelta(milliseconds=5)
            return _Result((self.clock,))
        if "pg_current_wal_lsn" in text:
            return _Result(("0/3000148", "000000010000000000000003"))
        if "pg_stat_archiver" in text:
            return _Result(self.archiver.pop(0) if len(self.archiver) > 1 else self.archiver[0])
        return _Result(None)

    def transaction(self) -> contextlib.AbstractContextManager[None]:
        return contextlib.nullcontext()

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def executemany(self, query: str, rows: list[tuple[Any, ...]]) -> None:
        self.conn.statements.append((query, ("rows", len(rows))))

    def execute(self, query: str, params: Sequence[Any]) -> None:
        self.conn.statements.append((query, tuple(params)))


def _patch_connect(
    monkeypatch: pytest.MonkeyPatch, connections: dict[str, _FakeConnection]
) -> list[str]:
    opened: list[str] = []

    def connect(dsn: str) -> _FakeConnection:
        opened.append(dsn)
        return connections[dsn.rsplit("/", 1)[1]]

    monkeypatch.setattr(canary, "_connect", connect)
    return opened


class TestPrepare:
    def test_it_creates_its_own_database_then_seeds_erases_and_writes_the_sentinel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        admin, drill = _FakeConnection(), _FakeConnection()
        opened = _patch_connect(monkeypatch, {"intake": admin, CANARY_DATABASE: drill})
        manifest = canary.prepare(BOOTSTRAP, _cipher(), run_id=RUN_ID)

        assert opened == [
            "postgresql://intake:pw@postgres:5432/intake",
            f"postgresql://intake:pw@postgres:5432/{CANARY_DATABASE}",
        ]
        assert any("CREATE DATABASE" in text for text, _ in admin.statements)
        texts = [text for text, _ in drill.statements]
        order = [
            next(i for i, t in enumerate(texts) if "INSERT INTO drill_rows" in t),
            next(i for i, t in enumerate(texts) if "INSERT INTO drill_subjects" in t),
            next(i for i, t in enumerate(texts) if "UPDATE drill_subjects" in t),
            next(i for i, t in enumerate(texts) if "INSERT INTO drill_sentinel" in t),
        ]
        assert order == sorted(order)
        rows = next(
            params for text, params in drill.statements if "drill_rows" in text and "INSERT" in text
        )
        assert rows == ("rows", ROWS_PER_RUN)
        assert manifest["run_id"] == RUN_ID
        assert manifest["rows"]["count"] == ROWS_PER_RUN
        assert manifest["walfile"] == "000000010000000000000003"
        assert manifest["before_erasure"] < manifest["recovery_target"]
        assert manifest["recovery_target"].endswith("+00")

    def test_the_erasure_writes_an_envelope_with_no_wrapped_dek(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drill = _FakeConnection()
        _patch_connect(monkeypatch, {"intake": _FakeConnection(), CANARY_DATABASE: drill})
        manifest = canary.prepare(BOOTSTRAP, _cipher(), run_id=RUN_ID)
        update = next(
            params for text, params in drill.statements if "UPDATE drill_subjects" in text
        )
        envelope = json.loads(update[0])
        assert envelope["wrapped_dek"] == ""
        assert update[1:] == (RUN_ID, SUBJECT_ERASED)
        assert (
            sha256_hex(base64.b64decode(envelope["ciphertext"]))
            == (manifest["subjects"][SUBJECT_ERASED]["ciphertext_sha256"])
        )

    def test_an_existing_database_is_reused_and_older_runs_are_cleared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        admin, drill = _FakeConnection(database_exists=True), _FakeConnection()
        _patch_connect(monkeypatch, {"intake": admin, CANARY_DATABASE: drill})
        canary.prepare(BOOTSTRAP, _cipher(), run_id=RUN_ID)
        assert not any("CREATE DATABASE" in text for text, _ in admin.statements)
        cleared = [
            text for text, params in drill.statements if "DELETE" in text and params == (RUN_ID,)
        ]
        assert len(cleared) == 3
        for table in ("drill_rows", "drill_subjects", "drill_sentinel"):
            assert any(table in text for text in cleared)

    def test_cleanup_removes_exactly_this_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        drill = _FakeConnection()
        _patch_connect(monkeypatch, {CANARY_DATABASE: drill})
        canary.cleanup(BOOTSTRAP, RUN_ID)
        assert [params for _text, params in drill.statements] == [(RUN_ID,)] * 3
        with pytest.raises(CanaryError):
            canary.cleanup(BOOTSTRAP, "not-a-run")


class TestWaitArchived:
    @pytest.mark.parametrize(
        ("last", "expected"),
        [
            ("000000010000000000000003", True),
            ("000000010000000000000004", True),
            ("000000010000000000000002", False),
            ("000000020000000000000003", False),
            ("00000002.history", False),
            ("000000010000000000000003.00000028.backup", False),
            (None, False),
        ],
    )
    def test_only_a_segment_at_or_past_the_target_on_its_timeline_counts(
        self, last: str | None, expected: bool
    ) -> None:
        assert canary.archived_covers(last, "000000010000000000000003") is expected

    def test_the_lag_from_the_last_write_is_the_observed_rpo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        archived_at = NOW + timedelta(seconds=42)
        conn = _FakeConnection(
            archiver=[
                ("000000010000000000000002", NOW - timedelta(minutes=1)),
                ("000000010000000000000002.00000028.backup", NOW),
                ("000000010000000000000003", archived_at),
            ]
        )
        _patch_connect(monkeypatch, {"intake": conn})
        sleeps: list[float] = []
        result = canary.wait_archived(
            BOOTSTRAP, "000000010000000000000003", NOW, clock=lambda: 0.0, sleep=sleeps.append
        )
        assert result == {
            "archived": True,
            "archived_at": "2026-09-27T11:00:42.000000Z",
            "rpo_observed_s": 42.0,
        }
        assert len(sleeps) == 2

    def test_not_archived_within_the_budget_is_reported_not_waited_forever(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conn = _FakeConnection(archiver=[("000000010000000000000002", NOW)])
        _patch_connect(monkeypatch, {"intake": conn})
        ticks = iter(range(0, 10_000, 100))
        result = canary.wait_archived(
            BOOTSTRAP,
            "000000010000000000000003",
            NOW,
            timeout_s=900,
            clock=lambda: float(next(ticks)),
            sleep=lambda _s: None,
        )
        assert result == {"archived": False, "rpo_observed_s": None, "waited_s": 900}


class TestDatabaseCli:
    def test_prepare_prints_the_manifest(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(canary, "prepare", lambda env, cipher: {"run_id": RUN_ID})
        assert canary.main(["prepare"], cipher=_cipher(), env=BOOTSTRAP) == 0
        assert json.loads(capsys.readouterr().out) == {"run_id": RUN_ID}

    @pytest.mark.parametrize(("archived", "code"), [(True, 0), (False, 1)])
    def test_wait_archived_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, archived: bool, code: int
    ) -> None:
        seen: dict[str, Any] = {}

        def fake(env: Any, walfile: str, since: datetime, timeout: float) -> dict[str, Any]:
            seen.update(walfile=walfile, since=since, timeout=timeout)
            return {"archived": archived, "rpo_observed_s": 1.0 if archived else None}

        monkeypatch.setattr(canary, "wait_archived", fake)
        argv = ["wait-archived", "--walfile", "000000010000000000000003"]
        argv += ["--since", "2026-09-27T11:00:00.000000Z", "--timeout", "900"]
        assert canary.main(argv, env=BOOTSTRAP) == code
        assert seen["since"] == NOW
        assert seen["timeout"] == 900.0

    def test_cleanup_subcommand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(canary, "cleanup", lambda env, run_id: calls.append(run_id))
        assert canary.main(["cleanup", "--run-id", RUN_ID], env=BOOTSTRAP) == 0
        assert calls == [RUN_ID]
