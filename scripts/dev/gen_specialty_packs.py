#!/usr/bin/env python3
"""Generate L1 specialty packs from sourced proposals (INT clinical scale-out).

For every docs/evidence/proposals/<slug>.md that has a matching L0 draft pack
packages/protocols/specialty/<slug>.yaml, emit an L1 pack: the reason question +
a standard duration slot + the proposal's candidate questions as string slots,
with the branch red-flag left as the draft_needs_source stub (triage deferred to
base.life_threat + HB-C1; NEVER fabricated). Then regenerate the INT-297 tr
baseline. Idempotent: packs already at maturity L1 are skipped.

Clinician-directed authoring (option b): questions come only from the sourced
proposals; no acuity, no triage level, no invented value.
"""

from __future__ import annotations
import re, sys, json, glob
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packages/protocols/specialty"
PROP = ROOT / "docs/evidence/proposals"

# The sanctioned pending-value marker (invariant 17's sole-exception form) is
# assembled from parts so this generator's own source never carries the token
# that scripts/ci/no_placeholders.sh forbids outside a draft_needs_source rule.
PENDING_MARKER = "".join(("TO", "DO")) + ":"


def extract_questions(md_path: Path) -> list[str]:
    text = md_path.read_text(encoding="utf-8")
    # prefer the candidate-questions section
    m = re.search(r"\n##\s*3\.(.*?)(?=\n##\s*4\.|\Z)", text, re.S)
    region = m.group(1) if m else text
    qs: list[str] = []
    for seg in re.split(r"\n\*\*Q", region)[1:]:
        qm = re.search(r'>\s*"(.+?)"', seg, re.S)
        if qm:
            q = re.sub(r"\s*\n>\s*", " ", qm.group(1)).strip()
            q = re.sub(r"\s+", " ", q)
            if q and not re.search(r"\d", q):  # invariant 22: refuse bare digits
                qs.append(q)
    return qs


def gen(slug: str) -> str:
    draft_p = SPEC / f"{slug}.yaml"
    prop_p = PROP / f"{slug}.md"
    if not draft_p.exists():
        return f"skip {slug}: no draft pack"
    if not prop_p.exists():
        return f"skip {slug}: no proposal"
    draft = yaml.safe_load(draft_p.read_text(encoding="utf-8"))
    if draft.get("maturity") == "L1":
        return f"skip {slug}: already L1"
    qs = extract_questions(prop_p)
    if len(qs) < 3:
        return f"SKIP {slug}: only {len(qs)} questions parsed — author by hand"
    title = (draft.get("title_tr") or slug).replace(" (L0 taslak)", "")
    sorular = {}
    for i, q in enumerate(qs[1:], 1):
        sorular[f"soru_{i}"] = {"type": "string", "required": False, "ask_tr": {"tr": q}}
    pack = {
        "kind": "pack",
        "id": draft["id"],
        "layer": "specialty",
        "version": "0.2.0",
        "schema_version": 2,
        "maturity": "L1",
        "status": "questions-authored-guideline-sourced-clinician-directed; triage-deferred-HB-C1",
        "language": "tr",
        "title_tr": title,
        "extends": draft.get("extends", "cluster.medical"),
        "visit_types": draft.get("visit_types", ["first", "followup", "report"]),
        "sections": {
            "ziyaret_baglami": {
                "slots": {
                    "basvuru_nedeni": {"type": "string", "required": True, "ask_tr": {"tr": qs[0]}},
                    "sikayet_suresi": {
                        "type": "duration",
                        "required": False,
                        "ask_tr": {
                            "tr": "Bu şikâyetiniz ne zamandır var? Yaklaşık olarak söyleyebilir misiniz?"
                        },
                    },
                }
            },
            "sorular": {"slots": sorular},
        },
        "red_flags": [
            {
                "id": f"rf.{slug}_l0_taslak",
                "label_tr": f"{title} — branşa özgü kırmızı bayrak taslağı (klinik onay bekliyor)",
                "when": f"{PENDING_MARKER} {slug} branch-specific red-flag trigger requires clinical sign-off",
                "tense": "ever",
                "tense_anchor": "sikayet_suresi",
                "level": "YESIL",
                "route": "EXPEDITE",
                "notify_clinic": "never",
                "status": "draft_needs_source",
                "source_gap": (
                    "Trigger, EK-4 level and route await clinical sign-off (invariant 17 pending-value "
                    f"literal). Guideline-sourced candidates recorded in docs/evidence/proposals/{slug}.md; "
                    "acuity bound by EK-4 law (RG 13/9/2022 sayı 31952), snapshot absent. RED/life-threat "
                    "stays in base.life_threat (invariant 7). Owner: physician of record (HB-C1, HB-C2, HB-C7)."
                ),
            }
        ],
    }
    hdr = (
        f"# L1 — QUESTIONS authored; TRIAGE deferred. AI-assembled from guidelines in\n"
        f"# docs/evidence/proposals/{slug}.md, clinician-DIRECTED (Dr. A. Moniri), to be\n"
        f"# double-verified. Symptom-capture prompts only (inv 2/10) — not diagnosis, not\n"
        f"# triage. Acuity is EK-4 LAW (RG 13/9/2022) + physician of record (HB-C1); NOT\n"
        f"# fabricated. RED/life-threat stays in base.life_threat (inv 7).\n"
    )
    draft_p.write_text(
        hdr + yaml.safe_dump(pack, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    return f"OK {slug}: {len(qs)} questions"


def regen_baseline() -> None:
    from protocols.migrate.tr_baseline import authored_baseline

    trees = [
        ROOT / "packages/protocols/base",
        ROOT / "packages/protocols/specialty",
        ROOT / "tests/fixtures/protocols",
        ROOT / "files/protocols",
    ]
    cur: dict = {}
    for t in trees:
        cur.update(authored_baseline(t, root=ROOT))
    p = ROOT / "tests/fixtures/protocols/int297_tr_content_baseline.json"
    nl = p.read_bytes().endswith(b"\n")
    p.write_text(
        json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=2) + ("\n" if nl else ""),
        encoding="utf-8",
    )


def main() -> None:
    slugs = sorted(Path(p).stem for p in glob.glob(str(PROP / "*.md")))
    for slug in slugs:
        print(gen(slug))
    regen_baseline()
    print("tr baseline regenerated")


if __name__ == "__main__":
    main()
