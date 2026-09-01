"""INT-084 — the three renderers, over one line model.

files/03 §11 fixes the clinician note's shape: *"CC · HPI (OLDCARTS) ·
Pertinent ROS · PMH · Meds · Allergies · FH/SH · Screening · Konuşma
özellikleri · Triage · Data gaps · Suggested focus questions ·
Sources/Provenance"*, **SOAP-compatible** with *"S = patient-reported; O =
imported objective data; A/P left for the clinician"* and a considerations
block that lists patterns, not diagnoses.

Two properties are load-bearing and are why SOAP and PDF share one line
builder rather than each formatting the note themselves:

* **Attribution survives the renderer.** Every fact line carries its marker —
  the patient's own words, a relative's condition with the relative named, a
  carried fact with the date it was first recorded, a record with its document
  id — so no rendering can flatten three different kinds of assertion into one
  clinical statement (INT-282, INT-256).
* **Provenance is reachable.** Every fact line carries its ``fNN`` handle and
  the document ends with the block that resolves each handle to a span. A note
  whose provenance lived only in a sidecar nobody rendered would satisfy the
  schema and fail the ``notes`` threat-model row's *"[R] a fact in the note
  with no provenance"*.

Nothing here emits markup. The SOAP and PDF faces are text; the FHIR face
delegates to the INT-033 mapper, whose narrative is generated, escaped XHTML.
That is the row's *"[T] XSS through note rendering (LLM05)"* answered by not
having an HTML renderer in the first place.
"""

from __future__ import annotations

from clinical_schemas.mappers.document import previsit_note_to_document_bundle
from clinical_schemas.mappers.r4 import Bundle
from intake_platform.pdf import render_document_pdf

from intake_voice_runtime.note.composer import ComposedNote, facts_by_section
from intake_voice_runtime.note.copy import NOTE_COPY_SECTIONS, NoteCopy
from intake_voice_runtime.note.facts import Attribution, NoteFact, SourceKind

__all__ = ["render_fhir_document", "render_note_pdf", "render_soap"]

#: files/03 §11 "S = patient-reported": everything the patient said or is
#: carried about them. ``imported_objective`` is the O block and is the only
#: section not listed here, which is the SOAP split stated once.
_SUBJECTIVE_SECTIONS = tuple(
    section for section in NOTE_COPY_SECTIONS if section != "imported_objective"
)
_INDENT = "  "


def _marker(fact: NoteFact, copy: NoteCopy) -> str:
    """The attribution marker, with the one detail that makes it checkable.

    A relative's line names the relative; a carried line names the date it was
    first recorded (without it, a carried fact reads as a current one, which
    is exactly the INT-247/INT-256 failure); a record line names the document.
    """
    base = copy.attribution(fact.attribution)
    if fact.attribution is Attribution.RELATIVE:
        return f"{base}: {copy.subject(fact.subject)}"
    if fact.attribution is Attribution.CARRIED and fact.span.kind is SourceKind.EARLIER_VISIT:
        return f"{base}: {fact.span.asserted_at}"
    if fact.attribution is Attribution.RECORD and fact.span.kind is SourceKind.DOCUMENT:
        return f"{base}: {fact.span.ref}"
    return base


def _fact_lines(fact: NoteFact, copy: NoteCopy) -> list[str]:
    marker = _marker(fact, copy)
    return [f"{_INDENT}[{fact.ref}] {marker} — {line}" for line in fact.lines]


def _screening_lines(composed: ComposedNote) -> list[str]:
    screening = composed.note.screening
    lines: list[str] = []
    for name in ("phq2", "gad2", "phq9", "gad7"):
        score = getattr(screening, name)
        if score is not None:
            lines.append(f"{_INDENT}{name}: {score}")
    provenance = screening.provenance
    lines.append(f"{_INDENT}administration_mode: {provenance.administration_mode}")
    lines.append(f"{_INDENT}proxy_reported: {str(provenance.proxy_reported).lower()}")
    lines.append(f"{_INDENT}third_party_present: {str(provenance.third_party_present).lower()}")
    if provenance.qualifier_tr:
        lines.append(f"{_INDENT}{provenance.qualifier_tr}")
    return lines


def _konusma_lines(composed: ComposedNote) -> list[str]:
    block = composed.note.konusma_ozellikleri
    if block is None:
        return []
    return [
        f"{_INDENT}speech_rate_syll_s: {block.speech_rate_syll_s}",
        f"{_INDENT}pause_ratio: {block.pause_ratio}",
        f"{_INDENT}f0_mean_hz: {block.f0_mean_hz}",
        f"{_INDENT}f0_sd_hz: {block.f0_sd_hz}",
        f"{_INDENT}response_latency_ms_mean: {block.response_latency_ms_mean}",
        f"{_INDENT}{block.recording_conditions_caveat_tr}",
    ]


def _section_block(composed: ComposedNote, section: str, copy: NoteCopy) -> list[str]:
    if section == "screening":
        body = _screening_lines(composed)
    elif section == "konusma_ozellikleri":
        body = _konusma_lines(composed)
    else:
        body = [
            line for fact in facts_by_section(composed, section) for line in _fact_lines(fact, copy)
        ]
    return [copy.section(section), *body, ""] if body else []


