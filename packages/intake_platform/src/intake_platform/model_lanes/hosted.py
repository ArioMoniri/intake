"""The hosted-lane seam, with no vendor in it (INT-428, ADR-035).

Hosted provider adapters belong to a **deployment**, not a tenant (AI/ML
review, binding): they ship only in the synthetic deployment's image (the
us-east-1 AWS host, simulated patients) as the separate
``intake_hosted_lanes`` package, and the PHI deployment's image contains none.
This module is what the rest of the platform sees of them — a Protocol and its
result types — so that nothing on the PHI closure imports a vendor adapter
(a test holds it), and a deployment without the package simply has
:meth:`HostedLanes.none`: no providers, no backends, nothing to route to.

**One outcome class for "no usable answer".** A refusal, a truncation
(``finish_reason: length``), a content filter or an empty output is a
:class:`HostedLaneUnavailable` with the code ``hosted_lane_no_answer`` — a
caller never has to tell them apart, and never mistakes a partial JSON object
for an extraction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from intake_platform.egress import DataClass
from intake_platform.model_lanes.model import Lane, ProviderId
from intake_platform.model_lanes.models import HostedModel

__all__ = [
    "NO_ANSWER",
    "HostedBackend",
    "HostedChat",
    "HostedLaneUnavailable",
    "HostedLanes",
    "HostedProviderInfo",
    "HostedSpeech",
    "HostedTranscript",
    "HostedUsage",
]

#: The single outcome class for a refusal, a truncation or an empty output.
NO_ANSWER: Final = "hosted_lane_no_answer"


class HostedLaneUnavailable(Exception):
    """A hosted call did not produce a usable answer. ``code`` is machine-shaped."""

    def __init__(self, code: str, *, status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class HostedUsage:
    """What a backend reported it charged for. Zero is the true count of what
    nothing reported, never an estimate."""

    input_tokens: int = 0
    output_tokens: int = 0
    audio_seconds: float = 0.0
    characters: int = 0


@dataclass(frozen=True)
class HostedChat:
    text: str = field(repr=False)
    #: The model the provider says answered — checked against the request.
    model: str
    usage: HostedUsage


@dataclass(frozen=True)
class HostedTranscript:
    text: str = field(repr=False)
    model: str
    usage: HostedUsage


@dataclass(frozen=True)
class HostedSpeech:
    pcm_s16le: bytes = field(repr=False)
    sample_rate_hz: int
    channels: int
    model: str
    usage: HostedUsage


class HostedBackend(Protocol):
    """A hosted provider's three lanes and its identity probe. ``model`` is
    always the resolved dated snapshot's wire name — a backend never picks."""

    @property
    def provider_id(self) -> ProviderId: ...

    def chat_json(
        self,
        *,
        instructions: str,
        data_block: str,
        schema_name: str,
        json_schema: Mapping[str, Any],
        data_class: DataClass,
        model: str,
    ) -> HostedChat: ...

    def transcribe(
        self, audio: bytes, *, audio_format: str, data_class: DataClass, model: str
    ) -> HostedTranscript: ...

    def speech(self, text_tr: str, *, data_class: DataClass, model: str) -> HostedSpeech: ...

    def probe(self, model: str) -> bool: ...


@dataclass(frozen=True)
class HostedProviderInfo:
    """What the console and the resolver know of one hosted provider."""

    provider: ProviderId
    egress_row: str
    #: Whether the provider's egress allow-list row exists.
    listed: bool
    models: tuple[HostedModel, ...]
    defaults: Mapping[Lane, str]


@dataclass(frozen=True)
class HostedLanes:
    """What a deployment's image contributes to the hosted lanes."""

    providers: Mapping[ProviderId, HostedProviderInfo] = field(default_factory=dict)
    backends: Mapping[ProviderId, HostedBackend] = field(default_factory=dict)

    @classmethod
    def none(cls) -> HostedLanes:
        """The PHI deployment, and any image without the hosted package."""
        return cls()

    def info(self, provider: ProviderId) -> HostedProviderInfo | None:
        return self.providers.get(provider)
