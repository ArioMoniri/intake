"""The legal decisions register (INT-471, owner decision D25).

files/00_STATE.md §3 D25: open legal questions are decided by a sourced
legal-author agent and verified by a separate legal-reviewer agent, **for
synthetic and test use only**. A licensed Turkish lawyer countersigns before
any real patient, and legal questions go to this lane, never to the owner.
D25 mirrors D18, the clinical lane (``protocols.clinical_decisions``), and
this module mirrors that loader.

Each decision is one YAML document under
``packages/intake_platform/legal_decisions/`` (``LD-NN.yaml``) with a
human-readable twin in ``docs/legal/decisions/``. Its verbatim snapshots live
under ``legal_decisions/sources/``, outside ``docs/legal/``, so nothing here
touches a hash-bound legal text. The module refuses, rather than repairs, a
decision that does not hold its own provenance:

- every source is an official text — legislation from mevzuat.gov.tr,
  resmigazete.gov.tr, kvkk.gov.tr, saglik.gov.tr or aile.gov.tr with its
  Resmî Gazete date and number, or a standard from its publisher with its
  version — and its ``quote`` appears **verbatim** in a committed snapshot
  whose header declares the same ``source_id`` and ``retrieved_on``
  (Unicode NFC and runs of whitespace are the only normalisation);
- no answer without a source: ``proposed`` and ``active`` need at least one
  source; ``draft`` carries a ``legal_gap`` sentence saying what is missing
  and which source would settle it, and so does any key ``value_status``
  marks ``draft``;
- no pending token anywhere: the invariant-17 literal is the clinical
  lane's sole exception, and this lane does not widen it — a draft states
  its gap in words and its value is absent;
- no active decision without the reviewer: ``active`` needs an ``agree`` or
  ``agree_with_changes`` verdict, and a decision the reviewer agreed with is
  not left ``proposed``;
- no real patient without a lawyer: ``real_patient`` scope needs an active
  decision and every field of a licensed Turkish lawyer's countersign, the
  six-field block that mirrors the physician's ``clinical_signoff``
  (HUMAN_BLOCKERS HB-C1).

A consumer reads a value only through :func:`value_for`, which runs
:func:`clearance` first: a draft or proposed decision, or a draft key, is
absent and never defaulted, and nothing reaches a real patient without the
countersign. The agent lane fills no counsel field anywhere else either —
``docs/legal/data-categories.yaml`` keeps its counsel fields until counsel
signs (INT-349), exactly as D18 fills no ``clinical_signoff``.
"""

from __future__ import annotations

import enum
import re
import unicodedata
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Literal
from urllib.parse import urlsplit

import yaml
from clinical_schemas.common import FrozenModel
from pydantic import Field, ValidationError, model_validator

__all__ = [
    "COUNTERSIGN_FIELDS",
    "OFFICIAL_LEGISLATION_HOSTS",
    "REGISTER_DIR",
    "SOURCES_DIR",
    "STANDARD_HOSTS",
    "Audience",
    "CounselCountersign",
    "DecisionStatus",
    "Gazette",
    "LegalClearanceError",
    "LegalDecision",
    "LegalDecisionError",
    "LegalSource",
    "Scope",
    "SpecBasis",
    "ValueStatus",
    "Verifier",
    "VerifierVerdict",
    "clearance",
    "draft_paths",
    "load_decision",
    "load_register",
    "quote_in_snapshot",
    "snapshot_body",
    "snapshot_header",
    "value_for",
]

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _PACKAGE_ROOT.parents[1]
REGISTER_DIR: Final[Path] = _PACKAGE_ROOT / "legal_decisions"
SOURCES_DIR: Final[Path] = REGISTER_DIR / "sources"
_SNAPSHOT_PREFIX = "packages/intake_platform/legal_decisions/sources/"

OFFICIAL_LEGISLATION_HOSTS: Final[tuple[str, ...]] = (
    "mevzuat.gov.tr",
    "resmigazete.gov.tr",
    "kvkk.gov.tr",
    "saglik.gov.tr",
    "aile.gov.tr",
)
"""Where Turkish legislation is published by the state itself. A commercial
mirror (a law firm's or a publisher's copy) may be read to find a text, but
the cited url is the official one."""

STANDARD_HOSTS: Final[tuple[str, ...]] = ("w3.org",)
"""Publishers of a standard a Turkish rule incorporates (Cumhurbaşkanlığı
Genelgesi 2025/10 names WCAG 2.2)."""

