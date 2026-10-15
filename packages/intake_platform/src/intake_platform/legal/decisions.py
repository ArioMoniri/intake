"""The legal decisions register (INT-471, owner decision D25).

files/00_STATE.md §3 D25: open legal questions are routed first to a sourced
legal-author agent and verified by a separate legal-reviewer agent, **for
synthetic and test use only**. A licensed Turkish lawyer countersigns before
any real patient. CLAUDE.md's stop-and-ask items and owner-named HB rows
still go to the owner, with the lane's output as a recommendation.
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
  Resmî Gazete date and number, an authority's guidance from the same hosts
  with its edition, or a standard from its publisher with its version — and
  its ``quote`` appears **verbatim** in a committed snapshot
  whose header declares the same ``source_id`` and ``retrieved_on``
  (Unicode NFC and runs of whitespace are the only normalisation);
- no answer without a source: ``proposed`` and ``active`` need at least one
  source; every source and spec sentence names the ``value`` path it
  ``supports`` and that path exists; every answered leaf of ``value`` is
  supported by one of them; ``draft`` carries a ``legal_gap`` sentence saying
  what is missing and which source would settle it, and so does any key
  ``value_status`` marks ``draft``; a leaf that says "not decided" is draft;
- a recommendation to the owner settles nothing until the owner answers it:
  the ``decision`` beside an ``owner_recommendation`` stays draft until an
  ``owner_answer`` names its files/00_STATE.md §3 row and a spec sentence
  quotes the reply verbatim from that row;
- the snapshot agrees with the citation: same ``source_id``, ``url``,
  ``retrieved_on`` and Resmî Gazete date and number (or standard version),
  and a quote of at least four words;
- no pending token anywhere: the invariant-17 literal is the clinical
  lane's sole exception, and this lane does not widen it — a draft states
  its gap in words and its value is absent;
- no active decision without an independent reviewer: ``active`` needs an
  ``agree`` verdict, or ``agree_with_changes`` with the applied changes in
  ``verifier.notes``, from a role that is not the author's; a decision the
  reviewer agreed with is not left ``proposed``;
- no real patient without a lawyer: ``real_patient`` scope needs an active
  decision and every field of a licensed Turkish lawyer's countersign, the
  six-field block that mirrors the physician's ``clinical_signoff``
  (HUMAN_BLOCKERS HB-C1) — a full 40-hex commit, a date no earlier than the
  reviewer's verdict, and an evidence file that is committed.

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
_MIN_QUOTE_WORDS = 4
_QUESTION_TARGET = "question"
_WILDCARD = "*"
_OPEN_MARKER = "not decided"
_RECOMMENDATION = "owner_recommendation"
_ANSWER = "owner_answer"
_DECIDED = "decision"
_OWNER_RECORD = "files/00_STATE.md"


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
    """An official text, quoted against a committed snapshot.

    ``legislation`` is a gazetted instrument; ``guidance`` is an authority's own
    published guidance (a Kurul guide) — the same official hosts, an edition in
    place of a Resmî Gazete number, and never binding on its own; ``standard`` is
    a standard a Turkish rule incorporates, from its publisher."""

    kind: Literal["legislation", "guidance", "standard"] = Field(description="Source kind.")
    source_id: str = Field(pattern=_SOURCE_ID, description="Stable id the snapshot declares.")
    instrument: str = Field(min_length=1, description="Name and number of the instrument.")
    provision: str = Field(min_length=1, description="Article, paragraph or criterion cited.")
    url: str = Field(pattern=r"^https://", description="Official place it was retrieved.")
    gazette: Gazette | None = Field(default=None, description="Resmî Gazete date and number.")
    version_or_date: str | None = Field(default=None, description="Version of a standard.")
    retrieved_on: date = Field(description="Retrieval date; the snapshot declares the same.")
    quote: str = Field(min_length=1, description="Verbatim supporting quote, four words or more.")
    snapshot: str = Field(description="Committed snapshot path under legal_decisions/sources/.")
    supports: str = Field(
        min_length=1, description="The dotted value path it supports ('*' matches one key)."
    )
    caveat: str | None = Field(default=None, description="Limits on how far it reaches.")
    note: str | None = Field(default=None, description="Provenance commentary.")

    @model_validator(mode="after")
    def _an_official_text(self) -> LegalSource:
        hosts = STANDARD_HOSTS if self.kind == "standard" else OFFICIAL_LEGISLATION_HOSTS
        if not _host_in(self.url, hosts):
            raise ValueError(
                f"{self.source_id}: {self.url} is not an official publisher's host "
                f"({', '.join(hosts)})"
            )
        if self.kind == "legislation" and self.gazette is None:
            raise ValueError(
                f"{self.source_id}: legislation names its Resmî Gazete date and number"
            )
        if self.kind != "legislation" and not (
            self.version_or_date and self.version_or_date.strip()
        ):
            raise ValueError(f"{self.source_id}: a {self.kind} names its version_or_date")
        if len(self.quote.split()) < _MIN_QUOTE_WORDS:
            raise ValueError(
                f"{self.source_id}: a quote of fewer than four words proves nothing: {self.quote!r}"
            )
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


class OwnerAnswer(FrozenModel):
    """The owner's answer to this lane's recommendation on a stop-and-ask item
    (D25). It sits beside the ``owner_recommendation`` it answers, and the
    reply is quoted verbatim from its files/00_STATE.md §3 row."""

    owner_decision: str = Field(pattern=r"^D\d+$", description="The files/00_STATE.md §3 row.")
    outcome: Literal["accepted", "rejected"] = Field(description="What the owner did with it.")
    quote: str = Field(min_length=1, description="The owner's reply, verbatim.")
    answered_on: date = Field(description="The day the owner answered.")
    channel: str = Field(min_length=1, description="How the reply reached this lane.")
    reading: str = Field(min_length=1, description="How the reply is read here.")


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _same_role(left: str, right: str) -> bool:
    return " ".join(left.lower().split()) == " ".join(right.lower().split())


class CounselCountersign(FrozenModel):
    """A licensed Turkish lawyer's countersign. Every field is nullable so an
    unsigned block still parses; the refusal is the decision's, where it can
    say which field is missing."""

    lawyer_name: str | None = Field(default=None, description="The countersigning lawyer.")
    bar_association: str | None = Field(default=None, description="Baro the lawyer is in.")
    bar_registration_no: str | None = Field(default=None, description="Baro sicil numarası.")
    signed_commit: str | None = Field(
        default=None, description="The full 40-hex commit the signature binds to."
    )
    signed_on: date | None = Field(default=None, description="Countersign date.")
    evidence: str | None = Field(default=None, description="Where the countersign is recorded.")

    @model_validator(mode="after")
    def _recorded_in_evidence(self) -> CounselCountersign:
        if not _blank(self.evidence) and not str(self.evidence).startswith(_EVIDENCE_PREFIX):
            raise ValueError(
                f"a countersign is recorded under {_EVIDENCE_PREFIX}, not {self.evidence!r}"
            )
        commit = self.signed_commit
        if not _blank(commit) and not re.fullmatch(r"[0-9a-f]{40}", str(commit)):
            raise ValueError(f"a countersign binds a full 40-hex commit, not {commit!r}")
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
        if (
            self.status is DecisionStatus.ACTIVE
            and verdict is VerifierVerdict.AGREE_WITH_CHANGES
            and _blank(self.verifier.notes)
        ):
            raise ValueError(
                f"{self.id}: agree_with_changes makes a decision active only once the changes "
                "are applied and recorded in verifier.notes"
            )
        role = self.verifier.role
        if role is not None and _same_role(role, self.author_role):
            raise ValueError(
                f"{self.id}: the reviewer must be independent of the author, not {role!r}"
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
            verified_on = self.verifier.verified_on
            signed_on = countersign.signed_on
            if signed_on is not None and verified_on is not None and signed_on < verified_on:
                raise ValueError(
                    f"{self.id}: the countersign is dated before the reviewer's verdict "
                    f"({signed_on} < {verified_on})"
                )
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


def _leaves(node: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every (dotted path, value) whose value is not a non-empty mapping."""
    for key, child in node.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(child, Mapping) and child:
            yield from _leaves(child, path)
        else:
            yield path, child


