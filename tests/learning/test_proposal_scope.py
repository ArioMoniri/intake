"""INT-172 — `proposal_scope`: the forbidden edits are unreachable, not unattempted.

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-172):
  "proposal_scope CI test blocks forbidden paths (red-flag levels, instruments,
   consent texts, Talker tools, PolicyGuard, residency routing); sandboxed job
   read-only creds no egress; signed proposals"

CLAUDE.md invariant 12 and files/09 §4 ("Forbidden for the agent") name six
things ``services/learning`` may never change. A runtime guard that inspected a
proposal before applying it would be the wrong shape of control: it presumes
the service is in a position to apply something. This file asserts the stronger
property — **the package cannot reach the code that would apply it** — by
reading source, not by importing and hoping.

Six gates, because each one alone has a hole:

1. :func:`test_the_import_closure_never_reaches_a_forbidden_module` walks the
   *transitive* first-party import graph. Transitive matters: a direct-import
   check is defeated by one hop through a helper. Ancestor ``__init__`` modules
   are included, because importing ``a.b.c`` executes ``a/__init__.py`` too.
2. :func:`test_the_pipeline_closure_reaches_no_network_or_process_module` is
   what makes files/09 §7's "no egress" a property of the source rather than of
   a container policy: no ``httpx``, no ``urllib``, no ``socket``, no
   ``subprocess`` anywhere the pipeline can reach.
3. :func:`test_the_pipeline_imports_nothing_outside_the_declared_allow_list` is
   an allow-list, not a deny-list. A deny-list answers "did we think of that
   one"; an allow-list answers "what can this package touch at all".
4. :func:`test_the_package_contains_no_write_capable_call` scans for filesystem
   and process mutation. The package returns values and never owns a sink,
   which is why "may not write to a protocol pack" needs no path allow-list:
   there is no writer to point at a path.
5. :func:`test_the_pipeline_composes_no_sql_of_its_own` is why INT-171's
   read-only credential is sufficient rather than merely present — the package
   has no expression through which a write could be attempted.
6. :func:`test_the_read_path_is_int_171s_gated_one_and_never_the_ungated_projection`
   pins that the read goes through ``materialise_view`` and never
   ``read_cells``, which projects rows without applying the k floor.

And three type-level gates, mirroring the posture INT-091 took for RED
preemption in ``services/voice-runtime/.../talker/preemption.py``: the set of
things a proposal can name is closed, no member carries a triage level or a
path, and the one target that comes near triage has no ``level`` field at all.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import get_type_hints

import pytest

REPO = Path(__file__).resolve().parents[2]
LEARNING_SRC = REPO / "services" / "learning" / "src"
LEARNING_ROOT = LEARNING_SRC / "intake_learning"

#: The invariant-15 shell. It mounts the four health endpoints through shared
#: platform code every service uses, so the gates about what the *pipeline* may
#: touch (2, 3, 5, 6) scope past it. Gates 1 and 4 do not: invariant 12 binds
#: the whole package, and so does "no writer".
SHELL_MODULES = frozenset({"app.py"})

#: Every first-party import root in the workspace, so the closure can follow a
#: hop into any of them rather than stopping at the package boundary.
FIRST_PARTY: dict[str, Path] = {
    "intake_learning": LEARNING_SRC,
    "intake_platform": REPO / "packages" / "intake_platform" / "src",
    "protocols": REPO / "packages" / "protocols" / "src",
    "clinical_schemas": REPO / "packages" / "clinical-schemas" / "src",
    "voice_clips": REPO / "packages" / "voice-clips" / "src",
    "intake_api": REPO / "services" / "api" / "src",
    "intake_metrics": REPO / "services" / "metrics" / "src",
    "intake_probes": REPO / "services" / "probes" / "src",
    "intake_voice_runtime": REPO / "services" / "voice-runtime" / "src",
}

#: The six forbidden subjects of invariant 12 / files/09 §4, as the modules
#: that hold them. Each entry names the subject it stands for, so a failure
#: reports the invariant rather than a file path.
FORBIDDEN_MODULES: dict[str, str] = {
    "protocols": (
        "red-flag levels and the instruments — packages/protocols holds the "
        "triage rules, the DSL, the compiler and the instrument licences "
        "(invariant 12; files/09 §4)"
    ),
    "intake_voice_runtime": (
        "the Talker tool list, PolicyGuard and voice profile routing — "
        "services/voice-runtime holds all three (invariants 9, 12, 19)"
    ),
    "intake_platform.legal": "the consent and legal texts (invariant 18)",
    "intake_platform.consent": "the consent scopes and their texts (invariant 4)",
    "intake_platform.profiles": "profile routing (invariant 12: residency routing)",
    "intake_api": (
        "the write path to every one of the above — services/api is what "
        "persists a change (invariant 12: proposal-only)"
    ),
    "voice_clips": "the spoken clip cache built from protocol text (invariant 10)",
}

#: Anything that opens a connection, spawns a process or touches a filesystem.
#: ``sqlalchemy`` is deliberately absent: it is the *read* side, exercised only
#: through ``intake_platform.analytics``, whose credentials are INT-171's
#: ``svc_learning_reader`` — SELECT on three aggregate views and nothing else
#: (migrations/versions/0009_int171_analytics_views.py).
NETWORK_OR_PROCESS_MODULES = frozenset(
    {
        "aiohttp",
        "ftplib",
        "http",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "smtplib",
        "socket",
        "subprocess",
        "tempfile",
        "urllib",
    }
)

#: What the pipeline's own modules may import. Deliberately short: adding to it
#: is a scope decision, and gate 2 re-checks the result.
#:
#: ``sqlalchemy`` appears exactly once, as ``intake_learning.run``'s
#: ``AsyncSession`` annotation under ``if TYPE_CHECKING`` — so it is not
#: imported at runtime at all. The walker counts it anyway (a name a module
#: mentions is a name it was designed around), and it is allowed for the reason
#: it is absent from :data:`NETWORK_OR_PROCESS_MODULES`: the session is the read
#: side, on INT-171's ``svc_learning_reader`` grants, and
#: :func:`test_the_pipeline_composes_no_sql_of_its_own` holds the other end.
ALLOWED_EXTERNAL = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "hashlib",
        "hmac",
        "json",
        "typing",
        "prometheus_client",
        "sqlalchemy",
    }
)

#: Attribute calls that mutate a filesystem or a process. ``write`` is here
#: too: the package returns values and never owns a sink. ``replace`` and
#: ``rename`` are here because ``os.replace``/``Path.replace`` overwrite
#: silently — the cost is that ``str.replace`` trips the gate as well, and the
#: package spells that munging out (``intake_learning.publisher._slug``) rather
#: than the gate carrying an exception list it would have to keep correct.
WRITE_CAPABLE_ATTRS = frozenset(
    {
        "chmod",
        "makedirs",
        "mkdir",
        "remove",
        "removedirs",
        "rename",
        "replace",
        "rmdir",
        "rmtree",
        "system",
        "touch",
        "unlink",
        "write",
        "write_bytes",
        "write_text",
        "writelines",
    }
)


# --- the walker -------------------------------------------------------------------


def _dotted_of(path: Path) -> str:
    for root in FIRST_PARTY.values():
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        parts = list(relative.parts)
        if parts[-1] == "__init__.py":
            parts.pop()
        else:
            parts[-1] = parts[-1].removesuffix(".py")
        return ".".join(parts)
    return ""


def _module_files(dotted: str) -> list[Path]:
    """Every first-party source file executed when ``dotted`` is imported.

    Importing ``a.b.c`` runs ``a/__init__.py`` and ``a/b/__init__.py`` before
    ``a/b/c.py``; a closure that skipped the ancestors would miss a forbidden
    import sitting in a package ``__init__``.
    """
    parts = dotted.split(".")
    root = FIRST_PARTY.get(parts[0])
    if root is None:
        return []
    found: list[Path] = []
    for depth in range(1, len(parts) + 1):
        prefix = root.joinpath(*parts[:depth])
        for candidate in (prefix / "__init__.py", prefix.with_suffix(".py")):
            if candidate.is_file():
                found.append(candidate)
    return found


def _imports_in(path: Path) -> set[str]:
    """Every dotted module name imported anywhere in ``path``.

    The whole tree is walked, not only module level: a function-local import is
    still a reachable edge, and one hidden under ``if TYPE_CHECKING`` would
    still be a design that names a forbidden module.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _dotted_of(path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level)[0] if "." in package else package
                names.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                names.add(node.module)
                names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _sources(*, pipeline_only: bool) -> list[Path]:
    return sorted(
        path
        for path in LEARNING_ROOT.rglob("*.py")
        if not (pipeline_only and path.name in SHELL_MODULES)
    )


