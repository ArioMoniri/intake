"""Hash-chained audit log (INT-016; files/10 §2, sec_row: audit).

Why a hash chain: invariant 4 says every read/share of clinical data is
audited, and an audit trail an insider can silently rewrite is not evidence —
KVKK-12 and KSVY-7 both hinge on showing the log was not edited after the
fact. Each entry carries the SHA-256 of its predecessor, so editing any row
invalidates every hash after it and the verifier can name the exact ``seq``
where history diverges.

What the chain does and does not defend (files/10 §2, corrected 25 Aug 2026):
an attacker who edits a row *and recomputes the chain forward* defeats any
self-contained chain. The unit-lane defence is the writer's **running head** —
a truncated-and-re-appended store is internally consistent yet no longer
matches the head the honest writer holds — and the full answer (the externally
anchored head plus the INSERT-only ``svc-audit-writer`` grant, invariant 40)
arrives with the integration slice. ``run_daily_verifier`` already accepts
that anchored head, so the integration slice adds transport, not logic.

No PHI ever enters an entry (invariant 6): the field set is closed —
dataclass fields, never a free-form mapping — and every caller-supplied value
must be id-shaped, so narrative text has no carrier. Refusal errors name the
offending field but never echo its value, because the value is exactly what
must not reach a log.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from typing import Protocol

__all__ = [
    "GENESIS_PREV_HASH",
    "AuditChain",
    "AuditEntry",
    "AuditStore",
    "InMemoryAuditStore",
    "VerificationResult",
    "build_worm_bundle",
    "run_daily_verifier",
    "verify_entries",
    "verify_worm_export",
]

GENESIS_PREV_HASH = "0" * 64

# Ids, refs and dotted action names only — anything with spaces or non-ASCII
# (the shape of a name, a formatted phone number, narrative) is refused.
_REF_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}")

_HEAD_RECORD_TYPE = "worm_head"


@dataclass(frozen=True)
class AuditEntry:
    """One chain link. The field set is closed on purpose (invariant 6): an
    audit log that accepts arbitrary keys accumulates PHI the first time
    someone logs a payload "for context". Ids and refs only; frozen so an
    in-process reference cannot drift from what was hashed."""

    seq: int
    timestamp_utc: str
    actor: str
    action: str
    resource_ref: str
    consent_scope_ref: str
    prev_hash: str
    entry_hash: str


_ENTRY_FIELDS = frozenset(f.name for f in fields(AuditEntry))


@dataclass(frozen=True)
class VerificationResult:
    """``first_bad_seq`` names the exact entry where the chain breaks; it is
    ``None`` when the chain is intact or when the break is not attributable to
    one entry (a fork detected only via the head, a malformed bundle)."""

    ok: bool
    first_bad_seq: int | None
    reason: str


def _entry_hash(entry: AuditEntry) -> str:
    """Canonical hash: sorted keys, no whitespace, ASCII-only JSON over every
    field except ``entry_hash`` itself. The format is deliberately boring and
    fully specified so an independent implementation — the standalone WORM
    check, or an auditor's own script — reproduces it byte for byte."""
    payload = asdict(entry)
    del payload["entry_hash"]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_ref_shaped(field_name: str, value: str) -> None:
    # The refused value is deliberately absent from the message: it may be the
    # very PHI the shape check exists to keep out of logs (invariant 6).
    if not _REF_SHAPE.fullmatch(value):
        raise ValueError(
            f"audit field {field_name!r} must be id-shaped ([A-Za-z0-9._:/@-], "
            "≤128 chars, no spaces): free text is how PHI reaches a log "
            "(invariant 6); the refused value is not echoed here for the same reason"
        )


class AuditStore(Protocol):
    """Storage seam, deliberately INSERT-shaped: no update, no delete —
    mirroring the production grant where ``svc-audit-writer`` holds the only
    INSERT and no principal holds UPDATE or DELETE (files/10 §2). A SQLAlchemy
    implementation maps ``append`` to an INSERT, ``last`` to ``ORDER BY seq
    DESC LIMIT 1`` and ``entries`` to an ``ORDER BY seq`` scan; it belongs to
    the integration slice, not this module."""

    def append(self, entry: AuditEntry) -> None: ...
    def last(self) -> AuditEntry | None: ...
    def entries(self) -> Sequence[AuditEntry]: ...


