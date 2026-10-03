"""The clinical decisions register (INT-432, owner decision D18).

files/00_STATE.md §3 D18: open clinical decisions are resolved by
medical-professional agents from current guidelines and openEHR CKM, and
verified by an independent agent, **for simulated-patient stress testing
only** — a licensed physician's review is required before any real patient.

Each decision is one YAML document under ``packages/protocols/decisions/``
(``CD-NN.yaml``) with a human-readable twin in ``docs/clinical/decisions/``.
This module is the typed boundary every consumer reads through (the INT-430
verifier among them), and it refuses, rather than repairs, a decision that
does not hold its own provenance:

- every guideline source names a committed snapshot under
  ``packages/protocols/sources/`` whose header declares the same
  ``guideline_id``, and the ``quote`` appears **verbatim** in that
  snapshot's body (Unicode NFC and runs of whitespace are the only
  normalisation — line wrapping in a snapshot is not a change of words);
- an openEHR CKM source names an archetype id and a revision;
- ``status: active`` needs at least one source and no ``source_gap``;
  ``status: draft_needs_source`` needs a non-empty ``source_gap``
  (files/04 §8.1 rule 3 applied to decisions);
- the invariant-17 pending literal may appear in ``value`` only inside the
  decision, or the entry, whose ``status`` is ``draft_needs_source`` — and
  no other pending token may appear anywhere (CLAUDE.md invariant 17);
- no source cites a retired or superseded guideline (files/04 §8.2).

Nothing here reads a value into the engine. A consumer that needs one asks
for it by decision id and must handle ``draft_needs_source`` by failing
closed: an unsourced value is absent, never defaulted.
"""

from __future__ import annotations

import enum
import re
import unicodedata
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal

import yaml
from clinical_schemas.common import FrozenModel
from pydantic import Field, TypeAdapter, ValidationError, model_validator

from protocols.validator import PLACEHOLDER_SIGNOFF_RE

__all__ = [
    "REGISTER_DIR",
    "SCOPE",
    "SOURCES_DIR",
    "CkmSource",
    "SpecBasis",
    "ClinicalDecision",
    "DecisionRegisterError",
    "DecisionStatus",
    "GuidelineSource",
    "Verifier",
    "VerifierVerdict",
    "load_decision",
    "load_register",
    "quote_in_snapshot",
    "snapshot_body",
    "snapshot_header",
    "unsourced_paths",
]

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REGISTER_DIR = _PACKAGE_ROOT / "decisions"
SOURCES_DIR = _PACKAGE_ROOT / "sources"

SCOPE = "simulated_patient_stress_testing"
"""D18's scope, as the one value a decision may declare. A decision that
claims any other scope is refused: the owner's decision does not reach a
real patient, and the register cannot be read as if it did."""

# Built rather than written, so this module never carries the token the
# no_placeholders gate scans for (the gate's own memory: a guard must not
# name what it forbids).
_PENDING_TOKEN = "TO" + "DO"
_GAP_KEYS = ("source_gap", "basis", "when")

_DECISION_ID = r"^CD-\d{2}$"
_ARCHETYPE_ID = r"^openEHR-EHR-[A-Z_]+\.[a-z0-9_]+\.v\d+$"
_SNAPSHOT_PREFIX = "packages/protocols/sources/"

# files/04 §8.2 `no_source_uses_a_retired_or_superseded_guideline`, by the
# id tokens a guideline_id spells them with.
RETIRED_GUIDELINE_TOKENS: frozenset[str] = frozenset(
    {"NG51", "CG102", "SSC-2021", "IDSA-2010", "ACC-AHA-2017-HTN"}
)


class DecisionRegisterError(ValueError):
    """A decision document that does not hold its own provenance."""


class DecisionStatus(enum.StrEnum):
    """files/04 §8.1 rule 3, applied to a decision rather than a rule."""

    ACTIVE = "active"
    DRAFT_NEEDS_SOURCE = "draft_needs_source"