def _names(pattern: str, path: str) -> bool:
    """Whether ``pattern`` names ``path`` or a key above it ('*' matches one key)."""
    wanted = pattern.split(".")
    parts = path.split(".")
    if len(wanted) > len(parts):
        return False
    return all(want in (_WILDCARD, part) for want, part in zip(wanted, parts, strict=False))


def _check_supports(decision: LegalDecision) -> None:
    """Every source and spec sentence supports a value that exists, and every
    answered leaf is supported by one of them. An open answer is draft."""
    leaves = list(_leaves(decision.value))
    targets = [
        (f"source {s.source_id} ({s.provision})", s.supports, False) for s in decision.sources
    ]
    targets += [(f"spec_basis {b.file}", b.supports, True) for b in decision.spec_basis]
    for label, pattern, may_name_question in targets:
        if may_name_question and pattern == _QUESTION_TARGET:
            continue
        if all(part == _WILDCARD for part in pattern.split(".")):
            raise LegalDecisionError(
                f"{decision.id}: {label} supports the bare wildcard {pattern!r}; name the value"
            )
        if not any(_names(pattern, path) for path, _ in leaves):
            raise LegalDecisionError(
                f"{decision.id}: {label} supports {pattern!r}, which resolves to nothing in value"
            )
    drafted = draft_paths(decision)
    patterns = [pattern for _, pattern, _ in targets]
    for path, leaf in leaves:
        if any(path == key or path.startswith(f"{key}.") for key in drafted):
            continue
        if isinstance(leaf, str) and _OPEN_MARKER in leaf.lower():
            raise LegalDecisionError(
                f"{decision.id}: {path!r} says it is not decided but is not marked draft; "
                "an open answer is draft and absent"
            )
        if not any(_names(pattern, path) for pattern in patterns):
            raise LegalDecisionError(
                f"{decision.id}: {path!r} has no source: name it in a source's or a spec "
                "sentence's supports, or mark it draft"
            )


