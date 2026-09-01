"""INT-016 — hash-chained audit log, unit lane (files/10 §2; invariants 4, 6, 14).

What these tests pin:

- every entry hashes a canonical JSON serialization (sorted keys, no
  whitespace) of the entry minus ``entry_hash``, and genesis ``prev_hash`` is
  64 zeros — an independent implementation can re-verify the chain from the
  spec alone;
- editing a middle entry is detected and the verifier names the exact ``seq``
  of the break; editing an entry *and* recomputing its hash moves the break to
  the next link, never hides it;
- a truncate-and-re-append fork yields a store that is internally consistent
  and is still caught, because the writer's running head no longer matches;
- the WORM export is a self-contained bundle that a standalone function
  verifies with no store at hand;
- the entry field set is closed and id-shaped, so free text — PHI's carrier —
  cannot enter the log (invariant 6).

Out of scope here (the integration slice): the SQLAlchemy store, the MinIO
object-lock copy, the externally anchored head (files/10 invariant 40) and the
worker scheduling of the daily verifier.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from intake_platform.audit import (
    GENESIS_PREV_HASH,
    AuditChain,
    AuditEntry,
    InMemoryAuditStore,
    build_worm_bundle,
    run_daily_verifier,
    verify_entries,
    verify_worm_export,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 27, 12, 0, 0, tzinfo=UTC)


def _chain(store: InMemoryAuditStore) -> AuditChain:
    return AuditChain(store, clock=_fixed_clock)


def _fill(chain: AuditChain, count: int) -> None:
    for i in range(1, count + 1):
        chain.append(
            actor="svc-api",
            action="clinical.note.read",
            resource_ref=f"note:{i:04d}",
            consent_scope_ref="consent:visit-notes:v1",
        )


def _rehash(entry: AuditEntry) -> str:
    """Independent re-implementation of the canonical hash, so the test pins
    the wire format instead of trusting the module's own helper."""
    payload = dataclasses.asdict(entry)
    del payload["entry_hash"]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- append + verify --------------------------------------------------------------


def test_append_builds_a_linked_chain_from_the_zero_genesis() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 3)

    first, second, third = store.entries()
    assert GENESIS_PREV_HASH == "0" * 64
    assert first.prev_hash == GENESIS_PREV_HASH
    assert second.prev_hash == first.entry_hash
    assert third.prev_hash == second.entry_hash
    assert (first.seq, second.seq, third.seq) == (1, 2, 3)
    assert first.timestamp_utc == "2026-08-27T12:00:00+00:00"
    assert chain.head == third.entry_hash

    result = chain.verify()
    assert result.ok
    assert result.first_bad_seq is None


def test_entry_hash_is_sha256_over_canonical_json_minus_entry_hash() -> None:
    store = InMemoryAuditStore()
    _fill(_chain(store), 2)
    for entry in store.entries():
        assert entry.entry_hash == _rehash(entry)


def test_empty_chain_verifies_and_head_is_the_genesis_value() -> None:
    chain = _chain(InMemoryAuditStore())
    assert chain.head == GENESIS_PREV_HASH
    result = chain.verify()
    assert result.ok
    assert result.first_bad_seq is None


def test_single_entry_chain_verifies() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 1)
    (only,) = store.entries()
    assert only.prev_hash == GENESIS_PREV_HASH
    assert chain.verify().ok


def test_a_new_chain_resumes_from_the_stored_tail() -> None:
    store = InMemoryAuditStore()
    _fill(_chain(store), 2)
    resumed = _chain(store)  # e.g. a writer restart over the same store
    _fill(resumed, 1)
    entries = store.entries()
    assert entries[2].seq == 3
    assert entries[2].prev_hash == entries[1].entry_hash
    assert resumed.verify().ok


# --- tamper detection -------------------------------------------------------------


def test_tampered_middle_entry_is_named_by_exact_seq() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 5)
    # Tampering is by definition outside the store's contract (it offers no
    # update), so the test reaches into the private list on purpose.
    victim = store._entries[2]
    store._entries[2] = dataclasses.replace(victim, resource_ref="note:9999")

    result = chain.verify()
    assert not result.ok
    assert result.first_bad_seq == 3
    assert "entry 3" in result.reason
    assert "hash" in result.reason


def test_tamper_plus_rehash_moves_the_break_to_the_next_link() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 5)
    edited = dataclasses.replace(store._entries[2], resource_ref="note:9999")
    store._entries[2] = dataclasses.replace(edited, entry_hash=_rehash(edited))

    result = chain.verify()
    assert not result.ok
    assert result.first_bad_seq == 4
    assert "prev_hash" in result.reason


