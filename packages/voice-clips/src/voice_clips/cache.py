"""The manifest the compiler emitted, and the bucket the clips land in.

**The key is the compiler's, never this module's.** files/03 §4.9.1 row 10
keys the cache by ``sha256(text_tr, voice_id)``, and the compiler already
computed that — it is the ``clip_id`` on every manifest row. The Talker looks
a clip up by exactly that id, so if anything here re-derived it (a different
Unicode normalisation, a different separator, a different case fold) every
lookup would miss and every scripted turn would fall through to dynamic TTS:
slower, and invisible, because a cache miss is not an error. So this module
carries no hasher. :func:`clip_object_key` takes the id verbatim and prefixes
it; a test in tests/voice asserts the whole package imports no ``hashlib``.

What it *does* check is the binding the compiler wrote down: a row's
``text_hash`` must still be :func:`~protocols.dsl.clip_text_hash` of that
row's ``text_tr``. That is the tampered-pack control files/10 §9 asks for on
the "Protocol registry & clip cache" row — a pack whose text was edited after
compilation has a clip that no longer says what the pack says.

The object-store seam follows :mod:`intake_platform.documents`: a narrow
``Protocol`` covering only the calls this module makes, plus an identity
function that proves under mypy that the real MinIO client still satisfies it.
The narrow slice is deliberate — the clip bucket has no quarantine flow, no
patient segment and no consent scope, because a clip belongs to a protocol
version rather than to a person.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from clinical_schemas.common import FrozenModel, Ref, Sha256
from minio import Minio
from minio.error import S3Error
from protocols.dsl import ClipManifestEntry, clip_text_hash
from protocols.locale_text import DEFAULT_LOCALE
from pydantic import Field, ValidationError

from voice_clips.delivery import DeliveryContext, DeliveryProfile, delivery_context_for_subject
from voice_clips.errors import ClipCacheError

__all__ = [
    "CLIP_KEY_PREFIX",
    "CLIP_MEDIA_TYPE",
    "DEFAULT_CLIPS_BUCKET",
    "ENV_CLIPS_BUCKET",
    "ClipCache",
    "ClipManifestRow",
    "ClipObjectStore",
    "CompiledClipManifest",
    "ManifestNotFoundError",
    "ManifestSchemaError",
    "ManifestTamperedError",
    "ManifestLocaleMismatchError",
    "ManifestVoiceMismatchError",
    "as_clip_storage",
    "clip_cache_from_env",
    "clip_manifest_filename",
    "clip_object_key",
    "discover_packs",
    "load_clip_manifest",
]

#: One flat namespace per (locale, voice, delivery profile) under the bucket.
#: No pack id in the key: two packs that share a scripted sentence share its
#: clip, which is the point of keying by the text hash in the first place — as
#: long as they deliver it the same way (INT-415). Two *locales* never do,
#: even where the bytes coincide — a short string can be identical in two
#: languages and is not the same utterance in either (INT-297).
CLIP_KEY_PREFIX: Final = "clips"
CLIP_MEDIA_TYPE: Final = "audio/ogg"
DEFAULT_CLIPS_BUCKET: Final = "intake-clips"

ENV_CLIPS_BUCKET: Final = "INTAKE_CLIPS_BUCKET"
ENV_MINIO_ENDPOINT: Final = "MINIO_ENDPOINT"
ENV_MINIO_ACCESS_KEY: Final = "MINIO_ROOT_USER"
ENV_MINIO_SECRET_KEY: Final = "MINIO_ROOT_PASSWORD"  # noqa: S105 — env var name
ENV_MINIO_SECURE: Final = "INTAKE_MINIO_SECURE"

_DEFAULT_MINIO_ENDPOINT: Final = "127.0.0.1:9000"
_DEFAULT_MINIO_ACCESS_KEY: Final = "intake-dev"
_DEFAULT_MINIO_SECRET_KEY: Final = "intake-dev-only"  # noqa: S105 — dev compose role
_MISSING_OBJECT_CODES: Final = frozenset({"NoSuchKey", "NoSuchObject"})


class ManifestError(ClipCacheError):
    """Base for every refusal to accept a compiled clip manifest."""


class ManifestNotFoundError(ManifestError):
    """No manifest was compiled for this pack and voice."""


class ManifestSchemaError(ManifestError):
    """The manifest on disk is not the shape the compiler emits."""


class ManifestVoiceMismatchError(ManifestError):
    """The manifest was keyed for another voice than the one requested."""


class ManifestLocaleMismatchError(ManifestError):
    """The manifest was keyed for another locale than the one requested.

    Separate from the voice mismatch on purpose: two locales may be pinned to
    one voice, so a voice check alone would pass on exactly the confusion that
    matters — another language's clip, in the right voice, in this session
    (INT-297).
    """


class ManifestTamperedError(ManifestError):
    """A row's text no longer hashes to the key the compiler wrote."""


