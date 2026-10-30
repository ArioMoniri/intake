"""The closed vocabularies the admin console renders from other services (INT-565).

The Protocols, Clinical quality & safety and Security composites
(``services/api/src/intake_api/admin/{protocols,quality_safety,security}_console.py``)
each paint a closed set that another service owns:

- **PolicyGuard's violation classes** — the ``class`` label on
  ``policyguard_blocks_total``, owned by
  ``intake_voice_runtime.talker.policy_guard.ViolationClass`` (invariant 2).
- **Loop 2's proposal targets and evidence checks** — owned by
  ``intake_learning.proposals.PROPOSAL_TARGETS`` and
  ``intake_learning.evidence.REQUIRED_CHECKS`` (invariant 12).
- **The audit verifier's outcomes** — owned by
  ``intake_platform.audit_verifier.job.VerifierOutcome`` (invariant 4).

The API imports none of those modules. ``intake-api`` does not depend on
``intake-voice-runtime`` or ``intake-learning``, and adding either edge would
put the Talker or the learning pipeline inside the API's import closure. The
verifier module is in this package but registers ``sec_audit_chain_ok`` when
it is imported, and an importing API process would export that gauge at 0 —
which ``infra/observability/security-rules.yaml`` reads as a broken chain.

So the sets live here, as data, in the one package all four services already
depend on, and ``tests/admin/test_console_vocab.py`` holds each one equal to
its owner's: when an owner adds, removes or renames a member, the Python lane
fails until this module and the console move with it. The owners are not
edited to import this module, because PolicyGuard and the learning pipeline
are invariant-12 surfaces and this issue has no business in either.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "AUDIT_VERIFIER_OUTCOMES",
    "EVIDENCE_CHECK_NAMES",
    "POLICYGUARD_CLASSES",
    "PROPOSAL_TARGET_NAMES",
]

#: ``ViolationClass`` values, in declaration order.
POLICYGUARD_CLASSES: Final[tuple[str, ...]] = (
    "diagnosis",
    "treatment",
    "prognosis",
    "multi_question",
    "too_long",
    "register",
    "jargon",
)

#: The type names in ``PROPOSAL_TARGETS``, in tuple order: everything Loop 2
#: may ever ask for, and nothing else (files/09 §4).
PROPOSAL_TARGET_NAMES: Final[tuple[str, ...]] = (
    "AskCondition",
    "CandidateRedFlag",
    "ChoiceList",
    "FollowUpText",
    "PackMaturity",
    "PromptModule",
    "QuestionOrder",
    "QuestionWording",
    "SkipCondition",
    "SttVocabulary",
)

#: The ``EvidenceCheck.name`` of every entry in ``REQUIRED_CHECKS``, in order.
EVIDENCE_CHECK_NAMES: Final[tuple[str, ...]] = (
    "simulator_run",
    "triage_goldens",
    "latency_harness",
    "shadow_replay",
    "langfuse_experiment",
)

#: ``VerifierOutcome`` values, in declaration order.
AUDIT_VERIFIER_OUTCOMES: Final[tuple[str, ...]] = ("intact", "chain_broken", "anchor_missing")
