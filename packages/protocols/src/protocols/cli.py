"""`protocols` console entry point (INT-042): the `coverage` subcommand.

``protocols coverage`` prints the branch × resolution matrix of
:func:`protocols.taxonomy.coverage` plus a one-line summary — the matrix
files/09 §6 says the admin console consumes, wired behind
``make coverage-matrix``.

Exit-code posture (documented per the INT-042 scope): the command exits
non-zero for MISSING branches only under ``--strict``. Today zero packs
exist, so the matrix is honestly all-MISSING (no-silent-caps) and CI runs
the report unstrict; the CI posture flips to ``--strict`` once the nine
cluster packs land (files/09 §2 rollout, P1).
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import yaml

from protocols.loader import PackRegistry, load_pack
from protocols.taxonomy import BranchResolution, ResolutionStatus, coverage, load_taxonomy
from protocols.types import PackLayer

__all__ = ["load_registry", "main"]

# The Makefile is the only entry point (CLAUDE.md §Commands) and runs from
# the repo root, so the defaults are root-relative; tests pass explicit paths.
DEFAULT_TAXONOMY = Path("packages/protocols/taxonomy/branches.yaml")
DEFAULT_PACKS_ROOT = Path("packages/protocols")


def load_registry(packs_root: Path) -> PackRegistry:
    """Load every chain pack under the files/12 §1 layer directories.

    Non-``pack`` documents (``life_threat_set``, ``ek4_mapping``) live in the
    same tree and belong to the compiler slice — they are passed over here.
    A malformed chain pack still fails loudly via ``load_pack``.
    """
    registry = PackRegistry()
    for layer in PackLayer:
        for path in sorted((packs_root / layer.value).glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("kind") != "pack":
                continue
            registry.add(load_pack(path))
    return registry


def _render(rows: Sequence[BranchResolution], pack_count: int) -> str:
    lines = [f"{'branch':40} {'cluster':20} {'status':9} {'pack':34} name_tr"]
    for row in rows:
        pack = row.pack_id if row.pack_id is not None else "-"
        lines.append(
            f"{row.branch_id:40} {row.cluster:20} {row.status.value:9} {pack:34} {row.name_tr}"
        )
    counts = Counter(row.status for row in rows)
    lines.append(
        f"coverage: {len(rows)} branches -> "
        f"{counts[ResolutionStatus.DIRECT]} DIRECT | "
        f"{counts[ResolutionStatus.CLUSTER]} CLUSTER | "
        f"{counts[ResolutionStatus.MISSING]} MISSING | "
        f"{counts[ResolutionStatus.EXCLUDED]} EXCLUDED"
    )
    if pack_count == 0:
        # No-silent-caps: an empty registry is stated plainly, never dressed
        # up as coverage.
        lines.append(
            "zero packs exist in the pack tree — every non-excluded branch is "
            "honestly MISSING; nothing is served today (files/09 §2 rollout)"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="protocols",
        description="INTAKE protocol registry tools (packages/protocols).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    cov = subparsers.add_parser(
        "coverage",
        help="print the branch x resolution matrix (CLAUDE.md invariant 13)",
        description="Branch x resolution matrix: DIRECT (own L1+ pack), "
        "CLUSTER (cluster pack), MISSING, EXCLUDED (Acil Tıp).",
        epilog="--strict makes MISSING branches fail the run (exit 1). CI "
        "runs unstrict until the nine cluster packs exist (files/09 §2 P1), "
        "then flips to --strict.",
    )
    cov.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    cov.add_argument("--packs", type=Path, default=DEFAULT_PACKS_ROOT)
    cov.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any branch resolves to nothing",
    )
    args = parser.parse_args(argv)
    taxonomy = load_taxonomy(args.taxonomy)
    registry = load_registry(args.packs)
    rows = coverage(registry, taxonomy)
    print(_render(rows, len(registry)))
    missing = sum(1 for row in rows if row.status is ResolutionStatus.MISSING)
    if args.strict and missing:
        print(f"STRICT: {missing} branch(es) resolve to nothing (invariant 13)")
        return 1
    return 0
