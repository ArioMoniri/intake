"""What the scripted-clip cache reused and what it paid to synthesise (INT-351).

The offline clip build (ADR-028; ``make clips``) is the one place the clip
cache is consulted and the one place a clip-gen gateway is called: a manifest
row whose clip is already stored is a **hit** and costs nothing; a **miss** is
a synthesis. Two families carry that, both catalogued in
``observability/metrics_catalog.yaml`` (invariant 13):

- ``voice_clip_cache_lookups_total{outcome}`` — ``hit`` / ``miss``;
- ``voice_clip_syntheses_total{gateway,outcome}`` — which gateway *kind* was
  asked (``self_hosted`` / ``recorded`` / ``elevenlabs`` / ``other``) and
  whether it answered (``ok`` / ``failed``).

And the manifest side, per compiled pack, locale and voice — what the manifest
declares and how much of it the cache holds, from the same coverage walk the
build already fails on (``voice_clip_manifest_rows`` /
``voice_clip_manifest_present``). A gap is a scripted turn that would fall to
dynamic TTS.

Every label is a closed set or an id. The script text and its hash never
become a label (invariant 6) — a clip id is an id, but one series per clip is
a cardinality nobody asked for and a map of the protocol nobody needs.

**A batch job is not a scraped service.** The build runs and exits, so its
counters live on their own registry — never the process-wide default one a
long-lived service serves — and are written as a Prometheus *textfile* when
``INTAKE_CLIPS_METRICS_TEXTFILE`` names one. The ops collector
(``intake_probes.ops_collector``) re-exports exactly these families from that
file, which is how the admin console's clip-cache tile reads them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from prometheus_client import CollectorRegistry, Counter, Gauge, write_to_textfile
from prometheus_client.metrics_core import Metric
from prometheus_client.registry import Collector

__all__ = [
    "CLIP_CACHE_LOOKUPS_TOTAL",
    "CLIP_MANIFEST_PRESENT",
    "CLIP_MANIFEST_ROWS",
    "CLIP_METRICS",
    "CLIP_SYNTHESES_TOTAL",
    "ENV_CLIPS_METRICS_TEXTFILE",
    "GATEWAY_KINDS",
    "gateway_kind",
    "record_coverage",
    "record_lookup",
    "record_synthesis",
    "reset_clip_metrics",
    "write_clip_metrics",
    "write_clip_metrics_from_env",
]

#: Where the build writes its textfile. Unset means nothing is written: a
#: build nobody asked to measure leaves no file behind to be mistaken for one.
ENV_CLIPS_METRICS_TEXTFILE: Final = "INTAKE_CLIPS_METRICS_TEXTFILE"

#: The closed gateway vocabulary. ``other`` is a wrapper or a test double —
#: named rather than guessed, so a series never claims a vendor it did not call.
GATEWAY_KINDS: Final = ("self_hosted", "recorded", "elevenlabs", "other")

CLIP_METRICS = CollectorRegistry(auto_describe=True)

CLIP_CACHE_LOOKUPS_TOTAL = Counter(
    "voice_clip_cache_lookups_total",
    "Scripted-clip cache lookups during a clip build, by outcome (hit = reused, "
    "miss = synthesised).",
    ["outcome"],
    registry=CLIP_METRICS,
)

CLIP_SYNTHESES_TOTAL = Counter(
    "voice_clip_syntheses_total",
    "Scripted-clip syntheses during a clip build, by gateway kind and outcome.",
    ["gateway", "outcome"],
    registry=CLIP_METRICS,
)

CLIP_MANIFEST_ROWS = Gauge(
    "voice_clip_manifest_rows",
    "Scripted-clip rows a compiled manifest declares, per pack, locale and voice.",
    ["pack", "locale", "voice"],
    registry=CLIP_METRICS,
)

CLIP_MANIFEST_PRESENT = Gauge(
    "voice_clip_manifest_present",
    "Manifest rows whose clip is in the cache, per pack, locale and voice.",
    ["pack", "locale", "voice"],
    registry=CLIP_METRICS,
)


def gateway_kind(gateway: object) -> str:
    """The closed-set kind of a TTS gateway, by its concrete class.

    Imported lazily so this module stays importable on its own (the ops
    collector reads only the family names from here).
    """
    from voice_clips.gateway import ElevenLabsClipGenGateway, HttpTtsGateway, RecordedTtsGateway

    if isinstance(gateway, HttpTtsGateway):
        return "self_hosted"
    if isinstance(gateway, RecordedTtsGateway):
        return "recorded"
    if isinstance(gateway, ElevenLabsClipGenGateway):
        return "elevenlabs"
    return "other"


def record_lookup(*, hit: bool) -> None:
    CLIP_CACHE_LOOKUPS_TOTAL.labels(outcome="hit" if hit else "miss").inc()


def record_synthesis(*, gateway: str, ok: bool) -> None:
    if gateway not in GATEWAY_KINDS:
        raise ValueError(f"gateway kind {gateway!r} is not one of {GATEWAY_KINDS}")
    CLIP_SYNTHESES_TOTAL.labels(gateway=gateway, outcome="ok" if ok else "failed").inc()


def record_coverage(*, pack: str, locale: str, voice: str, rows: int, present: int) -> None:
    labels = {"pack": pack, "locale": locale, "voice": voice}
    CLIP_MANIFEST_ROWS.labels(**labels).set(rows)
    CLIP_MANIFEST_PRESENT.labels(**labels).set(present)


def reset_clip_metrics() -> None:
    """Drop every child, so one build's counts never carry into the next."""
    for family in (
        CLIP_CACHE_LOOKUPS_TOTAL,
        CLIP_SYNTHESES_TOTAL,
        CLIP_MANIFEST_ROWS,
        CLIP_MANIFEST_PRESENT,
    ):
        family.clear()


class _TotalsOnly(Collector):
    """The clip families, counters reduced to their ``_total`` samples.

    prometheus_client adds a ``*_created`` timestamp sample to every counter
    child; in a textfile it parses back as another, uncatalogued family. The
    process-wide switch that disables it would change every other registry in
    a process that merely imports this package, so the filter is local.
    """

    def collect(self) -> list[Metric]:
        families: list[Metric] = []
        for family in CLIP_METRICS.collect():
            kept = Metric(family.name, family.documentation, family.type, family.unit)
            kept.samples = [
                s for s in family.samples if family.type != "counter" or s.name.endswith("_total")
            ]
            families.append(kept)
        return families


def write_clip_metrics(path: Path) -> None:
    """Write the clip families as a Prometheus textfile (atomic rename)."""
    registry = CollectorRegistry(auto_describe=False)
    registry.register(_TotalsOnly())
    write_to_textfile(str(path), registry)


def write_clip_metrics_from_env() -> Path | None:
    """Write the textfile when the environment names one; return where."""
    raw = os.environ.get(ENV_CLIPS_METRICS_TEXTFILE, "").strip()
    if not raw:
        return None
    path = Path(raw)
    write_clip_metrics(path)
    return path