def _closure(*, pipeline_only: bool) -> set[str]:
    """Every module name reachable, transitively, from the chosen corpus."""
    seen: set[Path] = set()
    named: set[str] = set()
    frontier = _sources(pipeline_only=pipeline_only)
    while frontier:
        path = frontier.pop()
        if path in seen:
            continue
        seen.add(path)
        for dotted in _imports_in(path):
            named.add(dotted)
            frontier.extend(nxt for nxt in _module_files(dotted) if nxt not in seen)
    return named


def _roots(named: set[str]) -> set[str]:
    return {dotted.split(".")[0] for dotted in named}


# --- gate 0: the scan walks a real corpus -----------------------------------------


def test_the_scan_walks_a_real_corpus() -> None:
    """The gate is hollow if the walker finds nothing to scan."""
    assert LEARNING_ROOT.is_dir(), "services/learning/src/intake_learning must exist"
    names = {path.name for path in _sources(pipeline_only=False)}
    for expected in ("proposals.py", "inspector.py", "architect.py", "evidence.py"):
        assert expected in names, f"{expected} must be inside the scan"
    assert "app.py" in names
    assert "app.py" not in {path.name for path in _sources(pipeline_only=True)}
    # the walker must actually follow a hop out of the package
    assert "intake_platform.analytics" in _closure(pipeline_only=True)


