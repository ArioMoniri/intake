"""INT-016 — the daily verifier, made runnable and observable.

``run_daily_verifier`` was a pure function nothing invoked: the chain was
verified only when a test called it. This suite pins the entry point that
makes it a job — ``python -m intake_platform.audit_verify`` — including the
three things a scheduler needs from a batch job and a pure function cannot
give it: a **process exit code**, a **machine-readable result on stdout**, and
a **metric** (``sec_audit_chain_ok``, already catalogued in
observability/metrics_catalog.yaml, so nothing uncatalogued is emitted).

It also pins the honesty of the weaker check: with no externally anchored head
(files/10 §2's invariant-40 half, which has no transport yet) the run reports
``anchored: false`` rather than a green tick that overstates what was proved.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from intake_platform.audit import GENESIS_PREV_HASH, AuditChain
from intake_platform.audit_verify import EXIT_BROKEN, EXIT_OK, EXIT_UNUSABLE, main
from intake_platform.db.audit_store import AuditChainRow, SqlAlchemyAuditStore
from intake_platform.db.models import Base
from sqlalchemy import Engine, create_engine, text


@pytest.fixture
def audit_db(tmp_path: Path) -> Iterator[tuple[str, Engine]]:
    path = tmp_path / "audit.db"
    url = f"sqlite+pysqlite:///{path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[AuditChainRow.__table__])
    yield url, engine
    engine.dispose()


def _fill(engine: Engine, count: int = 3) -> AuditChain:
    chain = AuditChain(SqlAlchemyAuditStore(engine))
    for index in range(count):
        chain.append(
            actor="svc-audit-writer",
            action="api.note.read",
            resource_ref=f"note:{index}",
            consent_scope_ref="scope:core",
        )
    return chain


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, object]]:
    code = main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_an_intact_chain_exits_zero_and_reports_the_head(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    url, engine = audit_db
    chain = _fill(engine)
    code, report = _run(capsys, "--audit-db-url", url)
    assert code == EXIT_OK
    assert report["ok"] is True
    assert report["check"] == "audit_chain"
    assert report["entry_count"] == 3
    assert report["chain_head"] == chain.head
    assert report["first_bad_seq"] is None


def test_an_empty_chain_verifies_and_reports_the_genesis_head(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    url, _engine = audit_db
    code, report = _run(capsys, "--audit-db-url", url)
    assert code == EXIT_OK
    assert report["entry_count"] == 0
    assert report["chain_head"] == GENESIS_PREV_HASH


def test_an_edited_row_exits_nonzero_and_names_the_exact_seq(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    url, engine = audit_db
    _fill(engine, 5)
    with engine.begin() as conn:
        conn.execute(text("UPDATE audit_chain SET actor = 'someone-else' WHERE seq = 3"))
    code, report = _run(capsys, "--audit-db-url", url)
    assert code == EXIT_BROKEN
    assert report["ok"] is False
    assert report["first_bad_seq"] == 3


def test_without_an_external_anchor_the_run_says_it_is_unanchored(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    """The chain alone cannot catch edit-and-recompute (files/10 §2). A run
    that did not check an external head must say so instead of reporting a
    green that overstates the property."""
    url, engine = audit_db
    _fill(engine)
    _code, report = _run(capsys, "--audit-db-url", url)
    assert report["anchored"] is False


def test_with_an_external_anchor_a_fork_is_caught(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    url, engine = audit_db
    chain = _fill(engine, 4)
    honest_head = chain.head
    # truncate and re-append: the forged store is internally consistent, so
    # only the anchored head can catch it
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_chain WHERE seq = 4"))
    forger = AuditChain(SqlAlchemyAuditStore(engine))
    forger.append(
        actor="platform-owner",
        action="api.note.read",
        resource_ref="note:forged",
        consent_scope_ref="scope:core",
    )
    unanchored_code, unanchored = _run(capsys, "--audit-db-url", url)
    assert unanchored_code == EXIT_OK and unanchored["ok"] is True

    code, report = _run(capsys, "--audit-db-url", url, "--expected-head", honest_head)
    assert code == EXIT_BROKEN
    assert report["anchored"] is True
    assert report["first_bad_seq"] is None


def test_the_run_writes_the_catalogued_gauge_to_a_textfile(
    audit_db: tuple[str, Engine], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url, engine = audit_db
    _fill(engine)
    metrics = tmp_path / "audit_chain.prom"
    code, _report = _run(capsys, "--audit-db-url", url, "--metrics-file", str(metrics))
    assert code == EXIT_OK
    written = metrics.read_text(encoding="utf-8")
    assert "sec_audit_chain_ok" in written
    assert "sec_audit_chain_ok 1.0" in written


def test_a_broken_chain_writes_the_gauge_as_zero(
    audit_db: tuple[str, Engine], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url, engine = audit_db
    _fill(engine, 3)
    with engine.begin() as conn:
        conn.execute(text("UPDATE audit_chain SET actor = 'x' WHERE seq = 2"))
    metrics = tmp_path / "audit_chain.prom"
    code, _report = _run(capsys, "--audit-db-url", url, "--metrics-file", str(metrics))
    assert code == EXIT_BROKEN
    assert "sec_audit_chain_ok 0.0" in metrics.read_text(encoding="utf-8")


def test_no_database_url_is_an_unusable_invocation_not_a_green_run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scheduler that mis-wires the job must not read 'chain intact'."""
    monkeypatch.delenv("INTAKE_AUDIT_DB_URL", raising=False)
    code, report = _run(capsys)
    assert code == EXIT_UNUSABLE
    assert report["ok"] is False
    assert report["error"] == "audit_db_url_missing"


