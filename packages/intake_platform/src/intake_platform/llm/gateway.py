"""The LLM seam: one adapter interface, two implementations (INT-083).

ADR-006: *"All STT/TTS/LLM access goes through SpeechGateway/LLMGateway
adapter interfaces with recorded-fixture contract tests… CI never calls a
vendor."* This module is the LLM half, built to the same shape as the TTS
half in ``packages/voice-clips/src/voice_clips/gateway.py`` — a Protocol, an
HTTP adapter for the self-hosted server, a recorded adapter for CI and for a
dev box with no GPU, and a factory that **fails closed** rather than picking
one.

**Configuration fails closed.** Exactly one of ``INTAKE_LLM_ENDPOINT`` (a
self-hosted vLLM server) or ``INTAKE_LLM_RECORDED_DIR`` (recorded
completions) must be set. Neither has a default: a guessed endpoint is an
extraction nobody ran, and two sources is an ambiguous provenance for
clinical structure.

**Egress is enforced in-process, not merely in the deployment.**
:class:`HttpLlmGateway` composes :func:`intake_platform.egress.guarded_transport`,
so a vendor host is refused before a byte leaves even if somebody points the
endpoint at one. That is invariant 19 made structural: the
``anthropic|openai|google`` adapters are the mock/dev path only and are
blocked on the PHI path by the allow-list. There is no vendor adapter in this
module at all — the dev tier is a *tier*, and a caller that supplies one must
pass INT-015's de-identification with it
(:class:`intake_platform.llm.extraction.ExtractionWork`).

**The model is pinned, and the pin is not ours to invent.**
:data:`PINNED_EXTRACTION_MODELS` mirrors files/03 §4.9.1 **row 9**, which
ADR-021 makes the single source of truth: a model not in that table is not
pinned. The gateway refuses any other id rather than serving from whatever an
operator typed. (The row this replaced —
``google/medgemma-27b-text-it`` — is gated and ``license: other``; §4.9.2(a)
records why it fails outright.)
"""

from __future__ import annotations

import enum
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import httpx

from intake_platform.egress import EgressDenied, EgressPolicy, guarded_transport
from intake_platform.llm.boundary import ExtractionPrompt
from intake_platform.llm.errors import (
    LlmNotConfiguredError,
    LlmRefusedError,
    LlmUnavailableError,
    RecordedCompletionMismatch,
    RecordedCompletionMissing,
    UnpinnedModelError,
)
from intake_platform.llm.slot_schema import SlotSchema

__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "DEFAULT_TIMEOUT_S",
    "ENV_LLM_ENDPOINT",
    "ENV_LLM_MODEL_ID",
    "ENV_LLM_MODEL_REVISION",
    "ENV_LLM_RECORDED_DIR",
    "PINNED_EXTRACTION_MODELS",
    "GatewayTier",
    "HttpLlmGateway",
    "LlmCompletion",
    "LlmGateway",
    "RecordedLlmGateway",
    "llm_gateway_from_env",
]

ENV_LLM_ENDPOINT: Final = "INTAKE_LLM_ENDPOINT"
ENV_LLM_RECORDED_DIR: Final = "INTAKE_LLM_RECORDED_DIR"
ENV_LLM_MODEL_ID: Final = "INTAKE_LLM_MODEL_ID"
ENV_LLM_MODEL_REVISION: Final = "INTAKE_LLM_MODEL_REVISION"

#: vLLM serves an OpenAI-compatible route; JSON-schema-constrained decoding is
#: requested through ``response_format`` (files/03 §4.3 "JSON-schema-constrained
#: decoding"). Nothing here has been exercised against a live server — this
#: container has no GPU and no daemon (docs/evidence/INT-083.md says so
#: plainly); the recorded adapter is what CI runs.
CHAT_COMPLETIONS_PATH: Final = "/v1/chat/completions"

DEFAULT_TIMEOUT_S: Final = 30.0

#: files/03 §4.9.1 row 9, mirrored — never extended here. ADR-021: no other
#: file pins a model, so this set is a *reflection* of that row and a change
#: to it is a change to §4.9.1 first.
PINNED_EXTRACTION_MODELS: Final[frozenset[str]] = frozenset(
    {
        "Qwen/Qwen3.6-35B-A3B",
        "Qwen/Qwen3.8-27B",
    }
)


class GatewayTier(enum.StrEnum):
    """Which egress tier the adapter sits on (mirrors ``egress.Tier``).

    ``dev`` is the mock/dev path of invariant 19. A ``dev`` gateway may only
    be driven through INT-015's ``deidentify_for_egress``, which itself fails
    closed without the NER tier.
    """

    PHI_PATH = "phi_path"
    DEV = "dev"


@dataclass(frozen=True)
class LlmCompletion:
    """One completion, plus what the trace needs. No prompt echo."""

    text: str
    model_id: str
    model_revision: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class LlmGateway(Protocol):
    """One prompt in, one completion out. Nothing streams here.

    ``tier`` is a read-only member on purpose: an adapter's tier is decided
    when it is constructed, and a caller that could reassign it could move a
    vendor adapter onto the PHI path at runtime (invariant 19).
    """

    @property
    def tier(self) -> GatewayTier: ...

    def complete(self, prompt: ExtractionPrompt, schema: SlotSchema) -> LlmCompletion: ...


def _assert_pinned(model_id: str) -> None:
    if model_id not in PINNED_EXTRACTION_MODELS:
        raise UnpinnedModelError(
            f"model {model_id!r} is not a row of files/03 §4.9.1 row 9 "
            f"({sorted(PINNED_EXTRACTION_MODELS)}). ADR-021: a model not in that "
            "table is not pinned, and this gateway will not serve from one."
        )


