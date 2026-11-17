"""The model-lane series (INT-428). Every one is catalogued in
``observability/metrics_catalog.yaml``; every label is an id or a closed
enumeration — never a tenant, a text or a key (invariant 6).

``route`` is ``self_hosted`` | ``hosted`` and ``provider`` is a
:class:`~intake_platform.model_lanes.model.ProviderId` or ``none``: two labels
rather than one ``hosted:openai`` value, because a colon is not id-shaped and
the console's Prometheus reader refuses it.
"""

from __future__ import annotations

from typing import Final

from prometheus_client import Counter, Histogram

__all__ = [
    "MODEL_LANE_AUDIO_SECONDS_TOTAL",
    "MODEL_LANE_CALLS_TOTAL",
    "MODEL_LANE_CHARACTERS_TOTAL",
    "MODEL_LANE_FALLBACK_TOTAL",
    "MODEL_LANE_LATENCY_SECONDS",
    "MODEL_LANE_REFUSED_TOTAL",
    "MODEL_LANE_TOKENS_TOTAL",
]

_LATENCY_BUCKETS: Final = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0)

MODEL_LANE_CALLS_TOTAL = Counter(
    "model_lane_calls_total",
    "Model-lane calls by lane, serving route, provider and outcome.",
    ["lane", "route", "provider", "outcome"],
)
MODEL_LANE_LATENCY_SECONDS = Histogram(
    "model_lane_latency_seconds",
    "Model-lane call latency in seconds, by lane, serving route and provider.",
    ["lane", "route", "provider"],
    buckets=_LATENCY_BUCKETS,
)
MODEL_LANE_TOKENS_TOTAL = Counter(
    "model_lane_tokens_total",
    "Tokens a model lane's backend reported, by direction (input|output).",
    ["lane", "route", "provider", "direction"],
)
MODEL_LANE_AUDIO_SECONDS_TOTAL = Counter(
    "model_lane_audio_seconds_total",
    "Audio seconds a model lane's backend reported transcribing.",
    ["lane", "route", "provider"],
)
MODEL_LANE_CHARACTERS_TOTAL = Counter(
    "model_lane_characters_total",
    "Characters a model lane sent for synthesis.",
    ["lane", "route", "provider"],
)
MODEL_LANE_FALLBACK_TOTAL = Counter(
    "model_lane_fallback_total",
    "Calls served by a hosted fallback because the self-hosted lane was unhealthy.",
    ["lane", "provider"],
)
MODEL_LANE_REFUSED_TOTAL = Counter(
    "model_lane_refused_total",
    "Model-lane calls refused before or after dispatch, by lane and reason code.",
    ["lane", "reason"],
)
