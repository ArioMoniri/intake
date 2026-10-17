"""INT-524, INT-544 — superseded pull request runs are cancelled; queued main runs collapse.

Acceptance lines under test (docs/backlog/issues.yaml):
  - INT-524: ci.yml and security.yml each declare a workflow-level concurrency
    group, and cancel in progress only on pull_request events, so a push to
    main is never cancelled in progress;
  - INT-544: queued push-to-main runs collapse to the newest pending run, a
    running main run is never cancelled, and a v* tag keeps a group of its own;
  - tests/ci pin the block in both workflows.

GitHub's semantics, from "Control the concurrency of workflows and jobs"
(https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency,
read 16 Oct 2026; quoted in docs/evidence/INT-524.md):
  - at most one run of a group is in progress;
  - with the default `queue` (single) at most one run of a group is pending,
    and a newly queued run cancels and replaces the pending one, whatever
    `cancel-in-progress` says;
  - `cancel-in-progress` also cancels the run in progress, and may be an
    expression;
  - group names are case-insensitive and shared by every workflow in the repo.

So the group is the workflow and the ref. A pull request's runs share its ref
(refs/pull/N/merge) and cancel each other. Every push to main shares
refs/heads/main: with cancel-in-progress false, the run in progress always
finishes, and a newer push replaces only the run waiting behind it. That is the
trade-off INT-544 takes and its evidence states: an intermediate main commit
whose run was replaced gets no run of its own. A v* tag's ref is its own, so a
tag on the commit main just pushed never replaces main's run, nor main its.
INT-524's per-sha block (every main commit keeps its own run) is now a near
miss below; restoring it is the one-line answer if the owner prefers it.

The model evaluates only the expression shapes the block uses: a property path,
`a || b` and `a == 'literal'`. Anything else raises, so a reworded block fails
here instead of passing unread.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO / ".github" / "workflows"
WORKFLOWS = ("ci.yml", "security.yml")

GROUP = "${{ github.workflow }}-${{ github.ref }}"
#: INT-524's block: a group per main commit, so no queued main run is replaced.
PER_SHA_GROUP = (
    "${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}-${{ github.ref }}"
)
CANCEL = "${{ github.event_name == 'pull_request' }}"

#: The only events the scenarios below cover. A new trigger (schedule,
#: workflow_dispatch, merge_group, workflow_run) needs its own scenario first.
MODELLED_EVENTS = {"pull_request", "push"}

SHA_A = "a" * 40
SHA_B = "b" * 40
MAIN = "refs/heads/main"


def _push(ref: str, sha: str) -> dict[str, object]:
    return {"event_name": "push", "ref": ref, "sha": sha, "event": {}}


def _pull_request(number: int, sha: str) -> dict[str, object]:
    return {
        "event_name": "pull_request",
        "ref": f"refs/pull/{number}/merge",
        "sha": sha,
        "event": {"pull_request": {"number": number}},
    }


#: One run per label, as GitHub's `github` context would describe it.
SCENARIOS: dict[str, dict[str, object]] = {
    "pull request 7, first push": _pull_request(7, SHA_A),
    "pull request 7, next push": _pull_request(7, SHA_B),
    "pull request 8": _pull_request(8, SHA_A),
    "push to main at A": _push(MAIN, SHA_A),
    "push to main at B": _push(MAIN, SHA_B),
    "v* tag on commit A": _push("refs/tags/v1.0.0", SHA_A),
    "second v* tag on commit A": _push("refs/tags/v1.0.0-rc.1", SHA_A),
}
MAIN_RUN = "push to main at A"
MAIN_RUNS = {MAIN_RUN, "push to main at B"}

_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}")
_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
_LITERAL = re.compile(r"'([^']*)'")


def _lookup(path: str, context: Mapping[str, object]) -> object:
    value: object = context
    for part in path.split("."):
        # a missing property is null, as in GitHub's expression engine
        value = value.get(part) if isinstance(value, Mapping) else None
    return value


def _operand(text: str, context: Mapping[str, object]) -> object:
    text = text.strip()
    literal = _LITERAL.fullmatch(text)
    if literal:
        return literal.group(1)
    if _PATH.fullmatch(text):
        return _lookup(text, context)
    raise ValueError(f"expression outside the model: {text!r}")


def _evaluate(expression: str, context: Mapping[str, object]) -> object:
    value: object = None
    for alternative in expression.split("||"):
        if "==" in alternative:
            left, _, right = alternative.partition("==")
            a, b = _operand(left, context), _operand(right, context)
            # GitHub compares strings ignoring case
            if isinstance(a, str) and isinstance(b, str):
                value = a.casefold() == b.casefold()
            else:
                value = a == b
        else:
            value = _operand(alternative, context)
        if value not in (None, False, 0, ""):
            return value
    return value


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _render(template: str, context: Mapping[str, object]) -> str:
    return _EXPRESSION.sub(lambda m: _text(_evaluate(m.group(1), context)), template)


def _truth(raw: object, context: Mapping[str, object]) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        whole = _EXPRESSION.fullmatch(raw.strip())
        if whole:
            return _evaluate(whole.group(1), context) not in (None, False, 0, "")
    raise ValueError(f"cancel-in-progress outside the model: {raw!r}")


def _triggers(document: Mapping[object, object]) -> set[str]:
    on = document.get("on", document.get(True))  # YAML 1.1 reads a bare `on` as True
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(event) for event in on}
    if isinstance(on, Mapping):
        return {str(event) for event in on}
    return set()


def _load(name: str) -> dict[object, object]:
    document = yaml.safe_load((WORKFLOW_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{name} does not parse to a mapping"
    return document


def _findings(workflows: Mapping[str, Mapping[object, object]]) -> list[str]:
    """Each way the blocks could cancel a run they must keep, or keep one they must cancel."""
    out: list[str] = []
    runs: dict[tuple[str, str], tuple[str, bool]] = {}
    for file, document in workflows.items():
        unmodelled = sorted(_triggers(document) - MODELLED_EVENTS)
        if unmodelled:
            out.append(f"{file}: fires on {unmodelled}, which no scenario here covers")
        block = document.get("concurrency")
        if not isinstance(block, Mapping) or set(block) != {"group", "cancel-in-progress"}:
            out.append(
                f"{file}: workflow-level concurrency is not exactly {{group, cancel-in-progress}}"
            )
            continue
        for label, run in SCENARIOS.items():
            context = {"github": {"workflow": document.get("name", file), **run}}
            group = _render(str(block["group"]), context).casefold()  # names ignore case
            runs[(file, label)] = (group, _truth(block["cancel-in-progress"], context))

    for file in workflows:
        if (file, MAIN_RUN) not in runs:
            continue
        first, first_cancels = runs[(file, "pull request 7, first push")]
        nxt, next_cancels = runs[(file, "pull request 7, next push")]
        if first != nxt:
            out.append(
                f"{file}: two pushes to one pull request land in different groups, "
                "so the older run is never cancelled"
            )
        if not (first_cancels and next_cancels):
            out.append(f"{file}: a pull_request run does not cancel the run in progress")
        if runs[(file, "pull request 8")][0] == first:
            out.append(f"{file}: two pull requests share a group, so one cancels the other")
        main, main_cancels = runs[(file, MAIN_RUN)]
        if main_cancels:
            out.append(f"{file}: a push to main cancels the run in progress")
        if runs[(file, "push to main at B")][0] != main:
            out.append(
                f"{file}: two pushes to main land in different groups, "
                "so a queued main run is never replaced by a newer one"
            )
        for label in SCENARIOS:
            if label not in MAIN_RUNS and runs[(file, label)][0] == main:
                out.append(
                    f"{file}: a push to main shares its group with {label!r}, "
                    "which replaces it while it waits"
                )
        tag, _ = runs[(file, "v* tag on commit A")]
        if runs[(file, "second v* tag on commit A")][0] == tag:
            out.append(
                f"{file}: two v* tags on one commit share a group, "
                "so one replaces the other while it waits"
            )

    files = sorted(file for file in workflows if (file, MAIN_RUN) in runs)
    for label in SCENARIOS:
        seen: dict[str, str] = {}
        for file in files:
            group = runs[(file, label)][0]
            if group in seen:
                out.append(
                    f"{seen[group]} and {file} share a group for {label!r}, "
                    "so one workflow cancels the other"
                )
            seen[group] = file
    return out


# --- the committed workflows ------------------------------------------------------------


@pytest.mark.parametrize("name", WORKFLOWS)
def test_the_workflow_declares_the_pinned_concurrency_block(name: str) -> None:
    block = _load(name).get("concurrency")
    assert block == {"group": GROUP, "cancel-in-progress": CANCEL}, (
        f"{name}: the workflow-level concurrency block must be exactly group {GROUP!r} "
        f"and cancel-in-progress {CANCEL!r} (INT-524, INT-544); found {block!r}"
    )


@pytest.mark.parametrize("name", WORKFLOWS)
def test_no_job_sets_its_own_concurrency(name: str) -> None:
    """A job-level group sits outside the workflow's and could cancel a job of a push to main."""
    jobs = _load(name)["jobs"]
    assert isinstance(jobs, dict) and jobs
    offenders = sorted(
        job for job, body in jobs.items() if isinstance(body, dict) and "concurrency" in body
    )
    assert not offenders, f"{name}: job-level concurrency on {offenders}"


