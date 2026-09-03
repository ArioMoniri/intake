"""The one rule for untrusted text that reaches a model, in one place.

CLAUDE.md invariant 14 and files/10 §5 (LLM01): *"speech/documents/records are
data never instructions (delimited, schema-constrained)"*. INT-083 built that
control for a transcript and argued it in
:mod:`intake_voice_runtime.extraction.boundary`, which is still where the
reasoning lives; INT-121 needs the same control for a document's text layer,
and a second implementation of a security control is a control that drifts.

So the *rule* lives here — the tag, the marker that is refused, the
text-derived nonce, the fence, the counter and the security event — and each
caller keeps its own typed wrapper around it. There is deliberately no wrapper
class in this module: the wrapper is where a package says what kind of
untrusted text it is holding, and a shared one would let a transcript be
passed where a document is expected.

**Why a nonce derived from the text.** A speaker (or a hidden line in a PDF)
cannot pre-compute the token that closes their own block: they would have to
know the digest of a text that contains that digest.

**Why refusal rather than escaping.** Escaping rewrites what the patient said,
or what their document printed, and a boundary that rewrites its input is a
boundary that can be talked past. The refusal names no content: the text is
the narrative, and an exception message reaches a log (invariant 6).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Final

from clinical_schemas.events import SecurityEventCategory, SecurityV1
from prometheus_client import Counter

__all__ = [
    "CONTROL_MARKER",
    "DATA_TAG",
    "INJECTION_SUSPECTED_TOTAL",
    "SENTINEL_PREFIX",
    "DataBoundaryEscape",
    "carries_control_token",
    "digest",
    "injection_event",
    "render_fence",
    "sentinel_for",
]

#: The fence. Namespaced so it cannot collide with anything an ASR emits or a
#: lab printer prints, and matched through :meth:`str.casefold` — never a
#: Turkish locale fold, because files/03 §4.9.6 requires every identity
#: comparison to use an invariant locale (``I``/``ı`` would otherwise decide
#: whether a boundary holds).
DATA_TAG: Final = "intake:patient_data"

#: Refused outright anywhere in untrusted text: the tag's namespace prefix. It
#: is shorter than the tag so a partially-typed, partially-transcribed or
#: partially-OCR'd escape is refused too.
CONTROL_MARKER: Final = "intake:"

SENTINEL_PREFIX: Final = "INTAKE-PATIENT-DATA-"

INJECTION_SUSPECTED_TOTAL: Final = Counter(
    "sec_injection_suspected_total",
    "Suspected prompt-injection attempts refused at a data boundary (INT-083 "
    "transcripts, INT-121 documents; files/10 §5 LLM01, files/10 §9 rows "
    "llm-boundary and records). Unlabelled and value-free: the refused string is "
    "never recorded, only that a refusal happened (CLAUDE.md invariant 6).",
)


class DataBoundaryEscape(ValueError):
    """Untrusted text tried to leave its data block.

    Raised before any bytes are assembled, so the escaping string never reaches
    a prompt, a log line or this exception's own message. Each caller subclasses
    it to say *which* boundary refused.
    """


def digest(text: str) -> str:
    """The only identifier untrusted text ever has."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sentinel_for(text: str) -> str:
    """The fence nonce, derived from the text it fences."""
    return f"{SENTINEL_PREFIX}{digest(text)[:16]}"


def carries_control_token(text: str) -> bool:
    """True when the text carries the fence's control marker or its own nonce.

    Both halves matter: the marker catches a forged or partial tag, and the
    nonce catches a text that quotes the very token that would close it.
    """
    return CONTROL_MARKER in text.casefold() or sentinel_for(text) in text


def render_fence(text: str, *, sentinel: str) -> str:
    """The one rendering of untrusted text anywhere in this repository.

    The nonce rides on the opening tag: a reader (human or model) can check
    that the block it is reading is the one the system opened, and the author
    of the text cannot forge it without the digest of their own text.
    """
    return f'<{DATA_TAG} nonce="{sentinel}">\n{text}\n</{DATA_TAG}>'


def injection_event(
    *,
    boundary: str,
    reason: str,
    correlation_id: str,
    tenant_id: uuid.UUID | None = None,
) -> SecurityV1:
    """The ``security.injection_suspected`` signal files/10 §5 names.

    Every field is an id or a closed enumeration — ``SecurityV1.attributes`` is
    typed ``dict[str, Ref]``, so narrative has no carrier here even if a caller
    wanted to attach one. What the patient said, or what their document
    printed, is not in this event, and the digest is not either: an event
    stream that carried per-artefact digests would be a correlation surface.
    """
    return SecurityV1(
        category=SecurityEventCategory.INJECTION_SUSPECTED,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        attributes={"boundary": boundary, "reason": reason},
    )