class VerifierVerdict(enum.StrEnum):
    """The independent verifier's verdict (INT-432 acceptance)."""

    PENDING = "pending"
    AGREE = "agree"
    AGREE_WITH_CHANGES = "agree_with_changes"
    DISAGREE = "disagree"


class GuidelineSource(FrozenModel):
    """A current guideline or regulation, quoted against a committed snapshot."""

    kind: Literal["guideline"] = Field(description="Source kind discriminator.")
    guideline_id: str = Field(min_length=1, description="Stable guideline id (files/12 §2.5).")
    title: str = Field(min_length=1, description="Guideline title.")
    version_or_date: str = Field(min_length=1, description="Version or date as printed.")
    url: str = Field(pattern=r"^https://", description="Where it was retrieved.")
    retrieved_on: date = Field(description="Retrieval date.")
    quote: str = Field(min_length=1, description="Verbatim supporting quote.")
    snapshot: str = Field(description="Committed snapshot path under packages/protocols/sources/.")
    section: str | None = Field(default=None, description="Section or recommendation cited.")
    supports: str | None = Field(default=None, description="Which value key it supports.")
    caveat: str | None = Field(default=None, description="Limits on how far it reaches.")
    note: str | None = Field(default=None, description="Provenance commentary.")


class CkmSource(FrozenModel):
    """An openEHR CKM archetype, cited by id and revision."""

    kind: Literal["openehr_ckm"] = Field(description="Source kind discriminator.")
    archetype_id: str = Field(pattern=_ARCHETYPE_ID, description="CKM archetype id.")
    revision: str = Field(min_length=1, description="CKM revision as shown on CKM.")
    url: str = Field(pattern=r"^https://", description="CKM page retrieved.")
    retrieved_on: date = Field(description="Retrieval date.")
    quote: str | None = Field(default=None, description="Optional verbatim element text.")
    snapshot: str | None = Field(default=None, description="Optional committed snapshot path.")
    section: str | None = Field(default=None, description="Section or recommendation cited.")
    supports: str | None = Field(default=None, description="Which value key it supports.")
    caveat: str | None = Field(default=None, description="Limits on how far it reaches.")
    note: str | None = Field(default=None, description="Provenance commentary.")


type Source = Annotated[GuidelineSource | CkmSource, Field(discriminator="kind")]

_SOURCE_ADAPTER: TypeAdapter[GuidelineSource | CkmSource] = TypeAdapter(Source)


class Verifier(FrozenModel):
    """The independent verifier's verdict on one decision."""

    verdict: VerifierVerdict = Field(description="pending until the verifier has read it.")
    role: str | None = Field(default=None, description="Verifier agent role.")
    verified_on: date | None = Field(default=None, description="Date of the verdict.")
    notes: str | None = Field(default=None, description="What the verifier checked or changed.")

    @model_validator(mode="after")
    def _a_verdict_names_who_and_when(self) -> Verifier:
        if self.verdict is not VerifierVerdict.PENDING and (
            self.role is None or self.verified_on is None
        ):
            raise ValueError("a non-pending verdict names the verifier role and verified_on")
        return self


class SpecBasis(FrozenModel):
    """A sentence of this repository's own spec that an engineering-side
    value rests on. Never a clinical source: it can support how the product
    behaves (a governor, a state, a screen), never a clinical number."""

    file: str = Field(min_length=1, description="Repo-relative path of the spec file.")
    section: str = Field(min_length=1, description="Section the quote sits in.")
    quote: str = Field(min_length=1, description="Verbatim sentence of that file.")
    supports: str = Field(min_length=1, description="Which value key it supports.")


