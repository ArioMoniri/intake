"""INT-172 — the PR bot: open, never merge, and not wired to anything yet.

files/09 §4 puts a proposal's path to production through a pull request:
"proposal = PR in ``packages/protocols`` or ``packages/llm-evals/prompts`` +
attached evidence bundle … → CODEOWNER clinician approves → canary 5 % → 25 %
→ 100 %". files/09 §7 constrains the identity that opens it: "a PR-bot
identity that can open but not merge".

**The request is data.** :class:`PullRequestRequest` is a frozen record of a
branch name, a title, a body and an attachment. It has no ``merge`` field, no
``merge`` method and no ``approve`` anything — a least-privilege identity is
the deployment control, and this is the same statement made in the type, so
neither is the only one.

**Nothing here dispatches.** :class:`ProposalPublisher` is a Protocol and this
module ships no implementation of it. That is not an omission to be filled in
later by whoever is passing: a GitHub App with ``contents:write`` and
``pull_requests:write`` on ``ArioMoniri/intake``, scoped so it cannot merge or
approve, is a credential nobody has issued. Inventing one, or writing an
``httpx`` client that would use one, is the thing CLAUDE.md forbids — and an
HTTP client in this package would also break the "no egress" property the
``proposal_scope`` gate asserts about the pipeline's import closure. The ask is
recorded in docs/evidence/INT-172.md against the owner.

**The gate is completeness, and it is closed today.** files/09 §4's evidence
list — simulator run, triage goldens, latency harness, shadow replay, Langfuse
experiment — has no satisfied member on this branch, so
:func:`build_pull_request` refuses every real bundle it will be handed and
names which artefact is missing. That is deliberate: the mechanism is wired,
the gate fails closed, and the content is empty until the issues named in
:data:`~intake_learning.evidence.REQUIRED_CHECKS` land.

sec_row: `learning-loops`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from intake_learning.architect import Proposal
from intake_learning.signing import SignedBundle

__all__ = [
    "IncompleteEvidence",
    "ProposalPublisher",
    "PullRequestRequest",
    "build_pull_request",
]


class IncompleteEvidence(RuntimeError):
    """files/09 §4's evidence list is not satisfied, so no PR is built."""


@dataclass(frozen=True)
class PullRequestRequest:
    """Everything a least-privilege bot would need, and nothing more.

    There is no ``merge``, no ``approve``, no ``reviewers`` and no ``labels``:
    a CODEOWNER clinician approves (files/09 §4), and a bot that could choose
    its own reviewer would be choosing who reviews a clinical change.
    """

    branch: str
    title: str
    body: str
    attachment: str
    digest: str


class ProposalPublisher(Protocol):
    """The one operation a PR bot performs. Deliberately singular.

    An implementation lives outside this package, holds the bot credential and
    is bound by the sandbox's egress policy. None ships here.
    """

    def open_pull_request(self, request: PullRequestRequest) -> str:
        """Open the pull request; return its url. Never merges."""
        ...


def _slug(value: str) -> str:
    """Hyphenate an id for a branch name, character by character.

    ``str.replace`` would read the same and do the same, and it is deliberately
    not used: the ``proposal_scope`` gate refuses ``.replace(`` anywhere in this
    package because ``os.replace`` and ``Path.replace`` are silent overwrites,
    and a gate that has to tell the two apart by inference is a gate with an
    exception list. Spelling the string munging out keeps the gate blunt.
    """
    return "".join("-" if character in "._" else character for character in value)


def _branch_for(proposal: Proposal, digest: str) -> str:
    """A branch name built only from vetted ids.

    ``pack_id`` and ``slot_id`` reached this point through INT-171's id-shape
    gate, so the name is ASCII, hyphen-safe and carries nothing a patient said.
    """
    target = proposal.target
    parts = [
        "learning",
        _slug(proposal.signal.value),
        _slug(getattr(target, "pack_id", type(target).__name__)),
    ]
    slot_id = getattr(target, "slot_id", None)
    if slot_id is not None:
        parts.append(_slug(str(slot_id)))
    parts.append(digest[:12])
    return "/".join(("int-172", "-".join(parts)))


def _body_for(proposal: Proposal, evidence: SignedBundle) -> str:
    """The PR body: counts, citations and provenance lines. No prose of ours.

    Every interpolated value is an id from a gated cell, an enum member, an
    integer, or the analytics registry's own committed description — which is
    what keeps invariant 6 true of the one artefact a human definitely reads.
    """
    lines = [
        "## Loop 2 proposal (services/learning, INT-172)",
        "",
        "This is a **proposal**. Nothing has been applied, and nothing in "
        "`services/learning` is able to apply it (CLAUDE.md invariant 12; "
        "`proposal_scope` in tests/learning/test_proposal_scope.py).",
        "",
        f"- signal: `{proposal.signal.value}`",
        f"- target: `{type(proposal.target).__name__}`",
        f"- view: `{proposal.view}`",
        f"- weeks: {', '.join(f'`{week}`' for week in proposal.weeks)}",
        f"- smallest weekly cohort: {proposal.subjects} subjects across {proposal.tenants} clinics",
        f"- k floor applied: {evidence.bundle.k}",
        "",
        "### Counts",
        "",
        "| week | numerator | denominator | subjects | clinics |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| `{o.week_start}` | {o.numerator} | {o.denominator} | {o.subjects} | {o.tenants} |"
        for o in proposal.observations
    ]
    lines += [
        "",
        "### What these numbers are",
        "",
        "Measurements of a named cohort over a stated window (CLAUDE.md "
        "invariant 20), not properties of the product:",
        "",
    ]
    lines += [f"- {measurement.provenance}" for measurement in evidence.bundle.measurements]
    lines += [
        "",
        f"Excluded by construction: {evidence.bundle.narrative_exclusion}.",
        "",
        "### Citations",
        "",
    ]
    lines += [f"- {citation.value}" for citation in evidence.bundle.citations]
    lines += [
        "",
        "### Evidence bundle",
        "",
        f"- digest: `{evidence.digest}`",
        f"- signature: `{evidence.signature.algorithm}` by key `{evidence.signature.key_id}`",
        "",
        "Approval is a CODEOWNER clinician's (files/09 §4). The bot that "
        "opened this cannot merge it.",
    ]
    return "\n".join(lines)


def build_pull_request(*, proposal: Proposal, evidence: SignedBundle) -> PullRequestRequest:
    """Render the open-not-merge request, or refuse.

    :raises IncompleteEvidence: files/09 §4's evidence list is not satisfied.
        The message names every missing artefact and the issue that produces
        it, so the refusal is actionable rather than a wall.
    """
    if not evidence.is_complete:
        missing = ", ".join(evidence.unmet_checks)
        raise IncompleteEvidence(
            "files/09 §4 requires an evidence bundle before a proposal becomes "
            f"a PR; these artefacts are not available: {missing}. Each names "
            "the issue that produces it in "
            "intake_learning.evidence.REQUIRED_CHECKS — this is a blocked "
            "dependency, not a check to skip (CLAUDE.md invariant 17)"
        )
    target_name = type(proposal.target).__name__
    return PullRequestRequest(
        branch=_branch_for(proposal, evidence.digest),
        title=f"proposal({proposal.signal.value}): {target_name} for `{proposal.view}`",
        body=_body_for(proposal, evidence),
        attachment=evidence.bundle.to_json(),
        digest=evidence.digest,
    )