class InMemoryAuditStore:
    """Unit-lane store: a list behind the :class:`AuditStore` shape. Tests
    that tamper reach into ``_entries`` directly — tampering is by definition
    outside the store's contract, so the contract offers no method for it."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def last(self) -> AuditEntry | None:
        return self._entries[-1] if self._entries else None

    def entries(self) -> Sequence[AuditEntry]:
        return tuple(self._entries)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class AuditChain:
    """Writer + verifier over a store. Holds the running head in memory: the
    head is the one fact a truncate-and-re-append fork cannot reproduce,
    because the forged tail never saw it. Publishing this head outside the
    writer's blast radius (invariant 40) is the integration slice's job.

    **One writer at a time** (INT-553). An append reads the running head and
    the next ``seq``, writes the store, then moves both; two threads inside it
    at once would both link to the same head under the same ``seq`` and fork
    the chain. A lock serialises the whole step — the voice runtime's
    clinic-item audit worker writes from its own thread — and the reads that
    must see the head and the store agree (:meth:`verify`, :meth:`export_worm`)
    take it too."""

    def __init__(self, store: AuditStore, *, clock: Callable[[], datetime] | None = None) -> None:
        self._store = store
        self._clock = clock if clock is not None else _utc_now
        self._lock = threading.Lock()
        tail = store.last()
        self._head = tail.entry_hash if tail is not None else GENESIS_PREV_HASH
        self._next_seq = tail.seq + 1 if tail is not None else 1

    @property
    def head(self) -> str:
        """The running head: the newest entry's hash, or the genesis value
        while the chain is empty (which is what entry 1 will link to)."""
        with self._lock:
            return self._head

    def append(
        self, *, actor: str, action: str, resource_ref: str, consent_scope_ref: str
    ) -> AuditEntry:
        for field_name, value in (
            ("actor", actor),
            ("action", action),
            ("resource_ref", resource_ref),
            ("consent_scope_ref", consent_scope_ref),
        ):
            _require_ref_shaped(field_name, value)
        with self._lock:
            stamp = self._clock()
            if stamp.tzinfo is None:
                raise ValueError("audit clock must return timezone-aware datetimes (UTC)")
            unsigned = AuditEntry(
                seq=self._next_seq,
                timestamp_utc=stamp.astimezone(UTC).isoformat(),
                actor=actor,
                action=action,
                resource_ref=resource_ref,
                consent_scope_ref=consent_scope_ref,
                prev_hash=self._head,
                entry_hash="",
            )
            entry = replace(unsigned, entry_hash=_entry_hash(unsigned))
            self._store.append(entry)
            self._head = entry.entry_hash
            self._next_seq += 1
            return entry

    def verify(self) -> VerificationResult:
        with self._lock:
            return verify_entries(self._store.entries(), expected_head=self._head)

    def export_worm(self) -> bytes:
        """The writer's view of :func:`build_worm_bundle`: this chain's
        entries under this chain's running head."""
        with self._lock:
            return build_worm_bundle(self._store.entries(), self._head)


