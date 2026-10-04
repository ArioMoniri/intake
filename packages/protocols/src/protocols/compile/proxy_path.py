"""INT-483 / ADR-040 — the compiler half of subject-aware addressing.

Owner decision D24, answer 1Y: in a proxy session every self-addressed
question is reworded for the patient or skipped, and the child and carer
paths stay closed until that mechanism exists. The DSL can now say which
(:mod:`protocols.addressing`); this module is where "closed until the content
exists" is enforced, on the merged pack, after every layer and every op:

**On every path** — a pack that states something unsafe about a proxy session
is refused wherever it is compiled, so the statement cannot sit in a served
self bundle waiting for the proxy path to open:

* ``PROXY_SKIPS_RED_FLAG_PROBE`` — a red-flag probe marked skipped in a proxy
  session. A probe nobody asks reads Unknown and its rule never fires, which is
  a relaxation by another door (CLAUDE.md invariant 7). In a proxy session a
  probe is reworded, never skipped.
* ``RED_FLAG_PROBE_SPEAKER_ADDRESSED`` — a red-flag probe declared as speaking
  to whoever holds the device. The speaker's own answer would fill the
  patient's rule slot: the hazard CD-01's chest-pain stop-gap exists for.

**On the proxy path only** — the path opens when nothing self-addressed is
left unhandled:

* ``PROXY_ADDRESSING_MISSING`` — an askable slot addressed to the patient with
  no proxy block. Every one, inherited base items included, and not only the
  ``must_ask`` ones: an optional question put in the second person to a proxy
  fills the patient's slot with the speaker's answer just the same, and
  choosing "skip" for it on the author's behalf would be a clinical decision
  taken by the compiler.
* ``PROXY_TEXT_INCOMPLETE`` — a rewording that does not speak every text its
  merged self form speaks. (A locale the proxy text lacks is refused earlier,
  as ``LOCALE_NOT_SELECTABLE``: the proxy maps are speakable fields.)
* ``RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE`` — a probe whose ``ask_if`` or
  ``skip_if`` reads, directly or through another slot's gate, the session's
  subject role or a speaker-addressed slot, so that the role or the speaker's
  own answer decides whether it is asked (the base pack's chest-pain stop-gap
  is one).
* ``PROXY_GATED_ON_SUBJECT_ROLE`` — any other patient-addressed slot whose gate
  reads the subject role: in a proxy session it is skipped without a trace, so
  the skip has to be the explicit, recorded ``proxy: skip`` instead.
* ``PROXY_TEXT_INCOMPLETE`` also covers a hospital ``override_text`` that
  rewrote the self form of a reworded slot, leaving its proxy form unreviewed.
* ``PROXY_SKIP_CLOSES_GATE`` — a question asked in the proxy session whose
  gate reads a skipped slot. A skipped slot reads Unknown, so the gate never
  opens and the question is silently never asked (files/13 §9.5).

* ``PROXY_ADMINISTERS_INSTRUMENT`` — a section of the chain administers a
  validated instrument. Its items are self-report by validation and are never
  reworded, so put to a proxy they produce a number a clinician reads as
  "screened"; files/12 §2.2 settles that a non-self item yields
  ``InstrumentNotScored``, and nothing in the engine implements that yet. The
  proxy path stays closed for such a chain until it does.

What a red-flag probe is: a slot any red-flag rule reads — a pack rule after
overlay composition or a ``base.life_threat`` rule, drafts included, through
``when`` or ``tense_anchor`` (the same reads INT-382 protects) — and every
slot of the files/04 §1 ``red_flags`` section, whose families' triggers are
unsigned (HB-C1) and must not become skippable in the gap.

The module only refuses and projects. It writes no proxy text, chooses no
skip, and touches no rule, level, predicate or the life-threat set.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from protocols.addressing import (
    RED_FLAG_PROBE_SECTION,
    SUBJECT_ROLE_REF,
    Addressee,
    Addressing,
    proxy_text_mismatches,
)
from protocols.bindings import fhir_link_id
from protocols.compile.errors import Refusal, RefusalCode
from protocols.compile.rule_reads import pointer_slot_names, rule_reads
from protocols.dsl import RedFlagRule, Slot
from protocols.gates import SlotNamespace, qualify_gate
from protocols.ops import AddSlotOp
from protocols.pack import ProtocolPack
from protocols.triage.expr import WhenGrammarError, parse_when, referenced_slots

__all__ = [
    "AddressedSlot",
    "addressing_refusals",
    "proxy_form",
    "slot_origins",
]


@dataclass(frozen=True, slots=True)
class AddressedSlot:
    """One merged slot, with the pack that declared it (for the message)."""

    section_id: str
    key: str
    slot: Slot
    origin: str

    @property
    def link_id(self) -> str:
        return fhir_link_id(self.section_id, self.key)


def slot_origins(packs: Sequence[ProtocolPack]) -> dict[tuple[str, str], str]:
    """Which pack of the applied chain declared each slot, the last writer
    winning as it does in the merge — so an inherited base item is named as
    ``base.intake``'s, which is the pack whose copy a fix has to touch."""
    origins: dict[tuple[str, str], str] = {}
    for pack in packs:
        for section_id, section in pack.sections.items():
            for key in section.slots:
                origins[(section_id, key)] = pack.id
        for op in pack.ops:
            if isinstance(op, AddSlotOp):
                parts = op.pointer.lstrip("/").split("/")
                if len(parts) == 4 and parts[0] == "sections" and parts[2] == "slots":
                    origins[(parts[1], parts[3])] = pack.id
    return origins


