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
from clinical_schemas.quantity import float_magnitude, render_quantity
from clinical_schemas.rule_evidence import render_rule_evidence
from intake_platform.pdf import render_document_pdf

from intake_voice_runtime.note.composer import ComposedNote, facts_by_section
from intake_voice_runtime.note.copy import NOTE_COPY_SECTIONS, NoteCopy
from intake_voice_runtime.note.facts import Attribution, NoteFact, SourceKind
from intake_voice_runtime.note.translation import TranslatedText, TranslatorUnidentified

__all__ = [
    "TranslatedOriginalUnreachable",
    "render_fhir_document",
    "render_note_pdf",
    "render_soap",
]


class TranslatedOriginalUnreachable(ValueError):
    """A face was asked to render a translated line it has nowhere to put the
    original on. Refused rather than exported: a rendering that leaves the
    building without the words it was rendered from *becomes* the record."""


#: files/03 §11 "S = patient-reported": everything the patient said or is
#: carried about them. ``imported_objective`` is the O block and is the only
#: section not listed here, which is the SOAP split stated once.
_SUBJECTIVE_SECTIONS = tuple(
    section for section in NOTE_COPY_SECTIONS if section != "imported_objective"
)
_INDENT = "  "

#: How an original is set off from the rendering it sits under. Punctuation
#: rather than a copy key: the marker above the line already says the line is
#: a translation and from which locale, and a second authored string would be
#: a second thing to keep in step with it.
_QUOTE_OPEN = "«"
_QUOTE_CLOSE = "»"


def _marker(fact: NoteFact, copy: NoteCopy) -> str:
    """The attribution marker, with the one detail that makes it checkable.

    A relative's line names the relative; a carried line names the date it was
    first recorded (without it, a carried fact reads as a current one, which
    is exactly the INT-247/INT-256 failure); a record line names the document;
    a translated line names the locale the patient actually spoke, so the
    clinician knows the sentence is a rendering *before* they read it.
    """
    base = copy.attribution(fact.attribution)
    if fact.attribution is Attribution.TRANSLATED:
        return f"{base}: {_translation(fact).source_locale}"
    if fact.attribution is Attribution.RELATIVE:
        return f"{base}: {copy.subject(fact.subject)}"
    if fact.attribution is Attribution.CARRIED and fact.span.kind is SourceKind.EARLIER_VISIT:
        return f"{base}: {fact.span.asserted_at}"
    if fact.attribution is Attribution.RECORD and fact.span.kind is SourceKind.DOCUMENT:
        return f"{base}: {fact.span.ref}"
    return base


def _translation(fact: NoteFact) -> TranslatedText:
    """The original behind a translated fact, or the refusal.

    ``NoteFact`` is a plain dataclass, so a caller can assemble one directly
    and skip the ``Sourced`` equivalence that normally makes this impossible.
    A renderer that met such a fact would print a machine's sentence with no
    identified producer and no way back to what the patient said, so it
    raises here instead — the acceptance's *"raises rather than rendering
    unattributed"*, at the last point where it can still be true.
    """
    if fact.translation is None:
        raise TranslatorUnidentified(
            f"fact {fact.ref} is attributed {Attribution.TRANSLATED.value!r} and carries no "
            "original and no translator; a note may not print an unattributed machine "
            "rendering of what a patient said"
        )
    return fact.translation


