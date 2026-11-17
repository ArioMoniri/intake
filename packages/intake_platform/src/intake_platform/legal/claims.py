"""Invariant 20 — the performance-claim text gate, in one place (INT-224).

CLAUDE.md invariant 20: *"No sensitivity, specificity, AUROC, WER or accuracy
figure appears in docs/regulatory/, docs/legal/, patient or clinician copy,
marketing or a store listing. … A CI text gate scans the regulatory and legal
trees for performance-claim patterns."*

Before this module the vocabulary lived in two test files with two private
copies — INT-020's over ``docs/security`` and INT-240's satisfaction figures
over ``docs/legal`` and ``docs/regulatory``. A store listing is exactly the
artefact invariant 20 names last, so it has to fall *inside* that gate rather
than beside it, and a third private copy would have made the gate a habit
instead of a rule. Both callers now read their patterns from here, and
tests/legal/test_store_labels.py asserts neither has grown a copy back.

Three named groups, because they are not interchangeable:

``performance``
    The metrics invariant 20 lists by name, plus the Turkish words for them.
    Safe on every prose tree we own. Since INT-536 it also carries the CI
    shell gate's strict-tier expressions verbatim (``CI_*``), so a text the
    CI gate would fail cannot pass at render time.
``satisfaction``
    INT-240's rule that an NPS or CSAT figure is a claim too.
``bare_percentage``
    INT-020's heuristic: in a security document a bare percentage has no
    innocent reading. It is **not** applied to ``docs/legal``, and that is a
    deliberate, recorded scope decision rather than an oversight — the
    accessibility statement legitimately quotes "200 %" text scaling, which is
    a WCAG requirement, not a claim about the product. Widening the heuristic
    to that tree would require exempting conformance text, which is a worse
    trade than naming the metrics.

Trees are declared in :data:`SCANNED_TREES`. A declared tree that does not
exist yet scans clean — ``docs/regulatory`` is named by the invariant and has
no files today, and the gate should already be waiting for it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

__all__ = [
    "CI_ALWAYS_PAT",
    "CI_FIG",
    "CI_NEAR",
    "CI_TERM_EN",
    "CI_TERM_TR",
    "PATTERN_GROUPS",
    "SCANNED_TREES",
    "TEXT_SUFFIXES",
    "ClaimHit",
    "ClaimPattern",
    "ScannedTree",
    "scan_declared_trees",
    "scan_file",
    "scan_text",
    "scan_tree",
]


@dataclass(frozen=True)
class ClaimPattern:
    """One named pattern and the reason it is a claim."""

    name: str
    regex: re.Pattern[str]
    why: str


@dataclass(frozen=True, order=True)
class ClaimHit:
    path: str
    line_no: int
    pattern: str
    line: str


#: INT-536 (INT-529 F3): the CI shell gate's own strict-tier expressions
#: (``scripts/ci/claims_scan.sh``), verbatim. The render-time scanner used to
#: carry only its own Turkish arm, ``\bdoğruluk``, so the softened form in
#: "doğruluğu yüzde 99" passed at render time while CI caught it.
#: tests/legal/test_claims_ci_parity.py holds each string equal to its shell
#: variable, and holds every line the shell flags as flagged here too.
CI_ALWAYS_PAT: Final[str] = r"auroc|(^|[^a-zA-Z])auc([^a-zA-Z]|$)|f1[ _-]?score"
CI_TERM_EN: Final[str] = r"sensitivit|specificit|accurac|(^|[^a-zA-Z])wer([^a-zA-Z]|$)"
CI_TERM_TR: Final[str] = (
    r"([Dd]oğrulu(k|ğ)|[Dd]uyarlıl(ı|i)(k|ğ)|(Ö|ö)zgüllü(k|ğ)|[Kk]esinli(k|ğ)|(İ|i)sabet)"
)
CI_FIG: Final[str] = r"(%[ ]*[0-9]|[0-9][ ]*%|yüzde[ ]*[0-9]|[0-9]+[.,][0-9]+)"
CI_NEAR: Final[str] = ".{0,40}"

_PERFORMANCE: Final[tuple[ClaimPattern, ...]] = (
    ClaimPattern("sensitivity", re.compile(r"(?i)\bsensitivit"), "invariant 20 names it"),
    ClaimPattern("specificity", re.compile(r"(?i)\bspecificit"), "invariant 20 names it"),
    ClaimPattern("auroc", re.compile(r"(?i)\bAUROC\b"), "invariant 20 names it"),
    ClaimPattern("auc", re.compile(r"(?i)\bAUC\b"), "the same figure under a shorter name"),
    ClaimPattern("wer", re.compile(r"(?i)\bWER\b"), "invariant 20 names it"),
    ClaimPattern("cer", re.compile(r"(?i)\bCER\b"), "WER's character-level sibling"),
    ClaimPattern("mos", re.compile(r"(?i)\bMOS\b"), "the TTS quality figure of files/00 §1"),
    ClaimPattern("accuracy", re.compile(r"(?i)\baccurac"), "invariant 20 names it"),
    ClaimPattern("f1", re.compile(r"(?i)\bF1[- ]score\b"), "a performance figure by another name"),
    ClaimPattern(
        "accuracy_tr",
        re.compile(r"(?i)\bdoğruluk|\bdogruluk"),
        "the Turkish word — the listing that matters most is Turkish",
    ),
    ClaimPattern(
        "sensitivity_tr",
        re.compile(r"(?i)\bduyarlılık|\bduyarlilik|\bözgüllük|\bozgulluk"),
        "duyarlılık / özgüllük are sensitivity and specificity",
    ),
    # The CI gate's strict tier, so nothing it flags renders (INT-536). grep
    # runs the first two with -i and the Turkish arm case-sensitively.
    ClaimPattern(
        "ci_always",
        re.compile(CI_ALWAYS_PAT, re.IGNORECASE),
        "claims_scan.sh ALWAYS_PAT: no non-performance reading in any tree",
    ),
    ClaimPattern(
        "ci_term_en",
        re.compile(CI_TERM_EN, re.IGNORECASE),
        "claims_scan.sh TERM_EN, bare as at the strict tier",
    ),
    ClaimPattern(
        "ci_claim_tr",
        re.compile(f"{CI_TERM_TR}{CI_NEAR}{CI_FIG}|{CI_FIG}{CI_NEAR}{CI_TERM_TR}"),
        "claims_scan.sh TR_CLAIM: a Turkish performance word, softened forms included "
        "(doğruluğu, duyarlılığı, özgüllüğü, kesinliği), beside a figure",
    ),
)

_SATISFACTION: Final[tuple[ClaimPattern, ...]] = (
    ClaimPattern(
        "nps_csat_figure",
        re.compile(r"(?i)\b(?:NPS|CSAT)\b[^.\n]{0,20}?\b\d+(?:[.,]\d+)?"),
        "INT-240: a satisfaction figure claimed as a property of the product",
    ),
    ClaimPattern(
        "satisfaction_figure",
        re.compile(r"(?i)[%\d][\d.,]*\s*(?:memnuniyet|satisfaction)"),
        "INT-240: the same claim in Turkish or with the number first",
    ),
)

_BARE_PERCENTAGE: Final[tuple[ClaimPattern, ...]] = (
    ClaimPattern(
        "bare_percentage",
        re.compile(r"\d\s*%"),
        "INT-020: a bare percentage in a security document has no innocent reading",
    ),
)

PATTERN_GROUPS: Final[Mapping[str, tuple[ClaimPattern, ...]]] = MappingProxyType(
    {
        "performance": _PERFORMANCE,
        "satisfaction": _SATISFACTION,
        "bare_percentage": _BARE_PERCENTAGE,
    }
)


@dataclass(frozen=True)
class ScannedTree:
    """A tree the gate walks, and the groups that apply to it."""

    path: str
    groups: tuple[str, ...]
    why: str


SCANNED_TREES: Final[tuple[ScannedTree, ...]] = (
    ScannedTree(
        "docs/security",
        ("performance", "satisfaction", "bare_percentage"),
        "INT-020's original scope, unchanged",
    ),
    ScannedTree(
        "docs/legal",
        ("performance", "satisfaction"),
        "invariant 20 names the legal tree; the store listing artefacts live under "
        "docs/legal/store so they are inside this scan by construction",
    ),
    ScannedTree(
        "docs/regulatory",
        ("performance", "satisfaction", "bare_percentage"),
        "invariant 20 names the regulatory tree; it has no files yet and the gate "
        "is already waiting for it",
    ),
)

#: Only prose-shaped files are read. A binary asset is not copy.
TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".yaml", ".yml", ".txt", ".json"})


def _patterns(groups: Sequence[str]) -> tuple[ClaimPattern, ...]:
    out: list[ClaimPattern] = []
    for group in groups:
        if group not in PATTERN_GROUPS:
            raise KeyError(f"unknown claim-pattern group {group!r}")
        out.extend(PATTERN_GROUPS[group])
    return tuple(out)


def scan_text(text: str, *, groups: Sequence[str], path: str = "<text>") -> tuple[ClaimHit, ...]:
    """Every hit in ``text``, line by line, in file order."""
    patterns = _patterns(groups)
    hits: list[ClaimHit] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            if pattern.regex.search(line):
                hits.append(ClaimHit(path, line_no, pattern.name, line.strip()))
    return tuple(hits)


def scan_file(
    path: Path, groups: Sequence[str], *, relative_to: Path | None = None
) -> tuple[ClaimHit, ...]:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return ()
    label = str(path.relative_to(relative_to)) if relative_to else str(path)
    return scan_text(path.read_text(encoding="utf-8", errors="ignore"), groups=groups, path=label)


def scan_tree(
    root: Path, groups: Sequence[str], *, relative_to: Path | None = None
) -> tuple[ClaimHit, ...]:
    """Walk one tree. A tree that does not exist yet scans clean — the gate is
    declared before the tree, not after it."""
    if not root.is_dir():
        return ()
    hits: list[ClaimHit] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hits.extend(scan_file(path, groups, relative_to=relative_to))
    return tuple(hits)


def scan_declared_trees(repo: Path) -> tuple[ClaimHit, ...]:
    """The gate itself: every tree in :data:`SCANNED_TREES` under ``repo``."""
    hits: list[ClaimHit] = []
    for tree in SCANNED_TREES:
        hits.extend(scan_tree(repo / tree.path, tree.groups, relative_to=repo))
    return tuple(hits)