def document_lines(composed: ComposedNote, copy: NoteCopy) -> list[str]:
    """Every line of the note except the title and the standing footer.

    Shared by the SOAP text and the PDF so the two cannot drift: a clinician
    reading the printed note and a clinician reading the pasted text are
    reading the same document.
    """
    note = composed.note
    lines: list[str] = [
        f"visit_id: {note.meta.visit_id}",
        f"generated_at: {note.meta.generated_at.isoformat()}",
        f"mode: {note.meta.mode}",
        f"protocol_hash: {note.meta.protocol_hash}",
        f"model: {note.meta.model}",
        f"prompt_version: {note.meta.prompt_version}",
        f"legal_strings_version: {copy.version}",
        f"legal_strings_sha256: {copy.text_hash}",
        "",
        copy.value("previsit_note.heading.triage"),
        f"{_INDENT}level: {note.triage.level.value}",
    ]
    lines.extend(f"{_INDENT}[{rule.id}] {rule.evidence}" for rule in note.triage.rules)
    lines.append("")

    lines.append(copy.value("previsit_note.soap.subjective"))
    for section in _SUBJECTIVE_SECTIONS:
        lines.extend(_section_block(composed, section, copy))

    lines.append(copy.value("previsit_note.soap.objective"))
    lines.extend(_section_block(composed, "imported_objective", copy))

    # A and P are the clinician's. They are rendered as empty headings rather
    # than omitted: a note that silently drops them invites the model-drafted
    # material above to be read as an assessment (invariant 2).
    lines.append(copy.value("previsit_note.soap.assessment"))
    lines.append("")
    lines.append(copy.value("previsit_note.soap.plan"))
    lines.append("")

    if note.considerations:
        lines.append(copy.value("previsit_note.heading.considerations"))
        lines.extend(f"{_INDENT}{item.pattern} — {item.why}" for item in note.considerations)
        lines.append("")
    if note.suggested_focus_questions:
        lines.append(copy.value("previsit_note.heading.focus_questions"))
        lines.extend(f"{_INDENT}{question}" for question in note.suggested_focus_questions)
        lines.append("")
    if note.patient_confirmed_sections:
        lines.append(copy.value("previsit_note.heading.confirmed"))
        lines.extend(f"{_INDENT}{section}" for section in note.patient_confirmed_sections)
        lines.append("")

    # Candidates sit AFTER A/P and under their own heading, never inside S:
    # invariant 1 caps them at YELLOW_REVIEW, and a candidate printed among
    # findings is that cap defeated by layout.
    if note.triage.llm_candidates:
        lines.append(copy.value("previsit_note.heading.candidates"))
        marker = copy.attribution(Attribution.LLM_CANDIDATE)
        lines.extend(
            f"{_INDENT}[{marker}] {candidate.text} — {candidate.evidence}"
            for candidate in note.triage.llm_candidates
        )
        lines.append("")

    if composed.gaps:
        lines.append(copy.value("previsit_note.heading.gaps"))
        for gap in composed.gaps:
            unit = f" · {gap.unit}" if gap.unit else ""
            lines.append(f"{_INDENT}{gap.section}{unit} — {copy.gap(gap.reason)}")
        lines.append("")

    lines.append(copy.value("previsit_note.heading.provenance"))
    lines.extend(f"{_INDENT}[{fact.ref}] {fact.span.locator}" for fact in composed.facts)
    return lines


def render_soap(composed: ComposedNote, copy: NoteCopy) -> str:
    """The SOAP-compatible plain-text face — files/03 §11's "plain text for
    paste into HBYS", and the one a clinician reads on the Doctor Link."""
    body = [
        copy.value("previsit_note.title"),
        "",
        *document_lines(composed, copy),
        "",
        copy.value("previsit_note.footer"),
    ]
    return "\n".join(body) + "\n"


def render_note_pdf(
    composed: ComposedNote, copy: NoteCopy, *, watermark: str | None = None
) -> bytes:
    """The watermark-ready PDF (files/02 §376 "watermarked PDF").

    The files/06 §7 footer is handed to the writer as the page's *standing*
    footer, not appended to the content: it is drawn in a band below the
    content box on every page, so no length of note can push it off the last
    page and no line can overlap it. INT-284 met the screen version of that
    failure — the provenance line rendered under the glass bar at large text —
    and this is the paper form of the same requirement."""
    return render_document_pdf(
        title=copy.value("previsit_note.title"),
        lines=document_lines(composed, copy),
        footer=copy.value("previsit_note.footer"),
        watermark=watermark,
        # The clinician note must be producible even when a patient typed a
        # character the export encoding cannot draw; the codepoint is named,
        # never transliterated (files/06 §7 copy is unaffected either way).
        escape_unencodable=True,
    )


def render_fhir_document(composed: ComposedNote, *, patient_id: str) -> Bundle:
    """The FHIR document face — INT-033's mapper, plus this issue's provenance.

    The spans ride as repeated Composition extensions rather than a section,
    because the section codes are exactly the files/04 §5 note keys and a
    ``provenance`` code would name a section no note field backs.
    """
    return previsit_note_to_document_bundle(
        composed.note,
        patient_id=patient_id,
        fact_provenance=tuple(fact.provenance_line for fact in composed.facts),
    )