class ClinicalDecision(FrozenModel):
    """One register entry (``packages/protocols/decisions/CD-NN.yaml``)."""

    kind: Literal["clinical_decision"] = Field(description="Document kind.")
    id: str = Field(pattern=_DECISION_ID, description="Register id, CD-NN.")
    title: str = Field(min_length=1, description="Short title.")
    question: str = Field(min_length=1, description="The open question this resolves.")
    decision: str = Field(min_length=1, description="The decision, in plain words.")
    status: DecisionStatus = Field(description="active | draft_needs_source. No default.")
    scope: Literal["simulated_patient_stress_testing"] = Field(description="D18 scope.")
    author_role: str = Field(min_length=1, description="The authoring agent's role.")
    sources: tuple[Source, ...] = Field(default=(), description="Guideline or CKM citations.")
    source_gap: str | None = Field(default=None, description="Why no source supports it.")
    value: dict[str, Any] = Field(default_factory=dict, description="Decision-specific values.")
    value_status: dict[str, DecisionStatus] = Field(
        default_factory=dict,
        description="Per-key status (dotted keys into value) where one decision is "
        "partly sourced: a consumer reads only the keys marked active.",
    )
    spec_basis: tuple[SpecBasis, ...] = Field(
        default=(), description="Repo spec sentences behind engineering-side values."
    )
    scope_note: str | None = Field(default=None, description="How D18's scope applies here.")
    question_origin: str | None = Field(default=None, description="Where the question was raised.")
    inference_disclosure: str | None = Field(
        default=None, description="Where the operationalisation is the author's (files/04 §8.1 r2)."
    )
    fail_closed_while_draft: str | None = Field(
        default=None, description="What the product does while a value stays draft."
    )
    verifier: Verifier = Field(description="Independent verifier verdict.")

    @model_validator(mode="after")
    def _status_and_provenance_agree(self) -> ClinicalDecision:
        if self.status is DecisionStatus.ACTIVE:
            if not self.sources:
                raise ValueError(f"{self.id}: an active decision cites at least one source")
            partly_draft = DecisionStatus.DRAFT_NEEDS_SOURCE in self.value_status.values()
            if self.source_gap and not partly_draft:
                raise ValueError(
                    f"{self.id}: an active decision carries a source_gap only for the "
                    "value_status keys it marks draft_needs_source"
                )
        elif not (self.source_gap and self.source_gap.strip()):
            raise ValueError(f"{self.id}: draft_needs_source needs a non-empty source_gap")
        return self


def _normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def snapshot_header(text: str) -> dict[str, str]:
    """The ``# key: value`` header lines above the ``---`` separator."""
    header: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip() == "---":
            return header
        match = re.match(r"^#\s*([a-z_]+):\s*(.*)$", line)
        if match:
            header[match.group(1)] = match.group(2).strip()
    raise DecisionRegisterError("snapshot has no '---' line separating header from body")


def snapshot_body(text: str) -> str:
    """Everything below the first ``---`` line: the verbatim excerpt."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :])
    raise DecisionRegisterError("snapshot has no '---' line separating header from body")


def quote_in_snapshot(quote: str, body: str) -> bool:
    """Verbatim containment, modulo NFC and whitespace runs only."""
    return _normalise(quote) in _normalise(body)


def _check_snapshot(
    decision_id: str,
    *,
    snapshot: str,
    quote: str | None,
    declared_id: tuple[tuple[str, ...], str],
    repo_root: Path,
    revision: str | None = None,
) -> None:
    if not snapshot.startswith(_SNAPSHOT_PREFIX) or ".." in snapshot:
        raise DecisionRegisterError(
            f"{decision_id}: snapshot {snapshot!r} must live under {_SNAPSHOT_PREFIX}"
        )
    path = repo_root / snapshot
    if not path.is_file():
        raise DecisionRegisterError(f"{decision_id}: snapshot {snapshot!r} is not committed")
    text = path.read_text(encoding="utf-8")
    keys, expected = declared_id
    header = snapshot_header(text)
    declared = next((header[key] for key in keys if key in header), None)
    if declared != expected:
        raise DecisionRegisterError(
            f"{decision_id}: snapshot {snapshot!r} declares {declared!r}, "
            f"the source cites {expected!r}"
        )
    if revision is not None and revision not in header.get("version_or_date", ""):
        raise DecisionRegisterError(
            f"{decision_id}: snapshot {snapshot!r} is not revision {revision!r} "
            "of the archetype the source cites"
        )
    if quote is not None and not quote_in_snapshot(quote, snapshot_body(text)):
        raise DecisionRegisterError(
            f"{decision_id}: quote is not verbatim in {snapshot!r}: {quote[:80]!r}"
        )


def _check_sources(decision: ClinicalDecision, repo_root: Path) -> None:
    for source in _all_sources(decision):
        if isinstance(source, GuidelineSource):
            tokens = set(re.split(r"[\s_/]+", source.guideline_id.upper()))
            tokens |= {source.guideline_id.upper()}
            retired = {t for t in RETIRED_GUIDELINE_TOKENS if any(t in tok for tok in tokens)}
            if retired:
                raise DecisionRegisterError(
                    f"{decision.id}: {source.guideline_id} is retired or superseded (files/04 §8.2)"
                )
            _check_snapshot(
                decision.id,
                snapshot=source.snapshot,
                quote=source.quote,
                declared_id=(("guideline_id",), source.guideline_id),
                repo_root=repo_root,
            )
        elif source.snapshot is not None:
            _check_snapshot(
                decision.id,
                snapshot=source.snapshot,
                quote=source.quote,
                declared_id=(("archetype_id", "guideline_id"), source.archetype_id),
                repo_root=repo_root,
                revision=source.revision,
            )


def _all_sources(decision: ClinicalDecision) -> Iterator[GuidelineSource | CkmSource]:
    """The decision's own sources and any ``sources:`` list nested in ``value``."""
    yield from decision.sources
    for raw in _nested_source_lists(decision.value):
        try:
            yield _SOURCE_ADAPTER.validate_python(raw)
        except ValidationError as exc:
            raise DecisionRegisterError(
                f"{decision.id}: nested source is malformed: {exc}"
            ) from exc


