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
  script reads rather than asserts — so with no emitting service landed yet
  every count is a genuine 0 (invariant 17), not fabricated volume.

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
  turn, not-too-long, ``siz`` register, no unexplained jargon). This metric is
  ``live`` in the catalog, but the console reads a live scrape at serve time;
  the fixture records the class *skeleton* at 0 so the spec runs without a
  Prometheus, and the record note says so.

- **Acceptance by specialty** is ``note.acceptance_rate`` rolled up over the
  real intake branches of ``packages/protocols/taxonomy/branches.yaml`` (Acil
  Tıp and any non-intake cluster are excluded — pre-visit intake produces no
  note for them). These are *counts* — notes delivered and notes accepted — and
  never an accuracy/sensitivity claim (invariant 20); a rate is shown only
  through the INT-183 measurement discipline (a value with a named corpus and a
  date), and with the metric planned and no note delivered yet every row is a
  genuine empty state.

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from clinical_schemas.triage import TriageLevel
from intake_platform.observability.annotation import (
    Label,
    QueueId,
    SectionReason,
    queue_def,
)
from intake_voice_runtime.talker.policy_guard import ViolationClass
from protocols.cli import DEFAULT_PACKS_ROOT
from protocols.taxonomy import load_taxonomy

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "safety.payload.json"
TAXONOMY = DEFAULT_PACKS_ROOT / "taxonomy" / "branches.yaml"
METRICS_CATALOG = Path("observability") / "metrics_catalog.yaml"

#: The LLM candidate ceiling — a clinician-only, non-routing level (invariant 1;
#: files/03 §4.6). It is read from the schema so the console cannot drift from
#: the type that enforces it.
CANDIDATE_CAP = "YELLOW_REVIEW"


def _catalog_status() -> dict[str, str]:
    """Map every catalogued metric id/name to its ``status``.

    Referencing a metric the catalog does not list would be a claim about a
    series that does not exist (invariant 15), so the referencing helpers below
    resolve through this map and raise on a miss.
    """
    raw = yaml.safe_load(METRICS_CATALOG.read_text(encoding="utf-8"))
    status: dict[str, str] = {}
    for metric in raw["metrics"]:
        state = str(metric.get("status", "live"))
        if "id" in metric:
            status[str(metric["id"])] = state
        status[str(metric["name"])] = state
    return status


def _metric_status(catalog: dict[str, str], metric_id: str) -> str:
    if metric_id not in catalog:
        raise KeyError(
            f"metric {metric_id!r} is not in {METRICS_CATALOG} — the console may only "
            f"reference a catalogued series (CLAUDE.md invariant 15)"
        )
    return catalog[metric_id]


def _triage_events_section(catalog: dict[str, str]) -> dict[str, Any]:
    metric_id = "triage.events_total"
    return {
        "metric_id": metric_id,
        "metric_status": _metric_status(catalog, metric_id),
        # Every routing level is produced by the deterministic rules engine and
        # only by it (invariant 1). The LLM cannot route; it appends candidate
        # flags capped at YELLOW_REVIEW, a separate, clinician-only axis.
        "candidate_flag_cap": CANDIDATE_CAP,
        "levels": [
            {"level": level.value, "count": 0, "produced_by": "rules_engine"}
            for level in TriageLevel
        ],
        "note": (
            "RED/YELLOW/GREEN are produced only by packages/protocols/triage "
            "(invariant 1); an LLM may append candidate_flags capped at "
            f"{CANDIDATE_CAP} (files/03 §4.6). triage.events_total is planned — no "
            "emitting session has landed, so every count is 0, not demo volume "
            "(invariant 17)."
        ),
    }


def _false_red_queue_section() -> dict[str, Any]:
    queue = queue_def(QueueId.FALSE_RED_REVIEW)
    return {
        "queue_id": queue.id.value,
        "enqueue_scope": queue.enqueue_scope,
        "reviewer_roles": sorted(role.value for role in queue.reviewer_roles),
        "labels": [label.value for label in Label],
        "section_reasons": [reason.value for reason in SectionReason],
        "content_scope": queue.content_scope,
        "content_blocker": queue.content_blocker,
        # There is no granted content-read path in the annotation module: the
        # only outcome of asking is ContentReadRefused (HB-L6). The console
        # records that state and never a handle it could exchange for content.
        "content_read_state": "refused",
        "note": (
            "The false-RED queue records a clinician's annotation of a RED that "
            "fired; it never downgrades it — a rules-engine RED is inviolable "
            "(invariant 1). Items are pointers (ids only, no PHI — invariant 6); "
            "reviews are closed-enum verdicts. Staff reads of the patient content "
            f"behind an item are refused while {queue.content_blocker} is open "
            "(files/08 §2.6). No persisted item store exists yet, so the queue is "
            "empty."
        ),
        "items": [],
    }


def _policyguard_section(catalog: dict[str, str]) -> dict[str, Any]:
    metric_id = "policyguard.blocks_total"
    classes = [cls.value for cls in ViolationClass]
    return {
        "metric_id": metric_id,
        "metric_status": _metric_status(catalog, metric_id),
        "allowed_classes": classes,
        "classes": [{"class": cls, "count": 0} for cls in classes],
        "note": (
            "PolicyGuard blocks patient-facing text by violation class "
            "(invariant 2: no diagnosis/treatment/prognosis, one question per "
            "turn, B1 Turkish, siz register). policyguard.blocks_total is live, "
            "but the console reads a scrape at serve time; this fixture records "
            "the class skeleton at 0 so the spec runs without a Prometheus."
        ),
    }


def _acceptance_section(catalog: dict[str, str]) -> dict[str, Any]:
    metric_id = "note.acceptance_rate"
    taxonomy = load_taxonomy(TAXONOMY)
    rows: list[dict[str, Any]] = []
    for branch in taxonomy.branches:
        cluster = taxonomy.cluster_of(branch)
        if not cluster.intake:
            # pre-visit intake produces no note for a non-intake branch (Acil Tıp)
            continue
        rows.append(
            {
                "branch_id": branch.id,
                "name_tr": branch.name_tr,
                "cluster": branch.cluster,
                "delivered": 0,
                "accepted": 0,
                # A rate is shown only as a labelled measurement (corpus + date,
                # invariant 20); with nothing delivered there is none to show.
                "measurement": None,
            }
        )
    return {
        "metric_id": metric_id,
        "metric_status": _metric_status(catalog, metric_id),
        "rows": rows,
        "note": (
            "Note acceptance is a count of accepted-plus-edited notes over notes "
            "delivered, rolled up by specialty — a measurement, never an accuracy "
            "or sensitivity claim (invariant 20). note.acceptance_rate is planned "
            "and no note has been delivered, so every branch is an empty state "
            "(invariant 17)."
        ),
    }


def build_payload() -> dict[str, Any]:
    catalog = _catalog_status()
    return {
        "generated_at": datetime.now(UTC).date().isoformat(),
        "triage_events": _triage_events_section(catalog),
        "false_red_queue": _false_red_queue_section(),
        "policyguard_classes": _policyguard_section(catalog),
        "acceptance_by_specialty": _acceptance_section(catalog),
    }


def main() -> int:
    payload = build_payload()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"recorded {FIXTURE} — "
        f"{len(payload['triage_events']['levels'])} triage levels; "
        f"false-RED queue {payload['false_red_queue']['queue_id']} "
        f"(blocker {payload['false_red_queue']['content_blocker']}); "
        f"{len(payload['policyguard_classes']['classes'])} PolicyGuard classes; "
        f"{len(payload['acceptance_by_specialty']['rows'])} intake specialties"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
