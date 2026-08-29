"""The KVKK m.11 access answer: one subject's record as FHIR R4 (INT-037).

Scope, per files/00 §3 D8: the P0 export bundles **FHIR + PDF**. The openEHR
composition joins it when INT-032 lands in P3 — it is deliberately absent
here rather than stubbed.

What it consumes and what it does not. The INT-033 exchange surface supplies
the resource models (:mod:`clinical_schemas.mappers.r4`) and the code systems
(:mod:`clinical_schemas.mappers.codes`), and the note Composition uses the
same section coding INT-033's document mapper uses. What it does NOT use is
``previsit_note_to_document_bundle``: that builder takes a full files/04 §5
``PreVisitNote``, and the record this API actually holds is a three-section
free-text note plus visit slots with no resolved protocol hash. Manufacturing
a ``SessionState`` to reach the mapper would mean inventing a ``protocol_hash``
— and inventing a value to unblock yourself is the one thing this codebase
never does (HUMAN_BLOCKERS.md rule 1). The QuestionnaireResponse is therefore
built from the stored slot rows directly, in the shape INT-033 emits.

Invariant 47 (`export_injection_guard`, files/10 §9; files/08 §0c F13)
applies here: the attacker writes the content, a compliance officer opens the
export in a spreadsheet, and KVKK m.13 obliges us to produce it. Every
free-text value crossing into the export goes through :func:`sanitise_cell` —
control characters and CRLF collapse to spaces, and a leading ``= + - @`` is
prefixed with an apostrophe per OWASP. The guard neutralises; it never
deletes, because an export that quietly drops what the patient wrote is a
worse answer than one with a visible apostrophe. The function itself moved to
``intake_platform.export_safety`` when INT-241 added a second export that
needs it; two copies of a security control are two copies that can drift.
"""

from __future__ import annotations

import html
import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from clinical_schemas.mappers import codes
from clinical_schemas.mappers.r4 import (
    Bundle,
    BundleEntry,
    CodeableConcept,
    Coding,
    Composition,
    CompositionSection,
    Identifier,
    Narrative,
    Patient,
    QrAnswer,
    QrItem,
    QuestionnaireResponse,
    Reference,
    to_wire,
)
from intake_platform.db.envelope_json import encrypted_field_from_json
from intake_platform.db.models import SessionStatus, SlotSensitivity
from intake_platform.envelope import EnvelopeCipher
from intake_platform.export_safety import sanitise_cell, sanitise_cells
from intake_platform.legal import LegalStrings

from intake_api.dsar.store import SubjectRecord
from intake_api.dsar.strings import DSAR_EXPORT_SECTIONS, section_key

__all__ = [
    "ExportView",
    "NoteView",
    "VisitView",
    "build_export_bundle",
    "build_view",
    "sanitise_cell",
]

_SUBJECT_ID_SYSTEM: Final = "urn:intake:fhir:NamingSystem:dsar-subject"
_DSAR_SECTION_SYSTEM: Final = "urn:intake:fhir:CodeSystem:dsar-export-section"

_SESSION_TO_QR_STATUS: Final[Mapping[SessionStatus, str]] = {
    SessionStatus.CREATED: "in-progress",
    SessionStatus.ACTIVE: "in-progress",
    SessionStatus.COMPLETED: "completed",
    SessionStatus.CANCELLED: "stopped",
}


def _cells(values: Iterable[object]) -> tuple[str, ...]:
    return sanitise_cells(values)


