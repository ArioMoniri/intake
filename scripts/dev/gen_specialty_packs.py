#!/usr/bin/env python3
"""Generate specialty question packs from sourced proposals (INT clinical scale-out).

For every docs/evidence/proposals/<slug>.md whose branch has its generated L0
draft at packages/protocols/specialty/<slug>.yaml, emit a QUESTIONS-authored
candidate into the review queue, packages/protocols/review/specialty/<slug>.yaml:
the reason question, a standard duration slot and the proposal's candidate
questions, with the branch red-flag left as the draft_needs_source stub (triage
deferred to base.life_threat + HB-C1; NEVER fabricated). Then regenerate the
INT-297 tr baseline.

The served tree is never written: specialty/<slug>.yaml stays the byte-exact
`protocols generate-l0` draft (files/09 §2, invariant 13) until the physician of
record signs a candidate and it is promoted to L1 (HB-C1). A candidate carrying
a `clinical_signoff` block, or one without the generator marker (hand-authored),
is never overwritten.

Proposal format (section titled "Candidate …", or `## 3.` when it holds Q items):
    **Q<n> — <label>** · archetype: `<ARCHETYPE>` · source: <ref>
    > "<one Turkish question>"
    gen: slot=<id>; type=<boolean|code|date|duration|string>; options=<id>|<id>…;
         ask_if=<expr> | skip_if=<expr>; follow_up=<t>; delivery=<d>; hold=<r>
    pack: duration_ask=<q>; duration_follow_up=<q>   or   pack: duration=omit
The `gen:` line is optional, and Q1, which fills basvuru_nedeni, takes none but
`hold=`. `hold=` keeps an item out of the pack (unsourced or unverified). One
`pack:` line at most. An ask with more than one question mark, or with a digit,
is refused (invariants 2 and 22). A `code` item names its answers by id from
CODE_OPTIONS, whose labels base.intake already carries, and never by free text;
its slot id is new to the chain. A gate (`ask_if` or `skip_if`, one per item) is
parsed with the DSL's own `when` grammar, reads only the fixed slots, base.intake
or an item before it, and compares a code item only with that item's option ids.

`duration=omit` removes the cluster/specialty `ziyaret_baglami.sikayet_suresi`
only; base.intake's must_ask `hpi.onset_date` and `hpi.duration` are still asked
and no pack can suppress them. It is refused (DURATION_OMIT_RULE_READS_SLOT)
while any red-flag rule of base.life_threat, the parent chain or the candidate
itself, draft or signed, reads that slot in `when` or as its `tense_anchor`: the
compiler refuses such a suppression for an overlay only (INT-382). Every stub
anchors on it today, so omit is refused everywhere until that changes.

A specialty pack merges into its cluster's `sorular` section, where a re-declared
cluster id keeps the cluster's position (the resolver's `_merge_chain`). When that
would put a gated question before its gate slot, the candidate carries a `reorder`
op (files/12 §3.1) that asks every gate slot first (files/13 §9.5). For the same
reason, leaving a slot out cannot remove one the parent declares: an admitted
`duration=omit` under a cluster that asks the duration carries a `suppress_slot`
op for it.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from protocols.triage.expr import (
    And,
    BoolRef,
    InSet,
    Lit,
    Not,
    Or,
    Ref,
    WhenGrammarError,
    WhenNode,
    parse_when,
    referenced_slots,
)
from protocols.types import SLOT_REF_PATTERN

ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = ROOT / "packages/protocols/base/intake.yaml"
# The sibling set evaluated on every session (files/12 §1): not in the chain, but a
# slot it read would be removed by a suppression just the same.
LIFE_THREAT = ROOT / "files/protocols/base.life_threat.yaml"
SPEC = ROOT / "packages/protocols/specialty"
REVIEW = ROOT / "packages/protocols/review/specialty"
REVIEW_CLUSTER = ROOT / "packages/protocols/review/cluster"
SERVED_CLUSTER = ROOT / "packages/protocols/cluster"
# Where a specialty candidate's parent cluster is read from, served first. Bound here,
# not read through REVIEW_CLUSTER, so that regenerating into another directory still
# orders a branch against the committed cluster it extends.
CLUSTER_PARENT_ROOTS = (SERVED_CLUSTER, REVIEW_CLUSTER)
REORDER_POINTER = "/sections/sorular/slots"
DURATION_POINTER = "/sections/ziyaret_baglami/slots/sikayet_suresi"
PROP = ROOT / "docs/evidence/proposals"
TAXONOMY = ROOT / "packages/protocols/taxonomy/branches.yaml"
CLUSTER_PREFIX = "cluster_"
# Display labels for the cluster packs (UI titles, not clinical content).
CLUSTER_TITLES = {
    "medical": "Dahili Bilimler",
    "surgical": "Cerrahi Bilimler",
    "sensory": "Göz ve Kulak Burun Boğaz",
    "womens_health": "Kadın Sağlığı",
    "child_health": "Çocuk Sağlığı",
    "mental_health": "Ruh Sağlığı",
    "dental": "Ağız ve Diş Sağlığı",
    "allied_and_reports": "Destek Hizmetleri ve Raporlar",
}

# The sanctioned pending-value marker (invariant 17's sole-exception form) is
# assembled from parts so this generator's own source never carries the token
# that scripts/ci/no_placeholders.sh forbids outside a draft_needs_source rule.
PENDING_MARKER = "".join(("TO", "DO")) + ":"

GEN_MARKER = "# generated-by: scripts/dev/gen_specialty_packs.py"
LEGACY_GEN_MARKER = "AI-assembled from guidelines in"
SLOT_TYPES = {"boolean", "code", "date", "duration", "string"}
DELIVERIES = {"voice", "text_first", "text_only"}
GEN_KEYS = {"slot", "type", "options", "ask_if", "skip_if", "follow_up", "hold", "delivery"}
GATE_KEYS = ("ask_if", "skip_if")
PACK_KEYS = {"duration", "duration_ask", "duration_follow_up"}
DURATION_OMIT = "omit"
DURATION_SLOT = "sikayet_suresi"
DURATION_OMIT_REFUSAL = "DURATION_OMIT_RULE_READS_SLOT"
# The draft stub's tense_anchor. Not moved here: which slot times each rule is
# red-flag semantics, the clinician's (INT-383, awaiting-human; HB-C1, HB-C2).
STUB_TENSE_ANCHOR = DURATION_SLOT
FIXED_SLOTS = frozenset({"basvuru_nedeni", DURATION_SLOT})
PACK_LINE = re.compile(r"^pack:\s*(.+)$", re.M)
# The answers a `type=code` item may offer (INT-379): option id → (label, the
# base.intake code slot whose choices_tr carries that label verbatim). Nothing here
# is new Turkish, and a label no base code slot carries is refused as
# CODE_OPTION_UNKNOWN for the clinician to word (HB-C1). base's subject_role labels
# are left out: they name who is speaking, and base already spells its own codes.
CODE_OPTIONS: dict[str, tuple[str, str]] = {
    "evet": ("evet", "meds_allergies.anticoagulant_use"),
    "hayir": ("hayır", "meds_allergies.anticoagulant_use"),
    "bilmiyorum": ("bilmiyorum", "meds_allergies.anticoagulant_use"),
    "emin_degilim": ("emin değilim", "pmh_fh_sh.pregnancy_status"),
    "biraktim": ("bıraktım", "pmh_fh_sh.smoking_status"),
    "hic_kullanmadim": ("hiç kullanmadım", "pmh_fh_sh.smoking_status"),
    "hic": ("hiç", "pmh_fh_sh.alcohol_use"),
    "ara_sira": ("ara sıra", "pmh_fh_sh.alcohol_use"),
    "duzenli": ("düzenli", "pmh_fh_sh.alcohol_use"),
    "daha_kotu": ("daha kötü", "hpi.trajectory"),
    "ayni": ("aynı", "hpi.trajectory"),
    "daha_iyi": ("daha iyi", "hpi.trajectory"),
    "sabahlari": ("sabahları", "hpi.timing_pattern"),
    "aksamlari": ("akşamları", "hpi.timing_pattern"),
    "geceleri": ("geceleri", "hpi.timing_pattern"),
    "belli_bir_saati_yok": ("belli bir saati yok", "hpi.timing_pattern"),
}
CODE_OPTION_UNKNOWN = "CODE_OPTION_NOT_IN_VOCABULARY"
DURATION_ASK = "Bu şikâyetiniz ne zamandır var?"
DURATION_FOLLOW_UP = "Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?"
REASON_FOLLOW_UP_WHEN_NEDIR = "Bugünkü randevunuzun sebebini kısaca anlatır mısınız?"
REASON_FOLLOW_UP_OTHERWISE = "Sizi hekime getiren en önemli şikâyetiniz nedir?"
SLOT_ID = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Question:
    text: str
    slot: str | None = None
    type: str = "string"
    ask_if: str | None = None
    follow_up: str | None = None
    archetype: str | None = None
    number: int | None = None
    delivery: str | None = None
    skip_if: str | None = None
    options: tuple[str, ...] = ()


def _one_question(text: str) -> bool:
    return text.count("?") == 1 and not re.search(r"\d", text)


def code_problem(slot: str | None, slot_type: str, options: tuple[str, ...]) -> str | None:
    """Why a question's answer options cannot be emitted, or None when they can.

    A `code` item offers two or more distinct ids from CODE_OPTIONS and names its
    own slot, whose id its valueset carries (`vs.<slot>`, as in base.intake); any
    other type offers none.
    """
    if slot_type != "code":
        return None if not options else f"options contradict type={slot_type} (code only)"
    if not options:
        return "type=code needs options=<id>|<id>… from the fixed answer vocabulary"
    if slot is None:
        return "type=code needs slot=<id>: its valueset is named after the slot"
    unknown = [option for option in options if option not in CODE_OPTIONS]
    if unknown:
        return (
            f"{CODE_OPTION_UNKNOWN} {unknown}: no base.intake code slot carries that "
            "label; clinician wording needed (HB-C1)"
        )
    if len(set(options)) != len(options):
        return f"an option is listed twice in {list(options)}"
    if len(options) < 2:
        return "a code item offers at least two options"
    return None


def _question_region(text: str) -> str:
    titled = re.search(r"\n##\s[^\n]*[Cc]andidate[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.S)
    if titled:
        return titled.group(1)
    numbered = re.search(r"\n##\s*3\.[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.S)
    if numbered and "\n**Q" in "\n" + numbered.group(1):
        return numbered.group(1)
    return text


def _parse_gen(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in line.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key.strip()] = value.strip().strip('"')
    return out


def extract_questions(md_text: str) -> tuple[list[Question], list[str]]:
    """Parse candidate questions; return (questions, warnings)."""
    region = _question_region(md_text)
    questions: list[Question] = []
    warnings: list[str] = []
    for seg in re.split(r"\n\*\*Q", "\n" + region)[1:]:
        qm = re.search(r'>\s*"(.+?)"', seg, re.S)
        if not qm:
            continue
        q = re.sub(r"\s*\n>\s*", " ", qm.group(1)).strip()
        q = re.sub(r"\s+", " ", q)
        label = seg.split("\n", 1)[0][:40]
        gm = re.search(r"^gen:\s*(.+)$", seg, re.M)
        gen = _parse_gen(gm.group(1)) if gm else {}
        nm = re.match(r"(\d+)", seg)
        number = int(nm.group(1)) if nm else None
        if "hold" in gen:
            warnings.append(f"hold Q{label}: {gen['hold']}")
            continue
        if number == 1 and gen:
            # Refused, never dropped: every key on the reason question would vanish.
            warnings.append(f"refused Q{label}: Q1 fills basvuru_nedeni; gen keys do not apply")
            continue
        unknown = sorted(set(gen) - GEN_KEYS)
        if unknown:
            warnings.append(f"refused Q{label}: unknown gen key(s) {unknown}")
            continue
        delivery = gen.get("delivery")
        if delivery is not None and delivery not in DELIVERIES:
            warnings.append(f"refused Q{label}: unknown delivery {delivery!r}")
            continue
        if re.search(r"\d", q):
            warnings.append(f"refused Q{label}: digit in patient text (invariant 22)")
            continue
        if q.count("?") != 1:
            warnings.append(f"refused Q{label}: not exactly one question (invariant 2)")
            continue
        slot_type = gen.get("type", "string")
        if slot_type not in SLOT_TYPES:
            warnings.append(f"refused Q{label}: unknown type {slot_type!r}")
            continue
        slot = gen.get("slot")
        if slot is not None and not SLOT_ID.match(slot):
            warnings.append(f"refused Q{label}: bad slot id {slot!r}")
            continue
        options = tuple(o.strip() for o in gen.get("options", "").split("|") if o.strip())
        problem = code_problem(slot, slot_type, options)
        if problem is not None:
            warnings.append(f"refused Q{label}: {problem}")
            continue
        if all(key in gen for key in GATE_KEYS):
            warnings.append(f"refused Q{label}: ask_if and skip_if contradict: one gate per item")
            continue
        grammar = [
            problem
            for key in GATE_KEYS
            if key in gen and (problem := _grammar_problem(key, gen[key])) is not None
        ]
        if grammar:
            warnings.append(f"refused Q{label}: {grammar[0]}")
            continue
        follow_up = gen.get("follow_up")
        if follow_up is not None and not _one_question(follow_up):
            warnings.append(f"refused Q{label}: follow-up must be one question, no digit")
            continue
        am = re.search(r"archetype:\s*`([^`]+)`", seg.split("\n", 1)[0])
        questions.append(
            Question(
                text=q,
                slot=slot,
                type=slot_type,
                ask_if=gen.get("ask_if"),
                follow_up=follow_up,
                archetype=am.group(1) if am else None,
                number=number,
                delivery=delivery,
                skip_if=gen.get("skip_if"),
                options=options,
            )
        )
    return questions, warnings


def extract_pack_options(md_text: str) -> dict[str, str]:
    """Read an optional `pack:` line (e.g. a branch-appropriate duration ask).

    Raises ValueError on a second `pack:` line or a key given twice (either would
    silently drop a value), an unknown key, an ask that is not one question, a
    `duration` other than `omit`, or `duration=omit` beside a duration text.
    """
    lines = PACK_LINE.findall(_question_region(md_text))
    if len(lines) > 1:
        raise ValueError(f"{len(lines)} pack: lines; one pack: line per proposal")
    keys = [part.split("=", 1)[0].strip() for part in (lines or [""])[0].split(";") if "=" in part]
    twice = sorted({key for key in keys if keys.count(key) > 1})
    if twice:
        raise ValueError(f"pack key(s) {twice} given twice")
    options = _parse_gen(lines[0]) if lines else {}
    unknown = sorted(set(options) - PACK_KEYS)
    if unknown:
        raise ValueError(f"unknown pack key(s) {unknown}")
    if "duration" in options:
        if options["duration"] != DURATION_OMIT:
            raise ValueError(f"pack duration={options['duration']!r}: the only value is omit")
        texts = sorted(set(options) - {"duration"})
        if texts:
            raise ValueError(f"pack duration=omit contradicts {texts}: an omitted slot has no ask")
    for key, text in options.items():
        if key != "duration" and not _one_question(text):
            raise ValueError(f"pack {key} must be one question without a digit")
    return options


def base_slot_names() -> frozenset[str]:
    """Slot names declared by base.intake, which a specialty gate may read."""
    base = yaml.safe_load(BASE_INTAKE.read_text("utf-8"))
    names: set[str] = set()
    for section in (base.get("sections") or {}).values():
        names.update((section or {}).get("slots") or {})
    return frozenset(names)


def _deferred_reason(slug: str, archetype: str | None) -> str:
    candidate = f"candidate archetype {archetype}" if archetype else "no candidate archetype"
    return (
        f"INT-032: openEHR binding deferred to the P3 export; {candidate} recorded in "
        f"docs/evidence/proposals/{slug}.md"
    )


def _slot(q: Question, sid: str, slug: str) -> dict[str, Any]:
    slot: dict[str, Any] = {"type": q.type}
    if q.options:
        slot["valueset"] = f"vs.{sid}"
    slot.update({"required": False, "ask_tr": {"tr": q.text}})
    if q.options:
        slot["choices_tr"] = {"tr": [CODE_OPTIONS[option][0] for option in q.options]}
    if q.follow_up:
        slot["follow_up_tr"] = {"tr": q.follow_up}
    if q.ask_if:
        slot["ask_if"] = q.ask_if
    if q.skip_if:
        slot["skip_if"] = q.skip_if
    if q.delivery:
        slot["delivery"] = q.delivery
    slot["openehr_deferred_reason"] = _deferred_reason(slug, q.archetype)
    return slot


def _slot_key(name: str) -> str:
    """The slot key of a bare or section-qualified reference (files/03 §6 atoms)."""
    return name.rsplit(".", 1)[-1]


def _grammar_problem(key: str, expr: str) -> str | None:
    """Why a gate is outside the DSL's `when` grammar, which the compiler parses it
    with (protocols.triage.expr), or None when it parses."""
    try:
        parse_when(expr)
    except WhenGrammarError as exc:
        return f"{key} {expr!r} is outside the gate grammar: {exc}"
    return None


def gate_reads(slot: Mapping[str, Any]) -> frozenset[str]:
    """The slot keys a slot's gates (`ask_if` and `skip_if`) read, as the DSL parses them.

    Raises WhenGrammarError (a ValueError) on a gate outside the grammar.
    """
    return frozenset(
        _slot_key(name)
        for key in GATE_KEYS
        if slot.get(key)
        for name in referenced_slots(parse_when(slot[key]))
    )


def rule_reads(rule: Mapping[str, Any]) -> frozenset[str]:
    """The slot keys a red-flag rule reads: its `when` references and its `tense_anchor`.

    base.life_threat spells the predicate `gate` (ADR-024). A predicate the grammar
    refuses (a draft's pending-value text) is read by its identifier tokens, so a
    slot it names still counts: the check fails closed, as the compiler's overlay
    check does for a `when` it cannot parse.
    """
    when = str(rule.get("when") or rule.get("gate") or "")
    try:
        names = set(referenced_slots(parse_when(when)))
    except WhenGrammarError:
        names = set(re.findall(SLOT_REF_PATTERN, when))
    anchor = rule.get("tense_anchor")
    if anchor:
        names.add(str(anchor))
    return frozenset(_slot_key(name) for name in names)


def _code_misreads(
    node: WhenNode, code_ids: Mapping[str, tuple[str, ...]]
) -> list[tuple[str, str]]:
    """(code slot, what it is compared with) for every read of a generated code slot
    that is not a comparison with one of its option ids."""
    if isinstance(node, Not):
        return _code_misreads(node.item, code_ids)
    if isinstance(node, And | Or):
        return [miss for item in node.items for miss in _code_misreads(item, code_ids)]
    if isinstance(node, BoolRef):
        name = _slot_key(node.ref.name)
        return [(name, "nothing (a bare read)")] if name in code_ids else []
    pairs: list[tuple[Ref | Lit, Ref | Lit]]
    if isinstance(node, InSet):
        pairs = [(node.operand, element) for element in node.elements]
    else:  # a Compare: either side may be the code slot
        pairs = [(node.left, node.right), (node.right, node.left)]
    misses: list[tuple[str, str]] = []
    for operand, other in pairs:
        if not isinstance(operand, Ref) or _slot_key(operand.name) not in code_ids:
            continue
        name = _slot_key(operand.name)
        if isinstance(other, Lit) and isinstance(other.value, str):
            if other.value not in code_ids[name]:
                misses.append((name, repr(other.value)))
        else:
            misses.append((name, other.name if isinstance(other, Ref) else repr(other.value)))
    return misses


def _gate_problem(
    sid: str,
    key: str,
    expr: str,
    readable: set[str],
    later: set[str],
    code_ids: Mapping[str, tuple[str, ...]],
) -> str | None:
    """Why the gate `key` of slot `sid` cannot be emitted, or None when it can.

    The gate is parsed with the DSL's `when` grammar, as the compiler parses it. It
    reads the fixed slots, base.intake or a slot declared before it — never itself
    or a later slot (files/13 §9.5, as INT-375 enforces on the merged chain), and
    never a slot nothing declares: such a gate never opens (INT-355). It compares a
    code slot of this pack only with that slot's option ids: a label (`'hayır'` for
    `hayir`) or any other value would never follow the answer.
    """
    grammar = _grammar_problem(key, expr)
    if grammar is not None:
        return f"{sid} {grammar}"
    node = parse_when(expr)
    names = {_slot_key(name) for name in referenced_slots(node)}
    if sid in names:
        return f"{sid} {key} reads itself"
    forward = sorted(names & later)
    if forward:
        return f"{sid} {key} reads later slot(s) {forward}: a gate reads only earlier slots"
    missing = sorted(names - readable)
    if missing:
        return f"{sid} {key} reads undeclared slot(s) {missing}"
    misreads = _code_misreads(node, code_ids)
    if misreads:
        name, other = misreads[0]
        return (
            f"{sid} {key} compares code slot {name} with {other}, not one of its option "
            f"ids {list(code_ids[name])}: the gate would never follow the answer"
        )
    return None


def ask_order(keys: list[str], reads: dict[str, frozenset[str]]) -> list[str]:
    """`keys` reordered so that every slot follows the slots of `keys` its gate reads.

    Stable: each step takes the earliest remaining key whose gate slots are already
    placed (a gate slot outside `keys` lives in an earlier section or in base). That
    is the order the engine's frontier asks them in (files/13 §9.2): the lowest
    position among the steps whose gate can open. Raises ValueError on a gate cycle.
    """
    inside = set(keys)
    remaining = list(keys)
    placed: list[str] = []
    while remaining:
        ready = [k for k in remaining if (reads.get(k, frozenset()) & inside) <= set(placed)]
        if not ready:
            raise ValueError(f"gate cycle among {remaining}")
        remaining.remove(ready[0])
        placed.append(ready[0])
    return placed


def _reorder_ops(
    parent_slots: dict[str, dict[str, Any]], sorular: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """A `reorder` op when the merged `sorular` would ask a gated slot before its gate.

    The merge is the resolver's: a re-declared parent id keeps the parent's position
    with this pack's definition, and a new id goes after every parent slot.
    """
    merged = {**parent_slots, **sorular}
    keys = list(merged)
    order = ask_order(keys, {key: gate_reads(slot) for key, slot in merged.items()})
    if order == keys:
        return []
    return [{"op": "reorder", "pointer": REORDER_POINTER, "order": order}]


def cluster_doc(extends: str) -> dict[str, Any] | None:
    """The committed cluster pack `extends` names, served first (None if none)."""
    name = extends.removeprefix("cluster.")
    if name == extends:
        return None
    for root in CLUSTER_PARENT_ROOTS:
        path = root / f"{name}.yaml"
        if path.exists():
            doc: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
            return doc
    return None


def parent_section(extends: str, section: str) -> dict[str, dict[str, Any]]:
    """The `section` slots, in order, of the cluster pack `extends` names ({} if none)."""
    doc = cluster_doc(extends) or {}
    slots: dict[str, dict[str, Any]] = ((doc.get("sections") or {}).get(section) or {}).get(
        "slots"
    ) or {}
    return slots


def parent_chain_rules(extends: str) -> list[dict[str, Any]]:
    """Every red-flag rule above a candidate that `extends` names, any status.

    base.life_threat (the sibling set every session evaluates), base.intake (the root
    of every chain) and each committed cluster pack between them. A draft counts: a
    physician signing it may keep its anchor.
    """
    life_threat = yaml.safe_load(LIFE_THREAT.read_text(encoding="utf-8"))
    base = yaml.safe_load(BASE_INTAKE.read_text(encoding="utf-8"))
    rules: list[dict[str, Any]] = [
        *(life_threat.get("rules") or []),
        *(base.get("red_flags") or []),
    ]
    seen = {"base.intake"}
    current = extends
    while current not in seen:
        seen.add(current)
        doc = cluster_doc(current)
        if doc is None:
            break
        rules.extend(doc.get("red_flags") or [])
        current = str(doc.get("extends") or "base.intake")
    return rules


def _omit_readers(rules: Sequence[Mapping[str, Any]]) -> list[str]:
    """The ids of the rules that read the duration slot, in `when` or as their anchor."""
    return sorted(str(rule["id"]) for rule in rules if DURATION_SLOT in rule_reads(rule))


def parent_sorular(extends: str) -> dict[str, dict[str, Any]]:
    """The `sorular` slots, in order, of the cluster pack `extends` names ({} if none)."""
    return parent_section(extends, "sorular")


def build_pack(
    draft: dict[str, Any],
    slug: str,
    questions: list[Question],
    *,
    base_slots: frozenset[str] = frozenset(),
    options: dict[str, str] | None = None,
    layer: str = "specialty",
    parent_slots: dict[str, dict[str, Any]] | None = None,
    parent_visit_slots: dict[str, dict[str, Any]] | None = None,
    chain_rules: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Pure: the pack document for `slug` (maturity L0 until signed).

    Raises ValueError on a duplicate slot id, a code item without its options or
    reusing a base or parent-chain slot id, any key on Q1, two gates on one item,
    or a gate (ask_if or skip_if) outside the `when` grammar, that reads itself, a
    later slot, or a slot neither declared earlier in this pack nor by base.intake —
    such a gate never opens, so the question would silently never be asked — or
    that compares a code item with anything but its option ids.

    `parent_slots` is the parent cluster's `sorular` section. When merging over it
    would ask a gated slot before its gate slot, the pack carries a `reorder` op.
    `parent_visit_slots` is its `ziyaret_baglami` section: under `duration=omit`
    a duration slot declared there is suppressed, since the merge would keep it.
    `chain_rules` are the red-flag rules above this pack (`parent_chain_rules`):
    `duration=omit` is refused as DURATION_OMIT_RULE_READS_SLOT while any of them,
    or this pack's own stub, reads the duration slot.
    """
    options = options or {}
    omit = options.get("duration") == DURATION_OMIT
    reason = questions[0]
    # Every field but the text, archetype and number is left at its default on Q1.
    if reason != Question(text=reason.text, archetype=reason.archetype, number=reason.number):
        raise ValueError(f"{slug}: Q1 fills basvuru_nedeni; gen keys do not apply")
    reason_follow_up = (
        REASON_FOLLOW_UP_WHEN_NEDIR
        if reason.text.endswith("nedir?")
        else REASON_FOLLOW_UP_OTHERWISE
    )
    title = (draft.get("title_tr") or slug).replace(" (L0 taslak)", "")
    stub = _stub_rule(slug, title, layer)
    readers = _omit_readers([*chain_rules, stub]) if omit else []
    if readers:
        raise ValueError(
            f"{slug}: {DURATION_OMIT_REFUSAL}: duration=omit would remove {DURATION_SLOT}, "
            f"which red-flag rule(s) {readers} read in `when` or as `tense_anchor`. A rule "
            "whose slot is gone never fires (invariant 7), and the compiler refuses that "
            "only for an overlay today (INT-382)"
        )
    fixed = FIXED_SLOTS - {DURATION_SLOT} if omit else FIXED_SLOTS
    # Every slot id the chain above already declares: a code slot may take none of them.
    chain_ids = base_slots | set(parent_slots or {}) | set(parent_visit_slots or {})
    sids = [q.slot or f"soru_{i}" for i, q in enumerate(questions[1:], 1)]
    sorular: dict[str, Any] = {}
    code_ids: dict[str, tuple[str, ...]] = {}
    for i, (sid, q) in enumerate(zip(sids, questions[1:], strict=True)):
        if sid in sorular or sid in FIXED_SLOTS:
            raise ValueError(f"{slug}: duplicate slot id {sid}")
        if q.ask_if is not None and q.skip_if is not None:
            raise ValueError(f"{slug}: {sid}: ask_if and skip_if contradict: one gate per item")
        problem = code_problem(q.slot, q.type, q.options)
        if problem is not None:
            raise ValueError(f"{slug}: {sid}: {problem}")
        if q.type == "code" and sid in chain_ids:
            raise ValueError(
                f"{slug}: {sid}: a type=code slot may not reuse a base.intake or parent-chain "
                f"slot id: two slots of that name make bare reads ambiguous and rebind vs.{sid}"
            )
        readable = set(fixed | base_slots | set(sorular))
        for key, expr in (("ask_if", q.ask_if), ("skip_if", q.skip_if)):
            if expr is None:
                continue
            gate = _gate_problem(sid, key, expr, readable, set(sids[i + 1 :]), code_ids)
            if gate is not None:
                raise ValueError(f"{slug}: {gate}")
        sorular[sid] = _slot(q, sid, slug)
        if q.type == "code":
            code_ids[sid] = q.options
    ops = _reorder_ops(parent_slots or {}, sorular)
    if omit and DURATION_SLOT in (parent_visit_slots or {}):
        ops.append({"op": "suppress_slot", "pointer": DURATION_POINTER})
    visit: dict[str, Any] = {
        "basvuru_nedeni": {
            "type": "string",
            "required": True,
            "ask_tr": {"tr": reason.text},
            "follow_up_tr": {"tr": reason_follow_up},
            "openehr_deferred_reason": _deferred_reason(slug, reason.archetype),
        },
    }
    if not omit:
        visit[DURATION_SLOT] = {
            "type": "duration",
            "required": False,
            "ask_tr": {"tr": options.get("duration_ask", DURATION_ASK)},
            "follow_up_tr": {"tr": options.get("duration_follow_up", DURATION_FOLLOW_UP)},
            "openehr_deferred_reason": _deferred_reason(slug, None),
        }
    pack: dict[str, Any] = {
        "kind": "pack",
        "id": draft["id"],
        "layer": layer,
        "version": "0.3.0",
        "schema_version": 2,
        "maturity": "L0",
        "status": "questions-authored; awaiting physician-of-record sign-off (HB-C1); not servable",
        "language": "tr",
        "title_tr": title,
        "extends": draft.get("extends", "cluster.medical"),
        "visit_types": draft.get("visit_types", ["first", "followup", "report"]),
        "sections": {
            "ziyaret_baglami": {"slots": visit},
            "sorular": {"slots": sorular},
        },
        **({"ops": ops} if ops else {}),
        "red_flags": [stub],
    }
    return pack


