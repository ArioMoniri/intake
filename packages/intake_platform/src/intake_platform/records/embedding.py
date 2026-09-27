"""The record-index embedding seam — and why it refuses today (INT-123).

files/03 §4.9 is canonical: *"a model that is not in §4.9.1 is not pinned"*.
§4.9.1 has twenty-one rows and **none of them is a record or text embedder**.
Row 18 is an embedding model, but a *speaker* embedding: biometric, ephemeral,
per-session and never persisted (invariant 15). Persisting one would turn a
diarization gate into biometric identification, so it is the one row this seam
must never be pointed at.

Choosing the model is not an engineering call. CLAUDE.md invariant 19 says what
a pin is — open weights, commercially usable, licence read from the raw LICENSE
blob and recorded with ``licence_verified_at``, weights pinned by
``model_id@revision + sha256`` — and §4.9.0 says which licences pass. Until the
owner adds a row, :data:`RECORD_EMBEDDING_ROW` is ``None`` and the default
embedder refuses every call with :class:`EmbeddingModelUnregistered`. Nothing
falls back to another model or a vendor endpoint: on the PHI path that would be
the invariant-19 defect, so the absence of a fallback is the control.

Build the mechanism, wire the gate, make it fail closed, leave the content
empty: the index, the retrieval Work and the citations are all real and are
exercised with recorded fixture vectors in the test tree.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

__all__ = [
    "MODEL_REF_SHAPE",
    "RECORD_EMBEDDING_ROW",
    "EmbeddingModelUnpinned",
    "EmbeddingModelUnregistered",
    "EmbeddingRefused",
    "EmbeddingShapeRefused",
    "NoEmbeddingModel",
    "RecordEmbedder",
    "default_record_embedder",
    "embed_checked",
    "pinned_model_ref",
]

#: The files/03 §4.9.1 row that pins the record embedder. ``None`` means **no
#: row exists** — not "not running", which is what ``self_hosted_now: false``
#: means in the registry. tests/records/test_record_index.py reads the table
#: and fails the day a row appears, so this cannot silently stay ``None``.
RECORD_EMBEDDING_ROW: Final[int | None] = None

#: ``org/model@revision``: a revision is a commit hash, never a branch or a tag
#: (invariant 14 — weights pinned by ``model_id@revision + sha256``).
MODEL_REF_SHAPE: Final = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+@[0-9a-f]{7,40}$")

_ASK: Final = (
    "files/03 §4.9.1 names no record-embedding model, so none is pinned: the owner adds "
    "the row (open weights, licence read from the raw LICENSE blob, model_id@revision + "
    "sha256) before any record is embedded"
)


class EmbeddingRefused(RuntimeError):
    """Base for every refusal to embed a patient's confirmed record."""


class EmbeddingModelUnregistered(EmbeddingRefused, LookupError):
    """No §4.9.1 row pins a record embedder."""


class EmbeddingModelUnpinned(EmbeddingRefused):
    """The embedder does not name a ``model_id@revision`` or a dimension."""


class EmbeddingShapeRefused(EmbeddingRefused, ValueError):
    """The embedder answered with the wrong number or shape of vectors."""


class RecordEmbedder(Protocol):
    """What the index needs from an embedding model, and nothing more.

    ``model_ref`` is stored on every row, so a vector is only ever compared with
    vectors from the same pinned model; ``dimensions`` is what the migration's
    ``vector_dims`` check holds each row to.
    """

    @property
    def model_ref(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


@dataclass(frozen=True, slots=True)
class NoEmbeddingModel:
    """The fail-closed default: every member refuses, and names the ask.

    The refusal carries no text it was asked to embed (invariant 6).
    """

    @property
    def model_ref(self) -> str:
        raise EmbeddingModelUnregistered(_ASK)

    @property
    def dimensions(self) -> int:
        raise EmbeddingModelUnregistered(_ASK)

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        raise EmbeddingModelUnregistered(_ASK)


def default_record_embedder() -> RecordEmbedder:
    """The embedder a composition root gets while §4.9.1 names none."""
    return NoEmbeddingModel()


def pinned_model_ref(embedder: RecordEmbedder) -> str:
    """The embedder's pin, or a refusal if it is not one."""
    model_ref = embedder.model_ref
    if not MODEL_REF_SHAPE.fullmatch(model_ref):
        raise EmbeddingModelUnpinned(
            "an embedder names its weights as org/model@<commit>; a branch, a tag or a "
            "bare model id is not a pin (invariant 14)"
        )
    if embedder.dimensions < 1:
        raise EmbeddingModelUnpinned("an embedder declares a positive dimension")
    return model_ref


def embed_checked(embedder: RecordEmbedder, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
    """Embed, then hold the answer to the embedder's own declaration."""
    dimensions = embedder.dimensions
    vectors = embedder.embed(texts)
    if len(vectors) != len(texts):
        raise EmbeddingShapeRefused(f"asked for {len(texts)} vector(s) and received {len(vectors)}")
    for vector in vectors:
        if len(vector) != dimensions:
            raise EmbeddingShapeRefused(
                f"a vector of {len(vector)} dimensions from a model declaring {dimensions}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingShapeRefused("a vector component is not finite")
    return tuple(tuple(float(value) for value in vector) for vector in vectors)
