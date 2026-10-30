"""The daily verification run (INT-016; files/10 §2, §3, §7; invariants 4, 6, 13, 14).

**Why this job refuses to be green by omission.** A hash chain detects an
attacker who edits a row and stops there. It does not detect one who edits a
row and recomputes every hash forward, nor one who truncates the tail: both
leave a chain that is internally flawless, which is the whole attack. files/10
§2 records the correction in those words and prescribes the remedy — the head
is published hourly to a location outside the ``platform_admin`` blast radius
(a second organisation's object store, or a KEP/e-imza timestamp from a
Turkish TSP) and the daily verifier checks against **that** copy.

So the anchored head is not an optional refinement here; without it the run
has verified that a store agrees with itself, which is not a claim worth
publishing. A run with no anchor therefore reports
:attr:`VerifierOutcome.ANCHOR_MISSING`, sets ``sec_audit_chain_ok`` to 0 and
exits non-zero. The alternative — walk the chain, find it self-consistent,
report 1 — is precisely the verifier that always passes, and an operator who
reads that gauge would be worse informed than one with no gauge at all.

**What this job does not do.** It does not *publish* the anchor. No publisher
exists in this repo: the destination is a commercial and infrastructure
decision (a counterparty organisation, or a TSP contract) that no agent may
invent — see files/HUMAN_BLOCKERS.md **HB-I12**. The mechanism is built, the
gate is wired, it fails closed, and the content is empty. Invariant 40's
nightly flip-and-repair test against a live external copy is a separate,
strictly stronger control and is not claimed here.

**Why a broken chain is not copied to WORM.** The audit bucket carries a
COMPLIANCE object lock with a 3650-day retention (files/10 §3: object lock,
10-year retention for hospital tenants). Writing a chain we already know is
forged into that bucket manufactures a permanent, unremovable artefact of the
attacker's version of history — object lock means it cannot be withdrawn for
ten years. A failed verification pages; it does not archive.

**No PHI** (invariant 6). :class:`VerificationReport` carries counts, ``seq``
positions and hashes. It never carries an ``actor``, a ``resource_ref`` or a
``timestamp`` lifted out of a row: the verifier's own output is a log, and the
whole point of the closed entry field set is that nothing downstream widens it.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Protocol

from prometheus_client import Gauge

from intake_platform.audit import GENESIS_PREV_HASH, AuditStore, build_worm_bundle, verify_entries

__all__ = [
    "SEC_AUDIT_CHAIN_OK",
    "AnchorSource",
    "VerificationReport",
    "VerifierOutcome",
    "WormSink",
    "run_daily_verification",
]

#: Catalogued in observability/metrics_catalog.yaml (inv. 13) as
#: ``sec.audit_chain_ok``; files/08 §4 group N. 1 means *verified against the
#: external anchor* — never merely "the store agrees with itself", which is
#: what a chain walk alone establishes and is not the claim this gauge makes.
SEC_AUDIT_CHAIN_OK = Gauge(
    "sec_audit_chain_ok",
    "Daily audit hash-chain verification against the externally anchored head "
    "(1 = intact and anchored; 0 = broken, or no anchor to check against).",
)

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class VerifierOutcome(enum.StrEnum):
    """Three outcomes, kept distinct on purpose. ``ANCHOR_MISSING`` is not a
    flavour of failure and not a flavour of success: the chain may be perfect,
    but nothing independent says so, and collapsing that into either verdict
    is how a control quietly stops being one."""

    INTACT = "intact"
    CHAIN_BROKEN = "chain_broken"
    ANCHOR_MISSING = "anchor_missing"


class AnchorSource(Protocol):
    """The external witness, reduced to the single fact the verifier needs.

    Implementations fetch the head from wherever it was published — a second
    organisation's object store, a KEP/e-imza timestamp, or an operator who
    read it and passed it on the command line. ``None`` means *no anchor is
    available*, which the job treats as a refusal, never as "skip the check".
    """

    def anchored_head(self) -> str | None: ...


class WormSink(Protocol):
    """The object-locked copy target. Satisfied by
    :meth:`intake_platform.documents.DocumentStore.put_audit_bundle`, which
    owns the MinIO object-lock semantics (INT-034); this job only decides
    *whether* a bundle should be archived, never how the lock works."""

    def put_audit_bundle(self, bundle: bytes) -> str: ...


@dataclass(frozen=True)
class VerificationReport:
    """One run's verdict. Frozen so a caller cannot edit the finding it is
    about to alert on."""

    outcome: VerifierOutcome
    ok: bool
    first_bad_seq: int | None
    reason: str
    entry_count: int
    local_head: str
    anchor_head: str | None
    worm_key: str | None


def _refusal(reason: str, entry_count: int, local_head: str) -> VerificationReport:
    SEC_AUDIT_CHAIN_OK.set(0)
    return VerificationReport(
        outcome=VerifierOutcome.ANCHOR_MISSING,
        ok=False,
        first_bad_seq=None,
        reason=reason,
        entry_count=entry_count,
        local_head=local_head,
        anchor_head=None,
        worm_key=None,
    )


def run_daily_verification(
    store: AuditStore,
    *,
    anchor: AnchorSource,
    worm_sink: WormSink | None = None,
) -> VerificationReport:
    """Verify the chain against the anchored head; archive it if it holds.

    The store is read, never written: the verifier holds no chain writer and
    therefore no INSERT capability, which is what lets it run under the
    read-only role while ``svc-audit-writer`` keeps the only INSERT grant
    (files/10 §2).
    """
    entries = store.entries()
    local_head = entries[-1].entry_hash if entries else GENESIS_PREV_HASH

    anchored = anchor.anchored_head()
    if anchored is None:
        return _refusal(
            "no externally anchored head was available, so this run verified only that "
            "the store agrees with itself — which a truncation and a full re-forge both "
            "survive. Reporting intact here would be a pass by omission (files/10 §2, "
            "invariant 40).",
            len(entries),
            local_head,
        )
    if not _SHA256_HEX.fullmatch(anchored):
        return _refusal(
            "the anchored head is not 64 lowercase hex characters; a malformed anchor is "
            "refused rather than compared, because an anchor that never matches is "
            "indistinguishable from a chain that is always broken.",
            len(entries),
            local_head,
        )

    result = verify_entries(entries, expected_head=anchored)
    if not result.ok:
        SEC_AUDIT_CHAIN_OK.set(0)
        return VerificationReport(
            outcome=VerifierOutcome.CHAIN_BROKEN,
            ok=False,
            first_bad_seq=result.first_bad_seq,
            reason=result.reason,
            entry_count=len(entries),
            local_head=local_head,
            anchor_head=anchored,
            worm_key=None,
        )

    SEC_AUDIT_CHAIN_OK.set(1)
    worm_key: str | None = None
    if worm_sink is not None:
        worm_key = worm_sink.put_audit_bundle(build_worm_bundle(entries, anchored))
    return VerificationReport(
        outcome=VerifierOutcome.INTACT,
        ok=True,
        first_bad_seq=None,
        reason=result.reason,
        entry_count=len(entries),
        local_head=local_head,
        anchor_head=anchored,
        worm_key=worm_key,
    )
