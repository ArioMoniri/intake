"""INT-488 — the owner's command for the App Review window (owner decision D39).

``python -m intake_api.review_cli status|on|off|rotated|revealed``, run inside
the API container on the synthetic host by ``infra/staging/review_signin.sh``.

- ``on`` refuses unless a reviewer could sign in here (``review_readiness``),
  closes a window whose 14 days ran out the way ``off`` does,
  empties the reviewer tenant (``intake_api.review_reset``), appends
  ``auth.review.window.opened`` and only then opens: an opening the audit
  store could not record does not happen, and nor does one over an earlier
  reviewer's data. A store that cannot be read refuses before any row.
- ``off`` closes first (the safer state), then appends
  ``auth.review.window.closed``, then empties the reviewer tenant; a failure
  of either is reported, and the window stays closed.
- ``status`` prints the window's state and, while it is open, when it closes
  itself and how long is left.
- ``rotated`` and ``revealed`` only append the owner script's row for a new
  code and for its one reveal.

The rows go on the API's own chain; the API adopts them before its next row
(``AuditChain.catch_up``). Nothing here prints a value.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Final, TextIO

import redis

from intake_api.review_signin import review_guards_from_env, review_readiness
from intake_api.review_window import ReviewWindow, ReviewWindowUnreadable
from intake_api.settings import ApiSettings

__all__ = ["main"]

logger = logging.getLogger("intake_api.review_signin")


# --- the owner's command ------------------------------------------------------------------------

#: What each verb appends to the hash-chained audit log.
_AUDIT_ACTIONS: Final = {
    "on": "auth.review.window.opened",
    "off": "auth.review.window.closed",
    "open_failed": "auth.review.window.open_failed",
    "rotated": "auth.review.code.rotated",
    "revealed": "auth.review.code.revealed",
}
_VERBS: Final = ("status", "on", "off", "rotated", "revealed")
_USAGE: Final = "usage: python -m intake_api.review_cli " + "|".join(_VERBS)


def _default_redis() -> redis.Redis:
    return redis.Redis.from_url(ApiSettings.from_env().redis_url)


def _default_audit(action: str) -> None:
    """Append the owner's act to the API's own hash chain. The API adopts the
    row before its next one (``AuditChain.catch_up``)."""
    from intake_platform.audit import AuditChain
    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from sqlalchemy import create_engine

    engine = create_engine(ApiSettings.from_env().audit_db_url)
    try:
        AuditChain(SqlAlchemyAuditStore(engine)).append(
            actor="operator:host",
            action=action,
            resource_ref="review_signin:window",
            consent_scope_ref="scope:auth",
        )
    finally:
        engine.dispose()


def _default_readiness() -> str | None:
    return review_readiness(ApiSettings.from_env(), None, review_guards_from_env(os.environ))


def _default_reset() -> str | None:
    """Empty the reviewer tenant through the platform's erasure. Run with the
    deployment's owner role, the one that provisions the tenant: the role a
    patient's own erasure runs as is INT-394's open decision, and this reset
    touches the reviewer tenant only."""
    import asyncio

    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from intake_platform.retention.executors import DocumentObjectDestroyer
    from sqlalchemy import create_engine

    from intake_api.app import _documents_from_env
    from intake_api.audit import AuditWriter
    from intake_api.db import build_engine
    from intake_api.review_reset import ReviewResetBlocked, reset_review_tenant

    settings = ApiSettings.from_env()
    documents = _documents_from_env()
    destroyer = DocumentObjectDestroyer(
        documents.client, bucket_docs=documents.bucket_docs, bucket_audit=documents.bucket_audit
    )

    async def run() -> int:
        engine = build_engine(settings.bootstrap_db_url)
        audit_engine = create_engine(settings.audit_db_url)
        try:
            return await reset_review_tenant(
                engine,
                audit=AuditWriter(SqlAlchemyAuditStore(audit_engine)),
                remove_object=destroyer,
                now=datetime.now(UTC),
            )
        finally:
            await engine.dispose()
            audit_engine.dispose()

    try:
        asyncio.run(run())
    except ReviewResetBlocked as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 — any failure keeps the window shut
        logger.warning("review tenant reset failed (%s)", type(exc).__name__)
        return f"the reviewer tenant could not be emptied ({type(exc).__name__})"
    return None


def _stamp(instant: float) -> str:
    return datetime.fromtimestamp(instant, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _left(seconds: float) -> str:
    """Whole days, hours and minutes, rounded down: never more time than is left."""
    whole = int(seconds)
    return f"{whole // 86400}d {whole % 86400 // 3600}h {whole % 3600 // 60}m"


def _describe(window: ReviewWindow) -> str:
    try:
        state = window.state()
    except ReviewWindowUnreadable:
        return "review window: unreadable (closed: no reviewer can sign in)"
    if state is None:
        return "review window: closed (no reviewer can sign in)"
    if window.expired(state):
        return (
            f"review window: expired at {_stamp(state.closes_at)} (closed: no reviewer can "
            "sign in; the API records the close and empties the reviewer tenant within a minute)"
        )
    return (
        f"review window: open since {_stamp(state.since)}; closes itself at "
        f"{_stamp(state.closes_at)}, in {_left(window.remaining(state))} "
        "(the App Review reviewer can sign in)"
    )


def _appended(audit: Callable[[str], None], verb: str, out: TextIO, failed: str) -> bool:
    try:
        audit(_AUDIT_ACTIONS[verb])
    except Exception as exc:  # noqa: BLE001 — every failure to append is reported
        logger.warning("review %s not audited: the append failed (%s)", verb, type(exc).__name__)
        print(failed, file=out)
        return False
    return True


def _open(
    window: ReviewWindow,
    audit: Callable[[str], None],
    reset: Callable[[], str | None],
    out: TextIO,
) -> int:
    """Readable, empty, recorded, then open: an opening the audit store could
    not record does not happen, and nor does one over a reviewer's data."""
    try:
        state = window.state()
    except ReviewWindowUnreadable:
        print("review window: unreadable, so it was not opened", file=out)
        return 1
    if state is not None and not window.expired(state):
        return 0
    if state is not None and _close(window, audit, reset, out) != 0:
        # an expired window is closed the way --off closes one before a fresh one opens
        print("review window: the expired window could not be closed cleanly", file=out)
        return 1
    problem = reset()
    if problem is not None:
        print(f"review window not opened: {problem}", file=out)
        return 1
    if not _appended(
        audit, "on", out, "review window: the opening could not be audited, so it stays closed"
    ):
        return 1
    try:
        window.open()
    except redis.RedisError:
        _appended(audit, "open_failed", out, "review window: the failed opening was not audited")
        print("review window: the opening was recorded but failed; it stays closed", file=out)
        return 1
    return 0


