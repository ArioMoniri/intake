"""The LLM seam: one adapter interface, two implementations, no guessing.

ADR-006 (provider-agnostic gateways) and CLAUDE.md ("all external AI/speech
calls go through gateways with adapter interfaces and recorded fixtures for
tests"). This module is that seam for ``extract_slots`` — files/03 §4.3's Layer
B Work, served by files/03 §4.9.1 row 9.

**Configuration fails closed.** Exactly one of ``INTAKE_EXTRACTION_ENDPOINT``
(a self-hosted, in-country serving endpoint) or
``INTAKE_EXTRACTION_RECORDED_DIR`` (recorded completions — the CI and dev path)
must be set. Neither has a default, on the ``INTAKE_CLAMD_HOST`` precedent that
``packages/voice-clips/.../gateway.py`` already follows: a guessed scanner is a
scan that did not happen, and a guessed model endpoint is an extraction nobody
performed. Both at once is refused too — an ambiguous source for a clinical
value is not a preference to resolve quietly.

**A vendor endpoint cannot be configured at all.** CLAUDE.md invariant 19 makes
the ``anthropic|openai|google`` adapters the mock/dev path only, blocked on the
PHI path by the egress allow-list (``intake_platform.egress``). This seam
refuses them one layer earlier and unconditionally: :func:`_refuse_vendor_host`
runs before any client is built, so there is no environment in which the
extraction gateway points at a vendor. The domain list is imported from the
egress module rather than restated, so the two cannot drift.

**A recording is bound to the call that produced it.** The file name is
``sha256(schema_id, prompt_version, instructions, transcript_digest)``, and the
file re-states the prompt version and the transcript digest, so a recording
made under other instructions or for other text is a refusal rather than a
silently wrong answer. That is the same rule ``RecordedTtsGateway`` applies to
a synthesised clip.

**No model is called in CI.** The recorded lane opens no socket, and this
module imports no vendor SDK — a test scans the source for it.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import httpx
from intake_platform.egress import VENDOR_LLM_DOMAINS

from intake_voice_runtime.extraction.boundary import PatientData, render_data_block
from intake_voice_runtime.extraction.errors import (
    ExtractionNotConfigured,
    ExtractionUnavailable,
    RecordedExtractionMismatchError,
    RecordedExtractionMissingError,
    VendorEndpointRefused,
)
from intake_voice_runtime.extraction.schema import EXTRACTION_SCHEMA_ID, PROMPT_VERSION

__all__ = [
    "COMPLETION_PATH",
    "DEFAULT_TIMEOUT_S",
    "ENV_EXTRACTION_ENDPOINT",
    "ENV_EXTRACTION_RECORDED_DIR",
    "Completion",
    "ExtractionCall",
    "ExtractionGateway",
    "HttpExtractionGateway",
    "RecordedExtractionGateway",
    "extraction_gateway_from_env",
    "render_request_payload",
]

ENV_EXTRACTION_ENDPOINT: Final = "INTAKE_EXTRACTION_ENDPOINT"
ENV_EXTRACTION_RECORDED_DIR: Final = "INTAKE_EXTRACTION_RECORDED_DIR"

#: The OpenAI-compatible route every self-hostable serving runtime in files/03
#: §4.9.1 exposes (vLLM, SGLang). It is a route on *our* endpoint; the vendor
#: whose API shape it borrows is unreachable from here by construction.
COMPLETION_PATH: Final = "/v1/chat/completions"
DEFAULT_TIMEOUT_S: Final = 30.0

RECORDING_SUFFIX: Final = ".json"


@dataclass(frozen=True)
class Completion:
    """What a gateway returns: the raw body, plus whatever usage it reported.

    Token counts are what the *serving endpoint* reported, not an estimate this
    process made. A recording that carries no usage block yields zero, which is
    the true count of tokens anything here has counted; the character counts on
    the span are the measurement that is always real. Session token budgets are
    INT-101, which owns the metering.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, repr=False)
class ExtractionCall:
    """One model call, with the instruction region and the data kept apart.

    Two fields and two types. ``instructions`` is a ``str`` built from
    declarations; ``data`` is a :class:`PatientData`, which is the type the
    boundary hands out. Nothing in this package concatenates the two.
    """

    instructions: str
    data: PatientData
    json_schema: Mapping[str, Any]

    @property
    def recording_key(self) -> str:
        """Address a recording by everything that could change the answer."""
        digest = hashlib.sha256(
            "\x00".join(
                (
                    EXTRACTION_SCHEMA_ID,
                    PROMPT_VERSION,
                    hashlib.sha256(self.instructions.encode("utf-8")).hexdigest(),
                    self.data.sha256,
                )
            ).encode("utf-8")
        ).hexdigest()
        return digest

    def __repr__(self) -> str:
        return f"ExtractionCall(schema_id={EXTRACTION_SCHEMA_ID!r}, data={self.data!r})"