# --- gate 1: invariant 12 ----------------------------------------------------------


def test_the_import_closure_never_reaches_a_forbidden_module() -> None:
    named = _closure(pipeline_only=False)
    breaches = [
        f"{dotted} -> {subject}"
        for dotted in sorted(named)
        for forbidden, subject in FORBIDDEN_MODULES.items()
        if dotted == forbidden or dotted.startswith(f"{forbidden}.")
    ]
    assert breaches == [], (
        f"services/learning reached a module invariant 12 forbids it changing: {breaches}"
    )


def test_the_gate_would_report_a_forbidden_import(tmp_path: Path) -> None:
    """Negative control: silence must not be the only possible answer."""
    sneaky = tmp_path / "sneaky.py"
    sneaky.write_text(
        "from protocols.triage import rules\nimport intake_voice_runtime.talker\n",
        encoding="utf-8",
    )
    named = _imports_in(sneaky)
    hits = [
        forbidden
        for dotted in named
        for forbidden in FORBIDDEN_MODULES
        if dotted == forbidden or dotted.startswith(f"{forbidden}.")
    ]
    assert set(hits) == {"protocols", "intake_voice_runtime"}


# --- gate 2: no egress -------------------------------------------------------------


def test_the_pipeline_closure_reaches_no_network_or_process_module() -> None:
    named = _closure(pipeline_only=True)
    hits = sorted(_roots(named) & NETWORK_OR_PROCESS_MODULES)
    assert hits == [], (
        "the Loop 2 pipeline reached a network or process module. files/09 §7 "
        "wants a sandboxed job with no egress; keeping that true in the source "
        f"means the sandbox is the second control, not the only one: {hits}"
    )


# --- gate 3: the allow-list --------------------------------------------------------


def test_the_pipeline_imports_nothing_outside_the_declared_allow_list() -> None:
    named: set[str] = set()
    for path in _sources(pipeline_only=True):
        named |= _imports_in(path)
    unexpected = sorted(_roots(named) - set(FIRST_PARTY) - _roots(set(ALLOWED_EXTERNAL)))
    assert unexpected == [], (
        f"the Loop 2 pipeline imports outside its declared allow-list: {unexpected}"
    )


def test_the_allow_list_holds_no_network_or_process_module() -> None:
    # The allow-list is the control; this pins that the control says what we
    # think it says, so widening it trips a second assertion.
    assert ALLOWED_EXTERNAL & NETWORK_OR_PROCESS_MODULES == frozenset()


# --- gate 4: no writer -------------------------------------------------------------


def test_the_package_contains_no_write_capable_call() -> None:
    offences: list[str] = []
    for path in _sources(pipeline_only=False):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in WRITE_CAPABLE_ATTRS:
                offences.append(f"{path.relative_to(REPO)}:{node.lineno} .{func.attr}(")
            if isinstance(func, ast.Name) and func.id in {"open", "exec", "eval", "compile"}:
                offences.append(f"{path.relative_to(REPO)}:{node.lineno} {func.id}(")
    assert offences == [], (
        "services/learning holds a write-capable call. A proposal is data: the "
        "package returns values and never owns a sink, which is why no path "
        f"allow-list is needed to keep it out of a protocol pack: {offences}"
    )


# --- the proposal type surface ----------------------------------------------------


def test_the_proposal_target_vocabulary_is_exactly_the_blueprint_list() -> None:
    """files/09 §4 "Proposal types (allowed)" is a closed list; so is the type.

    Adding a target is a deliberate edit to this assertion — a CODEOWNER-visible
    change — rather than a new class nobody reviews.
    """
    from intake_learning.proposals import PROPOSAL_TARGETS

    assert {target.__name__ for target in PROPOSAL_TARGETS} == {
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
    }


