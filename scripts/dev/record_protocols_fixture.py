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
  are the names in `intake_learning.proposals.PROPOSAL_TARGETS` (the closed set
  of things Loop 2 may ever ask for), and `unmet_checks` the names in
  `intake_learning.evidence.REQUIRED_CHECKS`, both through
  `intake_platform.admin.console_vocab`, which tests/admin/test_console_vocab.py
  holds equal to its owners (INT-565) — every producer is a later issue,
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

INT-565: the body is built by ``GET /admin/protocols``'s own builder,
``intake_api.admin.protocols_console.protocols_payload``, over the committed
taxonomy and pack tree, so the fixture and the route cannot drift
(``tests/admin/test_protocols_console.py`` holds them equal).

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from intake_api.admin.protocols_console import protocols_payload
from protocols.cli import DEFAULT_PACKS_ROOT, load_registry
from protocols.taxonomy import load_taxonomy

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "protocols.payload.json"
TAXONOMY = DEFAULT_PACKS_ROOT / "taxonomy" / "branches.yaml"


def build_payload() -> dict[str, Any]:
    """The route's own builder over the committed taxonomy and pack tree."""
    return protocols_payload(
        registry=load_registry(DEFAULT_PACKS_ROOT),
        taxonomy=load_taxonomy(TAXONOMY),
        taxonomy_source=str(TAXONOMY),
        generated_at=datetime.now(UTC),
    )


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
