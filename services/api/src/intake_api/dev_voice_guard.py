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
  the whole catalogue rather than widening it. The one widening is INT-414's:
  the fixed conversational delivery lines (:mod:`intake_api.dev_voice_delivery`,
  verbatim ``tr`` catalogue copy, pinned to it by test) join a catalogue that
  loaded, hashed the same way (:func:`with_delivery_lines`). They carry no
  delivery pin, so the route refuses them under ``red`` like any other text.
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
- **The synthetic host** (INT-443). Outside dev the route is mounted only in
  the synthetic deployment (the image bakes ``INTAKE_DEPLOYMENT_DATA_CLASS=
  synthetic``) that declares its hosted clip lane, ``INTAKE_HOSTED_TTS=
  elevenlabs``. A dev flag cannot be the switch there: INT-325 refuses the
  boot when any ``INTAKE_DEV_*`` is set outside dev. A PHI deployment never
  mounts it, whatever it declares.
- **The app's catalogue** (INT-443). No pack compiles on today's tree (HB-C1),
  and the dialogue speaks the composition of its own i18n question catalogue,
  not pack ``text_tr``. ``apps/mobile/src/lib/dialogue/scriptedCatalogue.tr.json``
  lists exactly that composition (a vitest staleness test holds it byte-equal
  to the code), and its rows are admitted alongside the compiled manifests.
  It is validated as a whole: a row a TTS may not see, a RED row, a duplicate
  or an unknown context refuses the file rather than narrowing it.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

from intake_platform.model_lanes.guard import deployment_data_class
from intake_platform.model_lanes.model import ClipVendor, TenantDataClass
from intake_platform.security.rate_limit import TokenBucketLimiter
from protocols.dsl import clip_text_hash
from protocols.locale_text import DEFAULT_LOCALE
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis import Redis
from voice_clips.cache import clip_manifest_filename, load_clip_manifest
from voice_clips.cli import DEFAULT_DIST_ROOT
from voice_clips.delivery import DELIVERY_CONTEXTS, PINNED_CONTEXTS, DeliveryContext
from voice_clips.errors import ClipCacheError
from voice_clips.gateway import UnspeakableScriptError, assert_speakable_tr

from intake_api.dev_voice_delivery import delivery_text_hashes
from intake_api.settings import is_dev_env

__all__ = [
    "APP_CATALOGUE_DEFAULT",
    "ENV_APP_CATALOGUE",
    "ENV_GEORGE_CLIP_DIST",
    "ENV_HOSTED_TTS",
    "ENV_INTAKE_ENV",
    "GEORGE_BUDGET_CAPACITY",
    "GEORGE_BUDGET_KEY_PREFIX",
    "GEORGE_BUDGET_REFILL_PER_S",
    "AppCatalogueError",
    "CatalogueRow",
    "catalogue_from_rows",
    "ScriptedCatalogue",
    "george_budget",
    "george_clip_dist_root",
    "george_route_mountable",
    "hosted_clip_lane_declared",
    "intake_env_is_prod",
    "load_app_catalogue",
    "load_scripted_catalogue",
    "scripted_catalogue_from_env",
    "with_delivery_lines",
]

logger = logging.getLogger("intake_api")

ENV_INTAKE_ENV: Final = "INTAKE_ENV"

#: Where the compiled clip manifests are read from; defaults to where
#: ``protocols compile`` writes and ``intake-clips`` reads.
ENV_GEORGE_CLIP_DIST: Final = "INTAKE_DEV_GEORGE_CLIP_DIST"

#: INT-443: the synthetic deployment's hosted clip lane. The one value is the
#: vendor's ``ClipVendor`` name; anything else leaves the lane undeclared.
ENV_HOSTED_TTS: Final = "INTAKE_HOSTED_TTS"
#: Where the app's scripted catalogue is read from (repo-relative by default;
#: the synthetic image ships exactly this file).
ENV_APP_CATALOGUE: Final = "INTAKE_SCRIPTED_CATALOGUE_PATH"
APP_CATALOGUE_DEFAULT: Final = "apps/mobile/src/lib/dialogue/scriptedCatalogue.tr.json"

#: Per-principal budget, charged for cache MISSES and refusals only (INT-443):
#: a cache hit dials no vendor and costs nothing. The burst is one session's
#: clips — a detailed intake asks up to thirty questions and the dialogue
#: pre-warms each question with its confirmation, so sixty — refilling at one
#: request every two seconds: far above a patient answering questions, far
#: below a synthesis loop. A refused request still costs a token, so hammering
#: the door with off-catalogue text is not free (the INT-131 OTP precedent).
GEORGE_BUDGET_CAPACITY: Final = 60
GEORGE_BUDGET_REFILL_PER_S: Final = 0.5
GEORGE_BUDGET_KEY_PREFIX: Final = "rl:george"

_MANIFEST_SUFFIX: Final = ".json"


def intake_env_is_prod() -> bool:
    """True for any ``prod*`` ``INTAKE_ENV`` (``prod``, ``production``, any case)."""
    return os.environ.get(ENV_INTAKE_ENV, "dev").lower().startswith("prod")


def hosted_clip_lane_declared(env: Mapping[str, str]) -> bool:
    """The synthetic deployment declares its hosted clip lane (INT-443).

    Both facts, and the exact literals: the image's baked data class and the
    compose's lane name. A PHI deployment that set the lane name still reads
    ``False`` here, and nothing downstream reads the key.
    """
    return (
        deployment_data_class(env) is TenantDataClass.SYNTHETIC
        and env.get(ENV_HOSTED_TTS) == ClipVendor.ELEVENLABS.value
    )