def _stub_rule(slug: str, title: str, layer: str) -> dict[str, Any]:
    """The branch red flag, left as the draft_needs_source stub (never fabricated)."""
    return {
        "id": f"rf.{slug}_l0_taslak",
        "label_tr": (
            f"{title} — {'kümeye' if layer == 'cluster' else 'branşa'} özgü kırmızı "
            "bayrak taslağı (klinik onay bekliyor)"
        ),
        "when": (
            f"{PENDING_MARKER} {slug} branch-specific red-flag trigger requires clinical sign-off"
        ),
        "tense": "ever",
        "tense_anchor": STUB_TENSE_ANCHOR,
        "level": "YESIL",
        "route": "EXPEDITE",
        "notify_clinic": "never",
        "status": "draft_needs_source",
        "source_gap": (
            "Trigger, EK-4 level and route await clinical sign-off (invariant 17 "
            "pending-value literal). Guideline-sourced candidates recorded in "
            f"docs/evidence/proposals/{slug}.md; acuity bound by EK-4 law "
            "(RG 13/9/2022 sayı 31952), snapshot absent. RED/life-threat stays in "
            "base.life_threat (invariant 7). Owner: physician of record "
            "(HB-C1, HB-C2, HB-C7)."
        ),
    }


def header(slug: str) -> str:
    return (
        "# REVIEW QUEUE — QUESTIONS authored; NOT servable. Promoted to L1 only by the\n"
        "# physician of record's sign-off (HB-C1).\n"
        f"{GEN_MARKER} from docs/evidence/proposals/{slug}.md\n"
        "# (guideline-sourced; reviewed per docs/evidence/verification/). Symptom-capture\n"
        "# prompts only (inv 2/10) — not diagnosis, not triage. Acuity is EK-4 law +\n"
        "# physician of record; never fabricated. RED/life-threat stays in\n"
        "# base.life_threat (inv 7).\n"
    )


