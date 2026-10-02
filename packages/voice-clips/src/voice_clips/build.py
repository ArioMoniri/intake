"""Walk a compiled manifest, synthesise what is missing, report the coverage.

The acceptance in one paragraph: *all scripted text pre-synthesised per voice
at compile keyed sha256(text_tr,voice_id); mock TTS in CI; coverage report per
pack.* The order of operations here is the part worth reading twice.

**Every string is checked before any string is synthesised.** The numeral gate
runs over the whole manifest first, so a pack carrying an unexpanded dose is
refused before the model is dialled even once — not after the first eleven
clips have already been written. A numeral that reaches a TTS is a silent
mispronounced dose (files/03 §4.9.6), and "we caught it on row twelve" is not
a defence when rows one to eleven are already in the bucket.

**A clip already in the bucket is not re-synthesised.** The key is a content
hash, so a stored object under that key *is* the clip for that text: rebuilding
it would burn GPU time to produce a byte-different encoding of identical audio.
``force`` exists for the case where the voice model itself changed under a
stable voice id, which is an operator decision rather than an inference.

**Coverage is reported per pack, and a hole fails the build.** files/03 §4.9.4:
"on failure at compile time the build fails, which is the correct place for a
TTS failure to happen."

**Every row is spoken in its delivery profile** (INT-415): a rule's action
script under ``red``, an instrument item under ``instrument``, a slot question
under ``routine`` — read from the row's subject, never from a caller. The
profile's id and version are in the object key, so a retuned profile is a miss
and re-synthesises instead of replaying the old tuning.

**Every lookup and every synthesis is counted** (INT-351): a stored clip is a
cache hit, a synthesis is a miss that paid a gateway — the two
:mod:`voice_clips.metrics` families the admin console's clip-cache tile reads.
``force`` asks the cache nothing, so it counts no lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from protocols.locale_text import DEFAULT_LOCALE

from voice_clips.audio import EncodedClip, encode_clip
from voice_clips.cache import (
    ClipCache,
    CompiledClipManifest,
    clip_object_key,
    discover_packs,
    load_clip_manifest,
)
from voice_clips.delivery import delivery_profile
from voice_clips.errors import ClipCacheError
from voice_clips.gateway import TtsGateway, assert_speakable_tr
from voice_clips.metrics import (
    gateway_kind,
    record_coverage,
    record_lookup,
    record_synthesis,
    write_clip_metrics_from_env,
)

__all__ = [
    "ClipBuildResult",
    "ClipCoverage",
    "ClipCoverageError",
    "assert_clip_coverage",
    "build_clip_cache",
    "clip_coverage",
    "render_coverage",
    "run_clip_build",
]

_MISSING: Final = "MISSING"


class ClipCoverageError(ClipCacheError):
    """A served pack has scripted text with no clip behind it."""


@dataclass(frozen=True)
class ClipBuildResult:
    """One manifest row after the builder dealt with it."""

    clip_id: str
    key: str
    subject: str
    scripted: bool
    synthesised: bool
    clip: EncodedClip | None


@dataclass(frozen=True)
class ClipCoverage:
    """What the object store actually holds for one pack, locale and voice."""

    pack_id: str
    voice: str
    locale: str
    total: int
    present: int
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing


def build_clip_cache(
    *,
    manifest: CompiledClipManifest,
    gateway: TtsGateway,
    cache: ClipCache,
    force: bool = False,
) -> tuple[ClipBuildResult, ...]:
    """Synthesise and store every clip the manifest describes."""
    for row in manifest.entries:
        assert_speakable_tr(row.text_tr)
    cache.ensure_bucket()
    kind = gateway_kind(gateway)
    results: list[ClipBuildResult] = []
    for row in manifest.entries:
        profile = delivery_profile(row.delivery_context)
        key = clip_object_key(row.entry, profile=profile)
        hit = False if force else cache.has(key)
        if not force:
            record_lookup(hit=hit)
        if hit:
            results.append(
                ClipBuildResult(
                    clip_id=row.entry.clip_id,
                    key=key,
                    subject=row.subject,
                    scripted=row.scripted,
                    synthesised=False,
                    clip=None,
                )
            )
            continue
        try:
            speech = gateway.synthesise(
                text_tr=row.text_tr, voice_id=manifest.voice, profile=profile
            )
        except Exception:
            record_synthesis(gateway=kind, ok=False)
            raise
        record_synthesis(gateway=kind, ok=True)
        clip = encode_clip(speech)
        cache.put(key, clip.data)
        results.append(
            ClipBuildResult(
                clip_id=row.entry.clip_id,
                key=key,
                subject=row.subject,
                scripted=row.scripted,
                synthesised=True,
                clip=clip,
            )
        )
    return tuple(results)


def clip_coverage(manifest: CompiledClipManifest, cache: ClipCache) -> ClipCoverage:
    """Ask the store, row by row, whether the clip is there — and publish it."""
    missing = tuple(
        row.entry.clip_id
        for row in manifest.entries
        if not cache.has(clip_object_key(row.entry, profile=delivery_profile(row.delivery_context)))
    )
    record_coverage(
        pack=manifest.pack_id,
        locale=manifest.locale,
        voice=manifest.voice,
        rows=len(manifest.entries),
        present=len(manifest.entries) - len(missing),
    )
    return ClipCoverage(
        pack_id=manifest.pack_id,
        voice=manifest.voice,
        locale=manifest.locale,
        total=len(manifest.entries),
        present=len(manifest.entries) - len(missing),
        missing=missing,
    )


def assert_clip_coverage(coverage: ClipCoverage) -> None:
    """Refuse an incomplete pack: a missing clip is a silent dynamic-TTS turn."""
    if coverage.complete:
        return
    raise ClipCoverageError(
        f"pack {coverage.pack_id} locale {coverage.locale} voice {coverage.voice}: "
        f"{len(coverage.missing)} of {coverage.total} scripted strings have no clip "
        f"({', '.join(coverage.missing)})"
    )


def render_coverage(coverage: ClipCoverage) -> str:
    """The per-pack coverage report the acceptance asks for."""
    head = (
        f"clips {coverage.pack_id} locale={coverage.locale} voice={coverage.voice}: "
        f"{coverage.present}/{coverage.total} present"
    )
    if coverage.complete:
        return f"{head} — complete"
    lines = [f"{head} — {len(coverage.missing)} {_MISSING}"]
    lines += [f"  {_MISSING} {clip_id}" for clip_id in coverage.missing]
    return "\n".join(lines)


def run_clip_build(
    *,
    dist_root: Path,
    voice: str,
    gateway: TtsGateway,
    cache: ClipCache,
    pack_ids: tuple[str, ...] = (),
    verify_only: bool = False,
    force: bool = False,
    locale: str = DEFAULT_LOCALE,
) -> int:
    """Build (or verify) every compiled pack for one (locale, voice). Exit-code shaped."""
    found = discover_packs(dist_root, voice, locale)
    wanted = tuple(pack for pack in found if not pack_ids or pack in pack_ids)
    if not wanted:
        print(
            f"clips: no compiled clip manifest for locale {locale!r} voice {voice!r} "
            f"under {dist_root} "
            "— nothing to build, which is a refusal rather than a success"
        )
        return 1
    failed = False
    for pack_id in wanted:
        try:
            manifest = load_clip_manifest(dist_root, pack_id=pack_id, voice=voice, locale=locale)
            if not verify_only:
                built = build_clip_cache(
                    manifest=manifest, gateway=gateway, cache=cache, force=force
                )
                synthesised = sum(1 for result in built if result.synthesised)
                print(
                    f"clips {pack_id}: {synthesised} synthesised, {len(built) - synthesised} reused"
                )
            coverage = clip_coverage(manifest, cache)
        except ClipCacheError as exc:
            print(f"clips: {pack_id}: {exc}")
            failed = True
            continue
        print(render_coverage(coverage))
        failed = failed or not coverage.complete
    written = write_clip_metrics_from_env()
    if written is not None:
        print(f"clips: lookup and synthesis counts written to {written}")
    return 1 if failed else 0
