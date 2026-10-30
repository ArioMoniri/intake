"""INT-016 — the daily verifier job (files/10 §2 §3 §7; invariants 4, 6, 13, 14).

The verifier is the part of a tamper-evident log that is easiest to fake: a
job that walks the chain and always reports green is worse than no job,
because it converts "nobody is checking" into "somebody checked and it was
fine". So the negative cases are the specification and they are written
first. Five ways to attack the store, and what each one costs the attacker:

===========================  ==============================================
attack                       how the verifier answers
===========================  ==============================================
mutate one entry             named by its exact ``seq``
delete one middle entry      named by the ``seq`` that went missing
swap two adjacent entries    named by the first out-of-place ``seq``
truncate the tail            caught by the anchored head; **no position**
re-forge the whole chain     caught **only** by the anchored head
===========================  ==============================================

The last two rows are the honest part. A chain is self-consistent by
construction after a truncation or a full re-forge — that is the whole attack
— so no entry can be blamed and the local walk goes green. The only witness
is a head published where the attacker's credentials do not reach (files/10
§2 (b), invariant 40). This job therefore **refuses to report green without
one**: no anchor is an ``ANCHOR_MISSING`` outcome, ``sec_audit_chain_ok`` 0,
and a non-zero exit — never a pass by omission.

Out of scope, and not claimed anywhere here: publishing that head hourly to a
second organisation's object store or a KEP/e-imza timestamp. That publisher
does not exist in this repo; the verifier consumes an anchor, it does not
manufacture one.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

import pytest
from intake_platform.audit import (
    AuditChain,
    AuditEntry,
    InMemoryAuditStore,
    verify_worm_export,
)
from intake_platform.audit_verifier import (
    SEC_AUDIT_CHAIN_OK,
    AnchorSource,
    VerificationReport,
    VerifierOutcome,
    run_daily_verification,
)
from intake_platform.audit_verifier.cli import (
    EXIT_CHAIN_BROKEN,
    EXIT_NO_ANCHOR,
    EXIT_OK,
    EXIT_REFUSED,
    main,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 29, 9, 0, 0, tzinfo=UTC)


def _chain(store: InMemoryAuditStore) -> AuditChain:
    return AuditChain(store, clock=_fixed_clock)


def _fill(chain: AuditChain, count: int) -> None:
    for i in range(1, count + 1):
        chain.append(
            actor="svc-api",
            action="api.note.read",
            resource_ref=f"note:{i:04d}",
            consent_scope_ref="consent:visit-notes:v1",
        )


def _stocked(count: int = 5) -> tuple[InMemoryAuditStore, str]:
    """A store with ``count`` honest entries, plus the head an external
    witness would have recorded at that moment."""
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, count)
    return store, chain.head


class _Anchor:
    """The external witness, reduced to the one fact the verifier needs."""

    def __init__(self, head: str | None) -> None:
        self._head = head

    def anchored_head(self) -> str | None:
        return self._head


class _Worm:
    """Stand-in for the object-locked bucket. Records what it was handed so a
    test can verify the bundle independently; it does not model object lock,
    which is MinIO's job and is proven in tests/security/test_document_store*."""

    def __init__(self) -> None:
        self.bundles: list[bytes] = []

    def put_audit_bundle(self, bundle: bytes) -> str:
        self.bundles.append(bundle)
        return f"audit/copy-{len(self.bundles)}.jsonl"


def _gauge_value() -> float | None:
    return SEC_AUDIT_CHAIN_OK._value.get()  # noqa: SLF001 — reading our own gauge


# --- the happy path ---------------------------------------------------------------


def test_an_intact_anchored_chain_reports_intact_and_copies_the_bundle() -> None:
    store, head = _stocked(5)
    worm = _Worm()

    report = run_daily_verification(store, anchor=_Anchor(head), worm_sink=worm)

    assert report.outcome is VerifierOutcome.INTACT
    assert report.ok
    assert report.first_bad_seq is None
    assert report.entry_count == 5
    assert report.local_head == head
    assert report.anchor_head == head
    assert report.worm_key == "audit/copy-1.jsonl"
    assert _gauge_value() == 1.0