def test_deleted_middle_entry_is_named_by_the_missing_seq() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 5)
    del store._entries[2]  # seq 3 vanishes; 1, 2, 4, 5 remain

    result = chain.verify()
    assert not result.ok
    assert result.first_bad_seq == 3
    assert "missing or reordered" in result.reason


def test_reordered_pair_is_named_by_the_first_out_of_place_seq() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 5)
    entries = store._entries
    entries[1], entries[2] = entries[2], entries[1]

    result = chain.verify()
    assert not result.ok
    assert result.first_bad_seq == 2


def test_rollback_of_the_store_is_detected_via_the_running_head() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 5)
    del store._entries[3:]

    result = chain.verify()
    assert not result.ok
    assert result.first_bad_seq is None
    assert "running head" in result.reason


def test_fork_truncate_and_reappend_is_detected_via_the_running_head() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 5)
    del store._entries[2:]
    forger = _chain(store)  # chains validly from the truncated tail
    forger.append(
        actor="svc-api",
        action="clinical.note.read",
        resource_ref="note:6666",
        consent_scope_ref="consent:visit-notes:v1",
    )
    # The forged store is internally consistent — that is the whole attack —
    # and only the honest writer's running head still knows better.
    assert forger.verify().ok
    result = chain.verify()
    assert not result.ok
    assert result.first_bad_seq is None
    assert "running head" in result.reason


def test_a_full_reforge_defeats_the_self_contained_walk_by_design() -> None:
    """State the limit rather than paper over it (files/10 §2, corrected
    25 Aug 2026). An attacker who edits a row **and recomputes every hash
    forward** produces a chain that is flawless on its own terms; the walk
    cannot tell it from history. Only a head recorded outside the attacker's
    reach can, which is why ``verify_entries`` takes ``expected_head`` and why
    the daily verifier refuses to report green without one (invariant 40)."""
    store = InMemoryAuditStore()
    honest = _chain(store)
    _fill(honest, 5)
    honest_head = honest.head

    del store._entries[1:]  # keep seq 1, discard the rest
    forger = _chain(store)
    for i in range(2, 6):
        forger.append(
            actor="svc-api",
            action="clinical.note.read",
            resource_ref=f"note:{i:04d}-forged",
            consent_scope_ref="consent:visit-notes:v1",
        )

    # Same length, same shape, every hash correct — the forgery passes.
    assert len(store.entries()) == 5
    assert verify_entries(store.entries()).ok
    assert verify_entries(store.entries(), expected_head=forger.head).ok

    # The externally recorded head is the only thing that still disagrees.
    against_anchor = verify_entries(store.entries(), expected_head=honest_head)
    assert not against_anchor.ok
    assert against_anchor.first_bad_seq is None
    assert "forked" in against_anchor.reason


# --- WORM export ------------------------------------------------------------------


def test_worm_export_is_a_self_verifying_bundle() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 4)
    bundle = chain.export_worm()
    result = verify_worm_export(bundle)
    assert result.ok
    assert result.first_bad_seq is None


def test_worm_export_of_an_empty_chain_self_verifies() -> None:
    bundle = _chain(InMemoryAuditStore()).export_worm()
    assert verify_worm_export(bundle).ok


def test_the_bundle_builder_is_reachable_without_a_writer() -> None:
    """The daily verifier holds no INSERT capability, so it must be able to
    build the WORM copy from entries and a head alone — byte-identical to
    what the writer's ``export_worm`` produces."""
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 3)
    assert build_worm_bundle(store.entries(), chain.head) == chain.export_worm()


def test_worm_export_detects_an_edited_line() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 4)
    bundle = chain.export_worm().replace(b"note:0002", b"note:9999")
    result = verify_worm_export(bundle)
    assert not result.ok
    assert result.first_bad_seq == 2


def test_worm_export_detects_a_dropped_line() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 4)
    lines = chain.export_worm().splitlines()
    del lines[2]  # remove the seq-3 entry
    result = verify_worm_export(b"\n".join(lines) + b"\n")
    assert not result.ok
    assert result.first_bad_seq == 3


def test_worm_export_without_its_head_record_is_rejected() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 2)
    lines = chain.export_worm().splitlines()
    result = verify_worm_export(b"\n".join(lines[:-1]) + b"\n")
    assert not result.ok
    assert "head record" in result.reason


def test_worm_export_rejects_garbage_bundles() -> None:
    assert not verify_worm_export(b"").ok
    assert not verify_worm_export(b"\xff\xfe").ok
    assert not verify_worm_export(b"not json at all\n").ok
    assert not verify_worm_export(b'["a","list"]\n').ok


