"""``python -m intake_platform.audit_verifier`` — the operator/cron entry point.

files/10 §3 schedules "daily chain verification"; this is what that schedule
calls. It prints a short verdict and returns an exit code a scheduler can act
on, and it prints **only** counts, ``seq`` positions and hashes — the report it
renders carries no entry content, and the printed form must not widen it
(invariant 6).

    intake-audit-verify --anchor-head <64-hex>          # verify
    intake-audit-verify --anchor-file /run/anchor.head  # same, read from a file
    intake-audit-verify --anchor-head <64-hex> --worm-copy

The anchored head is an **input**, never a default. There is no publisher for
it in this repo and inventing one would defeat the control it implements
(files/10 §2 (b); files/HUMAN_BLOCKERS.md HB-I12). Without it the command
refuses — exit 3 — rather than reporting a chain that merely agrees with
itself.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from intake_platform.audit import AuditStore
from intake_platform.audit_verifier.job import (
    AnchorSource,
    VerifierOutcome,
    WormSink,
    run_daily_verification,
)

__all__ = [
    "EXIT_CHAIN_BROKEN",
    "EXIT_NO_ANCHOR",
    "EXIT_OK",
    "EXIT_REFUSED",
    "main",
]

#: Exit codes. 0 verified against the anchor · 2 the chain does not hold ·
#: 3 no anchor to check against (a refusal, not a pass) · 4 the invocation or
#: the environment is unusable.
EXIT_OK = 0
EXIT_CHAIN_BROKEN = 2
EXIT_NO_ANCHOR = 3
EXIT_REFUSED = 4

DATABASE_URL_ENV = "INTAKE_DATABASE_URL"

_ANCHOR_ASK = (
    "supply the head that was published outside the platform_admin blast radius "
    "with --anchor-head or --anchor-file. Where that head is published is an open "
    "human decision — files/HUMAN_BLOCKERS.md HB-I12 (owner)."
)


class _FixedAnchor:
    """The head the operator supplied, wrapped in the job's protocol."""

    def __init__(self, head: str | None) -> None:
        self._head = head

    def anchored_head(self) -> str | None:
        return self._head


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intake-audit-verify",
        description=("INT-016 daily audit-chain verification against an externally anchored head."),
    )
    parser.add_argument("--anchor-head", default=None, help="the anchored head, 64 lowercase hex")
    parser.add_argument(
        "--anchor-file", type=Path, default=None, help="file holding the anchored head"
    )
    parser.add_argument(
        "--worm-copy",
        action="store_true",
        help="copy the verified bundle into the object-locked audit bucket",
    )
    return parser


def _read_anchor(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Return ``(head, refusal)``. ``(None, None)`` means *no anchor given*,
    which is a refusal at the job level rather than a bad invocation."""
    if args.anchor_head is not None and args.anchor_file is not None:
        return None, "exactly one of --anchor-head and --anchor-file may be given"
    if args.anchor_head is None and args.anchor_file is None:
        return None, None
    if args.anchor_file is not None:
        try:
            raw = args.anchor_file.read_text(encoding="utf-8")
        except OSError as err:
            return None, f"anchor file could not be read: {err.strerror or err.__class__.__name__}"
    else:
        raw = args.anchor_head
    head = raw.strip()
    if len(head) != 64 or any(character not in "0123456789abcdef" for character in head):
        return None, "the anchored head must be 64 lowercase hex characters"
    return head, None


def _store_from_env(env: dict[str, str]) -> tuple[AuditStore | None, str | None]:
    url = env.get(DATABASE_URL_ENV, "").strip()
    if not url:
        return None, (
            f"no audit store: pass one in, or set {DATABASE_URL_ENV} so the verifier can "
            "read the chain (it needs read access only; svc-audit-writer keeps the "
            "single INSERT grant)"
        )
    from sqlalchemy import create_engine

    from intake_platform.db.audit_store import SqlAlchemyAuditStore

    return SqlAlchemyAuditStore(create_engine(url)), None


def _worm_sink_from_env(env: dict[str, str], store: AuditStore) -> WormSink:
    """Build the object-locked sink from the same env contract services/api
    uses. The copy is itself an audited event, so the sink holds a chain
    writer — which is exactly why it is not the verifier's own capability."""
    from minio import Minio

    from intake_platform.audit import AuditChain
    from intake_platform.documents import DocumentStore, as_object_storage

    client = Minio(
        env.get("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=env.get("MINIO_ROOT_USER", "intake-dev"),
        secret_key=env.get("MINIO_ROOT_PASSWORD", "intake-dev-only"),
        secure=env.get("INTAKE_MINIO_SECURE", "") == "true",
    )
    sink = DocumentStore(
        as_object_storage(client),
        env.get("INTAKE_DOCS_BUCKET", "intake-docs"),
        env.get("INTAKE_AUDIT_BUCKET", "intake-audit-worm"),
        AuditChain(store),
    )
    sink.ensure_buckets()
    return sink


def main(
    argv: Sequence[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    store: AuditStore | None = None,
    worm_sink: WormSink | None = None,
) -> int:
    args = _build_parser().parse_args(argv)
    environ = dict(os.environ) if env is None else env

    head, refusal = _read_anchor(args)
    if refusal is not None:
        print(f"INT-016 audit verifier: refused — {refusal}")
        return EXIT_REFUSED

    if store is None:
        store, store_refusal = _store_from_env(environ)
        if store is None:
            print(f"INT-016 audit verifier: refused — {store_refusal}")
            return EXIT_REFUSED

    # ``--worm-copy`` is the only thing that archives. An injected sink says
    # *how* to archive, never *whether* — a flag that a caller's argument can
    # silently override is not a control.
    sink: WormSink | None = None
    if args.worm_copy:
        sink = worm_sink if worm_sink is not None else _worm_sink_from_env(environ, store)

    anchor: AnchorSource = _FixedAnchor(head)
    report = run_daily_verification(store, anchor=anchor, worm_sink=sink)

    print(f"INT-016 audit verifier: {report.outcome.value} — {report.entry_count} entries")
    print(f"  local head   {report.local_head}")
    print(f"  anchor head  {report.anchor_head or '(none supplied)'}")
    if report.first_bad_seq is not None:
        print(f"  broken at seq {report.first_bad_seq}")
    print(f"  {report.reason}")
    if report.worm_key is not None:
        print(f"  WORM copy    {report.worm_key}")

    if report.outcome is VerifierOutcome.INTACT:
        return EXIT_OK
    if report.outcome is VerifierOutcome.CHAIN_BROKEN:
        return EXIT_CHAIN_BROKEN
    print(f"  {_ANCHOR_ASK}")
    return EXIT_NO_ANCHOR