def eligible(candidate_text: str, candidate: dict[str, Any]) -> str | None:
    """None when an existing review candidate may be regenerated, else why not."""
    if "clinical_signoff" in candidate:
        return "signed (clinical_signoff present)"
    if GEN_MARKER in candidate_text or LEGACY_GEN_MARKER in candidate_text:
        return None
    return "hand-authored"


def taxonomy_clusters() -> frozenset[str]:
    """Cluster ids that carry a pack in taxonomy/branches.yaml."""
    doc = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))
    return frozenset(c["id"] for c in doc.get("clusters", []) if c.get("pack"))


def cluster_target(slug: str) -> tuple[dict[str, Any], Path, Path] | str:
    """(draft, review path, served path) for a cluster_* proposal, else why not."""
    name = slug[len(CLUSTER_PREFIX) :]
    if name not in taxonomy_clusters() or name not in CLUSTER_TITLES:
        return f"unknown cluster {name!r}"
    draft = {
        "id": f"cluster.{name}",
        "title_tr": CLUSTER_TITLES[name],
        "extends": "base.intake",
        "visit_types": ["first", "followup", "report"],
    }
    return draft, REVIEW_CLUSTER / f"{name}.yaml", SERVED_CLUSTER / f"{name}.yaml"


def gen(slug: str) -> tuple[str, bool]:
    prop_p = PROP / f"{slug}.md"
    layer = "cluster" if slug.startswith(CLUSTER_PREFIX) else "specialty"
    if layer == "cluster":
        target = cluster_target(slug)
        if isinstance(target, str):
            return f"SKIP {slug}: {target}", False
        draft, out_p, served_p = target
        if (
            served_p.exists()
            and yaml.safe_load(served_p.read_text("utf-8")).get("maturity") != "L0"
        ):
            return f"skip {slug}: served cluster pack is past L0", True
    else:
        draft_p = SPEC / f"{slug}.yaml"
        out_p = REVIEW / f"{slug}.yaml"
        if not draft_p.exists():
            return f"skip {slug}: no L0 draft for this branch", True
        draft = yaml.safe_load(draft_p.read_text(encoding="utf-8"))
        if draft.get("maturity") != "L0":
            return f"skip {slug}: served pack is past L0", True
    if out_p.exists():
        out_text = out_p.read_text(encoding="utf-8")
        why = eligible(out_text, yaml.safe_load(out_text))
        if why:
            return f"skip {slug}: {why}", True
    prop_text = prop_p.read_text(encoding="utf-8")
    qs, warnings = extract_questions(prop_text)
    notes = "".join(f"\n    {w}" for w in warnings)
    try:
        options = extract_pack_options(prop_text)
    except ValueError as exc:
        return f"SKIP {slug}: {exc}{notes}", False
    if len(qs) < 3:
        return f"SKIP {slug}: only {len(qs)} questions parsed — fix the proposal{notes}", False
    if qs[0].number != 1:
        # Never let a later question silently become the visit-reason slot.
        return f"SKIP {slug}: Q1 (reason for visit) was refused or held{notes}", False
    extends = draft.get("extends", "cluster.medical")
    try:
        pack = build_pack(
            draft,
            slug,
            qs,
            base_slots=base_slot_names(),
            options=options,
            layer=layer,
            parent_slots=parent_sorular(extends),
            parent_visit_slots=parent_section(extends, "ziyaret_baglami"),
            chain_rules=parent_chain_rules(extends),
        )
    except ValueError as exc:
        return f"SKIP {slug}: {exc}{notes}", False
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(
        header(slug) + yaml.safe_dump(pack, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    return f"OK {slug}: {len(qs)} questions{notes}", True


def regen_baseline() -> None:
    from protocols.migrate.tr_baseline import authored_baseline

    trees = [
        ROOT / "packages/protocols/base",
        ROOT / "packages/protocols/specialty",
        ROOT / "tests/fixtures/protocols",
        ROOT / "files/protocols",
    ]
    cur: dict[str, Any] = {}
    for t in trees:
        cur.update(authored_baseline(t, root=ROOT))
    p = ROOT / "tests/fixtures/protocols/int297_tr_content_baseline.json"
    nl = p.read_bytes().endswith(b"\n")
    p.write_text(
        json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=2) + ("\n" if nl else ""),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("slugs", nargs="*", help="only these slugs (default: every proposal)")
    args = ap.parse_args(argv)
    slugs = args.slugs or sorted(
        Path(p).stem for p in glob.glob(str(PROP / "*.md")) if not Path(p).stem.startswith("_")
    )
    # Clusters first: a specialty candidate's ask order is read from its cluster.
    slugs = sorted(slugs, key=lambda slug: not slug.startswith(CLUSTER_PREFIX))
    ok = True
    for slug in slugs:
        line, good = gen(slug)
        ok = ok and good
        print(line)
    regen_baseline()
    print("tr baseline regenerated")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