@dataclass(frozen=True)
class RecordedLlmGateway:
    """Replays committed completions. The CI path, and the dev path with no GPU.

    A recording carries the schema it was produced under, so a recording made
    for a different slot set is a refusal rather than a silently wrong
    extraction — the same rule ``RecordedTtsGateway`` applies to a clip whose
    text drifted from the script.
    """

    root: Path
    tier: GatewayTier = GatewayTier.PHI_PATH

    def complete(self, prompt: ExtractionPrompt, schema: SlotSchema) -> LlmCompletion:
        path = self.root / f"{prompt.input_digest}.json"
        if not path.is_file():
            raise RecordedCompletionMissing(
                f"no recorded completion for input_digest {prompt.input_digest} under "
                f"{self.root} — CI never calls a model, so a missing recording is a "
                "failed test, never an invented answer"
            )
        recorded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if recorded.get("schema_id") != schema.schema_id:
            raise RecordedCompletionMismatch(
                f"recording {prompt.input_digest} was made under another slot schema "
                f"({recorded.get('schema_id')}), not {schema.schema_id}"
            )
        model_id = str(recorded.get("model_id", ""))
        _assert_pinned(model_id)
        return LlmCompletion(
            text=str(recorded["text"]),
            model_id=model_id,
            model_revision=str(recorded["model_revision"]),
            input_tokens=int(recorded.get("input_tokens", 0)),
            output_tokens=int(recorded.get("output_tokens", 0)),
            latency_ms=int(recorded.get("latency_ms", 0)),
        )


@dataclass(frozen=True)
class HttpLlmGateway:
    """A self-hosted vLLM server reached over HTTP, behind the egress policy."""

    endpoint: str
    model_id: str
    model_revision: str
    policy: EgressPolicy
    tier: GatewayTier = GatewayTier.PHI_PATH
    inner_transport: httpx.BaseTransport | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S

    def __post_init__(self) -> None:
        _assert_pinned(self.model_id)

    def _body(self, prompt: ExtractionPrompt, schema: SlotSchema) -> dict[str, Any]:
        return {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "slot_extraction",
                    "schema": dict(schema.json_schema),
                    "strict": True,
                },
            },
        }

    def complete(self, prompt: ExtractionPrompt, schema: SlotSchema) -> LlmCompletion:
        url = f"{self.endpoint.rstrip('/')}{CHAT_COMPLETIONS_PATH}"
        transport = guarded_transport(self.policy, self.inner_transport)
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.timeout_s, transport=transport) as client:
                response = client.post(url, json=self._body(prompt, schema))
        except EgressDenied:
            # never softened into "unavailable": a denied egress is a policy
            # decision the caller must see as one (invariant 19)
            raise
        except httpx.HTTPError as exc:
            raise LlmUnavailableError(
                f"extraction endpoint unreachable ({type(exc).__name__}); configure a "
                f"reachable self-hosted server or point {ENV_LLM_RECORDED_DIR} at "
                "recorded completions"
            ) from exc
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        if response.status_code // 100 != 2:
            raise LlmRefusedError(
                f"extraction endpoint answered HTTP {response.status_code} for model "
                f"{self.model_id!r}"
            )
        payload = response.json()
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmRefusedError(
                "extraction endpoint answered a body with no completion in it"
            ) from exc
        usage = payload.get("usage") or {}
        return LlmCompletion(
            text=str(text),
            model_id=self.model_id,
            model_revision=self.model_revision,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
        )


def llm_gateway_from_env(*, policy: EgressPolicy | None = None) -> LlmGateway:
    """Select the one configured gateway, or refuse."""
    endpoint = os.environ.get(ENV_LLM_ENDPOINT, "").strip()
    recorded = os.environ.get(ENV_LLM_RECORDED_DIR, "").strip()
    if bool(endpoint) == bool(recorded):
        raise LlmNotConfiguredError(
            f"set exactly one of {ENV_LLM_ENDPOINT} (a self-hosted extraction server) "
            f"or {ENV_LLM_RECORDED_DIR} (recorded completions; the CI and no-GPU dev "
            "path). Neither is guessed and neither has a default: a guessed endpoint "
            "is an extraction nobody ran, and two sources is an ambiguous provenance "
            "for clinical structure."
        )
    if recorded:
        root = Path(recorded)
        if not root.is_dir():
            raise LlmNotConfiguredError(f"{ENV_LLM_RECORDED_DIR}={recorded!r} is not a directory")
        return RecordedLlmGateway(root=root)
    if policy is None:
        raise LlmNotConfiguredError(
            f"{ENV_LLM_ENDPOINT} is set but no egress policy was supplied — a live "
            "endpoint is reachable only behind the allow-list (invariant 19). Load "
            "infra/security/egress-allowlist.yaml and pass the phi_path tier."
        )
    model_id = os.environ.get(ENV_LLM_MODEL_ID, "").strip()
    revision = os.environ.get(ENV_LLM_MODEL_REVISION, "").strip()
    if not model_id or not revision:
        raise LlmNotConfiguredError(
            f"a live endpoint requires {ENV_LLM_MODEL_ID} and {ENV_LLM_MODEL_REVISION}: "
            "weights are pinned by model_id@revision (CLAUDE.md invariant 14) and an "
            "unpinned model has no place in a trace, a note or a technical file"
        )
    return HttpLlmGateway(
        endpoint=endpoint,
        model_id=model_id,
        model_revision=revision,
        policy=policy,
    )
