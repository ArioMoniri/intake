"""The member call: one payload shape for self-hosted and hosted, replayed from disk in CI.

**Parity is a payload, not a promise.** A self-hosted member (vLLM, SGLang)
and a hosted member on the synthetic deployment both speak the
OpenAI-compatible chat-completions shape, so :func:`render_member_payload`
renders one body for both: the same instruction region, the same fenced data
block, the same closed JSON Schema, the same decoding. The route decides only
*where* the body goes, and that decision is INT-428's lane router, outside
this package — ``clinical_agent`` imports no network client
(``tests/engine/test_fsm.py::TestNoLlmInside``).

**A per-session ``cache_salt``.** Prefix caching on a shared serving engine is
a cross-session side channel; the salt (vLLM's ``cache_salt``) partitions the
cache per session. It is excluded from the recording key, because a replay
must read the recording made for the same call in another session.

**Replay reads recorded outputs and never re-runs a model** (AI/ML review).
:class:`RecordedMemberTransport` addresses a recording by everything that
could change the answer — schema id, prompt version, provider,
``model@revision``, weights digest, decoding, sample index, instructions and
the transcript digest — and re-checks the binding stored inside the file, so
a recording made on another lane is a refusal, not a silently wrong answer.
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from intake_voice_runtime.clinical_agent.council.lanes import PinnedMember
from intake_voice_runtime.clinical_agent.council.readings import (
    VERIFIER_PROMPT_VERSION,
    VERIFIER_SCHEMA_ID,
)
from intake_voice_runtime.extraction.boundary import PatientData, render_data_block

__all__ = [
    "FinishReason",
    "MemberCall",
    "MemberCompletion",
    "MemberTransport",
    "RecordedMemberTransport",
    "RecordedVerificationMismatch",
    "RecordedVerificationMissing",
    "render_member_payload",
]

RECORDING_SUFFIX: Final = ".json"


class FinishReason(enum.StrEnum):
    """How the serving endpoint said the call ended."""

    STOP = "stop"
    LENGTH = "length"
    REFUSAL = "refusal"
    CONTENT_FILTER = "content_filter"


@dataclass(frozen=True, slots=True)
class MemberCompletion:
    text: str
    finish: FinishReason
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, repr=False)
class MemberCall:
    """One draw: a pinned member, the instruction region and the fenced data."""

    member: PinnedMember
    sample: int
    instructions: str
    data: PatientData
    json_schema: Mapping[str, Any]
    temperature: str
    cache_salt: str

    @property
    def recording_key(self) -> str:
        parts = (
            VERIFIER_SCHEMA_ID,
            VERIFIER_PROMPT_VERSION,
            self.member.provider,
            f"{self.member.model_id}@{self.member.revision}",
            self.member.weights_sha256,
            self.temperature,
            str(self.sample),
            hashlib.sha256(self.instructions.encode("utf-8")).hexdigest(),
            self.data.sha256,
        )
        return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return (
            f"MemberCall(member={self.member.member_id!r}, sample={self.sample}, "
            f"data={self.data!r})"
        )


class MemberTransport(Protocol):
    async def complete(self, call: MemberCall) -> MemberCompletion: ...


def render_member_payload(call: MemberCall) -> dict[str, Any]:
    """The one request body, whichever route carries it."""
    return {
        "model": call.member.model_id,
        "messages": [
            {"role": "system", "content": call.instructions},
            {"role": "user", "content": render_data_block(call.data)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "verification", "strict": True, "schema": call.json_schema},
        },
        "temperature": float(call.temperature),
        "seed": call.sample,
        "cache_salt": call.cache_salt,
    }


class RecordedVerificationMissing(LookupError):
    """No recording exists for this call; nothing is run in its place."""


class RecordedVerificationMismatch(ValueError):
    """A recording exists under this key but was made for another call or lane."""


@dataclass(frozen=True)
class RecordedMemberTransport:
    """The CI and replay lane: recordings on disk, no socket, no model."""

    directory: Path

    async def complete(self, call: MemberCall) -> MemberCompletion:
        path = self.directory / f"{call.recording_key}{RECORDING_SUFFIX}"
        if not path.is_file():
            raise RecordedVerificationMissing(
                f"no recording for key {call.recording_key[:12]}…; replay never re-runs a model"
            )
        body = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "prompt_version": VERIFIER_PROMPT_VERSION,
            "provider": call.member.provider,
            "model": f"{call.member.model_id}@{call.member.revision}",
            "weights_sha256": call.member.weights_sha256,
            "data_sha256": call.data.sha256,
            "sample": call.sample,
        }
        recorded = {key: body.get(key) for key in expected}
        if recorded != expected:
            raise RecordedVerificationMismatch(
                f"recording {call.recording_key[:12]}… was made for another call or lane"
            )
        usage = body.get("usage", {})
        return MemberCompletion(
            text=str(body["text"]),
            finish=FinishReason(body["finish"]),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )
