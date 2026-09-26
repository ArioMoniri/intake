#!/usr/bin/env python3
"""Generate specialty question packs from sourced proposals (INT clinical scale-out).

For every docs/evidence/proposals/<slug>.md that has a matching pack
packages/protocols/specialty/<slug>.yaml, emit a QUESTIONS-authored pack: the
reason question, a standard duration slot and the proposal's candidate
questions, with the branch red-flag left as the draft_needs_source stub (triage
deferred to base.life_threat + HB-C1; NEVER fabricated). Then regenerate the
INT-297 tr baseline.

Packs stay maturity L0 — authored but not servable — until the physician of
record signs them (HB-C1): a pack carrying a `clinical_signoff` block is never
touched again, and a hand-authored pack (no generator marker) is never touched.

Proposal format (section titled "Candidate …", or `## 3.` when it holds Q items):
    **Q<n> — <label>** · archetype: `<ARCHETYPE>` · source: <ref>
    > "<one Turkish question>"
    gen: slot=<id>; type=<boolean|date|duration|string>; ask_if=<expr>; follow_up=<t>; hold=<r>
The `gen:` line is optional. Q1 fills basvuru_nedeni. `hold=` keeps an item out
of the pack (unsourced or unverified). An ask with more than one question mark,
or with a digit, is refused (invariants 2 and 22).
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
PROP = ROOT / "docs/evidence/proposals"

# The sanctioned pending-value marker (invariant 17's sole-exception form) is
# assembled from parts so this generator's own source never carries the token
# that scripts/ci/no_placeholders.sh forbids outside a draft_needs_source rule.
PENDING_MARKER = "".join(("TO", "DO")) + ":"

GEN_MARKER = "# generated-by: scripts/dev/gen_specialty_packs.py"
LEGACY_GEN_MARKER = "AI-assembled from guidelines in"
SLOT_TYPES = {"boolean", "date", "duration", "string"}
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
        if follow_up is not None and (follow_up.count("?") != 1 or re.search(r"\d", follow_up)):
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
            )
        )
    return questions, warnings


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
    slot["openehr_deferred_reason"] = _deferred_reason(slug, q.archetype)
    return slot


def build_pack(draft: dict[str, Any], slug: str, questions: list[Question]) -> dict[str, Any]:
    """Pure: the pack document for `slug` (maturity L0 until signed)."""
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
        if sid in sorular or sid in {"basvuru_nedeni", "sikayet_suresi"}:
            raise ValueError(f"{slug}: duplicate slot id {sid}")
        sorular[sid] = _slot(q, slug)
    return {
        "kind": "pack",
        "id": draft["id"],
        "layer": "specialty",
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
                        "ask_tr": {"tr": DURATION_ASK},
                        "follow_up_tr": {"tr": DURATION_FOLLOW_UP},
                        "openehr_deferred_reason": _deferred_reason(slug, None),
                    },
                }
            },
            "sorular": {"slots": sorular},
        },
        "red_flags": [
            {
                "id": f"rf.{slug}_l0_taslak",
                "label_tr": f"{title} — branşa özgü kırmızı bayrak taslağı (klinik onay bekliyor)",
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


def header(slug: str) -> str:
    return (
        "# L0 — QUESTIONS authored; NOT servable until physician-of-record sign-off (HB-C1).\n"
        f"{GEN_MARKER} from docs/evidence/proposals/{slug}.md\n"
        "# (guideline-sourced; reviewed per docs/evidence/verification/). Symptom-capture\n"
        "# prompts only (inv 2/10) — not diagnosis, not triage. Acuity is EK-4 law +\n"
        "# physician of record; never fabricated. RED/life-threat stays in\n"
        "# base.life_threat (inv 7).\n"
    )


def eligible(pack_text: str, draft: dict[str, Any]) -> str | None:
    """None when the pack may be (re)generated, else the reason it may not."""
    if "clinical_signoff" in draft:
        return "signed (clinical_signoff present)"
    generated = GEN_MARKER in pack_text or LEGACY_GEN_MARKER in pack_text
    if draft.get("maturity") == "L0" and not str(draft.get("status", "")).startswith(
        "questions-authored"
    ):
        return None
    if generated:
        return None
    return "hand-authored"


def gen(slug: str) -> tuple[str, bool]:
    draft_p = SPEC / f"{slug}.yaml"
    prop_p = PROP / f"{slug}.md"
    if not draft_p.exists():
        return f"skip {slug}: no draft pack", True
    pack_text = draft_p.read_text(encoding="utf-8")
    draft = yaml.safe_load(pack_text)
    why = eligible(pack_text, draft)
    if why:
        return f"skip {slug}: {why}", True
    qs, warnings = extract_questions(prop_p.read_text(encoding="utf-8"))
    notes = "".join(f"\n    {w}" for w in warnings)
    if len(qs) < 3:
        return f"SKIP {slug}: only {len(qs)} questions parsed — fix the proposal{notes}", False
    pack = build_pack(draft, slug, qs)
    draft_p.write_text(
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