def _fact_lines(fact: NoteFact, copy: NoteCopy) -> list[str]:
    """The fact's own lines, and — for a translated fact — the original.

    The original is placed **directly beneath** the rendering it belongs to,
    under the same ``fNN`` handle and one indent deeper. That is the
    acceptance's *"beside the rendering"* taken literally: a clinician reading
    the Turkish is already looking at the words it came from, rather than
    being expected to go and find them in a block further down.
    """
    marker = _marker(fact, copy)
    lines = [f"{_INDENT}[{fact.ref}] {marker} — {line}" for line in fact.lines]
    if fact.attribution is Attribution.TRANSLATED:
        translated = _translation(fact)
        lines.append(
            f"{_INDENT * 2}{_QUOTE_OPEN} {translated.source_locale} {_QUOTE_CLOSE} "
            f"{translated.original}"
        )
    return lines


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
    """The speech measures, each written by the one quantity renderer for the
    note's reader (invariant 22, INT-386): the note language's decimal point,
    no grouping, and the float's printed digits rather than its binary
    expansion. The unit stays in the key, as it always has on this face."""
    block = composed.note.konusma_ozellikleri
    if block is None:
        return []
    locale = composed.note.meta.language

    def number(value: float) -> str:
        return render_quantity(float_magnitude(value), locale=locale)

    return [
        f"{_INDENT}speech_rate_syll_s: {number(block.speech_rate_syll_s)}",
        f"{_INDENT}pause_ratio: {number(block.pause_ratio)}",
        f"{_INDENT}f0_mean_hz: {number(block.f0_mean_hz)}",
        f"{_INDENT}f0_sd_hz: {number(block.f0_sd_hz)}",
        f"{_INDENT}response_latency_ms_mean: {number(block.response_latency_ms_mean)}",
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
    # A fired rule's evidence is written from its parts for the note's reader
    # (invariant 22, INT-404); the engine's own text keeps JSON's full stop.
    lines.extend(
        f"{_INDENT}[{rule.id}] {render_rule_evidence(rule, locale=note.meta.language)}"
        for rule in note.triage.rules
    )
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
    lines.extend(f"{_INDENT}[{fact.ref}] {_provenance(fact)}" for fact in composed.facts)
    return lines


def _provenance(fact: NoteFact) -> str:
    """One provenance entry: where the fact came from, and — for a translated
    one — which model rendered it.

    The identity is printed in full rather than abbreviated. It is what an
    auditor reads the note *against*, and a truncated hash is a hash nobody
    can re-check; ``model_id@revision`` is files/03 §4.9.4's form and the
    sha256 is invariant 19's weight pin. None of it is patient material, so
    unlike the original above it is safe on any surface that carries the
    locator.
    """
    if fact.attribution is not Attribution.TRANSLATED:
        return fact.span.locator
    translated = _translation(fact)
    return (
        f"{fact.span.locator} · {translated.source_locale} · {translated.translator.name} · "
        f"{translated.translator.pinned_id} · sha256:{translated.translator.sha256}"
    )


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

    **A translated note is refused here.** The bundle is built from the
    ``PreVisitNote`` value, which holds the Turkish rendering and nothing
    else; the original lives on the fact index, and the provenance extension
    is ids and offsets by contract (invariant 6) rather than a place to put a
    patient's sentence. Exporting the rendering alone would send the machine's
    version to the hospital as the patient's own words — this issue's defect
    at exchange scale, and the one place where it would leave the building.
    Giving the note value a field to hold the original is a schema change with
    a files/04 §5 inventory annotation and a new category of personal data
    (HB-L25 — a stored source locale is a fact about a person, and a language
    choice can proxy ethnic origin), so it is a decision with a human owner
    rather than an engineering default. Until it is taken, this face fails
    closed. It is inert today: no translator is registered, so no note can
    hold a translated fact in production.
    """
    translated = [fact.ref for fact in composed.facts if fact.attribution is Attribution.TRANSLATED]
    if translated:
        raise TranslatedOriginalUnreachable(
            "the FHIR document face carries the rendering and has nowhere to put the "
            f"original it was rendered from (facts: {', '.join(translated)}); exporting a "
            "machine translation as the patient's own words is refused. Adding a note "
            "field for the original is a files/04 §5 schema change and a new category of "
            "personal data (HB-L25), which is a human's decision"
        )
    return previsit_note_to_document_bundle(
        composed.note,
        patient_id=patient_id,
        fact_provenance=tuple(fact.provenance_line for fact in composed.facts),
    )