def george_route_mountable(env: Mapping[str, str]) -> bool:
    """Never in production; in dev (INT-326's lane); otherwise only on the
    synthetic deployment that declares its hosted clip lane (INT-443)."""
    if env.get(ENV_INTAKE_ENV, "dev").lower().startswith("prod"):
        return False
    return is_dev_env(env) or hosted_clip_lane_declared(env)


@dataclass(frozen=True)
class CatalogueRow:
    """One admitted text and the context it is pre-baked in (INT-443)."""

    text_tr: str
    delivery_context: DeliveryContext


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
    #: every admitted text with the context it is delivered in: what the
    #: pre-bake synthesises (INT-443). RED rows are listed and never baked.
    rows: tuple[CatalogueRow, ...] = ()

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
    rows: list[CatalogueRow] = []
    for path in sorted(dist_root.glob(f"*/{clip_manifest_filename('*', locale)}")):
        voice = path.name.removeprefix(prefix).removesuffix(_MANIFEST_SUFFIX)
        manifest = load_clip_manifest(
            dist_root, pack_id=path.parent.name, voice=voice, locale=locale
        )
        rows += [CatalogueRow(r.text_tr, r.delivery_context) for r in manifest.entries]
    return catalogue_from_rows(rows)


def catalogue_from_rows(rows: list[CatalogueRow]) -> ScriptedCatalogue:
    hashes: set[str] = set()
    pinned: dict[str, DeliveryContext] = {}
    by_hash: dict[str, CatalogueRow] = {}
    for row in rows:
        text_hash = clip_text_hash(row.text_tr)
        hashes.add(text_hash)
        context = row.delivery_context
        if context in PINNED_CONTEXTS and pinned.get(text_hash) != "red":
            # a text that is a RED script anywhere stays RED everywhere
            pinned[text_hash] = context
        by_hash.setdefault(text_hash, row)
    baked = tuple(
        CatalogueRow(row.text_tr, pinned.get(text_hash, row.delivery_context))
        for text_hash, row in sorted(by_hash.items())
    )
    return ScriptedCatalogue(
        text_hashes=frozenset(hashes), pinned_contexts=MappingProxyType(pinned), rows=baked
    )


def with_delivery_lines(catalogue: ScriptedCatalogue) -> ScriptedCatalogue:
    """``catalogue`` widened by the fixed conversational delivery lines (INT-414).

    Widening only: every manifest row stays admitted with whatever else the
    catalogue carries about it (``dataclasses.replace`` keeps every other
    field), and the lines added are the verbatim ``tr`` catalogue strings of
    :mod:`intake_api.dev_voice_delivery` — fixed copy with no slot a patient's
    words could fill."""
    return dataclasses.replace(
        catalogue, text_hashes=catalogue.text_hashes | delivery_text_hashes()
    )


class AppCatalogueError(ClipCacheError):
    """The app's scripted catalogue is not the file its generator writes."""


class _AppRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=200)
    text_tr: str = Field(min_length=1, max_length=600)
    delivery_context: str


class _AppCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    locale: str
    source: str
    rows: list[_AppRow]


def load_app_catalogue(path: Path, *, locale: str = DEFAULT_LOCALE) -> list[CatalogueRow]:
    """Every row of the app's committed catalogue, validated as a whole.

    Raises :class:`AppCatalogueError` for a file that is not the generator's
    shape, another locale, a text any TTS guard refuses (a numeral, markup),
    an unknown or ``red`` context, or a text listed twice. Never narrows a bad
    file to its good rows: a catalogue is an allow-list, and a list somebody
    edited by hand is not the one the test held to the code.
    """
    try:
        parsed = _AppCatalogue.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        raise AppCatalogueError("app catalogue: not the generator's shape") from None
    if parsed.version != 1 or parsed.locale != locale:
        raise AppCatalogueError("app catalogue: unknown version or another locale")
    rows: list[CatalogueRow] = []
    seen: set[str] = set()
    for row in parsed.rows:
        try:
            assert_speakable_tr(row.text_tr)
        except UnspeakableScriptError:
            raise AppCatalogueError("app catalogue: a row no TTS may see") from None
        context = row.delivery_context
        if context not in DELIVERY_CONTEXTS or context == "red":
            # RED is pre-positioned on the device and never fetched (invariant 21)
            raise AppCatalogueError("app catalogue: an unknown or red delivery context")
        if row.text_tr in seen:
            raise AppCatalogueError("app catalogue: a text listed twice")
        seen.add(row.text_tr)
        rows.append(CatalogueRow(row.text_tr, cast("DeliveryContext", context)))
    return rows


def scripted_catalogue_from_env(env: Mapping[str, str] | None = None) -> ScriptedCatalogue | None:
    """The compiled manifests under :func:`george_clip_dist_root` and the
    app's catalogue (INT-443), or ``None`` when either is unreadable or
    tampered, or both are empty — nothing the route could safely admit. An
    absent app catalogue is an empty one. Ids-only logs (invariant 6)."""
    env = os.environ if env is None else env
    try:
        compiled = load_scripted_catalogue(george_clip_dist_root())
    except (ClipCacheError, OSError):
        logger.warning("george lane unconfigured: compiled clip catalogue unreadable or tampered")
        return None
    app_path = Path(env.get(ENV_APP_CATALOGUE) or APP_CATALOGUE_DEFAULT)
    try:
        app_rows = load_app_catalogue(app_path) if app_path.is_file() else []
    except (AppCatalogueError, OSError):
        logger.warning("george lane unconfigured: the app's scripted catalogue is refused")
        return None
    catalogue = catalogue_from_rows([*compiled.rows, *app_rows])
    if not catalogue.text_hashes:
        logger.warning("george lane unconfigured: no catalogue to admit text from")
        return None
    return with_delivery_lines(catalogue)


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