COUNTERSIGN_FIELDS: Final[tuple[str, ...]] = (
    "lawyer_name",
    "bar_association",
    "bar_registration_no",
    "signed_commit",
    "signed_on",
    "evidence",
)
"""The licensed Turkish lawyer's countersign, every field required before a
real patient (D25). The mirror of the physician's sign-off block (HB-C1)."""

# Built rather than written, so this module never carries the token the
# no_placeholders gate scans for (a guard must not name what it forbids).
_PENDING_TOKEN = "TO" + "DO"
_DECISION_ID = r"^LD-\d{2,3}$"
_SOURCE_ID = r"^[A-Z0-9][A-Z0-9.-]*$"
_EVIDENCE_PREFIX = "docs/evidence/"


class LegalDecisionError(ValueError):
    """A decision document that does not hold its own provenance."""


class LegalClearanceError(LegalDecisionError):
    """A decision, or one of its values, may not be used for this audience."""


class DecisionStatus(enum.StrEnum):
    """``draft``: no source, no answer. ``proposed``: sourced, awaiting the
    legal reviewer. ``active``: sourced and verified."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    ACTIVE = "active"


class ValueStatus(enum.StrEnum):
    """Per-key status where one decision is partly sourced."""

    SOURCED = "sourced"
    DRAFT = "draft"


class Scope(enum.StrEnum):
    """D25: agents decide for synthetic and test use; a real patient needs
    a licensed Turkish lawyer's countersign."""

    SYNTHETIC_TEST_ONLY = "synthetic_test_only"
    REAL_PATIENT = "real_patient"


class Audience(enum.StrEnum):
    """Who a consumer is about to use a decision for."""

    SYNTHETIC_TEST = "synthetic_test"
    REAL_PATIENT = "real_patient"


class VerifierVerdict(enum.StrEnum):
    """The independent legal reviewer's verdict."""

    PENDING = "pending"
    AGREE = "agree"
    AGREE_WITH_CHANGES = "agree_with_changes"
    DISAGREE = "disagree"


_AGREEING: Final[frozenset[VerifierVerdict]] = frozenset(
    {VerifierVerdict.AGREE, VerifierVerdict.AGREE_WITH_CHANGES}
)


def _host_in(url: str, hosts: tuple[str, ...]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == known or host.endswith(f".{known}") for known in hosts)


class Gazette(FrozenModel):
    """Where a Turkish instrument was published."""

    published_on: date = Field(description="Resmî Gazete date.")
    number: int = Field(gt=0, description="Resmî Gazete number (sayı).")


class LegalSource(FrozenModel):
    """An official text, quoted against a committed snapshot."""

    kind: Literal["legislation", "standard"] = Field(description="Source kind.")
    source_id: str = Field(pattern=_SOURCE_ID, description="Stable id the snapshot declares.")
    instrument: str = Field(min_length=1, description="Name and number of the instrument.")
    provision: str = Field(min_length=1, description="Article, paragraph or criterion cited.")
    url: str = Field(pattern=r"^https://", description="Official place it was retrieved.")
    gazette: Gazette | None = Field(default=None, description="Resmî Gazete date and number.")
    version_or_date: str | None = Field(default=None, description="Version of a standard.")
    retrieved_on: date = Field(description="Retrieval date; the snapshot declares the same.")
    quote: str = Field(min_length=1, description="Verbatim supporting quote.")
    snapshot: str = Field(description="Committed snapshot path under legal_decisions/sources/.")
    supports: str | None = Field(default=None, description="Which value key it supports.")
    caveat: str | None = Field(default=None, description="Limits on how far it reaches.")
    note: str | None = Field(default=None, description="Provenance commentary.")

    @model_validator(mode="after")
    def _an_official_text(self) -> LegalSource:
        hosts = OFFICIAL_LEGISLATION_HOSTS if self.kind == "legislation" else STANDARD_HOSTS
        if not _host_in(self.url, hosts):
            raise ValueError(
                f"{self.source_id}: {self.url} is not an official publisher's host "
                f"({', '.join(hosts)})"
            )
        if self.kind == "legislation" and self.gazette is None:
            raise ValueError(
                f"{self.source_id}: legislation names its Resmî Gazete date and number"
            )
        if self.kind == "standard" and not (self.version_or_date and self.version_or_date.strip()):
            raise ValueError(f"{self.source_id}: a standard names its version_or_date")
        return self


