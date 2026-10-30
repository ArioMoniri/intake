"""Record the `GET /admin/quality-safety` body admin-web renders (INT-185).

`apps/admin-web/e2e/safety.spec.ts` needs a payload to render. As with
`record_models_fixture.py` and `record_protocols_fixture.py`, there are two
ways to give it one and only one is honest: hand-write a mock, or project the
payload out of the real sources. A hand-written mock is a second, hand-kept
copy of the triage levels, the annotation-queue contract, the PolicyGuard
violation classes and the branch taxonomy — it would keep passing on the day
any of those changed and the console stopped matching them (CLAUDE.md
invariant 17: render real data or a genuine empty state, never demo data).

So every field below is read from a real source at record time:

- **Triage events** — the RED/YELLOW/GREEN routing distribution — is keyed by
  ``clinical_schemas.triage.TriageLevel`` (the only three routing levels) and
  every row is attributed to ``rules_engine``, because invariant 1 makes the
  rules engine the *sole* producer of RED/YELLOW/GREEN; an LLM may only append
  ``candidate_flags`` capped at ``YELLOW_REVIEW`` (``LlmCandidateTriage`` — a
  clinician-only, non-routing ceiling). The metric id is ``triage.events_total``
  from ``observability/metrics_catalog.yaml``, whose ``status`` (planned) the
  builder checks — so with no emitting service landed yet every count is a
  genuine 0 (invariant 17), not fabricated volume.

- **The false-RED queue** is the ``false_red_review`` annotation queue
  (INT-175): its enqueue scope, reviewer roles, closed-enum verdict labels and
  section reasons, and — crucially — its ``content_scope`` (``None``) and open
  ``content_blocker`` (HB-L6) are read verbatim from
  ``intake_platform.observability.annotation``. The queue is a *review* surface
  that records annotations only; it can never downgrade a rules-engine RED
  (invariant 1), and staff reads of the patient content behind an item are
  refused, not granted (HB-L6). There is no persisted item store, so the live
  queue is a genuine empty list; the annotate-never-downgrade and content-leak
  refusals are exercised in the spec with near-miss rows constructed inline,
  the same convention ``compliance.spec.ts`` and ``protocols.spec.ts`` use for
  emptyable surfaces.

- **PolicyGuard classes** is the breakdown of ``policyguard.blocks_total`` by
  ``intake_voice_runtime.talker.policy_guard.ViolationClass`` — the seven
  invariant-2 categories (no diagnosis/treatment/prognosis, one question per
  turn, not-too-long, ``siz`` register, no unexplained jargon) — through
  ``intake_platform.admin.console_vocab``, which tests/admin/test_console_vocab.py
  holds equal to the enum. The metric is ``live`` and the route reads it from
  the scrape at serve time (INT-565). This repository records no scrape, so the
  fixture is the route's own unread state: ``source_available`` false, the
  reason ``prometheus_unconfigured`` and no count — never a skeleton of zeros.

- **Acceptance by specialty** is ``note.acceptance_rate`` rolled up over the
  real intake branches of ``packages/protocols/taxonomy/branches.yaml`` (Acil
  Tıp and any non-intake cluster are excluded — pre-visit intake produces no
  note for them). These are *counts* — notes delivered and notes accepted — and
  never an accuracy/sensitivity claim (invariant 20); a rate is shown only
  through the INT-183 measurement discipline (a value with a named corpus and a
  date), and with the metric planned and no note delivered yet every row is a
  genuine empty state.

INT-565: the body is built by ``GET /admin/quality-safety``'s own builder,
``intake_api.admin.quality_safety_console.quality_safety_payload``, so the
fixture and the route cannot drift (``tests/admin/test_quality_safety_console.py``
holds them equal).

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from intake_api.admin.console_sources import Reading, load_catalog
from intake_api.admin.quality_safety_console import quality_safety_payload
from protocols.cli import DEFAULT_PACKS_ROOT
from protocols.taxonomy import load_taxonomy

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "safety.payload.json"
TAXONOMY = DEFAULT_PACKS_ROOT / "taxonomy" / "branches.yaml"
METRICS_CATALOG = Path("observability") / "metrics_catalog.yaml"


def build_payload() -> dict[str, Any]:
    """The route's own builder with no scrape configured, as in this repository."""
    return quality_safety_payload(
        catalog=load_catalog(METRICS_CATALOG),
        taxonomy=load_taxonomy(TAXONOMY),
        policyguard=Reading.unavailable("prometheus_unconfigured"),
        generated_at=datetime.now(UTC),
    )


def main() -> int:
    payload = build_payload()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"recorded {FIXTURE} — "
        f"{len(payload['triage_events']['levels'])} triage levels; "
        f"false-RED queue {payload['false_red_queue']['queue_id']} "
        f"(blocker {payload['false_red_queue']['content_blocker']}); "
        f"{len(payload['policyguard_classes']['classes'])} PolicyGuard classes "
        f"(source_available={payload['policyguard_classes']['source_available']}); "
        f"{len(payload['acceptance_by_specialty']['rows'])} intake specialties"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