def proxy_form(slot: Slot) -> tuple[Slot, bool]:
    """The slot as a proxy session hears it, and whether it is skipped.

    A rewording replaces the three spoken fields with the pack's own proxy
    text, verbatim; the choices stay, because they are the literals a rule
    tests. A speaker-addressed slot, or a slot with no proxy block (which the
    proxy path has already refused), is returned unchanged.
    """
    proxy = slot.proxy
    if slot.addressee is Addressee.SPEAKER or proxy is None:
        return slot, False
    if proxy.skip:
        return slot, True
    return (
        slot.model_copy(
            update={
                "ask_tr": proxy.ask_tr,
                "confirm_tr": proxy.confirm_tr,
                "follow_up_tr": proxy.follow_up_tr,
            }
        ),
        False,
    )


def _probe_reads(rules: Iterable[RedFlagRule]) -> tuple[frozenset[str], tuple[str, ...]]:
    """Every reference a red-flag rule reads, and the rules whose ``when``
    cannot be read at all."""
    reads: set[str] = set()
    unreadable: list[str] = []
    for rule in rules:
        rule_read = rule_reads(rule)
        if rule_read is None:
            unreadable.append(rule.id)
            continue
        reads |= rule_read.all
    return frozenset(reads), tuple(sorted(set(unreadable)))


def _is_probe(entry: AddressedSlot, reads: frozenset[str]) -> bool:
    if entry.section_id == RED_FLAG_PROBE_SECTION:
        return True
    return bool(pointer_slot_names(f"/sections/{entry.section_id}/slots/{entry.key}") & reads)


def _gate_reads(slot: Slot, namespace: SlotNamespace) -> frozenset[str]:
    """The qualified slots a slot's ``ask_if`` and ``skip_if`` read. A gate
    outside the grammar, or one that does not resolve, reads nothing here:
    the resolver refuses it under its own code (INT-355)."""
    reads: set[str] = set()
    for text in (slot.ask_if, slot.skip_if):
        if text is None:
            continue
        try:
            node = parse_when(text)
        except WhenGrammarError:
            continue
        qualified, issues = qualify_gate(node, namespace)
        if not issues:
            reads |= referenced_slots(qualified)
    return frozenset(reads)


def _refusal(code: RefusalCode, subject: str, message: str) -> Refusal:
    return Refusal(code=code, subject=subject, message=message)


