"""The two byte-level read paths, and the engine gate in front of both (INT-122).

:mod:`~intake_platform.records.enabiz` and :mod:`~intake_platform.records.mhrs`
parse what a document *printed*: regions, and text. Something has to turn the
bytes of an upload into those regions first, and files/03 §4.9.1 names the
only two components allowed to:

* **row 20, "OCR — text layer"** — ``tesseract-ocr``; *"SMS screenshots for
  the appointment datetime"*. The MHRS screenshot path goes through this row.
* **row 21, "OCR — layout / structure"** — ``docling`` (and/or ``marker``);
  *"Table and column recovery on the mandated six-column Akılcı Laboratuvar
  report shape"*. The e-Nabız export path goes through this row.

**Neither row is licence-verified, and that is the gate, not a gap.** §4.9.2(f):
*"The OCR layer has never been licence-verified … Gate: no OCR component
reaches the PHI path without a ``licence_verified_at`` entry read from the raw
LICENSE blob."* CLAUDE.md invariant 19 says where that entry lives — the model
registry, ``observability/registry.yaml`` — and today it has no row for either
engine. So :func:`require_document_engine` refuses both, **before any byte
meets an engine**, with a :class:`DocumentReadStatus` that says which fact is
missing. It restates row 9's gate
(:func:`~intake_platform.records.lab_model.require_phi_ready`) for rows 20-21:
registered under a pin the table names, licence read from the blob, declared
self-hostable and on the PHI path, and served.

**An engine that reads nothing is a refusal, never an empty reading.** A
screenshot with no text is not "no appointment", and a PDF with no text layer
is not "an export with no labs" — HUMAN_BLOCKERS.md **HB-A1** says *"Do not
assume a text layer"*, and this is what not assuming one looks like.
``NoLayout`` (the wired default while the engine-and-sandbox ADR, files/10 §4,
is open) and a scanned page both land on :attr:`DocumentReadStatus.NOT_READ`.

**What the gate does not do.** It proves a row is registered; it does not
prove the ``layout`` a caller passes *is* that row's engine. That binding is
the adapter's, exactly as row 9's gateway can only be constructed from a
verified pin — and no row-20/21 adapter exists yet, because choosing one is the
open ADR. Whether an e-Nabız export also needs row 20 (a scanned PDF needs OCR
under the layout step) is HB-A1's question; an adapter that OCRs internally
carries both pins.

**No network, no locator** (the "no scraping" clause): every entry point takes
bytes someone already holds. **No message echoes what a document printed**
(invariant 6).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict

from intake_platform.records.document import (
    LayoutExtractor,
    LayoutUnavailable,
    TextRegion,
    fence_document_regions,
    read_document_regions,
)
from intake_platform.records.enabiz import LabTableImport, import_lab_table
from intake_platform.records.extraction import TerminologyBinder
from intake_platform.records.lab_model import REGISTRY_PATH
from intake_platform.records.mhrs import BranchVocabulary, parse_mhrs_sms
from intake_platform.records.unit_guard import SHIPPED_EXPECTATIONS, ExpectationTable
from intake_platform.records.visit_candidate import CandidateVisitFields

__all__ = [
    "DOCUMENT_ENGINE_PINS",
    "OCR_LAYOUT_ROW",
    "OCR_TEXT_LAYER_ROW",
    "DocumentNotRead",
    "DocumentReadStatus",
    "read_enabiz_export",
    "read_mhrs_screenshot",
    "require_document_engine",
]

#: files/03 §4.9.1 row 20 — "OCR — text layer".
OCR_TEXT_LAYER_ROW: Final = 20

#: files/03 §4.9.1 row 21 — "OCR — layout / structure".
OCR_LAYOUT_ROW: Final = 21

#: The pins rows 20 and 21 name, verbatim. A registry component with any other
#: name is not either row, whatever it can do: a model that is not in §4.9.1 is
#: not pinned.
DOCUMENT_ENGINE_PINS: Final[Mapping[int, tuple[str, ...]]] = MappingProxyType(
    {
        OCR_TEXT_LAYER_ROW: ("tesseract-ocr",),
        OCR_LAYOUT_ROW: ("docling", "marker"),
    }
)


class DocumentReadStatus(enum.StrEnum):
    """Why a document was not read. Closed; each member is a distinct fix.

    Collapsing them would send whoever reads the refusal looking for the wrong
    thing: an unregistered engine is a licence audit and an ADR, a registered
    one that is not served is a deployment, and a served one that read nothing
    is a property of the document.
    """

    #: No registry row carries a pin this row of §4.9.1 names.
    ENGINE_NOT_REGISTERED = "engine_not_registered"
    #: The row records no dated reading of the raw LICENSE blob (§4.9.2(f)).
    ENGINE_LICENCE_UNVERIFIED = "engine_licence_unverified"
    #: The row is not declared self-hostable and on the PHI path (invariant 19).
    ENGINE_OFF_PHI_PATH = "engine_off_phi_path"
    #: Registered, verified and declared, and no host serves it.
    ENGINE_NOT_SERVED = "engine_not_served"
    #: The engine ran and produced no region: no text layer, or nothing legible.
    NOT_READ = "not_read"


_EXPLANATIONS: Final[Mapping[DocumentReadStatus, str]] = MappingProxyType(
    {
        DocumentReadStatus.ENGINE_NOT_REGISTERED: (
            "observability/registry.yaml carries no component under a pin this row names, "
            "so no engine may read a patient's document through it (files/03 §4.9.2(f))"
        ),
        DocumentReadStatus.ENGINE_LICENCE_UNVERIFIED: (
            "the registry row records no dated reading of the raw LICENSE blob; a licence "
            "is verified from the blob, never a badge or a card tag (CLAUDE.md invariant 19)"
        ),
        DocumentReadStatus.ENGINE_OFF_PHI_PATH: (
            "the registry row is not declared self-hostable and on the PHI path, so it may "
            "not read a patient's document (CLAUDE.md invariant 19)"
        ),
        DocumentReadStatus.ENGINE_NOT_SERVED: (
            "the engine is registered and licence-verified and no host serves it; there is "
            "no fallback, because a cloud reader on the PHI path is what invariant 19 forbids"
        ),
        DocumentReadStatus.NOT_READ: (
            "the engine produced no region, so the document stays unread; that is a refusal, "
            "never an empty reading (HB-A1: do not assume a text layer)"
        ),
    }
)


class DocumentNotRead(RuntimeError):
    """The upload was not turned into regions, and :attr:`status` says why.

    The message names the §4.9.1 row and the status and nothing the upload
    carried — not its bytes, not its text, not its document id (invariant 6).
    """

    def __init__(self, status: DocumentReadStatus, *, row: int) -> None:
        self.status = status
        self.row = row
        super().__init__(
            f"files/03 §4.9.1 row {row}: {status.value} — {_EXPLANATIONS[status]}. "
            "Nothing the upload carried is echoed here (invariant 6)."
        )


class _EngineRow(BaseModel):
    """Only the fields the gate reads; every one defaults to the refusing value.

    Validation proper is ``intake_probes.registry``'s. This reader restates
    none of its rules, and a row missing a fact here is refused, not repaired.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    component: str
    self_hostable: bool = False
    self_hosted_now: bool = False
    phi_path: bool = False
    licence_verified_at: date | None = None
    licence_blob_sha256: str | None = None

    def refusal(self) -> DocumentReadStatus | None:
        if self.licence_verified_at is None or not self.licence_blob_sha256:
            return DocumentReadStatus.ENGINE_LICENCE_UNVERIFIED
        if not (self.phi_path and self.self_hostable):
            return DocumentReadStatus.ENGINE_OFF_PHI_PATH
        if not self.self_hosted_now:
            return DocumentReadStatus.ENGINE_NOT_SERVED
        return None


