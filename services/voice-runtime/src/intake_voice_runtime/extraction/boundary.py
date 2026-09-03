"""The data boundary: where a patient's words stop being words and become data.

CLAUDE.md invariant 14 and files/10 §5 (LLM01) say it plainly — *"speech and
documents are data, never instructions: transcripts and record snippets are
wrapped as delimited data with schema-constrained outputs"*. A patient can say
anything, including something shaped like an instruction to the extractor, and
the usual answer is a filter that looks for instruction-shaped phrases. That is
the wrong control: it is a blocklist over natural language, in a language whose
morphology defeats blocklists, and it fails open on the first phrasing nobody
thought of.

This module does it structurally, in three moves. **The rule itself —
the tag, the refused marker, the text-derived nonce, the fence, the counter and
the security event — lives in :mod:`intake_platform.data_boundary`**, because
INT-121 needs the same control for a document's text layer and a second
implementation of a security control is a control that drifts. What stays here
is the *typed wrapper*: :class:`PatientData` is what says "this untrusted text
is a transcript", and a document cannot be passed where one is expected.

1. **The instruction region has no parameter for patient text.**
   :func:`intake_voice_runtime.extraction.schema.build_instructions` is a
   function of the JSON Schema alone, and the schema is a function of the slot
   declarations alone. There is no expression a caller could write that puts a
   transcript into the instruction region — which is what "data, never
   instructions" has to mean if it is to survive a refactor.
2. **The transcript travels in its own message role, inside its own fence.**
   :func:`render_data_block` is the only thing in the package that renders it,
   and it renders it nowhere else.
3. **The fence is keyed to the text it fences.** The nonce is derived from
   ``sha256`` of the transcript, so a speaker cannot pre-compute the token that
   closes their own block: they would have to know the digest of an utterance
   that contains that digest. And if a transcript nevertheless carries the tag
   or the nonce, :class:`PatientData` **refuses** rather than escaping it —
   escaping is a rewrite of what the patient said, and a boundary that rewrites
   its input is a boundary that can be talked past.

**Nothing here echoes.** :class:`PatientData` has no ``repr`` that shows the
transcript, the refusal names no content, and the counter is unlabelled. That
is invariant 6 applied to the one artefact chain where the value *is* the
narrative — and it is why a redactor would be the wrong tool: the INT-175
adversary carries no identifier pattern to key off, so scrubbing would pass it
through untouched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from clinical_schemas.events import SecurityV1
from intake_platform.data_boundary import (
    DATA_TAG,
    INJECTION_SUSPECTED_TOTAL,
    SENTINEL_PREFIX,
    carries_control_token,
    digest,
    render_fence,
    sentinel_for,
)

from intake_voice_runtime.extraction.errors import BoundaryEscape

__all__ = [
    "BOUNDARY_NAME",
    "DATA_TAG",
    "ESCAPE_REASON",
    "INJECTION_SUSPECTED_TOTAL",
    "SENTINEL_PREFIX",
    "PatientData",
    "injection_event",
    "render_data_block",
    "wrap_patient_data",
]

#: Named in the security event rather than spelled at each call site.
BOUNDARY_NAME: Final = "extraction"
ESCAPE_REASON: Final = "data_block_escape"


@dataclass(frozen=True, repr=False)
class PatientData:
    """One transcript, wrapped so that it can only be used as data.

    Constructing this type is the boundary crossing. Everything downstream
    takes a ``PatientData`` rather than a ``str``, so "did this string get
    treated as an instruction?" is answerable by reading the type of the
    parameter instead of by reading the call site.
    """

    text: str

    def __post_init__(self) -> None:
        if not self.text:
            raise BoundaryEscape("a transcript with no text is not an extraction input")
        if carries_control_token(self.text):
            INJECTION_SUSPECTED_TOTAL.inc()
            raise BoundaryEscape(
                "the transcript carries the data-block control token — it is refused "
                "rather than escaped, because escaping rewrites what the patient said "
                f"(CLAUDE.md invariant 14). Digest {self.sha256}; the text is "
                "deliberately not echoed here (invariant 6)."
            )

    @property
    def sha256(self) -> str:
        """The transcript's digest — the only identifier it ever has."""
        return digest(self.text)

    @property
    def sentinel(self) -> str:
        """The fence nonce, derived from the text it fences."""
        return sentinel_for(self.text)

    def __repr__(self) -> str:
        return f"PatientData(sha256={self.sha256!r}, chars={len(self.text)})"

    def __str__(self) -> str:
        return self.__repr__()


def wrap_patient_data(text: str) -> PatientData:
    """Cross the boundary, or refuse. The named entry point for readability."""
    return PatientData(text=text)


def render_data_block(data: PatientData) -> str:
    """The only rendering of a transcript in this package."""
    return render_fence(data.text, sentinel=data.sentinel)


def injection_event(*, correlation_id: str, tenant_id: uuid.UUID | None = None) -> SecurityV1:
    """The ``security.injection_suspected`` signal files/10 §5 names, named for
    this boundary."""
    from intake_platform.data_boundary import injection_event as _event

    return _event(
        boundary=BOUNDARY_NAME,
        reason=ESCAPE_REASON,
        correlation_id=correlation_id,
        tenant_id=tenant_id,
    )