def test_an_unreachable_database_is_unusable_not_broken(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A chain that could not be READ is not a chain that failed: reporting a
    connection error as a tamper finding would page the wrong on-call and
    train them to ignore the real one."""
    code, report = _run(
        capsys, "--audit-db-url", f"sqlite+pysqlite:///{tmp_path / 'never-created.db'}"
    )
    assert code == EXIT_UNUSABLE
    assert report["error"] == "audit_store_unreadable"


@pytest.mark.parametrize("bad_url", ["not-a-url", "nosuchdriver://host/db"])
def test_a_malformed_url_is_unusable_and_is_never_echoed_back(
    bad_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A connection string carries credentials, so the refusal names the
    failure class and not the value (invariant 6) — the same rule the chain's
    own id-shape check follows."""
    code, report = _run(capsys, "--audit-db-url", bad_url)
    assert code == EXIT_UNUSABLE
    assert report["error"] == "audit_db_url_unusable"
    assert bad_url not in json.dumps(report)


def test_the_url_is_read_from_the_environment_when_not_passed(
    audit_db: tuple[str, Engine],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url, engine = audit_db
    _fill(engine)
    monkeypatch.setenv("INTAKE_AUDIT_DB_URL", url)
    code, report = _run(capsys)
    assert code == EXIT_OK
    assert report["entry_count"] == 3


def test_the_report_carries_ids_only(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    """Invariant 6: the verifier's output goes to a scheduler log. It may
    name seqs, counts and hashes — never a connection string (which carries
    credentials) and never an entry's content."""
    url, engine = audit_db
    _fill(engine)
    _code, report = _run(capsys, "--audit-db-url", url)
    rendered = json.dumps(report)
    assert url not in rendered
    assert "note:" not in rendered
    assert "svc-audit-writer" not in rendered


def test_a_rolled_back_store_is_caught_by_the_anchor(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    url, engine = audit_db
    chain = _fill(engine, 4)
    head = chain.head
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_chain WHERE seq = 4"))
    code, report = _run(capsys, "--audit-db-url", url, "--expected-head", head)
    assert code == EXIT_BROKEN
    assert report["anchored"] is True


def test_the_verifier_reads_the_same_entries_the_store_holds(
    audit_db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]
) -> None:
    """The job must not quietly re-serialise ``timestamp_utc`` on the way in —
    that is a rehash-breaking transformation, and it would turn every run
    into a false positive."""
    url, engine = audit_db
    _fill(engine)
    store = SqlAlchemyAuditStore(engine)
    entries = store.entries()
    assert replace(entries[0]) == entries[0]
    code, _report = _run(capsys, "--audit-db-url", url)
    assert code == EXIT_OK