class ClipManifestRow(FrozenModel):
    """One row of compiler output (e) (files/03 §6), as written to disk.

    The field set is the compiler's, flat, and it is validated strictly:
    ``FrozenModel`` forbids extras, so a manifest that grew a field the builder
    does not understand is a refusal rather than a partial read.
    """

    text_hash: Sha256 = Field(description="clip_text_hash of the scripted text.")
    clip_id: Ref = Field(description="sha256(text_tr, voice_id, locale), minted by the compiler.")
    voice: str = Field(description="Voice the clip id is keyed for.")
    locale: str = Field(
        default=DEFAULT_LOCALE, description="Locale the clip id is keyed for (INT-297)."
    )
    text_tr: str = Field(description="The expanded script for that locale, spoken verbatim.")
    scripted: bool = Field(description="True where paraphrase is never permitted.")
    subject: str = Field(description="Slot linkId, rule id or instrument item id.")

    @property
    def entry(self) -> ClipManifestEntry:
        """The same row as the compiler's in-memory type, so one key helper
        serves both the compiler's manifest and this one."""
        return ClipManifestEntry(
            text_hash=self.text_hash,
            clip_id=self.clip_id,
            voice=self.voice,
            locale=self.locale,
        )

    @property
    def delivery_context(self) -> DeliveryContext:
        """How this row is delivered, read from whose text it is (INT-415): a
        rule script is RED, an instrument item is instrument, a slot is routine."""
        return delivery_context_for_subject(self.subject)


class CompiledClipManifest(FrozenModel):
    """``clips.<locale>.<voice>.json`` for one pack."""

    pack_id: str = Field(description="Pack the manifest was compiled from.")
    voice: str = Field(description="Voice every clip id is keyed for.")
    locale: str = Field(
        default=DEFAULT_LOCALE, description="Locale every clip id is keyed for (INT-297)."
    )
    resolved_protocol_hash: Sha256 = Field(description="Pinned per session (files/03 §6).")
    entries: tuple[ClipManifestRow, ...] = Field(description="Every clippable string.")


def clip_manifest_filename(voice: str, locale: str = DEFAULT_LOCALE) -> str:
    """The compiler's own artefact name (protocols.compile.bundle)."""
    return f"clips.{locale}.{voice}.json"


def clip_object_key(entry: ClipManifestEntry, *, profile: DeliveryProfile) -> str:
    """``clips/<locale>/<voice>/<profile key>/<clip_id>``, with the clip id
    taken verbatim and never re-derived.

    The locale is a path segment as well as part of the id, so a bucket listing
    reads as one namespace per language and a misfiled clip is visible rather
    than merely improbable (INT-297). The delivery profile's id and version are
    a segment too (INT-415), so the same text delivered two ways is two
    objects, and a retuned profile (version bump) is a miss that re-synthesises
    rather than a hit that replays the old tuning. The compiler's ``clip_id``
    and its ``text_hash`` binding are unchanged (invariant 10).
    """
    return f"{CLIP_KEY_PREFIX}/{entry.locale}/{entry.voice}/{profile.key}/{entry.clip_id}"


def discover_packs(dist_root: Path, voice: str, locale: str = DEFAULT_LOCALE) -> tuple[str, ...]:
    """Every compiled pack under ``dist_root`` carrying a manifest for (locale, voice)."""
    name = clip_manifest_filename(voice, locale)
    return tuple(sorted(path.parent.name for path in dist_root.glob(f"*/{name}")))