def test_worm_export_rejects_malformed_entry_and_head_records() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 2)
    lines = chain.export_worm().splitlines()
    head = lines[-1]

    def bundle_with(entry_line: bytes) -> bytes:
        return b"\n".join([lines[0], entry_line, head]) + b"\n"

    record = dataclasses.asdict(store.entries()[1])

    # An entry line that is not JSON, not an object, or not the closed field
    # set — each names its line, none is coerced into a best guess.
    assert "line 2" in verify_worm_export(bundle_with(b"{broken json")).reason
    assert "line 2" in verify_worm_export(bundle_with(b'"just-a-string"')).reason
    extra = dict(record, note_text="free text has no field to hide in")
    assert (
        "closed audit field set"
        in verify_worm_export(bundle_with(json.dumps(extra).encode())).reason
    )
    bool_seq = dict(record, seq=True)
    assert not verify_worm_export(bundle_with(json.dumps(bool_seq).encode())).ok
    int_actor = dict(record, actor=7)
    assert not verify_worm_export(bundle_with(json.dumps(int_actor).encode())).ok

    # Head-record defects: wrong value types, and a count that contradicts an
    # otherwise intact chain (a forged head is a defect, not a rounding error).
    typed_head = json.loads(head)
    bad_types = dict(typed_head, entry_count="2")
    assert (
        "malformed"
        in verify_worm_export(
            b"\n".join([*lines[:-1], json.dumps(bad_types).encode()]) + b"\n"
        ).reason
    )
    bad_count = dict(typed_head, entry_count=5)
    assert (
        "declares 5 entries"
        in verify_worm_export(
            b"\n".join([*lines[:-1], json.dumps(bad_count).encode()]) + b"\n"
        ).reason
    )


def test_default_clock_writes_timezone_aware_utc_timestamps() -> None:
    store = InMemoryAuditStore()
    chain = AuditChain(store)  # no injected clock: the real one must be UTC
    chain.append(
        actor="svc-api",
        action="clinical.note.read",
        resource_ref="note:0001",
        consent_scope_ref="consent:visit-notes:v1",
    )
    (entry,) = store.entries()
    stamp = datetime.fromisoformat(entry.timestamp_utc)
    assert stamp.tzinfo is not None
    assert stamp.utcoffset() == timedelta(0)


# --- the closed, id-shaped field set (invariant 6) --------------------------------


def test_free_text_fields_are_refused_with_the_field_named() -> None:
    chain = _chain(InMemoryAuditStore())
    with pytest.raises(ValueError, match="actor"):
        chain.append(
            actor="Ayşe Yılmaz 0532 111 44 55",
            action="clinical.note.read",
            resource_ref="note:0001",
            consent_scope_ref="consent:visit-notes:v1",
        )
    with pytest.raises(ValueError, match="resource_ref"):
        chain.append(
            actor="svc-api",
            action="clinical.note.read",
            resource_ref="patient said chest pain since Tuesday",
            consent_scope_ref="consent:visit-notes:v1",
        )
    # Nothing may have been half-appended by a refused call.
    assert chain.verify().ok
    assert chain.head == GENESIS_PREV_HASH


def test_error_for_refused_fields_never_echoes_the_value() -> None:
    chain = _chain(InMemoryAuditStore())
    with pytest.raises(ValueError) as excinfo:
        chain.append(
            actor="Ayşe Yılmaz",
            action="clinical.note.read",
            resource_ref="note:0001",
            consent_scope_ref="consent:visit-notes:v1",
        )
    assert "Yılmaz" not in str(excinfo.value)


def test_entries_are_frozen() -> None:
    store = InMemoryAuditStore()
    _fill(_chain(store), 1)
    (entry,) = store.entries()
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.actor = "someone-else"  # type: ignore[misc]


def test_naive_clock_is_refused() -> None:
    def naive() -> datetime:
        return datetime(2026, 8, 27, 12, 0, 0)  # noqa: DTZ001 — the point of the test

    chain = AuditChain(InMemoryAuditStore(), clock=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        chain.append(
            actor="svc-api",
            action="clinical.note.read",
            resource_ref="note:0001",
            consent_scope_ref="consent:visit-notes:v1",
        )


# --- daily verifier ---------------------------------------------------------------


def test_daily_verifier_is_pure_over_a_store() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 3)
    assert run_daily_verifier(store).ok

    victim = store._entries[1]
    store._entries[1] = dataclasses.replace(victim, action="clinical.note.share")
    result = run_daily_verifier(store)
    assert not result.ok
    assert result.first_bad_seq == 2


def test_daily_verifier_accepts_an_expected_head_for_fork_detection() -> None:
    store = InMemoryAuditStore()
    chain = _chain(store)
    _fill(chain, 3)
    anchored_head = chain.head  # the integration slice anchors this externally
    assert run_daily_verifier(store, expected_head=anchored_head).ok

    del store._entries[2:]
    result = run_daily_verifier(store, expected_head=anchored_head)
    assert not result.ok
    assert "running head" in result.reason
