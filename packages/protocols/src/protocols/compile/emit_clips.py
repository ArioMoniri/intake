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
4. **The key carries the locale** (INT-297). Two locales may be pinned to one
   voice, and after per-locale expansion two languages can produce the same
   bytes for a short string — a brand name, a unit, a place. A cache found by
   text hash and voice alone then serves one language's clip into the other
   language's turn. So the row is keyed ``(locale, voice, text_hash)`` and the
   clip id names the locale, and a second row wanting one key with a different
   obligation on it is a **refusal**, never a first-writer-wins dedupe:
   identical rows are the same clip, and rows that disagree about whether the
   text may be paraphrased are two different promises sharing one cache entry.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator

from clinical_schemas.common import FrozenModel, Ref
from pydantic import Field

from protocols.compile.errors import Refusal, RefusalCode
from protocols.compile.number_expansion import expand_for_locale
from protocols.compile.resolve import ResolvedProtocol
from protocols.compile.tr_orthography import TrExpansionError
from protocols.dsl import ClipManifestEntry, clip_text_hash
from protocols.locale_text import DEFAULT_LOCALE, entry_for, safe_code
from protocols.types import Delivery

__all__ = ["ClipRow", "SpeakableText", "clip_manifest", "rows_from"]


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


def _clip_id(text: str, voice: str, locale: str) -> Ref:
    """``sha256(text_tr, voice_id, locale)`` (files/03 §4.9.1 row 10 plus the
    INT-297 locale), namespaced so a clip id reads as a clip id in a log line
    and names the language it speaks."""
    digest = hashlib.sha256(f"{text}\x00{voice}\x00{locale}".encode()).hexdigest()
    return f"clip.{locale}.{voice}.{digest}"


def _sources(document: ResolvedProtocol) -> Iterator[SpeakableText]:
    """Every string this document can speak, read for the document's own locale.

    The locale-keyed fields are read through :func:`entry_for`, which raises
    rather than falling back. That cannot fire here — ``resolve_protocol``
    refuses a locale the chain cannot speak before any emitter runs — and it is
    written this way so that if the gate is ever removed the manifest stops
    rather than quietly emitting Turkish under another language's clip id.
    """
    locale = document.locale
    speakable_sections: set[str] = set()
    for section in document.sections:
        section_clipped = section.delivery is not Delivery.TEXT_ONLY
        if section_clipped:
            speakable_sections.add(section.id)
        for slot in section.slots:
            if slot.proxy_skipped:
                # ADR-040: a proxy session never speaks a skipped slot, so its
                # bundle carries no clip and no prompt for it
                continue
            clipped = section_clipped and slot.delivery is not Delivery.TEXT_ONLY
            scripted = not section.allow_paraphrase
            if slot.slot.ask_tr is not None:
                yield SpeakableText(
                    subject=slot.fhir_link_id,
                    text=entry_for(slot.slot.ask_tr, locale),
                    scripted=scripted,
                    clipped=clipped,
                    is_prompt=True,
                )
            follow_up = (
                entry_for(slot.slot.follow_up_tr, locale)
                if slot.slot.follow_up_tr is not None
                else None
            )
            choices = (
                entry_for(slot.slot.choices_tr, locale) if slot.slot.choices_tr is not None else ()
            )
            confirm = (
                entry_for(slot.slot.confirm_tr, locale)
                if slot.slot.confirm_tr is not None
                else None
            )
            for text in (confirm, follow_up, *choices):
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
                text=entry_for(item.text_tr, locale),
                scripted=True,
                clipped=instrument.id in administered,
            )
    for rule in (*document.red_flags, *document.life_threat_rules):
        action = rule.action
        if action is None:
            continue
        for location in (action.remote, action.on_site):
            # INT-314: the action half of the script is per locale too, so each
            # of these is the locale's own entry rather than the Turkish one.
            # ``entry_for`` raises instead of falling back, which is what makes
            # a missing entry a compile refusal and not a Turkish clip served
            # under another language's clip id.
            why = entry_for(location.why_tr, locale) if location.why_tr is not None else None
            action_text = (
                entry_for(location.action_tr, locale) if location.action_tr is not None else None
            )
            do_nots = entry_for(location.do_nots_tr, locale) if location.do_nots_tr else ()
            for text in (action_text, why, *do_nots):
                if text is not None:
                    yield SpeakableText(subject=rule.id, text=text, scripted=True, clipped=True)
        yield SpeakableText(
            subject=rule.id,
            text=entry_for(action.unknown.ask_one_tr, locale),
            scripted=True,
            clipped=True,
        )