def _nested_source_lists(node: object) -> Iterator[Mapping[str, Any]]:
    if isinstance(node, Mapping):
        for key, child in node.items():
            if key == "sources" and isinstance(child, list):
                yield from (item for item in child if isinstance(item, Mapping) and "kind" in item)
            else:
                yield from _nested_source_lists(child)
    elif isinstance(node, list):
        for child in node:
            yield from _nested_source_lists(child)


def unsourced_paths(decision: ClinicalDecision) -> tuple[str, ...]:
    """JSON-ish paths in ``value`` that carry the invariant-17 literal."""
    return tuple(path for path, _, _ in _pending_strings(decision.value, "value", drafted=False))


def _pending_strings(node: object, path: str, *, drafted: bool) -> Iterator[tuple[str, str, bool]]:
    """(path, text, drafted) for every string carrying the pending token;
    ``drafted`` is whether it sits under a draft_needs_source status."""
    if isinstance(node, Mapping):
        here = drafted or node.get("status") == DecisionStatus.DRAFT_NEEDS_SOURCE.value
        for key, child in node.items():
            yield from _pending_strings(child, f"{path}.{key}", drafted=here)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _pending_strings(child, f"{path}[{index}]", drafted=drafted)
    elif isinstance(node, str) and _PENDING_TOKEN in node:
        yield path, node, drafted


def _drafted_by_value_status(decision: ClinicalDecision, path: str) -> bool:
    """Whether ``value_status`` marks this path, or a key above it, draft."""
    dotted = re.sub(r"\[\d+\]", "", path.removeprefix("value."))
    return any(
        status is DecisionStatus.DRAFT_NEEDS_SOURCE
        and (dotted == key or dotted.startswith(f"{key}."))
        for key, status in decision.value_status.items()
    )


def _check_pending_discipline(decision: ClinicalDecision) -> None:
    whole_draft = decision.status is DecisionStatus.DRAFT_NEEDS_SOURCE
    for path, text, drafted in _pending_strings(decision.value, "value", drafted=whole_draft):
        drafted = drafted or _drafted_by_value_status(decision, path)
        if not PLACEHOLDER_SIGNOFF_RE.fullmatch(text.strip()):
            raise DecisionRegisterError(
                f"{decision.id}: {path} carries a pending token outside the sanctioned "
                "invariant-17 form"
            )
        if not drafted:
            raise DecisionRegisterError(
                f"{decision.id}: {path} is unsourced but neither the decision nor its "
                "entry is draft_needs_source"
            )
    for field_name in ("title", "question", "decision", "author_role"):
        if _PENDING_TOKEN in getattr(decision, field_name):
            raise DecisionRegisterError(f"{decision.id}: {field_name} carries a pending token")