def test_the_committed_workflows_cancel_only_superseded_pull_request_runs() -> None:
    findings = _findings({name: _load(name) for name in WORKFLOWS})
    assert findings == [], "\n".join(findings)


def test_the_workflow_names_differ_so_their_groups_cannot_meet() -> None:
    names = [str(_load(name).get("name", name)).casefold() for name in WORKFLOWS]
    assert len(set(names)) == len(names), f"workflow names collide (groups ignore case): {names}"


# --- near misses: each breaks one property, and the model names it ------------------------


def _with_block(group: str, cancel: object) -> dict[str, dict[object, object]]:
    out: dict[str, dict[object, object]] = {}
    for name in WORKFLOWS:
        document = copy.deepcopy(_load(name))
        document["concurrency"] = {"group": group, "cancel-in-progress": cancel}
        out[name] = document
    return out


NEAR_MISSES = [
    pytest.param(
        PER_SHA_GROUP,
        CANCEL,
        "ci.yml: two pushes to main land in different groups",
        id="int-524-every-main-commit-keeps-its-own-run",
    ),
    pytest.param(
        "${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}",
        CANCEL,
        "security.yml: a push to main shares its group with 'v* tag on commit A'",
        id="no-ref-a-tag-replaces-a-waiting-main-run",
    ),
    pytest.param(
        "${{ github.workflow }}-${{ github.event_name }}",
        CANCEL,
        "security.yml: a push to main shares its group with 'v* tag on commit A'",
        id="event-name-groups-every-push-together",
    ),
    pytest.param(
        GROUP,
        True,
        "ci.yml: a push to main cancels the run in progress",
        id="cancel-always",
    ),
    pytest.param(
        GROUP,
        "${{ github.event_name == 'push' }}",
        "ci.yml: a pull_request run does not cancel the run in progress",
        id="cancel-inverted",
    ),
    pytest.param(
        "${{ github.workflow }}-${{ github.sha }}-${{ github.ref }}",
        CANCEL,
        "ci.yml: two pushes to one pull request land in different groups",
        id="sha-for-pull-requests-too",
    ),
    pytest.param(
        "${{ github.workflow }}",
        CANCEL,
        "ci.yml: two pull requests share a group",
        id="one-group-per-workflow",
    ),
    pytest.param(
        "${{ github.ref }}",
        CANCEL,
        "ci.yml and security.yml share a group for 'pull request 7, first push'",
        id="no-workflow-prefix",
    ),
]


