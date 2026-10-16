"""The synthetic host's hosted clip lane, wired for the George route (INT-443).

ElevenLabs is the default TTS of the synthetic deployment (ADR-035) once two
things exist that only humans add: its key in OpenBao
(``secret/model-lanes/providers/elevenlabs``, loaded by
``infra/staging/load_provider_key.sh``) and its egress allow-list row
(``elevenlabs-api``, the owner's protected change). Until the row exists the
lane is unconfigured and the route answers 503; until the key exists every
miss is a per-call ``hosted_key_not_set`` and falls back.

Each fact is configuration with no default and nothing guessed:

- the adapters are the synthetic image's ``intake_hosted_lanes`` package,
  reached by module name and only when the deployment is synthetic and
  declares the lane (``INTAKE_HOSTED_TTS=elevenlabs``). A PHI image carries no
  such package and never declares the lane, and the plugin refuses anyway;
- the vendor host is read off the allow-list row, never written here;
- the forward proxy is ``INTAKE_EGRESS_PROXY_URL`` through its guard (INT-442);
- the cache is ``INTAKE_HOSTED_TTS_CACHE_DIR``, a persistent volume pre-baked
  by ``python -m intake_api.george_prebake apply``;
- the fallback is the self-hosted TTS (``INTAKE_TTS_ENDPOINT``) in
  ``INTAKE_HOSTED_TTS_FALLBACK_VOICE``. Both or neither: a fallback with no
  voice of its own would ask the self-hosted model for the vendor's voice.

Logs name states and exception classes only (invariant 6).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from intake_platform.egress import load_allowlist
from intake_platform.model_lanes.keys import KvBackend, ProviderKeyVault
from intake_platform.model_lanes.wiring import ENV_MODEL_LANES_ALLOWLIST
from voice_clips.gateway import ENV_TTS_ENDPOINT, HttpTtsGateway, TtsGateway

from intake_api.dev_voice_guard import hosted_clip_lane_declared

__all__ = [
    "CLIP_LANE_MODULE",
    "ENV_HOSTED_TTS_CACHE_DIR",
    "ENV_HOSTED_TTS_FALLBACK_VOICE",
    "HostedClipLane",
    "hosted_clip_lane",
]

#: The synthetic image's adapter module. Named, never imported at module load.
CLIP_LANE_MODULE: Final = "intake_hosted_lanes.clip_lane"
ENV_HOSTED_TTS_CACHE_DIR: Final = "INTAKE_HOSTED_TTS_CACHE_DIR"
ENV_HOSTED_TTS_FALLBACK_VOICE: Final = "INTAKE_HOSTED_TTS_FALLBACK_VOICE"
_ALLOWLIST_DEFAULT: Final = "infra/security/egress-allowlist.yaml"

logger = logging.getLogger("intake_api")


@dataclass(frozen=True)
class HostedClipLane:
    """The vendor lane, its optional self-hosted fallback, and the cache."""

    primary: TtsGateway
    cache_dir: Path
    fallback: TtsGateway | None = None
    fallback_voice_id: str | None = None


def _fallback(env: Mapping[str, str]) -> tuple[TtsGateway | None, str | None]:
    endpoint = env.get(ENV_TTS_ENDPOINT, "").strip()
    voice = env.get(ENV_HOSTED_TTS_FALLBACK_VOICE, "").strip()
    if endpoint and voice:
        return HttpTtsGateway(endpoint=endpoint), voice
    return None, None


def hosted_clip_lane(
    env: Mapping[str, str],
    *,
    kv: Callable[[], KvBackend] | None,
    admits: Callable[[str], bool],
) -> HostedClipLane | None:
    """The lane, or ``None`` (fail closed, the route answers 503)."""
    if not hosted_clip_lane_declared(env):
        return None
    cache_dir = env.get(ENV_HOSTED_TTS_CACHE_DIR, "").strip()
    if not cache_dir:
        logger.warning("hosted clip lane unconfigured: no cache directory")
        return None
    if kv is None or importlib.util.find_spec(CLIP_LANE_MODULE.rsplit(".", 1)[0]) is None:
        logger.warning("hosted clip lane unconfigured: no key store or no adapter package")
        return None
    try:
        keys = ProviderKeyVault(kv())
    except Exception as err:  # noqa: BLE001 — the class names what is missing; no value is logged
        logger.warning("hosted clip lane unconfigured: key store %s", type(err).__name__)
        return None
    allowlist = load_allowlist(Path(env.get(ENV_MODEL_LANES_ALLOWLIST) or _ALLOWLIST_DEFAULT))
    module = importlib.import_module(CLIP_LANE_MODULE)
    primary = module.hosted_clip_tts_from_env(env, keys=keys, allowlist=allowlist, admits=admits)
    if primary is None:
        logger.warning("hosted clip lane unconfigured: hosted_egress_not_listed")
        return None
    fallback, voice = _fallback(env)
    return HostedClipLane(
        primary=primary, cache_dir=Path(cache_dir), fallback=fallback, fallback_voice_id=voice
    )