def test_no_proposal_target_can_carry_a_triage_level_or_a_path() -> None:
    """The INT-091 posture: refused by type, not validated at the edge.

    No field anywhere in the vocabulary could hold a triage level, a rule id or
    a filesystem path, so "a proposal that touches a red-flag level" has no
    representation to be rejected — it cannot be written down.
    """
    from intake_learning.proposals import PROPOSAL_TARGETS

    banned = ("TriageLevel", "RedFlagLevel", "Path", "PurePath", "PosixPath", "RuleFire")
    offences: list[str] = []
    for target in PROPOSAL_TARGETS:
        assert is_dataclass(target), f"{target.__name__} must be a frozen dataclass"
        hints = get_type_hints(target)
        for field in fields(target):
            rendered = str(hints[field.name])
            if any(name in rendered for name in banned):
                offences.append(f"{target.__name__}.{field.name}: {rendered}")
    assert offences == [], f"a proposal target names a forbidden carrier: {offences}"


def test_a_candidate_red_flag_has_no_level_field_at_all() -> None:
    """Invariant 1: an LLM-derived flag is capped at YELLOW_REVIEW.

    The cap is not a validator. ``CandidateRedFlag`` has no ``level`` in its
    field set, so there is no constructor argument through which RED could be
    expressed; the level is a class constant the type exposes read-only.
    """
    from intake_learning.proposals import CandidateRedFlag

    assert "level" not in {f.name for f in fields(CandidateRedFlag)}
    flag = CandidateRedFlag(pack_id="base.intake", slot_id="chest_pain_onset")
    assert flag.level == "YELLOW_REVIEW"
    with pytest.raises((AttributeError, TypeError)):
        flag.level = "RED"  # type: ignore[misc]
    with pytest.raises(TypeError):
        CandidateRedFlag(  # type: ignore[call-arg]
            pack_id="base.intake", slot_id="chest_pain_onset", level="RED"
        )


def test_the_prompt_module_target_excludes_the_talker_and_safety_prompts() -> None:
    """files/09 §4: GEPA optimises the extraction and note modules only."""
    from intake_learning.proposals import PROMPT_MODULES, PromptModule, PromptModuleId

    assert PROMPT_MODULES == ("extraction", "note")
    assert not any(
        token in member.value for member in PromptModuleId for token in ("talker", "policy")
    )
    for excluded in ("talker", "policyguard", "safety"):
        with pytest.raises(ValueError, match="extraction"):
            PromptModule(module=excluded)  # type: ignore[arg-type]


def test_a_maturity_proposal_promotes_and_never_demotes() -> None:
    from intake_learning.proposals import PackMaturity, PackMaturityLevel

    PackMaturity(
        pack_id="base.intake",
        slot_id="medication_adherence",
        from_level=PackMaturityLevel.L0,
        to_level=PackMaturityLevel.L1,
    )
    with pytest.raises(ValueError, match="promotes"):
        PackMaturity(
            pack_id="base.intake",
            slot_id="medication_adherence",
            from_level=PackMaturityLevel.L2,
            to_level=PackMaturityLevel.L1,
        )


def test_the_read_path_is_int_171s_gated_one_and_never_the_ungated_projection() -> None:
    """``materialise_view`` applies the k floor at the query layer; ``read_cells``
    projects rows without one. The run may only name the first.

    Read from source rather than by calling: the point is that no branch of the
    module can reach the ungated projection, not that today's happy path does
    not take it.
    """
    named: set[str] = set()
    for path in _sources(pipeline_only=True):
        named |= _imports_in(path)
    assert "intake_platform.analytics.materialise_view" in named
    assert not any(dotted.endswith(".read_cells") for dotted in named)
    assert not any(dotted.endswith(".cells_query") for dotted in named)


def test_the_pipeline_composes_no_sql_of_its_own() -> None:
    """The read-only credential is the control; this is why it is sufficient.

    The package issues one INT-171 call per view and never builds a statement,
    so there is no expression in it through which a write could be attempted —
    which is what makes ``svc_learning_reader``'s SELECT-only grant a belt
    rather than the only strap.
    """
    forbidden = {"text", "insert", "update", "delete", "execute", "executemany", "commit"}
    offences: list[str] = []
    for path in _sources(pipeline_only=True):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in forbidden:
                    offences.append(f"{path.relative_to(REPO)}:{node.lineno} {name}(")
    assert offences == [], f"the Loop 2 pipeline composes or issues SQL: {offences}"