def _recommendations(node: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every mapping of ``value`` that carries an owner_recommendation, with the
    dotted prefix its sibling keys take (empty at the top, else ending in '.')."""
    if _RECOMMENDATION in node:
        yield prefix, node
    for key, child in node.items():
        if isinstance(child, Mapping):
            yield from _recommendations(child, f"{prefix}{key}.")


def _check_owner_answers(decision: LegalDecision) -> None:
    """A recommendation to the owner settles nothing until the owner answers
    it: until then the ``decision`` beside it is draft; once answered, the
    answer names its files/00_STATE.md row, quotes the reply from it, and the
    ``decision`` holds the answer."""
    drafted = draft_paths(decision)
    for prefix, node in _recommendations(decision.value):
        decided = f"{prefix}{_DECIDED}"
        if _DECIDED not in node:
            raise LegalDecisionError(
                f"{decision.id}: {prefix}{_RECOMMENDATION} has no {_DECIDED!r} beside it "
                "to hold the owner's answer"
            )
        raw = node.get(_ANSWER)
        if raw is None:
            if decided not in drafted:
                raise LegalDecisionError(
                    f"{decision.id}: the owner has not answered {prefix}{_RECOMMENDATION}, so "
                    f"{decided!r} is draft: an unanswered recommendation stays a recommendation"
                )
            continue
        try:
            answer = OwnerAnswer.model_validate(raw)
        except ValidationError as exc:
            raise LegalDecisionError(f"{decision.id}: {prefix}{_ANSWER}: {exc}") from exc
        if decided in drafted:
            raise LegalDecisionError(
                f"{decision.id}: the owner answered ({answer.owner_decision}), so {decided!r} "
                "holds the answer and is not draft"
            )
        row = re.compile(rf"\b{answer.owner_decision}\b")
        if not any(
            basis.file == _OWNER_RECORD
            and row.search(basis.section)
            and _normalise(answer.quote) in _normalise(basis.quote)
            and _names(basis.supports, f"{prefix}{_ANSWER}.quote")
            for basis in decision.spec_basis
        ):
            raise LegalDecisionError(
                f"{decision.id}: the owner's reply is quoted verbatim from its {_OWNER_RECORD} "
                f"row {answer.owner_decision} in a spec sentence supporting {prefix}{_ANSWER}"
            )


def _gazette_in(header: Mapping[str, str]) -> tuple[date, int] | None:
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4}) sayı (\d+)\b", header.get("gazette", ""))
    if match is None:
        return None
    day, month, year, number = (int(group) for group in match.groups())
    return date(year, month, day), number


def _check_header(decision_id: str, source: LegalSource, header: Mapping[str, str]) -> None:
    snapshot = source.snapshot
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
    if header.get("url") != source.url:
        raise LegalDecisionError(
            f"{decision_id}: snapshot {snapshot!r} was taken from url {header.get('url')!r}, "
            f"the source cites {source.url!r}"
        )
    if source.gazette is not None:
        cited = (source.gazette.published_on, source.gazette.number)
        if _gazette_in(header) != cited:
            raise LegalDecisionError(
                f"{decision_id}: snapshot {snapshot!r} declares gazette "
                f"{header.get('gazette')!r}, the source cites {cited[0]} sayı {cited[1]}"
            )
    if source.kind != "legislation" and header.get("version_or_date") != source.version_or_date:
        raise LegalDecisionError(
            f"{decision_id}: snapshot {snapshot!r} declares version_or_date "
            f"{header.get('version_or_date')!r}, the source cites {source.version_or_date!r}"
        )


def _check_countersign_evidence(decision: LegalDecision, repo_root: Path) -> None:
    countersign = decision.counsel_countersign
    if countersign is None or _blank(countersign.evidence):
        return
    record = str(countersign.evidence).split("#", 1)[0]
    root = repo_root.resolve()
    path = (root / record).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise LegalDecisionError(
            f"{decision.id}: the countersign's evidence file {record!r} is not committed"
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
    _check_header(decision_id, source, header)
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
    _check_supports(decision)
    _check_owner_answers(decision)
    for source in decision.sources:
        _check_snapshot(decision.id, source, root)
    _check_spec_basis(decision, root)
    _check_countersign_evidence(decision, root)
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