class SpecBasis(FrozenModel):
    """A sentence of this repository (an owner decision, a review finding)
    that a value rests on. Never a legal source: it says what the product is
    or what was asked, never what the law requires."""

    file: str = Field(min_length=1, description="Repo-relative path of the file.")
    section: str = Field(min_length=1, description="Section the quote sits in.")
    quote: str = Field(min_length=1, description="Verbatim sentence of that file.")
    supports: str = Field(min_length=1, description="Which value key it supports.")


class Verifier(FrozenModel):
    """The independent legal reviewer's verdict on one decision."""

    verdict: VerifierVerdict = Field(description="pending until the reviewer has read it.")
    role: str | None = Field(default=None, description="Reviewer agent role.")
    verified_on: date | None = Field(default=None, description="Date of the verdict.")
    notes: str | None = Field(default=None, description="What the reviewer checked or changed.")

    @model_validator(mode="after")
    def _a_verdict_names_who_and_when(self) -> Verifier:
        if self.verdict is not VerifierVerdict.PENDING and (
            self.role is None or self.verified_on is None
        ):
            raise ValueError("a non-pending verdict names the reviewer role and verified_on")
        return self


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class CounselCountersign(FrozenModel):
    """A licensed Turkish lawyer's countersign. Every field is nullable so an
    unsigned block still parses; the refusal is the decision's, where it can
    say which field is missing."""

    lawyer_name: str | None = Field(default=None, description="The countersigning lawyer.")
    bar_association: str | None = Field(default=None, description="Baro the lawyer is in.")
    bar_registration_no: str | None = Field(default=None, description="Baro sicil numarası.")
    signed_commit: str | None = Field(default=None, description="Commit the signature binds to.")
    signed_on: date | None = Field(default=None, description="Countersign date.")
    evidence: str | None = Field(default=None, description="Where the countersign is recorded.")

    @model_validator(mode="after")
    def _recorded_in_evidence(self) -> CounselCountersign:
        if not _blank(self.evidence) and not str(self.evidence).startswith(_EVIDENCE_PREFIX):
            raise ValueError(
                f"a countersign is recorded under {_EVIDENCE_PREFIX}, not {self.evidence!r}"
            )
        return self

    def missing(self) -> tuple[str, ...]:
        """Which countersign fields are still empty, in declaration order."""
        return tuple(name for name in COUNTERSIGN_FIELDS if _blank(getattr(self, name)))

    def is_empty(self) -> bool:
        return len(self.missing()) == len(COUNTERSIGN_FIELDS)


class LegalDecision(FrozenModel):
    """One register entry (``packages/intake_platform/legal_decisions/LD-NN.yaml``)."""

    kind: Literal["legal_decision"] = Field(description="Document kind.")
    id: str = Field(pattern=_DECISION_ID, description="Register id, LD-NN.")
    title: str = Field(min_length=1, description="Short title.")
    question: str = Field(min_length=1, description="The open question this resolves.")
    outcome: str = Field(min_length=1, description="The decision, in plain words.")
    legal_basis: str = Field(min_length=1, description="The provisions it rests on.")
    status: DecisionStatus = Field(description="draft | proposed | active. No default.")
    scope: Scope = Field(description="D25 scope. No default.")
    author_role: str = Field(min_length=1, description="The authoring agent's role.")
    sources: tuple[LegalSource, ...] = Field(default=(), description="Official texts cited.")
    legal_gap: str | None = Field(
        default=None, description="What is missing and which source would settle it."
    )
    value: dict[str, Any] = Field(default_factory=dict, description="Decision-specific values.")
    value_status: dict[str, ValueStatus] = Field(
        default_factory=dict,
        description="Per-key status (dotted keys into value): a consumer reads only "
        "the keys not marked draft.",
    )
    spec_basis: tuple[SpecBasis, ...] = Field(
        default=(), description="Repo sentences behind product-side values."
    )
    scope_note: str | None = Field(default=None, description="How D25's scope applies here.")
    question_origin: str | None = Field(default=None, description="Where the question was raised.")
    inference_disclosure: str | None = Field(
        default=None, description="Where the reading is the author's, not the text's."
    )
    fail_closed_while_draft: str | None = Field(
        default=None, description="What the product does while a value stays draft."
    )
    verifier: Verifier = Field(description="Independent legal reviewer verdict.")
    counsel_countersign: CounselCountersign | None = Field(
        default=None, description="A licensed Turkish lawyer's countersign (real patients)."
    )

    @model_validator(mode="after")
    def _status_provenance_and_scope_agree(self) -> LegalDecision:
        has_gap = not _blank(self.legal_gap)
        draft_keys = [
            key for key, status in self.value_status.items() if status is ValueStatus.DRAFT
        ]
        if self.status is DecisionStatus.DRAFT:
            if not has_gap:
                raise ValueError(f"{self.id}: a draft names its legal_gap")
        else:
            if not self.sources:
                raise ValueError(
                    f"{self.id}: a {self.status.value} decision cites at least one source"
                )
            if draft_keys and not has_gap:
                raise ValueError(f"{self.id}: draft keys {draft_keys} need a legal_gap")
            if has_gap and not draft_keys:
                raise ValueError(
                    f"{self.id}: a sourced decision carries a legal_gap only for the "
                    "value_status keys it marks draft"
                )
        verdict = self.verifier.verdict
        if self.status is DecisionStatus.ACTIVE and verdict not in _AGREEING:
            raise ValueError(
                f"{self.id}: an active decision needs the legal reviewer's agree or "
                f"agree_with_changes verdict, not {verdict.value}"
            )
        if self.status is DecisionStatus.PROPOSED and verdict in _AGREEING:
            raise ValueError(
                f"{self.id}: a decision the reviewer agreed with is active, not proposed"
            )
        self._check_scope()
        return self

    def _check_scope(self) -> None:
        countersign = self.counsel_countersign
        if self.scope is Scope.REAL_PATIENT:
            if self.status is not DecisionStatus.ACTIVE:
                raise ValueError(f"{self.id}: a real_patient decision is active and verified first")
            if countersign is None:
                raise ValueError(
                    f"{self.id}: real_patient scope needs a licensed Turkish lawyer's countersign"
                )
            missing = countersign.missing()
            if missing:
                raise ValueError(f"{self.id}: the countersign is missing {', '.join(missing)}")
        elif countersign is not None and not countersign.is_empty():
            raise ValueError(f"{self.id}: a countersign belongs to a real_patient decision")


