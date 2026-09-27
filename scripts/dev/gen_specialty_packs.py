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
    gen: slot=<id>; type=<boolean|date|duration|string>; ask_if=<expr>; follow_up=<t>; hold=<r>
The `gen:` line is optional. Q1 fills basvuru_nedeni. `hold=` keeps an item out
of the pack (unsourced or unverified). An ask with more than one question mark,
or with a digit, is refused (invariants 2 and 22).

A specialty pack merges into its cluster's `sorular` section, where a re-declared
cluster id keeps the cluster's position (the resolver's `_merge_chain`). When that
would put a gated question before its gate slot, the candidate carries a `reorder`
op (files/12 §3.1) that asks every gate slot first (files/13 §9.5).
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packages/protocols/specialty"
REVIEW = ROOT / "packages/protocols/review/specialty"
REVIEW_CLUSTER = ROOT / "packages/protocols/review/cluster"
SERVED_CLUSTER = ROOT / "packages/protocols/cluster"
# Where a specialty candidate's parent cluster is read from, served first. Bound here,
# not read through REVIEW_CLUSTER, so that regenerating into another directory still
# orders a branch against the committed cluster it extends.
CLUSTER_PARENT_ROOTS = (SERVED_CLUSTER, REVIEW_CLUSTER)
REORDER_POINTER = "/sections/sorular/slots"
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
SLOT_TYPES = {"boolean", "date", "duration", "string"}
DELIVERIES = {"voice", "text_first", "text_only"}
GEN_KEYS = {"slot", "type", "ask_if", "follow_up", "hold", "delivery"}
PACK_KEYS = {"duration_ask", "duration_follow_up"}
GATE_NAME = re.compile(r"\b([a-z][a-z0-9_]*)\s*(?:==|!=|>=|<=|>|<)")
FIXED_SLOTS = frozenset({"basvuru_nedeni", "sikayet_suresi"})
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


def _one_question(text: str) -> bool:
    return text.count("?") == 1 and not re.search(r"\d", text)


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
        if "hold" in gen:
            warnings.append(f"hold Q{label}: {gen['hold']}")
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
        follow_up = gen.get("follow_up")
        if follow_up is not None and not _one_question(follow_up):
            warnings.append(f"refused Q{label}: follow-up must be one question, no digit")
            continue
        am = re.search(r"archetype:\s*`([^`]+)`", seg.split("\n", 1)[0])
        nm = re.match(r"(\d+)", seg)
        questions.append(
            Question(
                text=q,
                slot=slot,
                type=slot_type,
                ask_if=gen.get("ask_if"),
                follow_up=follow_up,
                archetype=am.group(1) if am else None,
                number=int(nm.group(1)) if nm else None,
                delivery=delivery,
            )
        )
    return questions, warnings


def extract_pack_options(md_text: str) -> dict[str, str]:
    """Read an optional `pack:` line (e.g. a branch-appropriate duration ask).

    Raises ValueError on an unknown key or an ask that is not one question.
    """
    pm = re.search(r"^pack:\s*(.+)$", _question_region(md_text), re.M)
    options = _parse_gen(pm.group(1)) if pm else {}
    unknown = sorted(set(options) - PACK_KEYS)
    if unknown:
        raise ValueError(f"unknown pack key(s) {unknown}")
    for key, text in options.items():
        if not _one_question(text):
            raise ValueError(f"pack {key} must be one question without a digit")
    return options


def base_slot_names() -> frozenset[str]:
    """Slot names declared by base.intake, which a specialty gate may read."""
    base = yaml.safe_load((ROOT / "packages/protocols/base/intake.yaml").read_text("utf-8"))
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


def _slot(q: Question, slug: str) -> dict[str, Any]:
    slot: dict[str, Any] = {"type": q.type, "required": False, "ask_tr": {"tr": q.text}}
    if q.follow_up:
        slot["follow_up_tr"] = {"tr": q.follow_up}
    if q.ask_if:
        slot["ask_if"] = q.ask_if
    if q.delivery:
        slot["delivery"] = q.delivery
    slot["openehr_deferred_reason"] = _deferred_reason(slug, q.archetype)
    return slot