def test_the_copied_bundle_verifies_on_its_own_with_no_store() -> None:
    store, head = _stocked(4)
    worm = _Worm()

    run_daily_verification(store, anchor=_Anchor(head), worm_sink=worm)

    (bundle,) = worm.bundles
    assert verify_worm_export(bundle).ok
    # The head record must carry the head that was actually verified, not a
    # head the bundle writer invented for itself.
    head_record = json.loads(bundle.decode("utf-8").splitlines()[-1])
    assert head_record["chain_head"] == head
    assert head_record["entry_count"] == 4


def test_a_run_without_a_worm_sink_still_verifies() -> None:
    store, head = _stocked(3)
    report = run_daily_verification(store, anchor=_Anchor(head))
    assert report.outcome is VerifierOutcome.INTACT
    assert report.worm_key is None


def test_an_empty_chain_verifies_against_the_genesis_anchor() -> None:
    store = InMemoryAuditStore()
    report = run_daily_verification(store, anchor=_Anchor("0" * 64))
    assert report.outcome is VerifierOutcome.INTACT
    assert report.entry_count == 0


# --- the five tamper cases --------------------------------------------------------


def test_case1_mutated_entry_is_named_by_its_exact_seq() -> None:
    store, head = _stocked(5)
    worm = _Worm()
    # Tampering is outside the store's contract (it offers no update), so the
    # test reaches into the private list the way an attacker reaches into the
    # table: past the interface.
    store._entries[2] = dataclasses.replace(store._entries[2], resource_ref="note:9999")  # noqa: SLF001

    report = run_daily_verification(store, anchor=_Anchor(head), worm_sink=worm)

    assert report.outcome is VerifierOutcome.CHAIN_BROKEN
    assert report.first_bad_seq == 3
    assert _gauge_value() == 0.0
    assert worm.bundles == [], "a chain known to be broken must not be immortalised"


def test_case2_deleted_middle_entry_is_named_by_the_missing_seq() -> None:
    store, head = _stocked(5)
    del store._entries[2]  # noqa: SLF001 — seq 3 vanishes; 1,2,4,5 remain

    report = run_daily_verification(store, anchor=_Anchor(head))

    assert report.outcome is VerifierOutcome.CHAIN_BROKEN
    assert report.first_bad_seq == 3
    assert "missing or reordered" in report.reason


def test_case3_reordered_pair_is_named_by_the_first_out_of_place_seq() -> None:
    store, head = _stocked(5)
    entries = store._entries  # noqa: SLF001
    entries[1], entries[2] = entries[2], entries[1]  # swap seq 2 and seq 3

    report = run_daily_verification(store, anchor=_Anchor(head))

    assert report.outcome is VerifierOutcome.CHAIN_BROKEN
    assert report.first_bad_seq == 2


def test_case4_truncated_tail_is_caught_by_the_anchor_and_names_no_position() -> None:
    store, head = _stocked(5)
    del store._entries[3:]  # noqa: SLF001 — seq 4 and 5 dropped

    report = run_daily_verification(store, anchor=_Anchor(head))

    assert report.outcome is VerifierOutcome.CHAIN_BROKEN
    # Honest: the surviving prefix is a perfectly valid chain. No entry is at
    # fault, so none is named — the anchor is the only witness.
    assert report.first_bad_seq is None
    assert "truncated, rolled back, or forked" in report.reason


