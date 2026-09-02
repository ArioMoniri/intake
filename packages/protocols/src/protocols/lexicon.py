"""Turkish lexicons for the ``linguistic`` observer lane (INT-112).

files/03 §4.7.5 gives the lane *"deterministic Turkish lexicons (negative
affect, hopelessness, anhedonia, somatic worry)"* plus a crisis family whose
hits *"bypass the lane"*. This module is the mechanism for all five and the
vocabulary for none of them.

**Why it lives in ``packages/protocols``.** A lexicon is clinical content. A
list of Turkish words asserted to mean hopelessness decides what counts as a
signal, in which dialect, at which reading level — and, for the crisis family,
who gets caught. That is a clinical judgement in exactly the way a threshold
is, so it belongs where the compiler, the CODEOWNER review and the
``draft_needs_source`` discipline already live, not next to the lane that
consumes it.

**Three refusals, mirroring files/04 §8.1 rule 3 exactly:**

- a ``draft_needs_source`` family carries no terms and must state its gap — a
  draft that could carry terms would be a way to ship unsigned vocabulary;
- an ``active`` family must carry a :class:`~protocols.dsl.SourceBlock` and at
  least one term;
- :func:`compile_lexicon` builds a matcher for the ``active`` families only,
  and records the refusal for every other. A family that did not compile has
  **no key at all** in a match result — ``0`` would read as *measured, none
  found*, which is not what an unsigned family means. This is INT-110's
  "a refused lane is absent, not idle", one layer in.

**Matching is by whole token, never by substring** (CLAUDE.md invariant 22:
*"``üre`` is never substring-matched"*), and folds case the Turkish way, where
``I`` lowercases to ``ı`` and ``İ`` to ``i`` — ``str.casefold`` gets both
wrong and would silently make ``IŞIK`` and ``İŞİK`` the same word.

**The marker families and the crisis family are reachable through different
methods.** :meth:`CompiledLexicon.match_markers` and
:meth:`CompiledLexicon.match_crisis` are separate, so a consumer whose
declared type has only the first cannot read a crisis hit — which is how the
lane is kept structurally unable to put one into ``ObserverState``.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal

import yaml
from clinical_schemas.common import FrozenModel
from pydantic import Field, StringConstraints, ValidationError, model_validator

from protocols.dsl import SourceBlock, TrText
from protocols.types import RuleStatus

__all__ = [
    "CompiledLexicon",
    "FamilyKind",
    "LexiconDocument",
    "LexiconFamily",
    "LexiconSchemaError",
    "compile_lexicon",
    "load_lexicon",
    "turkish_fold",
]

FamilyId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]

#: The two Turkish letters ``str.casefold`` gets wrong. ``"I".casefold()`` is
#: ``"i"`` and ``"İ".casefold()`` is ``"i"`` plus a combining dot, so folding a
#: Turkish string through the default rules merges ``ışık`` with ``işik``.
_TURKISH_UPPER = str.maketrans({"I": "ı", "İ": "i"})

#: Tokens are runs of letters, marks and digits; everything else is a boundary.
#: So a term matches a whole token run or not at all, and ``üreme`` can never
#: satisfy ``üre`` (CLAUDE.md invariant 22).
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class LexiconSchemaError(ValueError):
    """A lexicon file the schema rejects, or that is not readable YAML.

    One error type at the boundary, exactly as
    :class:`~protocols.loader.PackSchemaError` is for packs.
    """


class FamilyKind(enum.StrEnum):
    """What a family's hits are *for*, which decides where they may go.

    ``marker`` families land in ``ObserverState.linguistic_markers`` through
    the lane. ``crisis`` hits do not: files/03 §4.7.5 says they *"bypass the
    lane"* and reach the deterministic triage detector, regardless of
    wellbeing consent (files/04 §4.2 defect 3). The two are separate members
    because they have separate destinations, and a destination chosen at
    runtime would be a place a crisis hit could take a wrong turn.
    """

    MARKER = "marker"
    CRISIS = "crisis"


def turkish_fold(value: str) -> str:
    """Casefold ``value`` under Turkish rules (``I`` → ``ı``, ``İ`` → ``i``)."""
    return value.translate(_TURKISH_UPPER).casefold()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(turkish_fold(text)))


class LexiconFamily(FrozenModel):
    """One family: an id, a kind, its status, and — when signed — its terms."""

    id: FamilyId = Field(description="Family id, e.g. ``hopelessness`` (files/03 §4.7.5).")
    kind: FamilyKind = Field(description="Where this family's hits are allowed to go.")
    status: RuleStatus = Field(
        description="``active`` families carry a source block and terms; "
        "``draft_needs_source`` families carry a gap and no terms "
        "(files/04 §8.1 rule 3; CLAUDE.md invariant 17)."
    )
    terms: tuple[TrText, ...] = Field(
        default=(),
        description="The Turkish surface forms this family matches, whole-token. "
        "Empty on every family shipped today (HUMAN_BLOCKERS HB-C16, HB-C17).",
    )
    source: SourceBlock | None = Field(
        default=None, description="Provenance, required on an active family (files/12 §2.5)."
    )
    source_gap: str | None = Field(
        default=None,
        description="What is missing, required on a draft family (files/04 §8.1 rule 3).",
    )

    @model_validator(mode="after")
    def _status_binds_terms_and_provenance(self) -> LexiconFamily:
        if self.status is RuleStatus.DRAFT_NEEDS_SOURCE:
            if self.terms:
                raise ValueError(
                    f"{self.id}: a draft_needs_source family carries no terms — a draft "
                    "that could carry vocabulary would be a way to ship unsigned "
                    "clinical content (files/04 §8.1 rule 3)"
                )
            if not (self.source_gap or "").strip():
                raise ValueError(
                    f"{self.id}: a draft_needs_source family states its source_gap — what "
                    "is missing and whose it is (files/04 §8.1 rule 3)"
                )
            if self.source is not None:
                raise ValueError(
                    f"{self.id}: a draft_needs_source family has no source block; if it "
                    "has one it is not a draft"
                )
            return self
        if not self.terms:
            raise ValueError(f"{self.id}: an active family matches at least one term")
        if self.source is None:
            raise ValueError(
                f"{self.id}: an active family carries a source block against a committed "
                "snapshot (files/12 §2.5; CLAUDE.md clinical content rules)"
            )
        if self.source_gap is not None:
            raise ValueError(f"{self.id}: an active family has no source_gap to state")
        return self


class LexiconDocument(FrozenModel):
    """One ``kind: lexicon`` file. Turkish only — invariant 5 makes the ``tr``
    key the source of truth, and there is no English lexicon to drift from."""

    kind: Literal["lexicon"] = Field(description="Document kind; only lexicons load here.")
    language: Literal["tr"] = Field(description="files/12 §1 pins tr; invariant 5.")
    version: int = Field(ge=1, description="Lexicon version, bumped on every content change.")
    families: tuple[LexiconFamily, ...] = Field(
        min_length=1, description="The families of files/03 §4.7.5."
    )

    @model_validator(mode="after")
    def _ids_are_unique(self) -> LexiconDocument:
        seen: set[str] = set()
        for family in self.families:
            if family.id in seen:
                raise ValueError(f"duplicate family id {family.id!r}")
            seen.add(family.id)
        return self


class _Matcher:
    """One family's compiled terms: token sequences, longest first.

    Longest first so that a term which is a prefix of another cannot mask it;
    matching still advances by one token, because two overlapping disclosures
    are two disclosures.
    """

    __slots__ = ("_terms",)

    def __init__(self, terms: Sequence[str]) -> None:
        compiled = sorted({_tokens(term) for term in terms}, key=len, reverse=True)
        self._terms = tuple(term for term in compiled if term)

    def count(self, tokens: Sequence[str]) -> int:
        hits = 0
        for term in self._terms:
            width = len(term)
            for start in range(0, len(tokens) - width + 1):
                if tuple(tokens[start : start + width]) == term:
                    hits += 1
        return hits


class CompiledLexicon:
    """The servable half of a lexicon: the ``active`` families, and nothing else.

    Frozen by construction — every accessor returns a value rebuilt from
    private state, and there is no setter, so a caller cannot widen the
    vocabulary of a lexicon a CODEOWNER signed.
    """

    __slots__ = ("_crisis", "_marker", "_refused")

    _marker: dict[str, _Matcher]
    _crisis: dict[str, _Matcher]
    _refused: dict[str, str]

    def __init__(
        self,
        *,
        marker: Mapping[str, _Matcher],
        crisis: Mapping[str, _Matcher],
        refused: Mapping[str, str],
    ) -> None:
        object.__setattr__(self, "_marker", dict(marker))
        object.__setattr__(self, "_crisis", dict(crisis))
        object.__setattr__(self, "_refused", dict(refused))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(
            "a compiled lexicon is a value: widening a signed vocabulary in place would "
            "put unreviewed clinical content into a served matcher"
        )

    @property
    def marker_families(self) -> tuple[str, ...]:
        """The compiled ``marker`` family ids, in a stable order."""
        return tuple(sorted(self._marker))

    @property
    def crisis_families(self) -> tuple[str, ...]:
        """The compiled ``crisis`` family ids, in a stable order."""
        return tuple(sorted(self._crisis))

    @property
    def refused(self) -> Mapping[str, str]:
        """Family id → why it did not compile. Visible, so an unsigned family
        is an absence somebody can see rather than a silent zero."""
        return dict(self._refused)

    def match_markers(self, text: str) -> Mapping[str, int]:
        """Hits per compiled ``marker`` family. A family with no hit and a
        family that did not compile are both **absent**, never ``0``."""
        return self._match(self._marker, text)

    def match_crisis(self, text: str) -> Mapping[str, int]:
        """Hits per compiled ``crisis`` family — the surface a marker-typed
        consumer does not have."""
        return self._match(self._crisis, text)

    @staticmethod
    def _match(families: Mapping[str, _Matcher], text: str) -> Mapping[str, int]:
        tokens = _tokens(text)
        if not tokens:
            return {}
        hits = {name: families[name].count(tokens) for name in sorted(families)}
        return {name: count for name, count in hits.items() if count}


def compile_lexicon(document: LexiconDocument) -> CompiledLexicon:
    """Compile the ``active`` families; record a refusal for every other one."""
    marker: dict[str, _Matcher] = {}
    crisis: dict[str, _Matcher] = {}
    refused: dict[str, str] = {}
    for family in document.families:
        if family.status is not RuleStatus.ACTIVE:
            refused[family.id] = (
                f"{family.id} is {family.status.value} and is not compiled into a served "
                f"matcher (files/04 §8.1 rule 3; CLAUDE.md invariant 17): {family.source_gap}"
            )
            continue
        target = marker if family.kind is FamilyKind.MARKER else crisis
        target[family.id] = _Matcher(family.terms)
    return CompiledLexicon(marker=marker, crisis=crisis, refused=refused)


def load_lexicon(path: Path) -> LexiconDocument:
    """Load and schema-validate one lexicon YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LexiconSchemaError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise LexiconSchemaError(f"{path}: a lexicon document must be a YAML mapping")
    try:
        return LexiconDocument.model_validate(raw)
    except ValidationError as exc:
        raise LexiconSchemaError(f"{path}: {exc}") from exc
