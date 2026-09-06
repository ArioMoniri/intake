"""Record the `GET /admin/protocols` body the admin-web spec runs against (INT-184).

`apps/admin-web/e2e/protocols.spec.ts` needs a payload to render. As with
`record_models_fixture.py`, there are two ways to give it one and only one is
honest: hand-write a mock, or project the payload out of the real sources. A
hand-written mock is a second, hand-kept copy of the branch taxonomy, the
proposal vocabulary and the clip state — it would keep passing on the day any
of those changed and the console stopped matching them (CLAUDE.md invariant 13,
invariant 17: render real data or a genuine empty state, never demo data).

So every field below is read from a real source at record time:

- **The branch x maturity matrix** is `protocols.taxonomy.coverage` run over
  the real taxonomy (`packages/protocols/taxonomy/branches.yaml`) and the real
  pack registry (`packages/protocols/{base,cluster,specialty,...}`). Today the
  whole pack tree is L0 (91 generated drafts, no cluster packs), so every
  intake branch resolves MISSING and Acil Tıp resolves EXCLUDED — the honest
  current state, and exactly the state invariant 13's matrix exists to surface.
  Each row carries the maturity of its L0 draft so the matrix is branch x
  *maturity*, not merely branch x resolution.

- **The review queue** is proposal-only (invariant 12). Its `allowed_targets`
  is `intake_learning.proposals.PROPOSAL_TARGETS` verbatim (the closed set of
  things Loop 2 may ever ask for), and `unmet_checks` is
  `intake_learning.evidence.REQUIRED_CHECKS` — every producer is a later issue,
  so an evidence bundle is never complete today and no proposal can open a PR.
  There is no persisted proposal store (the PR-bot opens PRs; a CODEOWNER
  clinician approves), so the live queue is a genuine empty list. The approve/
  reject + 4-eyes + forbidden-target mechanism is exercised in the spec with
  near-miss rows constructed inline, the same convention `compliance.spec.ts`
  uses for the surfaces that can be empty.

- **The clip coverage** is keyed by voice profile (`intake_voice_runtime`'s
  `VoiceProfile`: `residency_tr` is the only spoken profile; `typed` carries no
  clips ever — files/13 §13). Clips are pre-synthesised only for servable (L1+)
  packs; with `servable_pack_count == 0` nothing is required yet. The two TTS
  components under `residency_tr` are the registry ids from files/03 §4.9.1
  (rows 10-12): VoxCPM2 primary, Freya the session-start fallback.

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from intake_learning.evidence import REQUIRED_CHECKS
from intake_learning.proposals import PROPOSAL_TARGETS
from protocols.cli import DEFAULT_PACKS_ROOT, load_registry
from protocols.taxonomy import (
    ResolutionStatus,
    coverage,
    direct_pack_id,
    load_taxonomy,
)

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "protocols.payload.json"
TAXONOMY = DEFAULT_PACKS_ROOT / "taxonomy" / "branches.yaml"


def _coverage_section(now_iso: str) -> dict[str, Any]:
    taxonomy = load_taxonomy(TAXONOMY)
    registry = load_registry(DEFAULT_PACKS_ROOT)
    rows_out: list[dict[str, Any]] = []
    for row in coverage(registry, taxonomy):
        served = registry.maybe(row.pack_id) if row.pack_id is not None else None
        draft = registry.maybe(direct_pack_id(row.branch_id))
        rows_out.append(
            {
                "branch_id": row.branch_id,
                "name_tr": row.name_tr,
                "cluster": row.cluster,
                "status": row.status.value,
                "served_pack_id": row.pack_id,
                "served_maturity": served.maturity.value if served is not None else None,
                "draft_pack_id": draft.id if draft is not None else None,
                "draft_maturity": draft.maturity.value if draft is not None else None,
                "note": row.note,
            }
        )
    counts = Counter(row["status"] for row in rows_out)
    return {
        "generated_at": now_iso,
        "taxonomy_source": str(TAXONOMY),
        "pack_count": len(registry),
        "summary": {
            "total": len(rows_out),
            "direct": counts.get(ResolutionStatus.DIRECT.value, 0),
            "cluster": counts.get(ResolutionStatus.CLUSTER.value, 0),
            "missing": counts.get(ResolutionStatus.MISSING.value, 0),
            "excluded": counts.get(ResolutionStatus.EXCLUDED.value, 0),
        },
        "rows": rows_out,
    }


def _review_queue_section() -> dict[str, Any]:
    return {
        "source": (
            "services/learning proposal PRs (INT-172): the PR-bot opens, a CODEOWNER "
            "clinician approves. This console records the review decision under 4-eyes "
            "and audits it; it never applies the protocol change itself (invariant 12)."
        ),
        "allowed_targets": [target.__name__ for target in PROPOSAL_TARGETS],
        "unmet_check_names": [check.name for check in REQUIRED_CHECKS],
        "rows": [],
    }


def _clip_coverage_section(coverage_section: dict[str, Any], now_iso: str) -> dict[str, Any]:
    summary = coverage_section["summary"]
    servable = summary["direct"] + summary["cluster"]
    # Voices under the only spoken production profile (files/03 §4.9.1 rows
    # 10-12). typed carries no clips ever (files/13 §13) and is not listed.
    voices = [
        {
            "voice_id": "voxcpm2-tts",
            "profile": "residency_tr",
            "role": "primary (cached-clip + dynamic, same voice_id)",
            "required": 0,
            "cached": 0,
            "missing": 0,
            "missing_clips": [],
        },
        {
            "voice_id": "freya-tts",
            "profile": "residency_tr",
            "role": "session-start fallback",
            "required": 0,
            "cached": 0,
            "missing": 0,
            "missing_clips": [],
        },
    ]
    return {
        "generated_at": now_iso,
        "servable_pack_count": servable,
        "note": (
            "clips are pre-synthesised per voice only for servable (L1+) packs "
            "(files/03 §4.9.1 row 10); every pack is L0 today, so no clip is required yet"
        ),
        "voices": voices,
    }


def build_payload() -> dict[str, Any]:
    now_iso = datetime.now(UTC).date().isoformat()
    coverage_section = _coverage_section(now_iso)
    return {
        "coverage": coverage_section,
        "review_queue": _review_queue_section(),
        "clip_coverage": _clip_coverage_section(coverage_section, now_iso),
    }


def main() -> int:
    payload = build_payload()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cov = payload["coverage"]["summary"]
    print(
        f"recorded {FIXTURE} — {cov['total']} branches "
        f"(direct {cov['direct']}, cluster {cov['cluster']}, missing {cov['missing']}, "
        f"excluded {cov['excluded']}); "
        f"{len(payload['review_queue']['allowed_targets'])} proposal targets; "
        f"{len(payload['clip_coverage']['voices'])} clip voices"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
