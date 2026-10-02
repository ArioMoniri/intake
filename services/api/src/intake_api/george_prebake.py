"""Pre-bake and probe the George clip cache (INT-443).

Run inside the api container, where the route's own wiring is built from the
process environment, so the bake fills exactly the cache the route reads:

    python -m intake_api.george_prebake plan                  # count, dial nothing
    python -m intake_api.george_prebake apply --max-characters N
    python -m intake_api.george_prebake probe                 # one question clip

``make clips`` is the INT-060 path into the MinIO clip cache, keyed by the
compiled manifests' clip ids. It cannot serve here: no pack compiles on today's
tree (HB-C1), and the route reads its own on-disk cache keyed by
``delivery.<context>@v<version>`` and ``clip_text_hash``. This bakes that cache
from the same catalogue the route admits.

- **Catalogue only, never RED.** Every row of the route's catalogue is baked in
  its pinned context; a RED row is skipped (pre-positioned on the device,
  never fetched — invariant 21).
- **A spend is a decision.** ``plan`` dials nothing. ``apply`` refuses unless
  ``--max-characters`` covers what the misses would send; the vendor bills by
  character. A cache hit sends nothing.
- **Ids only** (invariant 6): counts, lanes and refusal classes, never a text.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Final, TextIO

from voice_clips.delivery import delivery_profile
from voice_clips.gateway import TtsError

from intake_api.dev_voice import GeorgeWiring, george_wiring_from_env
from intake_api.dev_voice_guard import CatalogueRow

__all__ = ["PROBE_SUBJECT_TEXT_INDEX", "main"]

#: ``probe`` speaks the first catalogue row: deterministic, and a question.
PROBE_SUBJECT_TEXT_INDEX: Final = 0


def _bakeable(wiring: GeorgeWiring) -> list[CatalogueRow]:
    return [row for row in wiring.catalogue.rows if row.delivery_context != "red"]


def _misses(wiring: GeorgeWiring, rows: list[CatalogueRow]) -> list[CatalogueRow]:
    return [
        row
        for row in rows
        if not wiring.cache.has(row.text_tr, delivery_profile(row.delivery_context))
    ]


def _plan(wiring: GeorgeWiring, out: TextIO) -> tuple[list[CatalogueRow], int]:
    rows = _bakeable(wiring)
    misses = _misses(wiring, rows)
    characters = sum(len(row.text_tr) for row in misses)
    skipped = len(wiring.catalogue.rows) - len(rows)
    print(
        f"prebake: {len(rows)} rows ({skipped} red skipped), {len(rows) - len(misses)} cached, "
        f"{len(misses)} to synthesise, {characters} characters",
        file=out,
    )
    return misses, characters


def _apply(wiring: GeorgeWiring, max_characters: int, out: TextIO, err: TextIO) -> int:
    misses, characters = _plan(wiring, out)
    if characters > max_characters:
        print(
            f"prebake: refused — {characters} characters exceed --max-characters {max_characters}",
            file=err,
        )
        return 3
    lanes: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    for row in misses:
        try:
            served = wiring.cache.ensure(row.text_tr, delivery_profile(row.delivery_context))
        except TtsError as error:
            failures[getattr(error, "code", type(error).__name__)] += 1
            continue
        lanes[served.lane] += 1
    summary = ", ".join(f"{lane}={n}" for lane, n in sorted(lanes.items())) or "none"
    print(f"prebake: synthesised by lane: {summary}", file=out)
    if failures:
        failed = ", ".join(f"{code}={n}" for code, n in sorted(failures.items()))
        print(f"prebake: failed: {failed}", file=err)
        return 1
    return 0


def _probe(wiring: GeorgeWiring, out: TextIO, err: TextIO) -> int:
    rows = _bakeable(wiring)
    if not rows:
        print("clip: the catalogue is empty", file=err)
        return 1
    row = rows[PROBE_SUBJECT_TEXT_INDEX]
    try:
        served = wiring.cache.ensure(row.text_tr, delivery_profile(row.delivery_context))
    except TtsError as error:
        print(f"clip: FAIL {getattr(error, 'code', type(error).__name__)}", file=err)
        return 1
    cache = "hit" if served.hit else "miss"
    print(
        f"clip: lane={served.lane} cache={cache} profile={row.delivery_context} "
        f"bytes={len(served.wav)}",
        file=out,
    )
    return 0


def main(
    argv: Sequence[str],
    *,
    wiring_factory: Callable[[], GeorgeWiring | None] = george_wiring_from_env,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(prog="intake_api.george_prebake", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    apply = sub.add_parser("apply")
    apply.add_argument("--max-characters", type=int, required=True)
    sub.add_parser("probe")
    args = parser.parse_args(argv)
    wiring = wiring_factory()
    if wiring is None:
        # the route would answer 503 too: no lane, no catalogue or no row
        print("clip: the George lane is unconfigured on this host", file=stderr)
        return 2
    if args.command == "plan":
        _plan(wiring, stdout)
        return 0
    if args.command == "apply":
        return _apply(wiring, args.max_characters, stdout, stderr)
    return _probe(wiring, stdout, stderr)


def _wiring_from_env() -> GeorgeWiring | None:
    # imported here: the CLI builds the same wiring the API process builds,
    # with the OpenBao key store, and nothing else imports SecretsProvider
    from intake_platform.secrets import SecretsProvider

    from intake_api.settings import DEFAULT_REDIS_URL, ENV_REDIS_URL

    return george_wiring_from_env(
        os.environ.get(ENV_REDIS_URL) or DEFAULT_REDIS_URL, kv=SecretsProvider.from_env
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], wiring_factory=_wiring_from_env))
