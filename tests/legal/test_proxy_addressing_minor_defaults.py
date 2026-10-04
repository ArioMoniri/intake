"""INT-483 / ADR-040 — the proxy addressing mechanism relaxes no INT-223 default.

ADR-040 decides how a question is WORDED for a proxy. It decides nothing about
WHO may be a proxy: that is INT-223's age axis and INT-133's companion rules,
and LD-02 (INT-471) keeps every HB-L20 question that gates a guardian path in
draft. These tests pin that the new mechanism cannot reach those decisions:

* an under-18 subject is refused whoever answers and whatever was
  acknowledged — before any attribution, so before any addressing;
* the guardian-path policy rows stay awaiting-human;
* the profile flow takes no addressing input, and the platform package does
  not import the protocol addressing module, so no proxy document can stand in
  for proof of representation.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from intake_platform.consent.minors import (
    AgeBand,
    AgeContext,
    PolicyStatus,
    RequiredActor,
    policy_entry,
)
from intake_platform.profiles import (
    ProfileFlowStep,
    ProxyAcknowledgement,
    Speaker,
    SubjectRole,
    resolve_profile_flow,
)

REPO = Path(__file__).resolve().parents[2]
PLATFORM_SRC = REPO / "packages" / "intake_platform" / "src" / "intake_platform"
ON = date(2026, 10, 4)
ACKED = ProxyAcknowledgement(acknowledged=True, at=datetime(2026, 10, 4, 9, 0, tzinfo=UTC))

CHILD = AgeContext.verified(date(2020, 1, 1))
ADOLESCENT = AgeContext.verified(date(2010, 6, 1))
#: LD-02: majority is the eighteenth birthday, so the day before it is a minor.
DAY_BEFORE_MAJORITY = AgeContext.verified(date(2008, 10, 5))


@pytest.mark.parametrize(
    ("context", "band"),
    [
        (CHILD, AgeBand.CHILD),
        (ADOLESCENT, AgeBand.ADOLESCENT),
        (DAY_BEFORE_MAJORITY, AgeBand.ADOLESCENT),
    ],
)
@pytest.mark.parametrize(
    ("role", "speaker"),
    [
        (SubjectRole.COMPANION, Speaker.COMPANION),
        (SubjectRole.COMPANION, Speaker.PATIENT),
        (SubjectRole.SELF, Speaker.PATIENT),
    ],
)
def test_an_under_18_subject_is_refused_whoever_answers(
    context: AgeContext, band: AgeBand, role: SubjectRole, speaker: Speaker
) -> None:
    acknowledgement = ACKED if role is SubjectRole.COMPANION else None
    outcome = resolve_profile_flow(
        context,
        scope="core",
        on=ON,
        role=role,
        speaker=speaker,
        acknowledgement=acknowledgement,
    )
    assert outcome.band is band
    assert outcome.step is ProfileFlowStep.BLOCKED_AWAITING_HUMAN
    assert outcome.permitted is False
    assert outcome.refusal_code == "guardian_consent_required"
    assert outcome.required_actor is RequiredActor.GUARDIAN
    assert outcome.attribution is None
    assert {"guardian_link_basis", "guardian_relationship_proof"} <= set(outcome.blocked_on)


def test_the_near_miss_an_adult_on_the_day_of_majority_is_not_refused_on_age() -> None:
    outcome = resolve_profile_flow(AgeContext.verified(date(2008, 10, 4)), scope="core", on=ON)
    assert outcome.band is AgeBand.ADULT
    assert outcome.step is ProfileFlowStep.PROCEED


@pytest.mark.parametrize(
    "row_id",
    ["guardian_link_basis", "guardian_relationship_proof", "adolescent_self_consent"],
)
def test_the_guardian_path_rows_stay_awaiting_human(row_id: str) -> None:
    """LD-02 keeps these three in draft; nothing in ADR-040 answers them."""
    assert policy_entry(row_id).status is PolicyStatus.AWAITING_HUMAN


def test_the_profile_flow_takes_no_addressing_input() -> None:
    """A proxy-resolved document is a wording, never evidence of who may answer."""
    names = set(inspect.signature(resolve_profile_flow).parameters)
    assert not {name for name in names if "address" in name or "proxy_text" in name}


def test_the_platform_does_not_import_the_protocol_addressing_module() -> None:
    importers: list[str] = []
    for path in sorted(PLATFORM_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "protocols.addressing"
            ):
                importers.append(str(path.relative_to(REPO)))
            if isinstance(node, ast.Import) and any(
                alias.name.startswith("protocols.addressing") for alias in node.names
            ):
                importers.append(str(path.relative_to(REPO)))
    assert importers == []