def _every_path(entries: Sequence[AddressedSlot], reads: frozenset[str]) -> list[Refusal]:
    refusals: list[Refusal] = []
    for entry in entries:
        if not _is_probe(entry, reads):
            continue
        if entry.slot.proxy is not None and entry.slot.proxy.skip:
            refusals.append(
                _refusal(
                    RefusalCode.PROXY_SKIPS_RED_FLAG_PROBE,
                    entry.link_id,
                    "a red-flag probe is never skipped in a proxy session: unasked, it "
                    "reads Unknown and the rule that reads it never fires. In a proxy "
                    "session it is reworded for the patient (ADR-040; CLAUDE.md "
                    "invariant 7)",
                )
            )
        if entry.slot.addressee is Addressee.SPEAKER:
            refusals.append(
                _refusal(
                    RefusalCode.RED_FLAG_PROBE_SPEAKER_ADDRESSED,
                    entry.link_id,
                    "a red-flag probe is about the patient, never about whoever holds "
                    "the device: a speaker-addressed probe lets the speaker's own answer "
                    "fill the patient's rule slot (ADR-040; CLAUDE.md invariant 7; CD-01 "
                    "finding F13)",
                )
            )
    return refusals


def _missing(entry: AddressedSlot) -> Refusal:
    must_ask = ", a must_ask item" if entry.slot.must_ask else ""
    return _refusal(
        RefusalCode.PROXY_ADDRESSING_MISSING,
        entry.link_id,
        f"declared in {entry.origin}{must_ask}: the question speaks to the patient and "
        "has no proxy block, so a proxy would be asked about themselves and their "
        "answer filed as the patient's. Reword it for the patient or mark it skipped, "
        "per a clinical decision record (ADR-040; owner decision D24 answer 1Y; D18). "
        "The proxy path stays closed until then",
    )


def _incomplete(entry: AddressedSlot, overridden: frozenset[str]) -> list[Refusal]:
    proxy = entry.slot.proxy
    if proxy is None or proxy.skip:
        return []
    gaps = list(
        proxy_text_mismatches(
            proxy,
            ask_tr=entry.slot.ask_tr,
            confirm_tr=entry.slot.confirm_tr,
            follow_up_tr=entry.slot.follow_up_tr,
        )
    )
    if entry.link_id in overridden:
        # a hospital copy change rewrote the self form; the proxy form it was
        # reviewed against is no longer the one beside it
        gaps.append("override_text")
    if not gaps:
        return []
    return [
        _refusal(
            RefusalCode.PROXY_TEXT_INCOMPLETE,
            entry.link_id,
            "the proxy rewording no longer matches the merged slot, so a second-person "
            "text, an unreviewed one or no text at all would reach the proxy "
            f"({', '.join(gaps)}; ADR-040; CLAUDE.md invariant 10)",
        )
    ]


def _reach(start: str, gates: dict[str, frozenset[str]]) -> frozenset[str]:
    """Every slot a slot's gate depends on, through other slots' gates."""
    seen: set[str] = set()
    frontier = set(gates.get(start, frozenset()))
    while frontier:
        seen |= frontier
        frontier = {dep for ref in frontier for dep in gates.get(ref, frozenset())} - seen
    return frozenset(seen)