def load_clip_manifest(
    dist_root: Path, *, pack_id: str, voice: str, locale: str = DEFAULT_LOCALE
) -> CompiledClipManifest:
    """Read and validate one compiled clip manifest."""
    path = dist_root / pack_id / clip_manifest_filename(voice, locale)
    if not path.is_file():
        raise ManifestNotFoundError(
            f"no compiled clip manifest at {path} — run `make protocols-compile "
            f"PACK={pack_id} VOICE={voice} LOCALE={locale}` first"
        )
    try:
        manifest = CompiledClipManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ManifestSchemaError(f"{path} is not a compiled clip manifest: {exc}") from exc
    if manifest.voice != voice:
        raise ManifestVoiceMismatchError(
            f"{path} was compiled for voice {manifest.voice!r}, not {voice!r}"
        )
    if manifest.locale != locale:
        raise ManifestLocaleMismatchError(
            f"{path} was compiled for locale {manifest.locale!r}, not {locale!r}"
        )
    keys: dict[str, str] = {}
    for row in manifest.entries:
        if row.voice != voice:
            raise ManifestVoiceMismatchError(
                f"{path} row {row.clip_id} is keyed for voice {row.voice!r}, not {voice!r}"
            )
        if row.locale != locale:
            raise ManifestLocaleMismatchError(
                f"{path} row {row.clip_id} is keyed for locale {row.locale!r}, not {locale!r}"
            )
        seen = keys.setdefault(row.clip_id, row.text_tr)
        if seen != row.text_tr:
            raise ManifestTamperedError(
                f"{path} row {row.subject}: clip id {row.clip_id} is claimed by two "
                "different strings — one synthesised clip cannot speak both, and "
                "storing whichever was written last decides by file order what a "
                "patient hears (INT-297)"
            )
        if clip_text_hash(row.text_tr) != row.entry.text_hash:
            raise ManifestTamperedError(
                f"{path} row {row.subject}: text_tr no longer hashes to "
                f"{row.entry.text_hash} — the pack was edited after it was compiled, "
                "so its clip would no longer say what the pack says"
            )
    return manifest


class ClipObjectStore(Protocol):
    """The slice of the S3 client this module uses, call-compatible with
    :class:`minio.Minio` (pinned by :func:`as_clip_storage` under mypy)."""

    def bucket_exists(self, bucket_name: str) -> bool: ...

    def make_bucket(
        self, bucket_name: str, location: str | None = ..., object_lock: bool = ...
    ) -> None: ...

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: io.BytesIO,
        length: int,
        content_type: str = ...,
    ) -> object: ...

    def stat_object(self, bucket_name: str, object_name: str) -> object: ...


def as_clip_storage(client: Minio) -> ClipObjectStore:
    """Identity at runtime; at type-check time, the proof that the real MinIO
    client still satisfies :class:`ClipObjectStore`."""
    return client


@dataclass
class ClipCache:
    """One bucket of agent-voice clips, addressed by the compiler's clip ids."""

    client: ClipObjectStore
    bucket: str = DEFAULT_CLIPS_BUCKET
    _ensured: bool = field(default=False, repr=False)

    def ensure_bucket(self) -> None:
        if self._ensured:
            return
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        self._ensured = True

    def has(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
        except S3Error as exc:
            if exc.code in _MISSING_OBJECT_CODES:
                return False
            raise
        return True

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data), CLIP_MEDIA_TYPE)


def clip_cache_from_env() -> ClipCache:
    """Wire the cache to the compose MinIO role, overridable per deployment."""
    client = Minio(
        os.environ.get(ENV_MINIO_ENDPOINT, _DEFAULT_MINIO_ENDPOINT),
        access_key=os.environ.get(ENV_MINIO_ACCESS_KEY, _DEFAULT_MINIO_ACCESS_KEY),
        secret_key=os.environ.get(ENV_MINIO_SECRET_KEY, _DEFAULT_MINIO_SECRET_KEY),
        secure=os.environ.get(ENV_MINIO_SECURE, "") == "true",
    )
    return ClipCache(
        client=as_clip_storage(client),
        bucket=os.environ.get(ENV_CLIPS_BUCKET, DEFAULT_CLIPS_BUCKET),
    )