def require_document_engine(row: int, *, registry_path: Path | None = None) -> str:
    """The registered component that may read documents for ``row``, or a refusal.

    Candidates are taken in the order §4.9.1 names them; the first that is
    ready is returned, and when none is, the first candidate's missing fact is
    the status. :class:`ValueError` for a row that is not 20 or 21 — that is a
    caller's mistake, not a property of the registry.
    """
    pins = DOCUMENT_ENGINE_PINS.get(row)
    if pins is None:
        raise ValueError(
            f"files/03 §4.9.1 row {row} is not a document-reading engine; "
            f"rows {sorted(DOCUMENT_ENGINE_PINS)} are"
        )
    document = yaml.safe_load((registry_path or REGISTRY_PATH).read_text(encoding="utf-8"))
    registered = {raw.get("component"): raw for raw in document["components"]}
    refused: list[DocumentReadStatus] = []
    for pin in pins:
        raw = registered.get(pin)
        if raw is None:
            continue
        candidate = _EngineRow.model_validate(raw)
        refusal = candidate.refusal()
        if refusal is None:
            return candidate.component
        refused.append(refusal)
    raise DocumentNotRead(
        refused[0] if refused else DocumentReadStatus.ENGINE_NOT_REGISTERED, row=row
    )


def _read_regions(
    row: int,
    data: bytes,
    content_type: str,
    *,
    layout: LayoutExtractor,
    registry_path: Path | None,
) -> tuple[TextRegion, ...]:
    """The gate, then the engine; an engine that reads nothing is a refusal."""
    require_document_engine(row, registry_path=registry_path)
    try:
        return read_document_regions(data, content_type, layout=layout)
    except LayoutUnavailable as err:
        raise DocumentNotRead(DocumentReadStatus.NOT_READ, row=row) from err


def read_mhrs_screenshot(
    data: bytes,
    content_type: str,
    *,
    layout: LayoutExtractor,
    document_ref: str,
    vocabulary: BranchVocabulary,
    registry_path: Path | None = None,
) -> CandidateVisitFields:
    """An MHRS SMS screenshot → a candidate visit, through row 20 or not at all.

    What comes back is :func:`~intake_platform.records.mhrs.parse_mhrs_sms`'s
    candidate — never a visit; :func:`~intake_platform.records.visit_candidate.
    confirm_visit_candidate` is the only way on.
    """
    regions = _read_regions(
        OCR_TEXT_LAYER_ROW, data, content_type, layout=layout, registry_path=registry_path
    )
    return parse_mhrs_sms(
        fence_document_regions(regions).text, document_ref=document_ref, vocabulary=vocabulary
    )


def read_enabiz_export(
    data: bytes,
    content_type: str,
    *,
    layout: LayoutExtractor,
    document_ref: str,
    observed_at: datetime,
    table: ExpectationTable = SHIPPED_EXPECTATIONS,
    terminology: TerminologyBinder | None = None,
    registry_path: Path | None = None,
) -> LabTableImport:
    """A patient-exported e-Nabız document → guarded, unconfirmed lab items, through row 21.

    Every item is unconfirmed and boxed into ``document_ref``, and every lab
    value carries an INT-124 verdict (:func:`~intake_platform.records.enabiz.
    import_lab_table`).
    """
    regions = _read_regions(
        OCR_LAYOUT_ROW, data, content_type, layout=layout, registry_path=registry_path
    )
    return import_lab_table(
        regions,
        document_ref=document_ref,
        observed_at=observed_at,
        table=table,
        terminology=terminology,
    )