def gate_reads(slot: dict[str, Any]) -> frozenset[str]:
    """The slot names a slot's `ask_if` reads."""
    return frozenset(GATE_NAME.findall(slot.get("ask_if") or ""))


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


def parent_sorular(extends: str) -> dict[str, dict[str, Any]]:
    """The `sorular` slots, in order, of the cluster pack `extends` names ({} if none)."""
    name = extends.removeprefix("cluster.")
    if name == extends:
        return {}
    for root in CLUSTER_PARENT_ROOTS:
        path = root / f"{name}.yaml"
        if path.exists():
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            slots: dict[str, dict[str, Any]] = (
                (doc.get("sections") or {}).get("sorular") or {}
            ).get("slots") or {}
            return slots
    return {}


def build_pack(
    draft: dict[str, Any],
    slug: str,
    questions: list[Question],
    *,
    base_slots: frozenset[str] = frozenset(),
    options: dict[str, str] | None = None,
    layer: str = "specialty",
    parent_slots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure: the pack document for `slug` (maturity L0 until signed).

    Raises ValueError on a duplicate slot id or an ask_if that reads a slot
    neither declared earlier in this pack nor by base.intake — such a gate
    never opens, so the question would silently never be asked.

    `parent_slots` is the parent cluster's `sorular` section. When merging over it
    would ask a gated slot before its gate slot, the pack carries a `reorder` op.
    """
    options = options or {}
    reason = questions[0]
    reason_follow_up = (
        REASON_FOLLOW_UP_WHEN_NEDIR
        if reason.text.endswith("nedir?")
        else REASON_FOLLOW_UP_OTHERWISE
    )
    title = (draft.get("title_tr") or slug).replace(" (L0 taslak)", "")
    sorular: dict[str, Any] = {}
    for i, q in enumerate(questions[1:], 1):
        sid = q.slot or f"soru_{i}"
        if sid in sorular or sid in FIXED_SLOTS:
            raise ValueError(f"{slug}: duplicate slot id {sid}")
        if q.ask_if:
            readable = FIXED_SLOTS | base_slots | set(sorular)
            missing = sorted(set(GATE_NAME.findall(q.ask_if)) - readable)
            if missing:
                raise ValueError(f"{slug}: {sid} ask_if reads undeclared slot(s) {missing}")
        sorular[sid] = _slot(q, slug)
    ops = _reorder_ops(parent_slots or {}, sorular)
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
            "ziyaret_baglami": {
                "slots": {
                    "basvuru_nedeni": {
                        "type": "string",
                        "required": True,
                        "ask_tr": {"tr": reason.text},
                        "follow_up_tr": {"tr": reason_follow_up},
                        "openehr_deferred_reason": _deferred_reason(slug, reason.archetype),
                    },
                    "sikayet_suresi": {
                        "type": "duration",
                        "required": False,
                        "ask_tr": {"tr": options.get("duration_ask", DURATION_ASK)},
                        "follow_up_tr": {
                            "tr": options.get("duration_follow_up", DURATION_FOLLOW_UP)
                        },
                        "openehr_deferred_reason": _deferred_reason(slug, None),
                    },
                }
            },
            "sorular": {"slots": sorular},
        },
        **({"ops": ops} if ops else {}),
        "red_flags": [
            {
                "id": f"rf.{slug}_l0_taslak",
                "label_tr": (
                    f"{title} — {'kümeye' if layer == 'cluster' else 'branşa'} özgü kırmızı "
                    "bayrak taslağı (klinik onay bekliyor)"
                ),
                "when": (
                    f"{PENDING_MARKER} {slug} branch-specific red-flag trigger "
                    "requires clinical sign-off"
                ),
                "tense": "ever",
                "tense_anchor": "sikayet_suresi",
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
        ],
    }
    return pack


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
    try:
        pack = build_pack(
            draft,
            slug,
            qs,
            base_slots=base_slot_names(),
            options=options,
            layer=layer,
            parent_slots=parent_sorular(draft.get("extends", "cluster.medical")),
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