def _stamp(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


# --- the decrypted, sanitised view -------------------------------------------------


@dataclass(frozen=True)
class NoteSectionView:
    id: str
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class NoteView:
    id: uuid.UUID
    session_id: uuid.UUID
    sections: tuple[NoteSectionView, ...]


@dataclass(frozen=True)
class VisitView:
    id: uuid.UUID
    protocol_id: str
    protocol_version: str
    status: SessionStatus
    created_at: datetime
    slots: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class ExportView:
    """Everything the export renders, decrypted once and sanitised once, so
    the FHIR bundle and the PDF can never disagree about the content."""

    patient_id: uuid.UUID
    generated_at: datetime
    visits: tuple[VisitView, ...]
    notes: tuple[NoteView, ...]
    section_lines: Mapping[str, tuple[str, ...]]


def _decrypt_json(cipher: EnvelopeCipher, tenant_id: uuid.UUID, payload: Mapping[str, Any]) -> Any:
    field = encrypted_field_from_json(payload)
    return json.loads(cipher.decrypt_field(str(tenant_id), field).decode("utf-8"))


def _note_views(
    record: SubjectRecord, *, cipher: EnvelopeCipher, tenant_id: uuid.UUID
) -> tuple[NoteView, ...]:
    views: list[NoteView] = []
    for note in record.notes:
        body = _decrypt_json(cipher, tenant_id, dict(note.payload))
        sections = tuple(
            NoteSectionView(
                id=sanitise_cell(str(section.get("id", ""))),
                title=sanitise_cell(str(section.get("title", ""))),
                lines=_cells(section.get("lines", ())),
            )
            for section in body.get("sections", ())
        )
        views.append(NoteView(id=note.id, session_id=note.session_id, sections=sections))
    return tuple(views)


def _visit_views(
    record: SubjectRecord, *, cipher: EnvelopeCipher, tenant_id: uuid.UUID
) -> tuple[VisitView, ...]:
    views: list[VisitView] = []
    for visit in record.sessions:
        slots: list[tuple[str, Any]] = []
        for slot in record.slots_for(visit.id):
            value: Any = dict(slot.value)
            if slot.sensitivity is SlotSensitivity.SENSITIVE:
                value = _decrypt_json(cipher, tenant_id, value)
            slots.append((sanitise_cell(slot.slot_id), _sanitise_value(value)))
        views.append(
            VisitView(
                id=visit.id,
                protocol_id=sanitise_cell(visit.protocol_id),
                protocol_version=sanitise_cell(visit.protocol_version),
                status=visit.status,
                created_at=visit.created_at,
                slots=tuple(slots),
            )
        )
    return tuple(views)


def _sanitise_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitise_cell(value)
    if isinstance(value, dict):
        return {sanitise_cell(str(k)): _sanitise_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitise_value(item) for item in value]
    return value


def build_view(
    record: SubjectRecord,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    cipher: EnvelopeCipher,
    generated_at: datetime,
) -> ExportView:
    """Decrypt and sanitise the subject's record exactly once."""
    visits = _visit_views(record, cipher=cipher, tenant_id=tenant_id)
    notes = _note_views(record, cipher=cipher, tenant_id=tenant_id)

    lines: dict[str, tuple[str, ...]] = {
        "visits": tuple(
            " · ".join(
                _cells(
                    [
                        f"visit:{visit.id}",
                        visit.protocol_id,
                        visit.protocol_version,
                        visit.status.value,
                        _stamp(visit.created_at),
                    ]
                )
            )
            for visit in visits
        ),
        "notes": tuple(
            " · ".join(_cells([f"note:{note.id}", f"visit:{note.session_id}", section.title, line]))
            for note in notes
            for section in note.sections
            for line in section.lines
        ),
        "documents": tuple(
            " · ".join(
                _cells(
                    [
                        f"document:{doc.id}",
                        doc.media_type,
                        f"sha256:{doc.sha256}",
                        _stamp(doc.created_at),
                    ]
                )
            )
            for doc in record.documents
        ),
        "consents": tuple(
            " · ".join(
                _cells(
                    [
                        consent.scope,
                        consent.version,
                        f"text_hash:{consent.text_hash or ''}",
                        f"channel:{consent.channel or ''}",
                        _stamp(consent.granted_at),
                        f"revoked:{_stamp(consent.revoked_at)}",
                    ]
                )
            )
            for consent in record.consents
        ),
        "shares": tuple(
            " · ".join(
                _cells(
                    [
                        f"share:{share.id}",
                        f"note:{share.note_id}",
                        ",".join(str(item) for item in share.scope_sections.get("section_ids", ())),
                        f"expires:{_stamp(share.expires_at)}",
                        f"revoked:{_stamp(share.revoked_at)}",
                    ]
                )
            )
            for share in record.shares
        ),
        "rectifications": tuple(
            " · ".join(
                _cells(
                    [
                        entry.target_ref,
                        _stamp(entry.created_at),
                        str(_decrypt_json(cipher, tenant_id, dict(entry.payload))["correction"]),
                    ]
                )
            )
            for entry in record.rectifications
        ),
        "requests": tuple(
            " · ".join(
                _cells(
                    [
                        f"dsar-request:{request.id}",
                        request.kind.value,
                        request.status.value,
                        f"received:{_stamp(request.received_at)}",
                        f"due:{_stamp(request.due_at)}",
                        f"grace_ends:{_stamp(request.grace_ends_at)}",
                        f"completed:{_stamp(request.completed_at)}",
                    ]
                )
            )
            for request in record.requests
        ),
    }
    return ExportView(
        patient_id=patient_id,
        generated_at=generated_at,
        visits=visits,
        notes=notes,
        section_lines=lines,
    )


# --- FHIR ---------------------------------------------------------------------------


def _div(lines: Sequence[str]) -> Narrative:
    # quote=False: an apostrophe is the invariant-47 guard's own mark and must
    # stay legible; a text node needs only & < > escaped.
    body = "".join(f"<p>{html.escape(line, quote=False)}</p>" for line in lines)
    return Narrative(
        status="generated", div=f'<div xmlns="http://www.w3.org/1999/xhtml">{body}</div>'
    )


def _answer(value: Any) -> QrAnswer:
    if isinstance(value, bool):
        return QrAnswer(value_boolean=value)
    if isinstance(value, int):
        return QrAnswer(value_integer=value)
    if isinstance(value, float):
        return QrAnswer(value_decimal=value)
    return QrAnswer(value_string=str(value))


def _slot_item(slot_id: str, value: Any) -> QrItem | None:
    if value is None:
        return None
    if isinstance(value, dict):
        children = tuple(
            QrItem(link_id=key, answer=(_answer(inner),))
            for key, inner in value.items()
            if inner is not None
        )
        return QrItem(link_id=slot_id, item=children) if children else None
    if isinstance(value, list):
        return QrItem(link_id=slot_id, answer=tuple(_answer(item) for item in value))
    return QrItem(link_id=slot_id, answer=(_answer(value),))


def _questionnaire_response(visit: VisitView, *, subject_url: str) -> QuestionnaireResponse:
    items = tuple(
        item for slot_id, value in visit.slots if (item := _slot_item(slot_id, value)) is not None
    )
    return QuestionnaireResponse(
        identifier=Identifier(system=codes.SESSION_ID_SYSTEM, value=str(visit.id)),
        questionnaire=(
            f"{codes.PROTOCOL_CANONICAL_PREFIX}{visit.protocol_id}|{visit.protocol_version}"
        ),
        status=_SESSION_TO_QR_STATUS[visit.status],
        subject=Reference(reference=subject_url),
        authored=visit.created_at.isoformat(),
        item=items or None,
    )


def _note_composition(note: NoteView, *, subject_url: str, generated_at: datetime) -> Composition:
    return Composition(
        text=_div([codes.DOCUMENT_TITLE_TR]),
        status="final",
        type=CodeableConcept(
            coding=(Coding(system=codes.DOC_TYPE_SYSTEM, code=codes.DOCUMENT_TYPE_CODE),),
            text=codes.DOCUMENT_TYPE_CODE,
        ),
        subject=Reference(reference=subject_url),
        date=generated_at.isoformat(),
        author=(Reference(reference=subject_url),),
        title=codes.DOCUMENT_TITLE_TR,
        section=tuple(
            CompositionSection(
                title=section.id,
                code=CodeableConcept(
                    coding=(Coding(system=codes.SECTION_SYSTEM, code=section.id),),
                    text=section.title,
                ),
                text=_div(section.lines),
            )
            for section in note.sections
            if section.lines
        )
        or None,
    )


def build_export_bundle(view: ExportView, *, strings: LegalStrings) -> dict[str, Any]:
    """The subject's record as a FHIR R4 collection Bundle, wire-shaped.

    Deterministic for a given view: same subject, same ``generated_at``, same
    bytes — so re-issuing an export produces the same receipt.
    """
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "urn:intake:dsar:export")

    def full_url(name: str) -> str:
        return f"urn:uuid:{uuid.uuid5(namespace, f'{view.patient_id}:{name}')}"

    subject_url = full_url("subject")
    entries: list[BundleEntry] = [
        BundleEntry(full_url=subject_url, resource=Patient(id=str(view.patient_id)))
    ]
    section_refs: dict[str, list[Reference]] = {}

    for visit in view.visits:
        url = full_url(f"visit:{visit.id}")
        entries.append(
            BundleEntry(
                full_url=url, resource=_questionnaire_response(visit, subject_url=subject_url)
            )
        )
        section_refs.setdefault("visits", []).append(Reference(reference=url))
    for note in view.notes:
        url = full_url(f"note:{note.id}")
        entries.append(
            BundleEntry(
                full_url=url,
                resource=_note_composition(
                    note, subject_url=subject_url, generated_at=view.generated_at
                ),
            )
        )
        section_refs.setdefault("notes", []).append(Reference(reference=url))

    sections: list[CompositionSection] = []
    for section_id in DSAR_EXPORT_SECTIONS:
        lines = view.section_lines.get(section_id, ())
        refs = section_refs.get(section_id)
        if not lines and not refs:
            continue  # cmp-1: a section carries text or entries, or is absent
        sections.append(
            CompositionSection(
                title=strings.values[section_key(section_id)],
                code=CodeableConcept(
                    coding=(Coding(system=_DSAR_SECTION_SYSTEM, code=section_id),)
                ),
                text=_div(lines) if lines else None,
                entry=tuple(refs) if refs else None,
            )
        )

    cover = Composition(
        text=_div([strings.values["dsar_export.title"], strings.values["dsar_export.footer"]]),
        status="final",
        type=CodeableConcept(
            coding=(Coding(system=_DSAR_SECTION_SYSTEM, code="dsar_export"),),
            text="dsar_export",
        ),
        subject=Reference(reference=subject_url),
        date=view.generated_at.isoformat(),
        author=(Reference(reference=subject_url),),
        title=strings.values["dsar_export.title"],
        section=tuple(sections) or None,
    )
    bundle = Bundle(
        identifier=Identifier(system=_SUBJECT_ID_SYSTEM, value=str(view.patient_id)),
        type="collection",
        timestamp=view.generated_at.isoformat(),
        entry=(BundleEntry(full_url=full_url("cover"), resource=cover), *entries),
    )
    return to_wire(bundle)
