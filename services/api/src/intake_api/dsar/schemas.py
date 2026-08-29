"""Request/response bodies for the DSAR surface (INT-037), pydantic v2.

Two boundary rules the shapes encode. ``target_ref`` is a REFERENCE and is
validated as one — ``kind:uuid`` and nothing else — because a free-text
column here would put PHI where the tracker and the audit both read
(invariant 6). And a correction is the patient's own words, so it is bounded
in length and stored encrypted, never echoed into an error.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

__all__ = [
    "DsarExportOut",
    "DsarPdfOut",
    "DsarRectifyIn",
    "DsarRectifyOut",
    "DsarRequestOut",
    "DsarScheduleOut",
    "TARGET_REF_SHAPE",
]

#: ``note:<uuid>`` / ``visit:<uuid>`` / ``document:<uuid>`` — the record kinds
#: a data subject can ask to have corrected in this slice.
TARGET_REF_SHAPE = re.compile(r"^(note|visit|document):[0-9a-fA-F-]{36}$")

Correction = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class DsarRequestOut(BaseModel):
    """One row of the KVKK m.13 tracker: ids and clocks only."""

    request_id: uuid.UUID
    kind: Literal["export", "delete", "rectify"]
    status: Literal["received", "scheduled", "completed", "cancelled"]
    received_at: str
    due_at: str
    grace_ends_at: str | None
    completed_at: str | None
    overdue: bool


class DsarScheduleOut(DsarRequestOut):
    """An erasure request: the grace clock plus what filing it already did."""

    shares_cancelled: int


class DsarPdfOut(BaseModel):
    media_type: Literal["application/pdf"]
    sha256: str
    base64: str


class DsarExportOut(BaseModel):
    request_id: uuid.UUID
    generated_at: str
    legal_strings_version: str
    legal_strings_hash: str
    fhir_bundle: dict[str, Any]
    pdf: DsarPdfOut


class DsarRectifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_ref: str = Field(max_length=64)
    correction: Correction

    @field_validator("target_ref")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        if not TARGET_REF_SHAPE.fullmatch(value):
            raise ValueError("target_ref must be '<note|visit|document>:<uuid>'")
        return value


class DsarRectifyOut(BaseModel):
    request_id: uuid.UUID
    rectification_id: uuid.UUID
    target_ref: str
    status: Literal["completed"]