def clip_manifest(
    document: ResolvedProtocol, voice: str, *, locale: str | None = None
) -> tuple[tuple[ClipRow, ...], dict[str, str], list[Refusal]]:
    """Build the manifest, the linkId → expanded-prompt map, and any refusals.

    ``locale`` defaults to the document's own and may not disagree with it: a
    manifest built for one language out of a document resolved for another is
    the exact confusion the (locale, voice) key exists to prevent.
    """
    if locale is not None and locale != document.locale:
        return (
            (),
            {},
            [
                Refusal(
                    code=RefusalCode.LOCALE_NOT_SELECTABLE,
                    subject=document.pack_id,
                    message=(
                        f"clip manifest asked for {safe_code(locale)} from a document "
                        f"resolved for {safe_code(document.locale)}; resolve the pack "
                        "for the locale you intend to serve (INT-296; INT-297)"
                    ),
                )
            ],
        )
    return rows_from(_sources(document), voice=voice, locale=document.locale)


def rows_from(
    sources: Iterable[SpeakableText], *, voice: str, locale: str = DEFAULT_LOCALE
) -> tuple[tuple[ClipRow, ...], dict[str, str], list[Refusal]]:
    """Expand, key on ``(locale, voice, text_hash)``, and refuse a collision."""
    refusals: list[Refusal] = []
    rows: dict[str, ClipRow] = {}
    prompts: dict[str, str] = {}
    for source in sources:
        try:
            # INT-300: expansion is per locale. ``tr`` runs the Turkish expander
            # and its round-trip gate exactly as before; a locale with no
            # expander refuses a numeral (``NumeralWithoutExpander``, a
            # ``TrExpansionError``) rather than passing it to a TTS model.
            expansion = expand_for_locale(source.text, locale)
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
        # expand_for_locale's contract is total: for a locale with an expander it
        # either produces digit-free text or raises, and for one without it
        # either passes numeral-free text through or raises, so there is no
        # post-check here to go stale. The property is asserted from the outside
        # in tests/protocols/test_compiler_emitters.py.
        expanded = expansion.text
        if source.is_prompt:
            prompts.setdefault(source.subject, expanded)
        if not source.clipped:
            continue
        text_hash = clip_text_hash(expanded)
        row = ClipRow(
            subject=source.subject,
            text_tr=expanded,
            scripted=source.scripted,
            entry=ClipManifestEntry(
                text_hash=text_hash,
                clip_id=_clip_id(expanded, voice, locale),
                voice=voice,
                locale=locale,
            ),
        )
        seen = rows.get(text_hash)
        if seen is None:
            rows[text_hash] = row
            continue
        if seen.scripted != row.scripted:
            refusals.append(
                Refusal(
                    code=RefusalCode.CLIP_KEY_COLLISION,
                    subject=f"{seen.subject}|{row.subject}",
                    message=(
                        f"two rows claim clip key ({safe_code(locale)}, {voice}, "
                        f"{text_hash[:12]}…) with different paraphrase obligations — "
                        "one clip cannot be both verbatim-only and paraphrasable, and "
                        "preferring whichever row was seen first decides invariant 10 "
                        "by iteration order (CLAUDE.md invariant 10; INT-297)"
                    ),
                )
            )
    return tuple(rows[key] for key in sorted(rows)), prompts, refusals