def test_case5_full_reforge_is_invisible_locally_and_caught_only_by_the_anchor() -> None:
    """The attack files/10 §2 names: edit a row **and recompute forward**."""
    store, honest_head = _stocked(5)
    del store._entries[2:]  # noqa: SLF001 — cut back to seq 1..2
    forger = _chain(store)  # re-chains validly from the truncated tail
    for i in range(3, 6):
        forger.append(
            actor="svc-api",
            action="api.note.read",
            resource_ref=f"note:{i:04d}-forged",
            consent_scope_ref="consent:visit-notes:v1",
        )

    # Same entry count, same shape, internally flawless — a self-contained
    # walk cannot tell the difference, and pretending otherwise would be the
    # fake test this suite exists to avoid.
    unanchored = run_daily_verification(store, anchor=_Anchor(forger.head))
    assert unanchored.outcome is VerifierOutcome.INTACT
    assert len(store.entries()) == 5

    anchored = run_daily_verification(store, anchor=_Anchor(honest_head))
    assert anchored.outcome is VerifierOutcome.CHAIN_BROKEN
    assert anchored.first_bad_seq is None
    assert "truncated, rolled back, or forked" in anchored.reason


# --- refusing to be green by omission ---------------------------------------------


def test_no_anchor_is_a_refusal_not_a_pass() -> None:
    store, _ = _stocked(3)
    worm = _Worm()

    report = run_daily_verification(store, anchor=_Anchor(None), worm_sink=worm)

    assert report.outcome is VerifierOutcome.ANCHOR_MISSING
    assert not report.ok
    assert report.anchor_head is None
    assert _gauge_value() == 0.0
    assert worm.bundles == []
    assert "invariant 40" in report.reason


def test_a_malformed_anchor_is_refused_rather_than_compared() -> None:
    store, _ = _stocked(2)
    report = run_daily_verification(store, anchor=_Anchor("not-a-sha256"))
    assert report.outcome is VerifierOutcome.ANCHOR_MISSING
    assert "64" in report.reason


def test_the_report_carries_no_entry_content() -> None:
    """Invariant 6: the verifier's own output is a log too. Ids, hashes and
    counts — never a resource_ref, an actor or a timestamp lifted from a row."""
    store, head = _stocked(3)
    store._entries[1] = dataclasses.replace(  # noqa: SLF001
        store._entries[1], resource_ref="note:leak-me"
    )
    report = run_daily_verification(store, anchor=_Anchor(head))
    blob = json.dumps(dataclasses.asdict(report), default=str)
    assert "leak-me" not in blob
    assert "svc-api" not in blob


def test_report_is_frozen() -> None:
    store, head = _stocked(1)
    report = run_daily_verification(store, anchor=_Anchor(head))
    assert isinstance(report, VerificationReport)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.ok = True  # type: ignore[misc]


def test_anchor_source_protocol_is_satisfied_structurally() -> None:
    anchor: AnchorSource = _Anchor("0" * 64)
    assert anchor.anchored_head() == "0" * 64


# --- the CLI --------------------------------------------------------------------


def test_cli_reports_ok_for_an_anchored_intact_chain(capsys: pytest.CaptureFixture[str]) -> None:
    store, head = _stocked(4)
    code = main(["--anchor-head", head], store=store)
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "intact" in out
    assert "4" in out


def test_cli_exits_non_zero_on_a_broken_chain(capsys: pytest.CaptureFixture[str]) -> None:
    store, head = _stocked(4)
    store._entries[1] = dataclasses.replace(store._entries[1], action="api.note.share")  # noqa: SLF001
    code = main(["--anchor-head", head], store=store)
    assert code == EXIT_CHAIN_BROKEN
    assert "seq 2" in capsys.readouterr().out


def test_cli_without_an_anchor_refuses_and_says_who_must_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, _ = _stocked(2)
    code = main([], store=store)
    assert code == EXIT_NO_ANCHOR
    out = capsys.readouterr().out
    assert "--anchor-head" in out
    assert "HB-I12" in out


def test_cli_rejects_a_malformed_anchor(capsys: pytest.CaptureFixture[str]) -> None:
    store, _ = _stocked(2)
    assert main(["--anchor-head", "cafe"], store=store) == EXIT_REFUSED
    assert "64 lowercase hex" in capsys.readouterr().out


