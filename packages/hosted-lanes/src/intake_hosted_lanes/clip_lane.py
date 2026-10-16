"""The synthetic image's hosted clip lane (INT-443, ADR-035).

:func:`hosted_clip_tts_from_env` is the one entry point the API reaches for —
by module name, only when the deployment is synthetic and declares the lane
(``INTAKE_HOSTED_TTS=elevenlabs``). Like :mod:`intake_hosted_lanes.plugin` it
refuses outright in any other deployment, so an image that carried this
package by mistake still could not build a vendor TTS for real patients.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial

from intake_platform.egress import EgressAllowlist, EgressPolicy
from intake_platform.model_lanes.guard import deployment_data_class, egress_proxy_url
from intake_platform.model_lanes.keys import ProviderKeyVault
from intake_platform.model_lanes.model import ClipVendor, TenantDataClass

from intake_hosted_lanes.elevenlabs import ElevenLabsHostedTts, elevenlabs_row
from intake_hosted_lanes.plugin import HostedLanesRefused

__all__ = ["hosted_clip_tts_from_env"]


def hosted_clip_tts_from_env(
    env: Mapping[str, str],
    *,
    keys: ProviderKeyVault,
    allowlist: EgressAllowlist,
    admits: Callable[[str], bool],
) -> ElevenLabsHostedTts | None:
    """The hosted ElevenLabs lane, or ``None`` while its allow-list row is
    absent (``hosted_egress_not_listed``: the row is the owner's change).

    The key is read per call, through the vault's short cache, so a key loaded
    after boot (``load_provider_key.sh``) is used without a restart, and a
    key that is absent is a per-call ``hosted_key_not_set``.
    """
    if deployment_data_class(env) is not TenantDataClass.SYNTHETIC:
        raise HostedLanesRefused("the hosted clip lane exists only in the synthetic deployment")
    row = elevenlabs_row(allowlist)
    if row is None:
        return None
    return ElevenLabsHostedTts(
        host=row.host,
        key=partial(keys.key_for_call, ClipVendor.ELEVENLABS),
        policy=EgressPolicy.for_tier(allowlist, "dev"),
        admits=admits,
        proxy=egress_proxy_url(env),
    )
