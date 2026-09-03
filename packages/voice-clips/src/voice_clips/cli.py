"""`intake-clips` console entry point, behind `make clips VOICE=<voice_id>`.

Its own command rather than `protocols clips`: the protocols package is
I/O-free by construction and two import-boundary tests enforce that, so the
command that dials a TTS and writes to an object store cannot live inside it.
It reads what `protocols compile` wrote and adds nothing to the manifest.

``--voice`` has no default, exactly as ``protocols compile --voice`` has none:
the cache is keyed per voice (files/03 §4.9.1 row 10), and a default would be
one engineer's choice silently applied to every future build.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from protocols.locale_text import DEFAULT_LOCALE

from voice_clips.build import run_clip_build
from voice_clips.cache import clip_cache_from_env
from voice_clips.errors import ClipCacheError
from voice_clips.gateway import tts_gateway_from_env

__all__ = ["DEFAULT_DIST_ROOT", "main"]

#: Where `protocols compile` writes (protocols.compile.bundle.DIST_ROOT). Named
#: here as a path rather than imported so this CLI does not reach into the
#: compiler's module layout for a constant.
DEFAULT_DIST_ROOT = Path("packages/protocols/dist")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intake-clips",
        description="Pre-synthesise the compiled clip manifests for one voice "
        "into the MinIO clip cache (INT-060; files/03 §4.9.1 row 10).",
        epilog="Exactly one of INTAKE_TTS_ENDPOINT (a self-hosted TTS) or "
        "INTAKE_TTS_RECORDED_DIR (recorded responses; the CI and no-GPU dev "
        "path) must be set — neither is guessed. A pack with a missing clip "
        "exits 1.",
    )
    parser.add_argument(
        "--voice",
        required=True,
        help="voice id the clips are keyed for; no default (files/03 §4.9.1)",
    )
    parser.add_argument(
        "--locale",
        default=DEFAULT_LOCALE,
        help="locale the clips are keyed for (default: %(default)s). The cache "
        "keys on (locale, voice) since INT-297: two locales may share a voice, "
        "and a clip found by text and voice alone is then another language's "
        "clip played into this session.",
    )
    parser.add_argument(
        "--pack",
        action="append",
        default=[],
        dest="only_packs",
        help="restrict the build to this pack id; repeatable (default: all)",
    )
    parser.add_argument(
        "--dist",
        type=Path,
        default=DEFAULT_DIST_ROOT,
        help="compiler output root (default: %(default)s)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="report coverage without synthesising anything",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-synthesise clips already in the store (a changed voice model "
        "under a stable voice id is an operator decision, never an inference)",
    )
    args = parser.parse_args(argv)
    try:
        gateway = tts_gateway_from_env()
        cache = clip_cache_from_env()
    except ClipCacheError as exc:
        print(f"clips: {exc}")
        return 1
    return run_clip_build(
        dist_root=args.dist,
        voice=args.voice,
        gateway=gateway,
        cache=cache,
        pack_ids=tuple(args.only_packs),
        verify_only=args.verify_only,
        force=args.force,
        locale=args.locale,
    )
