"""The DSAR export as a human-readable PDF (INT-037).

Scope: the data-subject export document and nothing else. INT-084's
clinician-note renderer is a separate artefact with its own layout and its own
sign-off; this one answers KVKK m.13 to the patient.

Every fixed string on the page — the title, each section heading, the footer —
renders from ``docs/legal/strings.yaml`` through the hash-bound loader, the
same way :mod:`intake_platform.consent.texts` binds consent copy. There is no
default anywhere in this module: with the file absent (today, pending INT-210)
the caller has already failed closed before reaching here, and with the file
present the document carries counsel's words, byte-for-byte, and records the
hash of the file it read.
"""

from __future__ import annotations

from dataclasses import dataclass

from intake_platform.legal import LegalStrings
from intake_platform.pdf import render_text_pdf

from intake_api.dsar.export import ExportView
from intake_api.dsar.strings import DSAR_EXPORT_SECTIONS, section_key

__all__ = ["ExportDocument", "render_export_document"]


@dataclass(frozen=True)
class ExportDocument:
    """The rendered document plus the binding that proves what it said."""

    pdf: bytes
    legal_strings_version: str
    legal_strings_hash: str


def render_export_document(view: ExportView, *, strings: LegalStrings) -> ExportDocument:
    """Render the export document. Deterministic for a given view."""
    lines: list[str] = [
        f"subject: {view.patient_id}",
        f"generated_at: {view.generated_at.isoformat()}",
        f"legal_strings_version: {strings.version}",
        f"legal_strings_sha256: {strings.text_hash}",
        "",
    ]
    for section_id in DSAR_EXPORT_SECTIONS:
        body = view.section_lines.get(section_id, ())
        lines.append(strings.values[section_key(section_id)])
        lines.extend(body if body else ("-",))
        lines.append("")
    lines.append(strings.values["dsar_export.footer"])
    return ExportDocument(
        pdf=render_text_pdf(title=strings.values["dsar_export.title"], lines=lines),
        legal_strings_version=strings.version,
        legal_strings_hash=strings.text_hash,
    )
