"""Department-dynamic previsit routing: department string → branch → pack (INT-323).

An inbound visit (from the Acıbadem/MHRS connector, or any inbound source)
carries a free-text ``department`` string. To make the previsit
department-dynamic it must be MAPPED onto the branch taxonomy
(:mod:`protocols.taxonomy`, ``packages/protocols/taxonomy/branches.yaml``,
files/09 §1) and then resolved to the SERVED pack per CLAUDE.md invariant 13.

This module is the DURABLE backend layer. The mobile app's ``packForDepartment``
(``apps/mobile/src/lib/intake/questions.ts``) regex-matches a department onto
ten UI fixture packs and silently falls back to ``general``; that fallback is
the failure this module removes. Here an unmapped department is an EXPLICIT
state (:class:`DepartmentMatch.UNMAPPED`) and the live path fails closed —
never a silent wrong specialty pack.

Two steps, cleanly separated so each fails closed on its own:

- **department → branch** (:func:`map_department`). Normalise the department
  with :func:`fold_department` — the exact mirror of the mobile
  ``foldDepartment`` — then match it against a deterministic index of every
  branch's folded ``name_tr`` plus the aliases DERIVED from the committed
  mobile ``PACKS`` regexes (:data:`DEPARTMENT_ALIASES`). The match is EXACT on
  the folded key; there is no substring or fuzzy match, so a partial or
  unknown department resolves to ``UNMAPPED`` rather than into a neighbouring
  specialty (the same discipline invariant 22 states as "``üre`` is never
  substring-matched"). No branch id is ever invented — every value is a
  ``branches.yaml`` branch, checked at index-build time.

- **branch → served pack** (:func:`resolve_department`). Delegates to
  :func:`protocols.taxonomy.resolve_branch`, so invariant 13 holds end to end:
  a branch serves its own L1+ ``specialty.<id>`` pack, else its cluster pack;
  an L0 pack resolved for a live session raises
  (:class:`~protocols.taxonomy.L0PackServedError`); Acil Tıp raises
  (:class:`~protocols.taxonomy.ExcludedBranchError`); nothing servable raises
  (:class:`~protocols.taxonomy.NoServablePackError`) rather than serving bare
  ``base.intake``; and an unmapped department raises
  :class:`DepartmentNotRoutableError` with no pack at all.

The routing MECHANISM is what INT-323 delivers. The served pack CONTENT past
L0 is gated on HB-C1 (clinical sign-off) exactly as INT-042/INT-043 — while
that gate is open every branch resolves to an L0 draft or nothing, so this
layer fails closed by construction rather than inventing pack content.
"""

from __future__ import annotations

import enum
import unicodedata

from clinical_schemas.common import FrozenModel
from pydantic import Field

from protocols.loader import PackRegistry
from protocols.taxonomy import (
    BranchResolution,
    BranchResolutionError,
    Taxonomy,
    TaxonomyError,
    resolve_branch,
)

__all__ = [
    "DEPARTMENT_ALIASES",
    "DepartmentMatch",
    "DepartmentNotRoutableError",
    "DepartmentRouting",
    "department_index",
    "fold_department",
    "map_department",
    "resolve_department",
]


def fold_department(value: str) -> str:
    """Normalise a Turkish department string for matching, mirroring the mobile
    ``foldDepartment`` (``apps/mobile/src/lib/intake/questions.ts``):
    locale-independent lowercase, then strip combining diacritics, then map the
    dotless ``ı`` to ``i``. So "İç Hastalıkları", "iç hastalıkları" and a
    truncated "ic hastaliklari" all land on the same key.

    ``str.lower`` already turns the dotted capital ``İ`` into ``i`` + combining
    dot (stripped below) and the plain capital ``I`` into ``i``; the explicit
    ``ı``/``İ`` replacements catch any residue so the fold never depends on the
    platform's Turkish locale (the mobile comment records that combining-mark
    regexes proved environment-fragile — :func:`unicodedata.combining` is not).
    """
    lowered = value.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace("ı", "i").replace("İ", "i")


class DepartmentNotRoutableError(BranchResolutionError):
    """The inbound department maps to no taxonomy branch (INT-323): the live
    path fails closed here rather than guessing a specialty. A subclass of
    :class:`~protocols.taxonomy.BranchResolutionError`, so a caller already
    catching resolution failures catches this too."""


class DepartmentMatch(enum.StrEnum):
    """How (whether) a department mapped onto the branch taxonomy."""

    EXACT_NAME = "EXACT_NAME"
    ALIAS = "ALIAS"
    UNMAPPED = "UNMAPPED"


class DepartmentRouting(FrozenModel):
    """The department → branch mapping outcome — an explicit UNMAPPED state,
    never a silent fallback (INT-323)."""

    department: str = Field(description="The inbound department string, as received.")
    folded: str = Field(description="Its normalised form (:func:`fold_department`).")
    branch_id: str | None = Field(
        default=None,
        description="The taxonomy branch it maps to; None iff UNMAPPED.",
    )
    match: DepartmentMatch = Field(description="EXACT_NAME | ALIAS | UNMAPPED.")


