"""The council, as the two challenger reviews reshaped it: a verifier (INT-430).

Owner request, 2 Oct 2026: questions that follow from earlier answers and the
patient's documents, on an agent council that runs on self-hosted or API
models. ADR-036 records what survived review:

- the deterministic :class:`~intake_voice_runtime.clinical_agent.fsm.IntakeEngine`
  stays the only authority on the next question, and the primary single-pass
  extraction still feeds triage — RED never waits on a model;
- the council **verifies** an answer already bound, on red-flag and numeric
  slots only (:mod:`.scope`), and may only *append* a scripted re-ask or
  confirm-back (:mod:`.adjudicate`), compare-and-swapped on the slot revision;
- adjudication is asymmetric: one arming reading re-asks, and no number of
  absent readings clears anything;
- the free follow-up ranker and the critic are cut; the document reader stays
  the existing ``parse_document`` Work;
- members are pinned per session through the INT-428 lane router
  (:mod:`.lanes`), hosted members exist only on a synthetic deployment, and
  multi-member mode is off until its studies are recorded (:mod:`.policy`).

Nothing in this package imports a network client; the transport is a port
(:mod:`.transport`) and CI replays recorded outputs.
"""

from __future__ import annotations

from intake_voice_runtime.clinical_agent.council.adjudicate import (
    ActionKind,
    Agreement,
    ContestedField,
    SlotView,
    Verdict,
    VerifierAction,
    adjudicate,
    views_of,
)
from intake_voice_runtime.clinical_agent.council.desk import (
    AddendumSink,
    AdmissionGate,
    ApplyVerdictHandler,
    ClinicianAddendum,
    DeskOutcome,
    TriageRerun,
    VerdictVault,
    VerifierDesk,
)
from intake_voice_runtime.clinical_agent.council.lanes import (
    DeploymentDataClass,
    MemberRefused,
    SessionPins,
    pin_member,
)
from intake_voice_runtime.clinical_agent.council.ledger import (
    FieldRecord,
    Provenance,
    VerifierLedger,
)
from intake_voice_runtime.clinical_agent.council.orchestrator import (
    MemberOutcome,
    VerificationRound,
    VerifierOrchestrator,
)
from intake_voice_runtime.clinical_agent.council.policy import VerifierMode, VerifierPolicy
from intake_voice_runtime.clinical_agent.council.readings import Reading
from intake_voice_runtime.clinical_agent.council.scope import VerifierScope, verifier_scope

__all__ = [
    "ActionKind",
    "AddendumSink",
    "AdmissionGate",
    "Agreement",
    "ApplyVerdictHandler",
    "ClinicianAddendum",
    "ContestedField",
    "DeploymentDataClass",
    "DeskOutcome",
    "FieldRecord",
    "MemberOutcome",
    "MemberRefused",
    "Provenance",
    "Reading",
    "SessionPins",
    "SlotView",
    "TriageRerun",
    "Verdict",
    "VerdictVault",
    "VerificationRound",
    "VerifierAction",
    "VerifierDesk",
    "VerifierLedger",
    "VerifierMode",
    "VerifierOrchestrator",
    "VerifierPolicy",
    "VerifierScope",
    "adjudicate",
    "pin_member",
    "verifier_scope",
    "views_of",
]
