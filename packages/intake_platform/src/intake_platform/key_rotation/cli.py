"""``python -m intake_platform.key_rotation`` — one tick of the scheduled rotation.

The scheduler calls this (``make key-rotation``; docs/runbooks/key-rotation.md
says what calls it and how often). It reads the OpenBao pointer the way every
service does (:meth:`intake_platform.secrets.SecretsProvider.from_env`, which
fails closed in prod), rotates the tenant KEKs that are due, and prints one
line per key: the Transit key name, what happened, and the countdown. Key
names are identifiers; nothing else is printed (invariant 6).

    exit 0  every key is current or was rotated
    exit 2  a rotation failed or a key's metadata was unreadable: still overdue
    exit 4  refused — no OpenBao, or the key list could not be read
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import httpx

from intake_platform.envelope import TransitKekProvider
from intake_platform.key_rotation.job import RotationAction, run_rotation
from intake_platform.key_rotation.transit import KeyMetadataError, TransitKekInventory
from intake_platform.secrets import SecretsBootError, SecretsProvider

__all__ = ["EXIT_OK", "EXIT_OVERDUE", "EXIT_REFUSED", "main"]

EXIT_OK = 0
EXIT_OVERDUE = 2
EXIT_REFUSED = 4

_PREFIX = "INT-367 key rotation"
_SUMMARY_ORDER = (
    RotationAction.ROTATED,
    RotationAction.CURRENT,
    RotationAction.FAILED,
    RotationAction.UNREADABLE,
)


def _now() -> datetime:
    return datetime.now(UTC)


def main(
    argv: Sequence[str] | None = None,
    *,
    secrets: SecretsProvider | None = None,
    clock: Callable[[], datetime] = _now,
) -> int:
    argparse.ArgumentParser(
        prog="intake-key-rotation",
        description=(
            "INT-367: rotate every tenant KEK in OpenBao Transit whose latest version "
            "is a quarter old (files/10 §3), and report the countdown per key."
        ),
    ).parse_args(argv)

    if secrets is None:
        try:
            secrets = SecretsProvider.from_env()
        except SecretsBootError as err:
            print(f"{_PREFIX}: refused — {err}")
            return EXIT_REFUSED

    try:
        report = run_rotation(
            TransitKekInventory(secrets), TransitKekProvider(secrets), now=clock()
        )
    except (httpx.HTTPError, KeyMetadataError) as err:
        print(f"{_PREFIX}: refused — the Transit key list could not be read ({type(err).__name__})")
        return EXIT_REFUSED

    counts = ", ".join(f"{report.count(action)} {action.value}" for action in _SUMMARY_ORDER)
    print(f"{_PREFIX}: {len(report.outcomes)} envelope KEKs — {counts}")
    for outcome in report.outcomes:
        due = "unknown" if outcome.due_days is None else f"{outcome.due_days:.1f} d"
        version = "" if outcome.key_version is None else f" (v{outcome.key_version})"
        print(f"  {outcome.key_id}  {outcome.action.value}  next due in {due}{version}")
    return EXIT_OK if report.ok else EXIT_OVERDUE
