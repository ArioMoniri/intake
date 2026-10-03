"""The server-side doors of the dev George clip route (INT-326, audit F05).

``intake_api.dev_voice`` reaches a paid US vendor with the ElevenLabs key. Before
INT-326 its only guards were a client-side "scripted text only" brand and a
dev opt-in phrase, so on any public host it was an open, unauthenticated
synthesis proxy for arbitrary text — cost abuse, and possibly PHI crossing to
the vendor against invariant 19. This module holds what the route now checks
itself, so none of it depends on a well-behaved client:

- **The catalogue.** ``text_tr`` is admitted only when ``clip_text_hash(text_tr)``
  is a row of a compiled clip manifest — the ``clips.<locale>.<voice>.json``
  that ``make protocols-compile`` writes and ``make clips`` builds from
  (ADR-028, INT-060). Those rows are the committed, verbatim, numeral-expanded
  scripts (invariants 10 and 22); a patient answer can never hash to one, so
  "patient words never reach the vendor" is a server fact, not a client promise.
  Every manifest is read through ``voice_clips.load_clip_manifest``, so a pack
  edited after compile (a row whose text no longer hashes to its key) refuses
  the whole catalogue rather than widening it.
- **The delivery pins** (INT-415). The same compiled rows say whose text each
  one is. A rule's action script is pinned to ``red``, which is never served
  on demand, and an instrument item is pinned to ``instrument``. So a client
  that labels a RED script "routine" does not get it synthesised.
- **The budget.** A per-principal token bucket on the INT-012 Redis limiter
  (``intake_platform.security.rate_limit``), shared by every replica.
- **Production.** ``INTAKE_ENV`` read the way the platform reads it
  (``intake_platform.secrets`` / ``documents`` / ``room_tokens``): default
  ``dev``, case-folded, any ``prod*`` value is production. In production the
  route is not mounted and no wiring is built, whatever the dev flags say.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final

from intake_platform.security.rate_limit import TokenBucketLimiter
from protocols.dsl import clip_text_hash
from protocols.locale_text import DEFAULT_LOCALE
from redis import Redis
from voice_clips.cache import clip_manifest_filename, load_clip_manifest
from voice_clips.cli import DEFAULT_DIST_ROOT
from voice_clips.delivery import PINNED_CONTEXTS, DeliveryContext
from voice_clips.errors import ClipCacheError

__all__ = [
    "ENV_GEORGE_CLIP_DIST",
    "ENV_INTAKE_ENV",
    "GEORGE_BUDGET_CAPACITY",
    "GEORGE_BUDGET_KEY_PREFIX",
    "GEORGE_BUDGET_REFILL_PER_S",
    "ScriptedCatalogue",
    "george_budget",
    "george_clip_dist_root",
    "intake_env_is_prod",
    "load_scripted_catalogue",
    "scripted_catalogue_from_env",
]

logger = logging.getLogger("intake_api")

ENV_INTAKE_ENV: Final = "INTAKE_ENV"

#: Where the compiled clip manifests are read from; defaults to where
#: ``protocols compile`` writes and ``intake-clips`` reads.
ENV_GEORGE_CLIP_DIST: Final = "INTAKE_DEV_GEORGE_CLIP_DIST"

#: Per-principal budget: a burst of 30 (one intake's worth of prefetched
#: questions) refilling at one request every two seconds — far above a patient
#: answering questions, far below a synthesis loop. Every request that passes
#: authentication costs a token, refused ones included, so hammering the door
#: with off-catalogue text is not free (the INT-131 OTP precedent).
GEORGE_BUDGET_CAPACITY: Final = 30
GEORGE_BUDGET_REFILL_PER_S: Final = 0.5
GEORGE_BUDGET_KEY_PREFIX: Final = "rl:george"

_MANIFEST_SUFFIX: Final = ".json"


def intake_env_is_prod() -> bool:
    """True for any ``prod*`` ``INTAKE_ENV`` (``prod``, ``production``, any case)."""
    return os.environ.get(ENV_INTAKE_ENV, "dev").lower().startswith("prod")


@dataclass(frozen=True)
class ScriptedCatalogue:
    """The ``clip_text_hash`` of every compiled clip-manifest row, and the
    delivery context a row is pinned to when its subject decides one.

    ``pinned_contexts`` (INT-415) maps a text hash to the only context it may
    be spoken in: a rule's action script is ``red``, an instrument item is
    ``instrument``. Both are derived here, server-side, from the compiled row's
    subject (``voice_clips.delivery.delivery_context_for_subject``), so the
    route never takes the client's word for which delivery a script gets. An
    ordinary scripted question is not pinned.
    """

    text_hashes: frozenset[str]
    pinned_contexts: Mapping[str, DeliveryContext] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def admits(self, text_tr: str) -> bool:
        return clip_text_hash(text_tr) in self.text_hashes

    def pinned_context(self, text_tr: str) -> DeliveryContext | None:
        return self.pinned_contexts.get(clip_text_hash(text_tr))


def george_clip_dist_root() -> Path:
    return Path(os.environ.get(ENV_GEORGE_CLIP_DIST) or DEFAULT_DIST_ROOT)


def load_scripted_catalogue(dist_root: Path, *, locale: str = DEFAULT_LOCALE) -> ScriptedCatalogue:
    """Every row of every compiled ``clips.<locale>.<voice>.json`` under ``dist_root``.

    The text hash is voice-independent (``clip_text_hash`` keys the text alone),
    so every voice's manifest contributes the same scripts. Raises the
    ``voice_clips`` manifest errors (schema, voice/locale mismatch, tamper)
    unchanged: a catalogue that cannot be read whole is not read at all.
    """
    prefix = clip_manifest_filename("", locale).removesuffix(_MANIFEST_SUFFIX)
    hashes: set[str] = set()
    pinned: dict[str, DeliveryContext] = {}
    for path in sorted(dist_root.glob(f"*/{clip_manifest_filename('*', locale)}")):
        voice = path.name.removeprefix(prefix).removesuffix(_MANIFEST_SUFFIX)
        manifest = load_clip_manifest(
            dist_root, pack_id=path.parent.name, voice=voice, locale=locale
        )
        for row in manifest.entries:
            hashes.add(row.text_hash)
            context = row.delivery_context
            if context in PINNED_CONTEXTS and pinned.get(row.text_hash) != "red":
                # a text that is a RED script anywhere stays RED everywhere
                pinned[row.text_hash] = context
    return ScriptedCatalogue(
        text_hashes=frozenset(hashes), pinned_contexts=MappingProxyType(pinned)
    )


def scripted_catalogue_from_env() -> ScriptedCatalogue | None:
    """The catalogue under :func:`george_clip_dist_root`, or ``None`` when it
    is unreadable, tampered or empty — nothing the route could safely admit.
    Ids-only logs (invariant 6): no path contents, no text."""
    try:
        catalogue = load_scripted_catalogue(george_clip_dist_root())
    except (ClipCacheError, OSError):
        logger.warning("george lane unconfigured: compiled clip catalogue unreadable or tampered")
        return None
    if not catalogue.text_hashes:
        logger.warning("george lane unconfigured: no compiled clip manifest to admit text from")
        return None
    return catalogue


def george_budget(redis_url: str) -> TokenBucketLimiter:
    """The production-shaped budget: Redis server time, shared by replicas.
    Building it opens no connection; an unreachable store surfaces per request
    and the route fails closed."""
    return TokenBucketLimiter(
        redis_client=Redis.from_url(redis_url),
        capacity=GEORGE_BUDGET_CAPACITY,
        refill_per_s=GEORGE_BUDGET_REFILL_PER_S,
        key_prefix=GEORGE_BUDGET_KEY_PREFIX,
    )