def render_request_payload(call: ExtractionCall, *, model_id: str | None) -> dict[str, Any]:
    """The wire body: instructions in the system role, data in the user role.

    Two roles, never one string. The response format is a JSON Schema in strict
    mode, so the serving runtime constrains decoding to the contract rather
    than the parser catching a violation afterwards — belt and braces, since
    the parser refuses anyway.
    """
    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": call.instructions},
            {"role": "user", "content": render_data_block(call.data)},
        ],
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": EXTRACTION_SCHEMA_ID.replace(".", "_"),
                "schema": call.json_schema,
                "strict": True,
            },
        },
    }
    if model_id is not None:
        payload["model"] = model_id
    return payload


class ExtractionGateway(Protocol):
    """One call in, one completion out. Nothing streams here: extraction is off
    the spoken critical path (files/03 §4.9.1 row 9)."""

    def complete(self, call: ExtractionCall) -> Completion: ...


def _refuse_vendor_host(endpoint: str) -> str:
    host = (httpx.URL(endpoint).host or "").casefold()
    if not host:
        raise ExtractionNotConfigured(f"{ENV_EXTRACTION_ENDPOINT} names no host")
    for domain in sorted(VENDOR_LLM_DOMAINS):
        if host == domain or host.endswith(f".{domain}"):
            raise VendorEndpointRefused(
                f"host {host!r} is under the vendor LLM domain {domain!r}. Those adapters "
                "are the mock/dev path only and are blocked on the PHI path by the egress "
                "allow-list (CLAUDE.md invariant 19); the extraction gateway refuses them "
                "outright, so there is no configuration in which one is reachable"
            )
    return endpoint.rstrip("/")


class RecordedExtractionGateway:
    """Replay a committed completion. The CI and no-GPU dev lane."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def complete(self, call: ExtractionCall) -> Completion:
        path = self._root / f"{call.recording_key}{RECORDING_SUFFIX}"
        if not path.is_file():
            raise RecordedExtractionMissingError(
                f"no recorded completion under {self._root.name} for call "
                f"{call.recording_key}. Record one, or point "
                f"{ENV_EXTRACTION_ENDPOINT} at a self-hosted endpoint — nothing is "
                "synthesised to fill the gap"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RecordedExtractionMismatchError(
                f"recording {call.recording_key} is not an object"
            )
        for field_name, expected in (
            ("schema_id", EXTRACTION_SCHEMA_ID),
            ("prompt_version", PROMPT_VERSION),
            ("data_sha256", call.data.sha256),
        ):
            if payload.get(field_name) != expected:
                raise RecordedExtractionMismatchError(
                    f"recording {call.recording_key} was made for a different "
                    f"{field_name}; a recording that has drifted from its call is not a "
                    "recording of it"
                )
        text = payload.get("completion")
        if not isinstance(text, str):
            raise RecordedExtractionMismatchError(
                f"recording {call.recording_key} carries no 'completion' string"
            )
        return Completion(
            text=text,
            input_tokens=int(payload.get("input_tokens", 0)),
            output_tokens=int(payload.get("output_tokens", 0)),
        )


class HttpExtractionGateway:
    """The self-hosted lane: an OpenAI-compatible route on our own endpoint.

    ``transport`` is a seam so a contract test can exercise the wire shape
    without a server; it is never a way to reach a vendor, because the host is
    refused in ``__init__`` before a transport is consulted.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        model_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._endpoint = _refuse_vendor_host(endpoint)
        self._model_id = model_id
        self._transport = transport
        self._timeout_s = timeout_s

    def complete(self, call: ExtractionCall) -> Completion:
        payload = render_request_payload(call, model_id=self._model_id)
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout_s) as client:
                response = client.post(f"{self._endpoint}{COMPLETION_PATH}", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as err:
            raise ExtractionUnavailable(
                f"the extraction endpoint did not answer: {type(err).__name__}. The request "
                "body is deliberately not echoed (CLAUDE.md invariant 6)"
            ) from None
        try:
            text = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
        except (KeyError, IndexError, TypeError):
            raise ExtractionUnavailable(
                "the extraction endpoint answered in a shape this adapter does not read"
            ) from None
        if not isinstance(text, str):
            raise ExtractionUnavailable("the extraction endpoint returned a non-string completion")
        return Completion(
            text=text,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )


def extraction_gateway_from_env(
    environ: Mapping[str, str] | None = None, *, model_id: str | None = None
) -> ExtractionGateway:
    """Resolve the one configured lane, or refuse to choose one."""
    env = os.environ if environ is None else environ
    endpoint = env.get(ENV_EXTRACTION_ENDPOINT)
    recorded = env.get(ENV_EXTRACTION_RECORDED_DIR)
    if bool(endpoint) == bool(recorded):
        raise ExtractionNotConfigured(
            f"set exactly one of {ENV_EXTRACTION_ENDPOINT} (a self-hosted endpoint) or "
            f"{ENV_EXTRACTION_RECORDED_DIR} (recorded completions). Neither has a default: "
            "a guessed model endpoint is an extraction nobody performed, and both at once "
            "is an ambiguous source for a clinical value"
        )
    if endpoint:
        return HttpExtractionGateway(endpoint, model_id=model_id)
    return RecordedExtractionGateway(Path(str(recorded)))