def _check_entry_drafts(decision: ClinicalDecision) -> None:
    """An entry that declares itself draft says why, like a rule does: in its
    ``source_gap``, or in the ``basis`` / ``when`` sentence a placement row
    uses for the same purpose, or in the decision's own ``source_gap`` when it
    has one. The pending literal itself is not a reason."""
    for entry in _mappings(decision.value):
        if entry.get("status") == DecisionStatus.DRAFT_NEEDS_SOURCE.value:
            reasons = [entry.get(key) for key in _GAP_KEYS] + [decision.source_gap]
            if not any(
                isinstance(text, str) and text.strip() and _PENDING_TOKEN not in text
                for text in reasons
            ):
                raise DecisionRegisterError(
                    f"{decision.id}: an entry marked draft_needs_source names no source_gap"
                )


def _mappings(node: object) -> Iterator[Mapping[str, Any]]:
    if isinstance(node, Mapping):
        yield node
        for child in node.values():
            yield from _mappings(child)
    elif isinstance(node, list):
        for child in node:
            yield from _mappings(child)


def load_decision(path: Path, *, repo_root: Path | None = None) -> ClinicalDecision:
    """Load, validate and provenance-check one ``CD-NN.yaml``."""
    root = repo_root if repo_root is not None else _PACKAGE_ROOT.parents[1]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise DecisionRegisterError(f"{path.name}: a decision is a mapping")
    try:
        decision = ClinicalDecision.model_validate(raw)
    except ValidationError as exc:
        raise DecisionRegisterError(f"{path.name}: {exc}") from exc
    if path.stem != decision.id:
        raise DecisionRegisterError(f"{path.name}: file name and id {decision.id!r} disagree")
    _check_pending_discipline(decision)
    _check_entry_drafts(decision)
    _check_value_status(decision)
    _check_sources(decision, root)
    _check_spec_basis(decision, root)
    return decision


def _check_spec_basis(decision: ClinicalDecision, repo_root: Path) -> None:
    for basis in decision.spec_basis:
        path = (repo_root / basis.file).resolve()
        if not path.is_relative_to(repo_root.resolve()) or not path.is_file():
            raise DecisionRegisterError(f"{decision.id}: spec file {basis.file!r} is not committed")
        if not quote_in_snapshot(basis.quote, path.read_text(encoding="utf-8")):
            raise DecisionRegisterError(
                f"{decision.id}: spec quote is not verbatim in {basis.file!r}: {basis.quote[:80]!r}"
            )


def _check_value_status(decision: ClinicalDecision) -> None:
    """A per-key status names keys that exist, and a key marked active never
    carries the pending literal except inside an entry that itself says
    draft_needs_source (the whole-decision status cannot hide it)."""
    for dotted, status in decision.value_status.items():
        node: Any = decision.value
        for part in dotted.split("."):
            if not isinstance(node, Mapping) or part not in node:
                raise DecisionRegisterError(
                    f"{decision.id}: value_status names {dotted!r}, which value lacks"
                )
            node = node[part]
        if status is DecisionStatus.ACTIVE:
            pending = [
                path
                for path, _, drafted in _pending_strings(node, dotted, drafted=False)
                if not drafted
            ]
            if pending:
                raise DecisionRegisterError(
                    f"{decision.id}: {pending[0]} is marked active but carries the pending literal"
                )


def load_register(
    directory: Path = REGISTER_DIR, *, repo_root: Path | None = None
) -> Mapping[str, ClinicalDecision]:
    """Every decision in the register, keyed by id, read-only."""
    decisions = {
        decision.id: decision
        for decision in (
            load_decision(path, repo_root=repo_root) for path in sorted(directory.glob("CD-*.yaml"))
        )
    }
    if not decisions:
        raise DecisionRegisterError(f"{directory}: the register is empty")
    return MappingProxyType(decisions)
