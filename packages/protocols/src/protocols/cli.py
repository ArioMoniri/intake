"""`protocols` console entry point: `coverage`, `generate-l0`, `compile`.

``protocols coverage`` prints the branch × resolution matrix of
:func:`protocols.taxonomy.coverage` plus a one-line summary — the matrix
files/09 §6 says the admin console consumes, wired behind
``make coverage-matrix``.

Exit-code posture (documented per the INT-042 scope): the command exits
non-zero for MISSING branches only under ``--strict``. Today only L0 drafts
exist, which never count as coverage, so the matrix is honestly all-MISSING
(no-silent-caps) and CI runs the report unstrict; the CI posture flips to
``--strict`` once the nine cluster packs land (files/09 §2 rollout, P1).

``protocols generate-l0 --branch <id>`` (or ``--all``) scaffolds the
review-queue-only L0 drafts via :mod:`protocols.authoring` — deterministic,
refusing excluded branches and never overwriting a pack promoted past L0.

``protocols compile --pack <id> --voice <voice_id>`` emits the five files/03
§6 artefacts into ``packages/protocols/dist`` (INT-041). It writes nothing
unless every gate passes, and prints every refusal rather than the first —
today the real pack tree is all L0, so on that tree it refuses, which is the
honest state and not a failure of the command.

``--voice`` has no default on purpose: the clip cache is keyed by
``sha256(text_tr, voice_id, locale)`` (files/03 §4.9.1 row 10 plus INT-297's
locale), and a default voice
id would be a value chosen once by an engineer for every future build.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import yaml

from protocols.addressing import Addressing
from protocols.authoring import AuthoringError, generate_all, generate_l0
from protocols.bindings import OPT_PATH, OptError, load_opt
from protocols.compile import (
    DIST_ROOT,
    CompileError,
    LifeThreatSetError,
    compile_bundle,
    load_life_threat_set,
    write_bundle,
)
from protocols.data_register import DATA_REGISTER_PATH, DataRegisterError, load_data_register
from protocols.loader import PackRegistry, PackSchemaError, load_pack
from protocols.locale_text import DEFAULT_LOCALE
from protocols.taxonomy import (
    BranchResolution,
    BranchResolutionError,
    ResolutionStatus,
    Taxonomy,
    coverage,
    load_taxonomy,
)
from protocols.types import PackLayer

__all__ = ["REVIEW_QUEUE_DIRNAME", "ReviewQueueRootError", "load_registry", "main"]

# The Makefile is the only entry point (CLAUDE.md §Commands) and runs from
# the repo root, so the defaults are root-relative; tests pass explicit paths.
DEFAULT_TAXONOMY = Path("packages/protocols/taxonomy/branches.yaml")
DEFAULT_PACKS_ROOT = Path("packages/protocols")

# packages/protocols/review/ mirrors the layer layout and holds candidates
# awaiting the physician of record's sign-off (HB-C1). They carry the served
# drafts' own ids, so it must never be read as a packs root (INT-353).
REVIEW_QUEUE_DIRNAME = "review"


class ReviewQueueRootError(PackSchemaError):
    """The review queue was passed where the served pack tree belongs."""


def load_registry(packs_root: Path) -> PackRegistry:
    """Load every chain pack under the files/12 §1 layer directories.

    Non-``pack`` documents (``life_threat_set``, ``ek4_mapping``) live in the
    same tree and belong to the compiler slice — they are passed over here.
    A malformed chain pack still fails loudly via ``load_pack``. The review
    queue is refused as a root; it is never a layer, so the default root
    never reads it either. A layer directory or pack file that resolves into
    the queue (``review/<layer>/<pack>.yaml``, e.g. ``cluster/`` linked to
    ``review/cluster``) is refused too (CLAUDE.md invariant 13; HB-C1).
    """
    if packs_root.resolve().name == REVIEW_QUEUE_DIRNAME:
        raise ReviewQueueRootError(
            f"{packs_root}: the review queue holds unsigned candidates and is "
            "never a served pack tree (invariant 13; promotion needs HB-C1)"
        )
    registry = PackRegistry()
    for layer in PackLayer:
        for path in sorted((packs_root / layer.value).glob("*.yaml")):
            if path.resolve().parent.parent.name == REVIEW_QUEUE_DIRNAME:
                raise ReviewQueueRootError(
                    f"{path}: resolves into the review queue; a candidate is "
                    "never served (invariant 13; promotion needs HB-C1)"
                )
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
    gen = subparsers.add_parser(
        "generate-l0",
        help="scaffold review-queue-only L0 drafts (files/09 §2; INT-057)",
        description="Deterministic L0 scaffolds from the branch taxonomy + "
        "cluster template. L0 is never served (CLAUDE.md invariant 13); a "
        "pack promoted past L0 is never overwritten.",
    )
    gen.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    gen.add_argument("--packs", type=Path, default=DEFAULT_PACKS_ROOT)
    which = gen.add_mutually_exclusive_group(required=True)
    which.add_argument("--branch", help="branch id from taxonomy/branches.yaml")
    which.add_argument(
        "--all",
        action="store_true",
        help="every intake branch (files/09 §2: P0 generates L0 for all)",
    )
    com = subparsers.add_parser(
        "compile",
        help="emit the files/03 §6 artefacts for one pack (INT-041)",
        description="Resolve a pack over its chain and overlays, then emit the "
        "FHIR R4 Questionnaire, openEHR bindings, Pydantic and TS slot types and "
        "the clip manifest. Deterministic: two runs are byte-identical.",
        epilog="Writes nothing unless every gate passes; prints every refusal. "
        "The clinical sign-off interlock (HB-C1) and the L0 no-serve rule "
        "(invariant 13) mean the real pack tree refuses today, by design.",
    )
    com.add_argument("--pack", required=True, help="pack id to compile")
    com.add_argument("--packs", type=Path, default=DEFAULT_PACKS_ROOT)
    com.add_argument(
        "--life-threat",
        type=Path,
        default=DEFAULT_PACKS_ROOT / "base" / "life_threat.yaml",
        help="the kind: life_threat_set document (files/12 §1)",
    )
    com.add_argument("--opt", type=Path, default=OPT_PATH, help="the pinned .opt")
    com.add_argument(
        "--data-register",
        type=Path,
        default=DATA_REGISTER_PATH,
        help="the per-category data register (INT-349); a slot whose category row "
        "is incomplete is refused",
    )
    com.add_argument(
        "--locale",
        default=DEFAULT_LOCALE,
        help="locale the bundle speaks (default: %(default)s). The clip manifest "
        "keys on (locale, voice), so the artefact is clips.<locale>.<voice>.json "
        "(INT-297); a locale the pack cannot speak in every scripted field is "
        "refused rather than served with the gaps in Turkish.",
    )
    com.add_argument(
        "--voice",
        required=True,
        help="voice id the clip manifest is keyed for; no default (files/03 §4.9.1)",
    )
    com.add_argument(
        "--overlay",
        action="append",
        default=[],
        dest="overlays",
        help="overlay pack id to apply; repeatable",
    )
    com.add_argument(
        "--addressing",
        choices=[member.value for member in Addressing],
        default=Addressing.SELF.value,
        help="the session the bundle speaks to (ADR-040; default: %(default)s). The "
        "proxy bundle is refused while any self-addressed slot of the chain has no "
        "proxy handling, and is written under <out>/<pack>/proxy/.",
    )
    com.add_argument("--out", type=Path, default=DIST_ROOT)
    args = parser.parse_args(argv)
    if args.command == "compile":
        return _compile_command(args)
    taxonomy = load_taxonomy(args.taxonomy)
    if args.command == "generate-l0":
        return _generate_l0_command(args, taxonomy)
    registry = load_registry(args.packs)
    rows = coverage(registry, taxonomy)
    print(_render(rows, len(registry)))
    missing = sum(1 for row in rows if row.status is ResolutionStatus.MISSING)
    if args.strict and missing:
        print(f"STRICT: {missing} branch(es) resolve to nothing (invariant 13)")
        return 1
    return 0


def _compile_command(args: argparse.Namespace) -> int:
    """Compile one pack, or print every reason the compiler refused."""
    try:
        life_threat = load_life_threat_set(args.life_threat)
        template = load_opt(args.opt)
        registry = load_registry(args.packs)
        data_register = load_data_register(args.data_register)
    except (LifeThreatSetError, OptError, PackSchemaError, DataRegisterError) as exc:
        print(f"compile: {exc}")
        return 1
    try:
        bundle = compile_bundle(
            pack_id=args.pack,
            registry=registry,
            life_threat=life_threat,
            template=template,
            voice=args.voice,
            locale=args.locale,
            overlays=tuple(args.overlays),
            data_register=data_register,
            addressing=Addressing(args.addressing),
        )
    except CompileError as exc:
        print(f"compile: refused to emit {args.pack} ({len(exc.refusals)} reasons)")
        for refusal in exc.refusals:
            print(f"  {refusal.code.value} {refusal.subject}: {refusal.message}")
        return 1
    for path in write_bundle(bundle, args.out):
        print(path)
    print(f"resolved_protocol_hash: {bundle.resolved_protocol_hash}")
    return 0


def _generate_l0_command(args: argparse.Namespace, taxonomy: Taxonomy) -> int:
    try:
        if args.all:
            paths = generate_all(taxonomy, args.packs)
        else:
            paths = (generate_l0(taxonomy, args.branch, args.packs),)
    except (AuthoringError, BranchResolutionError) as exc:
        print(f"generate-l0: {exc}")
        return 1
    for path in paths:
        print(path)
    return 0