# --- snapshots ----------------------------------------------------------------------


def _normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _separator_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line.strip() == "---":
            return index
    raise LegalDecisionError("snapshot has no '---' line separating header from body")


def snapshot_header(text: str) -> dict[str, str]:
    """The ``# key: value`` header lines above the ``---`` separator."""
    lines = text.splitlines()
    header: dict[str, str] = {}
    for line in lines[: _separator_index(lines)]:
        match = re.match(r"^#\s*([a-z_]+):\s*(.*)$", line)
        if match:
            header[match.group(1)] = match.group(2).strip()
    return header


def snapshot_body(text: str) -> str:
    """Everything below the first ``---`` line: the verbatim excerpt."""
    lines = text.splitlines()
    return "\n".join(lines[_separator_index(lines) + 1 :])


def quote_in_snapshot(quote: str, body: str) -> bool:
    """Verbatim containment, modulo NFC and whitespace runs only."""
    return _normalise(quote) in _normalise(body)


# --- load-time checks ----------------------------------------------------------------


def _strings(node: object, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(node, Mapping):
        for key, child in node.items():
            yield f"{path}.{key}", str(key)
            yield from _strings(child, f"{path}.{key}")
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _strings(child, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def _refuse_pending_tokens(raw: Mapping[str, Any], name: str) -> None:
    for path, text in _strings(raw, name):
        if _PENDING_TOKEN in text:
            raise LegalDecisionError(
                f"{path} carries a pending token: a legal draft states its legal_gap in "
                "words and leaves the value absent (the invariant-17 literal is clinical)"
            )


def _node(value: Mapping[str, Any], dotted: str) -> tuple[bool, Any]:
    node: Any = value
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _check_value_status(decision: LegalDecision) -> None:
    for dotted in decision.value_status:
        found, _ = _node(decision.value, dotted)
        if not found:
            raise LegalDecisionError(
                f"{decision.id}: value_status names {dotted!r}, which value lacks"
            )


def _check_snapshot(decision_id: str, source: LegalSource, repo_root: Path) -> None:
    snapshot = source.snapshot
    if not snapshot.startswith(_SNAPSHOT_PREFIX) or ".." in Path(snapshot).parts:
        raise LegalDecisionError(
            f"{decision_id}: snapshot {snapshot!r} must live under {_SNAPSHOT_PREFIX}"
        )
    path = repo_root / snapshot
    if not path.is_file():
        raise LegalDecisionError(f"{decision_id}: snapshot {snapshot!r} is not committed")
    text = path.read_text(encoding="utf-8")
    try:
        header = snapshot_header(text)
        body = snapshot_body(text)
    except LegalDecisionError as exc:
        raise LegalDecisionError(f"{decision_id}: {snapshot!r}: {exc}") from exc
    if header.get("source_id") != source.source_id:
        raise LegalDecisionError(
            f"{decision_id}: snapshot {snapshot!r} declares {header.get('source_id')!r}, "
            f"the source cites {source.source_id!r}"
        )
    if header.get("retrieved_on") != source.retrieved_on.isoformat():
        raise LegalDecisionError(
            f"{decision_id}: snapshot {snapshot!r} was retrieved_on "
            f"{header.get('retrieved_on')!r}, the source says {source.retrieved_on.isoformat()!r}"
        )
    if not quote_in_snapshot(source.quote, body):
        raise LegalDecisionError(
            f"{decision_id}: quote is not verbatim in {snapshot!r}: {source.quote[:80]!r}"
        )


def _check_spec_basis(decision: LegalDecision, repo_root: Path) -> None:
    root = repo_root.resolve()
    for basis in decision.spec_basis:
        path = (root / basis.file).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise LegalDecisionError(f"{decision.id}: spec file {basis.file!r} is not committed")
        if not quote_in_snapshot(basis.quote, path.read_text(encoding="utf-8")):
            raise LegalDecisionError(
                f"{decision.id}: spec quote is not verbatim in {basis.file!r}: {basis.quote[:80]!r}"
            )


def load_decision(path: Path, *, repo_root: Path | None = None) -> LegalDecision:
    """Load, validate and provenance-check one ``LD-NN.yaml``."""
    root = repo_root if repo_root is not None else _REPO_ROOT
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise LegalDecisionError(f"{path.name}: a decision is a mapping")
    _refuse_pending_tokens(raw, path.name)
    try:
        decision = LegalDecision.model_validate(raw)
    except ValidationError as exc:
        raise LegalDecisionError(f"{path.name}: {exc}") from exc
    if path.stem != decision.id:
        raise LegalDecisionError(f"{path.name}: file name and id {decision.id!r} disagree")
    _check_value_status(decision)
    for source in decision.sources:
        _check_snapshot(decision.id, source, root)
    _check_spec_basis(decision, root)
    return decision


def load_register(
    directory: Path = REGISTER_DIR, *, repo_root: Path | None = None
) -> Mapping[str, LegalDecision]:
    """Every decision in the register, keyed by id, read-only."""
    decisions = {
        decision.id: decision
        for decision in (
            load_decision(path, repo_root=repo_root) for path in sorted(directory.glob("LD-*.yaml"))
        )
    }
    if not decisions:
        raise LegalDecisionError(f"{directory}: the register is empty")
    return MappingProxyType(decisions)


# --- the gate a consumer reads through --------------------------------------------------


def draft_paths(decision: LegalDecision) -> tuple[str, ...]:
    """The dotted ``value`` keys marked draft, in declaration order."""
    return tuple(
        key for key, status in decision.value_status.items() if status is ValueStatus.DRAFT
    )


def clearance(decision: LegalDecision, audience: Audience) -> None:
    """Refuse unless ``decision`` may be used for ``audience``.

    A real patient needs a licensed Turkish lawyer's countersign on a
    ``real_patient`` decision (D25) — checked first, so the refusal names the
    missing lawyer whatever else is missing. Synthetic and test use needs an
    ``active`` decision: a draft has no answer and a proposed one has no
    reviewer verdict yet.
    """
    if audience is Audience.REAL_PATIENT:
        countersign = decision.counsel_countersign
        if decision.scope is not Scope.REAL_PATIENT or countersign is None or countersign.missing():
            raise LegalClearanceError(
                f"{decision.id}: no licensed Turkish lawyer has countersigned it, so it does "
                "not reach a real patient (D25)"
            )
    if decision.status is not DecisionStatus.ACTIVE:
        raise LegalClearanceError(
            f"{decision.id} is {decision.status.value}: only an active decision, verified by "
            "the legal reviewer, may be used"
        )


def value_for(decision: LegalDecision, key: str, audience: Audience) -> Any:
    """One value, after :func:`clearance`. A draft key — or a key above or
    below one — is absent, never defaulted."""
    clearance(decision, audience)
    for drafted in draft_paths(decision):
        if drafted == key or drafted.startswith(f"{key}.") or key.startswith(f"{drafted}."):
            raise LegalClearanceError(f"{decision.id}: {key!r} is draft ({drafted!r}): no answer")
    found, node = _node(decision.value, key)
    if not found:
        raise LegalClearanceError(f"{decision.id}: {key!r} has no value")
    return node
