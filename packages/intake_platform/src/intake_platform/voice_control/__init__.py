"""Per-tenant voice control: kill switch, default profile, canary (INT-182).

Shared by the two sides of the Voice module: ``services/api/admin`` writes a
tenant's control (four-eyes toward voice, one key toward typed —
files/08 §8.2), and ``services/voice-runtime`` reads it at every session start
and on a poll for live sessions. See :mod:`.model` for the record and
:mod:`.store` for where it lives and how it fails closed.
"""

from __future__ import annotations

from intake_platform.voice_control.model import (
    CANARY_WEIGHT_MAX,
    CANARY_WEIGHT_MIN,
    CanaryWeightOutOfBounds,
    TenantInvalid,
    TenantVoiceControl,
    UnknownVoiceProfile,
    VoiceControlChange,
    VoiceControlProfile,
    VoiceControlRefused,
    parse_canary_weight,
    parse_profile,
    require_tenant_id,
)
from intake_platform.voice_control.store import (
    ENV_VOICE_CONTROL_REDIS_URL,
    KEY_PREFIX,
    RedisVoiceControlStore,
    VoiceControlConflict,
    VoiceControlReader,
    VoiceControlStore,
    VoiceControlUnavailable,
    voice_control_store_from_env,
)

__all__ = [
    "CANARY_WEIGHT_MAX",
    "CANARY_WEIGHT_MIN",
    "ENV_VOICE_CONTROL_REDIS_URL",
    "KEY_PREFIX",
    "CanaryWeightOutOfBounds",
    "RedisVoiceControlStore",
    "TenantInvalid",
    "TenantVoiceControl",
    "UnknownVoiceProfile",
    "VoiceControlChange",
    "VoiceControlConflict",
    "VoiceControlProfile",
    "VoiceControlReader",
    "VoiceControlRefused",
    "VoiceControlStore",
    "VoiceControlUnavailable",
    "parse_canary_weight",
    "parse_profile",
    "require_tenant_id",
    "voice_control_store_from_env",
]