# Aliases transcribed (already folded) from the committed mobile ``PACKS``
# regexes (``apps/mobile/src/lib/intake/questions.ts``) — the app's own derived
# short forms and synonyms for a department. Every value is a ``branches.yaml``
# branch id (files/09 §1); :func:`department_index` re-checks that against the
# loaded taxonomy at build time, so a stale alias fails closed rather than
# routing to a branch that is not there. No exact ``name_tr`` needs an entry
# here — those are indexed directly from the taxonomy.
DEPARTMENT_ALIASES: dict[str, str] = {
    # /kardiyoloji|ic hastalik|dahiliye/
    "dahiliye": "ic_hastaliklari",
    # /kulak|kbb|burun bogaz/
    "kbb": "kulak_burun_bogaz_hastaliklari",
    "kulak burun bogaz": "kulak_burun_bogaz_hastaliklari",
    # /ortopedi|travmatoloji/
    "ortopedi": "ortopedi_ve_travmatoloji",
    "travmatoloji": "ortopedi_ve_travmatoloji",
    # /cilt|cildiye|dermatoloji/
    "cilt": "deri_ve_zuhrevi_hastaliklari",
    "cildiye": "deri_ve_zuhrevi_hastaliklari",
    "dermatoloji": "deri_ve_zuhrevi_hastaliklari",
    # /gogus|pulmonoloji/
    "gogus": "gogus_hastaliklari",
    "pulmonoloji": "gogus_hastaliklari",
    # /kadin dogum|jinekoloji|kadin hastaliklari/
    "kadin dogum": "kadin_hastaliklari_ve_dogum",
    "jinekoloji": "kadin_hastaliklari_ve_dogum",
    # /uroloji|bevliye/
    "bevliye": "uroloji",
    # /goz/
    "goz": "goz_hastaliklari",
    # /gastro|mide barsak|sindirim/
    "gastro": "gastroenteroloji",
    "mide barsak": "gastroenteroloji",
    "sindirim": "gastroenteroloji",
}


def department_index(taxonomy: Taxonomy) -> dict[str, str]:
    """Build the folded-department → ``branch_id`` index for ``taxonomy``.

    Every branch contributes its folded ``name_tr``; :data:`DEPARTMENT_ALIASES`
    then adds the derived short forms. Two guards keep the map honest and fail
    closed at build time rather than at a live session:

    - two distinct branches whose names fold to the same key raise
      :class:`~protocols.taxonomy.TaxonomyError` (**ambiguous** — a department
      could not be routed deterministically);
    - an alias whose target branch is absent from the taxonomy, or that
      collides with an exact name owned by a different branch, raises too
      (**stale alias**) — an alias may never invent or shadow a branch.
    """
    index: dict[str, str] = {}
    for branch in taxonomy.branches:
        key = fold_department(branch.name_tr)
        existing = index.get(key)
        if existing is not None and existing != branch.id:
            raise TaxonomyError(
                f"ambiguous department name: {branch.name_tr!r} folds to {key!r}, "
                f"already owned by branch {existing!r} — a department must route "
                f"to exactly one branch (INT-323)"
            )
        index[key] = branch.id

    known = {branch.id for branch in taxonomy.branches}
    for alias, branch_id in DEPARTMENT_ALIASES.items():
        if branch_id not in known:
            raise TaxonomyError(
                f"alias {alias!r} maps to unknown branch {branch_id!r} — an alias "
                f"may never route to a branch the taxonomy does not define (INT-323)"
            )
        folded = fold_department(alias)
        existing = index.get(folded)
        if existing is not None and existing != branch_id:
            raise TaxonomyError(
                f"alias {folded!r} → {branch_id!r} collides with exact name owned "
                f"by branch {existing!r} — an alias may not shadow a branch (INT-323)"
            )
        index.setdefault(folded, branch_id)
    return index


def map_department(taxonomy: Taxonomy, department: str) -> DepartmentRouting:
    """Map a free-text ``department`` onto a taxonomy branch (INT-323).

    Exact match on the folded key: a branch's own ``name_tr`` reports
    :attr:`DepartmentMatch.EXACT_NAME`, a derived short form reports
    :attr:`DepartmentMatch.ALIAS`, and anything else — a blank string, a
    partial name, an unknown clinic — reports :attr:`DepartmentMatch.UNMAPPED`
    with ``branch_id`` None. Never raises and never guesses; the fail-closed
    decision is left to :func:`resolve_department`.
    """
    folded = fold_department(department.strip())
    index = department_index(taxonomy)
    branch_id = index.get(folded)
    if branch_id is None:
        return DepartmentRouting(
            department=department,
            folded=folded,
            branch_id=None,
            match=DepartmentMatch.UNMAPPED,
        )
    exact = any(fold_department(branch.name_tr) == folded for branch in taxonomy.branches)
    return DepartmentRouting(
        department=department,
        folded=folded,
        branch_id=branch_id,
        match=DepartmentMatch.EXACT_NAME if exact else DepartmentMatch.ALIAS,
    )


def resolve_department(
    packs: PackRegistry, taxonomy: Taxonomy, department: str
) -> BranchResolution:
    """Resolve a free-text ``department`` to the SERVED pack: department →
    branch → pack (INT-323; CLAUDE.md invariant 13).

    Raises :class:`DepartmentNotRoutableError` when the department maps to no
    branch — an unmapped department never silently runs a specialty pack. A
    mapped department delegates to :func:`protocols.taxonomy.resolve_branch`,
    which raises :class:`~protocols.taxonomy.ExcludedBranchError` (Acil Tıp),
    :class:`~protocols.taxonomy.L0PackServedError` (invariant 13 — the pack
    that would serve is L0) or :class:`~protocols.taxonomy.NoServablePackError`
    (nothing servable; never bare ``base.intake``) as appropriate.
    """
    routing = map_department(taxonomy, department)
    if routing.branch_id is None:
        raise DepartmentNotRoutableError(
            f"department {routing.folded!r} maps to no taxonomy branch — an "
            f"unmapped department fails closed, never a silent specialty pack "
            f"(INT-323; CLAUDE.md invariant 13)"
        )
    return resolve_branch(packs, taxonomy, routing.branch_id)
