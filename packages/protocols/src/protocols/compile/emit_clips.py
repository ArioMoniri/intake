"""Compiler output (e): the clip manifest (files/03 §6; files/03 §4.9.1 row 10).

The cached-clip TTS path "runs at compile time, not at session time — which
is why ≈70 % of fast-mode turns cost 0 ms of TTS". It consumes every
``ask_tr`` / ``confirm_tr`` / ``action_tr`` string **after Turkish
normalisation has already been applied by the compiler** (files/03 §4.9.6),
and keys the result by ``sha256(text_tr, voice_id)``.

Three rules that are load-bearing rather than incidental:

1. **Expansion happens before the key is computed.** The clip cache and the
   TTS request must agree byte-for-byte, so the hash is taken over the
   expanded text — never the authored one (CLAUDE.md invariant 22).
2. **``text_only`` contributes no clip.** files/13 §13: "text_only must mean
   text only: no clip, no ``speech_tr``, ever". Screening and safeguarding
   content is still *rendered*, so its text is still expanded and still
   reaches the Questionnaire — what it never gets is a row here.
3. **Scripted stays scripted.** Instrument items and red-flag action scripts
   are marked ``scripted`` unconditionally; a paraphrasable section can only
   ever relax an ordinary protocol question (CLAUDE.md invariant 10).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

from clinical_schemas.common import FrozenModel, Ref
from pydantic import Field

from protocols.compile.errors import Refusal, RefusalCode
from protocols.compile.resolve import ResolvedProtocol
from protocols.compile.tr_orthography import TrExpansionError, assert_round_trip, expand_tr
from protocols.dsl import ClipManifestEntry, clip_text_hash
from protocols.types import Delivery

__all__ = ["ClipRow", "SpeakableText", "clip_manifest"]


class ClipRow(FrozenModel):
    """One clip-manifest row: what to synthesise, keyed for the Talker."""

    subject: str = Field(description="Where the text came from (slot, rule or item).")
    text_tr: str = Field(description="The tr-expanded script — no numeral, no unit symbol.")
    scripted: bool = Field(
        description="True where the text is spoken verbatim and paraphrase is never "
        "permitted (CLAUDE.md invariant 10)."
    )
    entry: ClipManifestEntry = Field(description="text_hash → clip_id per voice (files/03 §6).")


class SpeakableText(FrozenModel):
    """One authored string on its way to expansion."""

    subject: str = Field(description="Slot linkId, rule id or instrument item id.")
    text: str = Field(description="The authored Turkish, before expansion.")
    scripted: bool = Field(description="Whether paraphrase is forbidden here.")
    clipped: bool = Field(description="Whether it may be pre-synthesised (files/13 §13).")
    is_prompt: bool = Field(
        default=False, description="True for the slot's ask_tr — the Questionnaire item text."
    )


def _clip_id(text: str, voice: str) -> Ref:
    """``sha256(text_tr, voice_id)`` (files/03 §4.9.1 row 10), namespaced so a
    clip id reads as a clip id in a log line."""
    digest = hashlib.sha256(f"{text}\x00{voice}".encode()).hexdigest()
    return f"clip.{voice}.{digest}"


def _sources(document: ResolvedProtocol) -> Iterator[SpeakableText]:
    speakable_sections: set[str] = set()
    for section in document.sections:
        section_clipped = section.delivery is not Delivery.TEXT_ONLY
        if section_clipped:
            speakable_sections.add(section.id)
        for slot in section.slots:
            clipped = section_clipped and slot.delivery is not Delivery.TEXT_ONLY
            scripted = not section.allow_paraphrase
            if slot.slot.ask_tr is not None:
                yield SpeakableText(
                    subject=slot.fhir_link_id,
                    text=slot.slot.ask_tr,
                    scripted=scripted,
                    clipped=clipped,
                    is_prompt=True,
                )
            for text in (
                slot.slot.confirm_tr,
                slot.slot.follow_up_tr,
                *(slot.slot.choices_tr or ()),
            ):
                if text is not None:
                    yield SpeakableText(
                        subject=slot.fhir_link_id, text=text, scripted=scripted, clipped=clipped
                    )
    administered = {
        instrument_id
        for section in document.sections
        if section.id in speakable_sections
        for instrument_id in section.questionnaires
    }
    for instrument in document.instruments:
        for item in instrument.items:
            yield SpeakableText(
                subject=f"{instrument.id}.{item.id}",
                text=item.text_tr,
                scripted=True,
                clipped=instrument.id in administered,
            )
    for rule in (*document.red_flags, *document.life_threat_rules):
        action = rule.action
        if action is None:
            continue
        for location in (action.remote, action.on_site):
            for text in (location.action_tr, location.why_tr, *location.do_nots_tr):
                if text is not None:
                    yield SpeakableText(subject=rule.id, text=text, scripted=True, clipped=True)
        yield SpeakableText(
            subject=rule.id, text=action.unknown.ask_one_tr, scripted=True, clipped=True
        )


def clip_manifest(
    document: ResolvedProtocol, voice: str
) -> tuple[tuple[ClipRow, ...], dict[str, str], list[Refusal]]:
    """Build the manifest, the linkId → expanded-prompt map, and any refusals."""
    refusals: list[Refusal] = []
    rows: dict[str, ClipRow] = {}
    prompts: dict[str, str] = {}
    for source in _sources(document):
        try:
            expansion = expand_tr(source.text)
            assert_round_trip(expansion)
        except TrExpansionError as exc:
            refusals.append(
                Refusal(
                    code=RefusalCode.TR_EXPANSION_FAILED,
                    subject=source.subject,
                    message=(
                        f"{exc} — no numeral reaches any TTS model, and the models' "
                        "built-in normalisers are disabled, so the compiler is the only "
                        "place this can be fixed (CLAUDE.md invariant 22; files/03 §4.9.6)"
                    ),
                )
            )
            continue
        # expand_tr's contract is total: it either produces digit-free Turkish
        # or raises, so there is no post-check here to go stale. The property
        # is asserted from the outside in
        # tests/protocols/test_compiler_emitters.py.
        expanded = expansion.text
        if source.is_prompt:
            prompts.setdefault(source.subject, expanded)
        if not source.clipped:
            continue
        text_hash = clip_text_hash(expanded)
        rows.setdefault(
            text_hash,
            ClipRow(
                subject=source.subject,
                text_tr=expanded,
                scripted=source.scripted,
                entry=ClipManifestEntry(
                    text_hash=text_hash, clip_id=_clip_id(expanded, voice), voice=voice
                ),
            ),
        )
    return tuple(rows[key] for key in sorted(rows)), prompts, refusals