def build_worm_bundle(entries: Sequence[AuditEntry], head: str) -> bytes:
    """A self-verifying JSON-lines bundle: every entry in canonical form, then
    one head record carrying ``head`` and the count. The bundle needs no store
    to check — that independence is what makes the object-lock (WORM) copy
    auditable on its own, and it is why this is a free function rather than a
    method: the daily verifier builds the copy while holding no writer, and
    therefore no INSERT capability on the chain (files/10 §2)."""
    lines = [
        json.dumps(asdict(entry), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        for entry in entries
    ]
    head_record: dict[str, int | str] = {
        "chain_head": head,
        "entry_count": len(entries),
        "hash_algorithm": "sha256",
        "record_type": _HEAD_RECORD_TYPE,
    }
    lines.append(json.dumps(head_record, sort_keys=True, separators=(",", ":")))
    return ("\n".join(lines) + "\n").encode("utf-8")


def verify_entries(
    entries: Sequence[AuditEntry], expected_head: str | None = None
) -> VerificationResult:
    """Walk the chain from genesis. Per-entry breaks (sequence gap, broken
    link, edited content) are reported with the exact ``seq``; only after
    every entry checks out is the recomputed head compared against
    ``expected_head`` — a mismatch there means fork or rollback, which no
    single entry can be blamed for."""
    prev_hash = GENESIS_PREV_HASH
    for position, entry in enumerate(entries):
        expected_seq = position + 1
        if entry.seq != expected_seq:
            return VerificationResult(
                ok=False,
                first_bad_seq=expected_seq,
                reason=(
                    f"entry at position {position} has seq {entry.seq}, expected "
                    f"{expected_seq}: an entry is missing or reordered"
                ),
            )
        if entry.prev_hash != prev_hash:
            reason = (
                f"entry {entry.seq}: prev_hash does not match the hash of entry {entry.seq - 1}"
                if entry.seq > 1
                else "entry 1: prev_hash is not the 64-zero genesis value"
            )
            return VerificationResult(ok=False, first_bad_seq=entry.seq, reason=reason)
        if entry.entry_hash != _entry_hash(entry):
            return VerificationResult(
                ok=False,
                first_bad_seq=entry.seq,
                reason=(
                    f"entry {entry.seq}: entry_hash does not match its recomputed "
                    "hash — the entry was edited in place"
                ),
            )
        prev_hash = entry.entry_hash
    if expected_head is not None and prev_hash != expected_head:
        return VerificationResult(
            ok=False,
            first_bad_seq=None,
            reason=(
                "recomputed chain head does not match the running head: the store "
                "was truncated, rolled back, or forked and re-appended"
            ),
        )
    return VerificationResult(
        ok=True, first_bad_seq=None, reason=f"chain intact ({len(entries)} entries)"
    )


def run_daily_verifier(store: AuditStore, expected_head: str | None = None) -> VerificationResult:
    """The daily verification job's entire logic, kept pure: read the store,
    verify, report. Scheduling (services/workers), the ``sec.audit_chain_ok``
    metric, and fetching the externally anchored ``expected_head`` (invariant
    40) live outside this function so the unit lane can exercise every branch
    of the decision without any infrastructure."""
    return verify_entries(store.entries(), expected_head=expected_head)


def _parse_entry(record: dict[str, object]) -> AuditEntry | None:
    """Strict parse of one exported line back into an entry: exactly the
    closed field set, correct primitive types — anything else is a malformed
    bundle, never coerced into a best guess."""
    if set(record) != _ENTRY_FIELDS:
        return None
    seq = record["seq"]
    if not isinstance(seq, int) or isinstance(seq, bool):
        return None
    strings: dict[str, str] = {}
    for name in sorted(_ENTRY_FIELDS - {"seq"}):
        value = record[name]
        if not isinstance(value, str):
            return None
        strings[name] = value
    return AuditEntry(
        seq=seq,
        timestamp_utc=strings["timestamp_utc"],
        actor=strings["actor"],
        action=strings["action"],
        resource_ref=strings["resource_ref"],
        consent_scope_ref=strings["consent_scope_ref"],
        prev_hash=strings["prev_hash"],
        entry_hash=strings["entry_hash"],
    )


def verify_worm_export(bundle: bytes) -> VerificationResult:
    """Standalone check of an exported bundle — no store, no chain object,
    nothing but the bytes. Malformed input returns a failed result instead of
    raising, because the caller is a verifier job that must report every
    defect the same way, not crash on the interesting ones."""
    try:
        lines = bundle.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return VerificationResult(ok=False, first_bad_seq=None, reason="bundle is not UTF-8")
    if not lines:
        return VerificationResult(
            ok=False,
            first_bad_seq=None,
            reason="bundle is empty — a valid export always ends with a head record",
        )
    entries: list[AuditEntry] = []
    for number, line in enumerate(lines[:-1], start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return VerificationResult(
                ok=False, first_bad_seq=None, reason=f"line {number} is not valid JSON"
            )
        if not isinstance(record, dict):
            return VerificationResult(
                ok=False, first_bad_seq=None, reason=f"line {number} is not a JSON object"
            )
        entry = _parse_entry(record)
        if entry is None:
            return VerificationResult(
                ok=False,
                first_bad_seq=None,
                reason=f"line {number} does not carry exactly the closed audit field set",
            )
        entries.append(entry)
    try:
        head_record = json.loads(lines[-1])
    except json.JSONDecodeError:
        return VerificationResult(
            ok=False, first_bad_seq=None, reason="last line is not valid JSON"
        )
    if not isinstance(head_record, dict) or head_record.get("record_type") != _HEAD_RECORD_TYPE:
        return VerificationResult(
            ok=False,
            first_bad_seq=None,
            reason="bundle does not end with a head record — truncated or not a WORM export",
        )
    chain_head = head_record.get("chain_head")
    entry_count = head_record.get("entry_count")
    if not isinstance(chain_head, str) or not isinstance(entry_count, int):
        return VerificationResult(
            ok=False,
            first_bad_seq=None,
            reason="head record is malformed: chain_head must be a string, entry_count an integer",
        )
    # Chain walk first: a dropped line is then named by its exact seq, which
    # is more actionable than the count mismatch that also results from it.
    chain_result = verify_entries(entries, expected_head=chain_head)
    if not chain_result.ok:
        return chain_result
    if entry_count != len(entries):
        return VerificationResult(
            ok=False,
            first_bad_seq=None,
            reason=f"head record declares {entry_count} entries, bundle carries {len(entries)}",
        )
    return chain_result