def _close(
    window: ReviewWindow,
    audit: Callable[[str], None],
    reset: Callable[[], str | None],
    out: TextIO,
) -> int:
    """Closed first (the safer state), then recorded, then emptied."""
    code = 0
    try:
        closed = window.close()
    except redis.RedisError:
        print("review window: unreadable store; it reads closed, but run --off again", file=out)
        return 1
    if closed and not _appended(
        audit, "off", out, "review window: closed, but the close could not be audited"
    ):
        code = 1
    problem = reset()
    if problem is not None:
        print(
            f"review window: closed, but the reviewer tenant was not emptied: {problem}", file=out
        )
        code = 1
    return code


def main(
    argv: Sequence[str] | None = None,
    *,
    out: TextIO = sys.stdout,
    redis_factory: Callable[[], redis.Redis] = _default_redis,
    audit: Callable[[str], None] = _default_audit,
    readiness: Callable[[], str | None] = _default_readiness,
    reset: Callable[[], str | None] = _default_reset,
    now_fn: Callable[[], float] = time.time,
) -> int:
    """``python -m intake_api.review_cli status|on|off|rotated|revealed``,
    run inside the API container on the synthetic host by
    ``infra/staging/review_signin.sh``. ``rotated`` and ``revealed`` only
    append the script's row; nothing here prints a value."""
    parser = argparse.ArgumentParser(prog="intake_api.review_cli", exit_on_error=False)
    parser.add_argument("verb")
    try:
        verb = parser.parse_args(list(argv) if argv is not None else None).verb
    except (argparse.ArgumentError, SystemExit):
        print(_USAGE, file=out)
        return 2
    if verb not in _VERBS:
        print(_USAGE, file=out)
        return 2
    if verb in ("rotated", "revealed"):
        return 0 if _appended(audit, verb, out, f"review {verb}: not audited") else 1
    window = ReviewWindow(redis_factory(), now_fn)
    code = 0
    if verb == "on":
        problem = readiness()
        if problem is not None:
            print(f"review window not opened: {problem}", file=out)
            return 1
        code = _open(window, audit, reset, out)
    elif verb == "off":
        code = _close(window, audit, reset, out)
    print(_describe(window), file=out)
    return code


if __name__ == "__main__":
    sys.exit(main())
