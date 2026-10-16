"""The verifier's engineering policy: who verifies, how often, bound to what.

Nothing in this module is a clinical decision. The clinical decisions the
verifier touches — the confirmation ceiling, the hedge table, what a
narrative PRESENT may do — live in ``packages/protocols/council/
verification.yaml`` as ``draft_needs_source`` and are read by
:mod:`intake_voice_runtime.clinical_agent.council.clinical`.

**Two modes, and the second is gated on evidence that does not exist yet.**
The AI/ML review: multi-member mode turns on *"only after an error-
independence study and a calibration study (docs/evidence, with a date and a
named corpus) pass. Until then, use same-model self-consistency"*. So
:attr:`VerifierMode.MULTI_MEMBER` is unrepresentable without two
:class:`StudyEvidence` values, and self-consistency is exactly one member
sampled ``samples`` times.

**Every member is bound by hash.** :class:`LaneBinding` is the tuple the
review names — provider, ``model@revision`` (with the weights digest), the
prompt version, the decoding and the slot types — and the policy carries its
sha256 per member. A session whose resolved member hashes to anything else is
refused at pin time, so a model swap cannot inherit a policy that was
written against another model.
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Mapping
from datetime import date
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field, model_validator

__all__ = [
    "MEMBER_ID_PATTERN",
    "ROLE_PREFIX",
    "LaneBinding",
    "MemberSpec",
    "StudyEvidence",
    "VerifierMode",
    "VerifierPolicy",
]

#: INT-428's role-segment grammar, so a member id is always a valid role id.
MEMBER_ID_PATTERN: Final = r"^[a-z0-9][a-z0-9_-]{0,31}$"
#: Every member resolves as ``llm.council.<member_id>`` through the INT-428
#: lane router; a member with no route of its own inherits the ``llm`` lane.
ROLE_PREFIX: Final = "llm.council."
_SHA256_PATTERN: Final = r"^[0-9a-f]{64}$"
_DECIMAL_PATTERN: Final = r"^[0-9]+(\.[0-9]+)?$"


class VerifierMode(enum.StrEnum):
    SELF_CONSISTENCY = "self_consistency"
    MULTI_MEMBER = "multi_member"


class MemberSpec(FrozenModel):
    """One configured member. Its model is whatever the lane router pins."""

    member_id: str = Field(pattern=MEMBER_ID_PATTERN)

    @property
    def role_id(self) -> str:
        return f"{ROLE_PREFIX}{self.member_id}"


class StudyEvidence(FrozenModel):
    """A dated measurement on a named corpus, committed under docs/evidence.

    Described as a measurement, never as a property of the product (CLAUDE.md
    invariant 20): this type records *that* a study exists, not a figure.
    """

    path: str = Field(pattern=r"^docs/evidence/[A-Za-z0-9._/-]+\.md$")
    measured_on: date
    corpus: str = Field(min_length=1, max_length=128)


class LaneBinding(FrozenModel):
    """Everything that could change what a member reads, hashed as one value."""

    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    weights_sha256: str = Field(pattern=_SHA256_PATTERN)
    prompt_version: str = Field(min_length=1)
    temperature: str = Field(pattern=_DECIMAL_PATTERN)
    slot_types: tuple[str, ...] = Field(min_length=1)

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()


class VerifierPolicy(FrozenModel):
    """One deployment's verifier configuration, as the admin console writes it."""

    mode: VerifierMode
    members: tuple[MemberSpec, ...] = Field(min_length=1, max_length=8)
    samples: int = Field(ge=1, le=8, description="Self-consistency draws per verification.")
    temperature: str = Field(pattern=_DECIMAL_PATTERN)
    deadline_ms: int = Field(ge=1, description="Whole-round deadline; stragglers abstain.")
    bindings: Mapping[str, str] = Field(
        description="member_id -> LaneBinding.digest the policy was calibrated against."
    )
    independence_study: StudyEvidence | None = None
    calibration_study: StudyEvidence | None = None

    @model_validator(mode="after")
    def _mode_is_earned(self) -> VerifierPolicy:
        ids = [member.member_id for member in self.members]
        if len(set(ids)) != len(ids):
            raise ValueError("member ids must be unique")
        if self.mode is VerifierMode.SELF_CONSISTENCY and len(self.members) != 1:
            raise ValueError("self-consistency samples exactly one member")
        if self.mode is VerifierMode.MULTI_MEMBER:
            if len(self.members) < 2:
                raise ValueError("multi-member mode needs at least two members")
            if self.independence_study is None or self.calibration_study is None:
                raise ValueError(
                    "multi-member mode is off until an error-independence study and a "
                    "calibration study are recorded under docs/evidence (ADR-036)"
                )
            if self.samples != 1:
                raise ValueError("multi-member mode draws once per member")
        missing = sorted(set(ids) - set(self.bindings))
        if missing:
            raise ValueError(f"members without a calibrated binding: {missing}")
        for member_id, digest in self.bindings.items():
            if member_id not in ids:
                raise ValueError(f"binding for a member that is not configured: {member_id!r}")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"binding for {member_id!r} is not a sha256 digest")
        return self

    @property
    def draws(self) -> tuple[tuple[str, int], ...]:
        """``(member_id, sample)`` for every call one verification makes."""
        if self.mode is VerifierMode.SELF_CONSISTENCY:
            only = self.members[0].member_id
            return tuple((only, sample) for sample in range(self.samples))
        return tuple((member.member_id, 0) for member in self.members)
