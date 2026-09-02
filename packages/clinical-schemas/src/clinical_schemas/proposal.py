"""Proposal (INT-031).

files/09 §4 (Loop 2) and files/07 §Loop-2 sketch: ``Proposal{type, diff,
evidence:{stats, exemplars_deid, simulator_run, goldens, latency,
shadow_replay, langfuse_experiment}}``. Learning is proposal-only
(invariant 12): a proposal is a PR against ``packages/protocols`` or
``packages/llm-evals/prompts`` plus an evidence bundle — the pipeline is
technically unable to modify red-flag levels, instruments, consent texts,
Talker tools or PolicyGuard, and the CI ``proposal_scope`` test is the hard
stop. The evidence thresholds (≥ 10 patients, ≥ 2 clinics, stable ≥ 2
weeks) are type-level here so an under-evidenced bundle cannot exist.
"""

from __future__ import annotations

import enum
import posixpath

from pydantic import Field, field_validator

from clinical_schemas.common import FrozenModel, Ref

#: files/09 §4: "proposal = PR in packages/protocols or packages/llm-evals/prompts".
ALLOWED_TARGET_PREFIXES = ("packages/protocols/", "packages/llm-evals/prompts/")


class ProposalType(enum.StrEnum):
    """The allowed proposal types, one per clause of files/09 §4."""

    REWORD_QUESTION = "reword_question"
    REORDER_QUESTIONS = "reorder_questions"
    ADD_FOLLOW_UP_TR = "add_follow_up_tr"
    ADD_CHOICES_TR = "add_choices_tr"
    ADD_ASK_IF = "add_ask_if"
    ADD_SKIP_IF = "add_skip_if"
    ADD_STT_VOCABULARY = "add_stt_vocabulary"
    PROMOTE_PACK_MATURITY = "promote_pack_maturity"
    ADD_CANDIDATE_RED_FLAG = "add_candidate_red_flag"
    PROMPT_IMPROVEMENT_EXTRACTION = "prompt_improvement_extraction"
    PROMPT_IMPROVEMENT_NOTE = "prompt_improvement_note"


class EvidenceStats(FrozenModel):
    """Aggregate evidence behind a proposal. The Architect's thresholds
    (files/09 §4: ≥ 10 patients, ≥ 2 clinics, stable over 2 weeks) are the
    field constraints — an under-evidenced stats block is unrepresentable."""

    patients: int = Field(
        ge=10,
        description="Distinct patients behind the pattern (files/09 §4: k >= 10; the "
        "k-anonymity helper refuses smaller patterns, files/09 §7).",
    )
    clinics: int = Field(
        ge=2, description="Distinct clinics showing the pattern (files/09 §4: >= 2 clinics)."
    )
    weeks_stable: int = Field(
        ge=2,
        description="Weeks the effect size and direction stayed stable "
        "(files/09 §4: stable over 2 weeks).",
    )


class EvidenceBundle(FrozenModel):
    """The attached evidence bundle, keys verbatim from the files/07 Loop-2
    sketch; every artefact is referenced by id — nothing identifiable rides
    in a proposal (files/09 §4 forbidden list)."""

    stats: EvidenceStats = Field(description="Aggregate stats (files/07 evidence.stats).")
    exemplars_deid: tuple[Ref, ...] = Field(
        min_length=1,
        description="Ids of de-identified exemplar traces (files/07 "
        "evidence.exemplars_deid; de-identification per invariant 6).",
    )
    simulator_run: Ref = Field(
        description="Simulator run id (files/07 evidence.simulator_run; files/04 §6)."
    )
    goldens: Ref = Field(
        description="Triage golden suite run id (files/07 evidence.goldens; files/04 §7)."
    )
    latency: Ref = Field(
        description="Latency harness run id (files/07 evidence.latency; make runtime-sim)."
    )
    shadow_replay: Ref = Field(
        description="Shadow replay id over de-identified transcripts (files/07 "
        "evidence.shadow_replay; files/09 §4 path to production)."
    )
    langfuse_experiment: Ref = Field(
        description="Langfuse experiment link id (files/07 evidence.langfuse_experiment; "
        "files/09 §4 tooling)."
    )


class Proposal(FrozenModel):
    """One Loop-2 proposal: a diff plus its evidence, never a direct change
    (files/09 §4; invariant 12)."""

    type: ProposalType = Field(
        description="Which allowed change class this is (files/09 §4 proposal types)."
    )
    target_path: str = Field(
        description="Repo path the diff applies to — only packages/protocols/** or "
        "packages/llm-evals/prompts/** (files/09 §4); anything else fails validation "
        "and the CI proposal_scope test."
    )
    diff: str = Field(
        min_length=1,
        description="The proposed change as a unified diff — proposals are PRs, not "
        "writes (files/09 §4 path to production).",
    )
    evidence: EvidenceBundle = Field(
        description="The evidence bundle; a proposal without one fails CI "
        "(files/09 §6 proposal_scope)."
    )

    @field_validator("target_path")
    @classmethod
    def _target_inside_learnable_paths(cls, value: str) -> str:
        normalised = posixpath.normpath(value)
        if normalised != value or value.startswith("/") or ".." in value.split("/"):
            raise ValueError("target_path must be a normalised repo-relative path")
        if not value.startswith(ALLOWED_TARGET_PREFIXES):
            raise ValueError(
                "proposals may target only packages/protocols/** or "
                "packages/llm-evals/prompts/** (files/09 §4)"
            )
        return value
