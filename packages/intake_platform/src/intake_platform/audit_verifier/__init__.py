"""INT-016 — the daily audit-chain verifier job (files/10 §2, §3, §7).

``intake_platform.audit`` provides the chain and a pure ``verify_entries``.
This package is the *job* around it: read the store, compare the recomputed
head against an externally anchored one, publish the verdict as
``sec_audit_chain_ok``, and copy the WORM bundle into the object-locked
bucket. Run it with ``python -m intake_platform.audit_verifier`` (or
``make audit-verify``).

See :mod:`intake_platform.audit_verifier.job` for why a run without an anchor
is a refusal rather than a pass.
"""

from intake_platform.audit_verifier.job import (
    SEC_AUDIT_CHAIN_OK,
    AnchorSource,
    VerificationReport,
    VerifierOutcome,
    WormSink,
    run_daily_verification,
)

__all__ = [
    "SEC_AUDIT_CHAIN_OK",
    "AnchorSource",
    "VerificationReport",
    "VerifierOutcome",
    "WormSink",
    "run_daily_verification",
]