def test_cli_reads_the_anchor_from_a_file(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:  # type: ignore[no-untyped-def]
    store, head = _stocked(3)
    path = tmp_path / "anchor.head"
    path.write_text(f"  {head}\n", encoding="utf-8")
    assert main(["--anchor-file", str(path)], store=store) == EXIT_OK
    assert "intact" in capsys.readouterr().out


def test_cli_refuses_an_unreadable_anchor_file(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:  # type: ignore[no-untyped-def]
    store, _ = _stocked(1)
    missing = tmp_path / "nope.head"
    assert main(["--anchor-file", str(missing)], store=store) == EXIT_REFUSED
    assert "anchor file" in capsys.readouterr().out


def test_cli_refuses_both_anchor_flags_at_once(capsys: pytest.CaptureFixture[str]) -> None:
    store, head = _stocked(1)
    code = main(["--anchor-head", head, "--anchor-file", "/dev/null"], store=store)
    assert code == EXIT_REFUSED
    assert "exactly one" in capsys.readouterr().out


def test_cli_archives_only_when_worm_copy_is_asked_for(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A flag a caller's argument can silently override is not a control: the
    injected sink says *how* to archive, ``--worm-copy`` says *whether*."""
    store, head = _stocked(2)
    worm = _Worm()

    assert main(["--anchor-head", head], store=store, worm_sink=worm) == EXIT_OK
    assert worm.bundles == []
    assert "WORM copy" not in capsys.readouterr().out

    assert main(["--anchor-head", head, "--worm-copy"], store=store, worm_sink=worm) == EXIT_OK
    assert len(worm.bundles) == 1
    assert "WORM copy" in capsys.readouterr().out


def test_cli_prints_no_entry_content(capsys: pytest.CaptureFixture[str]) -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    chain.append(
        actor="clinician:abc",
        action="api.note.read",
        resource_ref="note:secret-ref",
        consent_scope_ref="consent:visit-notes:v1",
    )
    main(["--anchor-head", chain.head], store=store)
    out = capsys.readouterr().out
    assert "secret-ref" not in out
    assert "clinician:abc" not in out


def test_cli_without_a_store_and_without_a_database_url_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--anchor-head", "0" * 64], env={})
    assert code == EXIT_REFUSED
    assert "INTAKE_DATABASE_URL" in capsys.readouterr().out


def test_cli_builds_its_store_from_the_database_url(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:  # type: ignore[no-untyped-def]
    """The production wiring, exercised without docker: SQLite carries the
    ``audit_chain`` table because its columns are dialect-neutral (INT-030)."""
    from intake_platform.db.audit_store import AuditChainRow, SqlAlchemyAuditStore
    from intake_platform.db.models import Base
    from sqlalchemy import create_engine

    url = f"sqlite+pysqlite:///{tmp_path / 'audit.sqlite3'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[AuditChainRow.__table__])
    chain = AuditChain(SqlAlchemyAuditStore(engine), clock=_fixed_clock)
    _fill(chain, 3)
    engine.dispose()

    code = main(["--anchor-head", chain.head], env={"INTAKE_DATABASE_URL": url})

    assert code == EXIT_OK
    assert "intact" in capsys.readouterr().out


def test_entries_returned_by_the_store_are_what_is_verified() -> None:
    """A store that lies about its own tail cannot make the walk agree with
    the anchor: the walk recomputes every hash from the entries themselves."""
    store, head = _stocked(3)
    forged_tail = AuditEntry(
        seq=3,
        timestamp_utc="2026-08-29T09:00:00+00:00",
        actor="svc-api",
        action="api.note.read",
        resource_ref="note:0003-substituted",
        consent_scope_ref="consent:visit-notes:v1",
        prev_hash=store._entries[1].entry_hash,  # noqa: SLF001
        entry_hash=head,  # claims the honest head while carrying other content
    )
    store._entries[2] = forged_tail  # noqa: SLF001
    report = run_daily_verification(store, anchor=_Anchor(head))
    assert report.outcome is VerifierOutcome.CHAIN_BROKEN
    assert report.first_bad_seq == 3