@pytest.mark.parametrize(("group", "cancel", "expected"), NEAR_MISSES)
def test_near_miss_is_caught(group: str, cancel: object, expected: str) -> None:
    findings = _findings(_with_block(group, cancel))
    assert any(finding.startswith(expected) for finding in findings), findings


def test_near_miss_a_missing_block_is_caught() -> None:
    documents = {name: copy.deepcopy(_load(name)) for name in WORKFLOWS}
    for document in documents.values():
        document.pop("concurrency", None)
    findings = _findings(documents)
    for name in WORKFLOWS:
        assert (
            f"{name}: workflow-level concurrency is not exactly {{group, cancel-in-progress}}"
            in findings
        )


def test_near_miss_a_queue_key_is_caught() -> None:
    documents = _with_block(GROUP, CANCEL)
    documents["ci.yml"]["concurrency"] = {
        "group": GROUP,
        "cancel-in-progress": CANCEL,
        "queue": "max",
    }
    assert (
        "ci.yml: workflow-level concurrency is not exactly {group, cancel-in-progress}"
        in _findings(documents)
    )


def test_near_miss_an_unmodelled_trigger_is_caught() -> None:
    documents = _with_block(GROUP, CANCEL)
    documents["ci.yml"]["on"] = {
        "pull_request": None,
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }
    documents["ci.yml"].pop(True, None)
    assert "ci.yml: fires on ['workflow_dispatch'], which no scenario here covers" in _findings(
        documents
    )


def test_the_model_refuses_an_expression_it_does_not_implement() -> None:
    with pytest.raises(ValueError, match="outside the model"):
        _render("${{ contains(github.ref, 'main') }}", {"github": {"ref": MAIN}})
    with pytest.raises(ValueError, match="outside the model"):
        _truth("always", {"github": {}})


def test_the_model_follows_github_for_the_fallback_and_the_comparison() -> None:
    pr = {"github": _pull_request(7, SHA_A)}
    push = {"github": _push(MAIN, SHA_A)}
    assert _render("${{ github.event.pull_request.number || github.sha }}", pr) == "7"
    assert _render("${{ github.event.pull_request.number || github.sha }}", push) == SHA_A
    assert _truth(CANCEL, pr) is True
    assert _truth(CANCEL, push) is False
    assert _truth("${{ github.event_name == 'PULL_REQUEST' }}", pr) is True  # strings ignore case