def _proxy_path(
    entries: Sequence[AddressedSlot], reads: frozenset[str], overridden: frozenset[str]
) -> list[Refusal]:
    namespace = SlotNamespace((entry.section_id, entry.key) for entry in entries)
    skipped = frozenset(
        entry.link_id for entry in entries if entry.slot.proxy is not None and entry.slot.proxy.skip
    )
    gates = {entry.link_id: _gate_reads(entry.slot, namespace) for entry in entries}
    # what a speaker decides: the subject role itself and every speaker slot
    speaker_side = frozenset({SUBJECT_ROLE_REF}) | frozenset(
        entry.link_id for entry in entries if entry.slot.addressee is Addressee.SPEAKER
    )
    refusals: list[Refusal] = []
    for entry in entries:
        slot = entry.slot
        if slot.ask_tr is not None and slot.addressee is Addressee.PATIENT and slot.proxy is None:
            refusals.append(_missing(entry))
        refusals.extend(_incomplete(entry, overridden))
        gate_reads = gates[entry.link_id]
        if _is_probe(entry, reads):
            decided_by_speaker = _reach(entry.link_id, gates) & speaker_side
            if decided_by_speaker:
                refusals.append(
                    _refusal(
                        RefusalCode.RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE,
                        entry.link_id,
                        f"the probe's gate reads {', '.join(sorted(decided_by_speaker))}, "
                        "directly or through another gate, so whether it is asked in a "
                        "proxy session is decided by the subject role or the speaker's "
                        "own answer — a red-flag probe stays asked in a proxy session, "
                        "reworded. Drop the gate when the proxy text lands (ADR-040; "
                        "CLAUDE.md invariant 7; CD-01's stop-gap)",
                    )
                )
        elif slot.addressee is Addressee.PATIENT and SUBJECT_ROLE_REF in gate_reads:
            refusals.append(
                _refusal(
                    RefusalCode.PROXY_GATED_ON_SUBJECT_ROLE,
                    entry.link_id,
                    f"the gate reads {SUBJECT_ROLE_REF}: a gate that closes in a proxy "
                    "session skips the question without a trace — no NOT_ASKED_PROXY, "
                    "no coverage gap, no note line. Mark it skipped with `proxy: skip` "
                    "instead, so the skip is recorded and shown (ADR-040)",
                )
            )
        if entry.link_id not in skipped and gate_reads & skipped:
            refusals.append(
                _refusal(
                    RefusalCode.PROXY_SKIP_CLOSES_GATE,
                    entry.link_id,
                    f"the gate reads {', '.join(sorted(gate_reads & skipped))}, which a "
                    "proxy session skips; a skipped slot reads Unknown, so the gate never "
                    "opens and this question is silently never asked (files/13 §9.5; "
                    "ADR-040). Skip this question too, or gate it on an asked slot",
                )
            )
    return refusals


def _instrument_refusals(
    instrument_sections: Sequence[tuple[str, tuple[str, ...]]],
) -> list[Refusal]:
    return [
        _refusal(
            RefusalCode.PROXY_ADMINISTERS_INSTRUMENT,
            section_id,
            f"the section administers {', '.join(instruments)}: validated self-report "
            "items, never reworded (CLAUDE.md invariant 10), so a proxy's answers would "
            "produce a score a clinician reads as screened. files/12 §2.2 settles that a "
            "non-self item yields InstrumentNotScored, never a number, and no engine path "
            "implements that yet — the proxy path stays closed for this chain (ADR-040)",
        )
        for section_id, instruments in instrument_sections
        if instruments
    ]


def addressing_refusals(
    *,
    slots: Sequence[AddressedSlot],
    rules: Iterable[RedFlagRule],
    addressing: Addressing,
    instrument_sections: Sequence[tuple[str, tuple[str, ...]]],
    overridden: Iterable[str],
) -> list[Refusal]:
    """Every addressing refusal for one merged pack, in slot order.

    ``rules`` is every pack rule after overlay composition plus every
    ``base.life_threat`` rule. A rule whose ``when`` cannot be read makes its
    probes unknowable, so no skip anywhere can be shown to spare them: with a
    skip present, each such rule is refused here, the way INT-382 refuses an
    unreadable rule beside a ``suppress_slot``. ``instrument_sections`` is
    every merged section's id and the instruments it administers;
    ``overridden`` the link ids an applied ``override_text`` rewrote.
    """
    reads, unreadable = _probe_reads(rules)
    refusals = _every_path(slots, reads)
    if unreadable and any(e.slot.proxy is not None and e.slot.proxy.skip for e in slots):
        refusals.extend(
            _refusal(
                RefusalCode.PROXY_SKIPS_RED_FLAG_PROBE,
                rule_id,
                "a slot is skipped in a proxy session and this rule's when is outside "
                "the closed when grammar, so the slots it reads cannot be listed and "
                "the skip cannot be shown to spare its probes (ADR-040; CLAUDE.md "
                "invariant 7)",
            )
            for rule_id in unreadable
        )
    if addressing is Addressing.PROXY:
        refusals.extend(_proxy_path(slots, reads, frozenset(overridden)))
        refusals.extend(_instrument_refusals(instrument_sections))
    return refusals
