"""The Clinical quality & safety module's console composite (INT-565; files/08 §3, §4 D/E).

``GET /admin/quality-safety`` is the body ``apps/admin-web/src/safety`` renders
(INT-185): the RED/YELLOW/GREEN distribution, the false-RED review queue,
PolicyGuard blocks by violation class and note acceptance by specialty.

- **Triage routing has one producer.** Every level is attributed to the rules
  engine, because only ``packages/protocols/triage`` produces one (invariant
  1); an LLM appends ``candidate_flags`` capped at ``YELLOW_REVIEW``.
- **The false-RED queue annotates, never downgrades,** and holds pointers, not
  patient words (invariant 6). Its contract is the INT-175 ``false_red_review``
  queue verbatim; a staff read of the content behind an item is refused while
  HB-L6 is open. There is no persisted item store, so the queue is empty.
- **PolicyGuard blocks are a live counter read at serve time** through the
  API's Prometheus reader, by the sealed violation classes
  (:mod:`intake_platform.admin.console_vocab`; the API does not import the
  voice runtime). Unread, the section says why and carries no count.
- **Triage events and note acceptance are catalogued as planned:** nothing
  emits them, so their counts are the empty state the note names. The builder
  refuses to paint that state for a series the catalogue calls live, so the
  day one is promoted, the parity test fails until this composite reads it.

Counts and ids only, and no rate without a named corpus and a date
(invariant 20). :func:`quality_safety_payload` is pure;
``scripts/dev/record_safety_fixture.py`` records the e2e fixture through it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

from clinical_schemas.triage import TriageLevel
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import AdminRole, AdminWiring
from intake_platform.admin.console_vocab import POLICYGUARD_CLASSES
from intake_platform.observability.annotation import Label, QueueId, SectionReason, queue_def
from intake_platform.slo import MetricsCatalog
from protocols.taxonomy import Taxonomy

from intake_api.admin.console_sources import (
    WINDOW,
    Reading,
    catalogued,
    load_catalog,
    prom_from_env,
    read_counts,
)
from intake_api.admin.deps import AdminCaller
from intake_api.errors import taxonomy_unconfigured
from intake_api.state import get_state

__all__ = [
    "QUALITY_SAFETY_LABELS",
    "QUALITY_SAFETY_QUERIES",
    "quality_safety_payload",
    "quality_safety_read",
]

#: The LLM candidate ceiling — a clinician-only, non-routing level (invariant 1).
CANDIDATE_CAP: Final = "YELLOW_REVIEW"

#: The only PromQL this composite runs. A caller cannot add to it.
QUALITY_SAFETY_QUERIES: Final[Mapping[str, str]] = {
    "policyguard_blocks": f"sum by (class) (increase(policyguard_blocks_total[{WINDOW}]))",
}
QUALITY_SAFETY_LABELS: Final[Mapping[str, frozenset[str]]] = {
    "policyguard_blocks": frozenset({"class"}),
}


def _planned(catalog: MetricsCatalog, metric_id: str) -> str:
    status = catalogued(catalog, metric_id).status
    if status != "planned":
        raise ValueError(
            f"{metric_id} is catalogued {status}: its counts come from a scrape, and this "
            "composite paints only the planned empty state for it (invariant 17)"
        )
    return status


def _triage(catalog: MetricsCatalog) -> dict[str, Any]:
    metric_id = "triage.events_total"
    return {
        "metric_id": metric_id,
        "metric_status": _planned(catalog, metric_id),
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


def _false_red() -> dict[str, Any]:
    queue = queue_def(QueueId.FALSE_RED_REVIEW)
    return {
        "queue_id": queue.id.value,
        "enqueue_scope": queue.enqueue_scope,
        "reviewer_roles": sorted(role.value for role in queue.reviewer_roles),
        "labels": [label.value for label in Label],
        "section_reasons": [reason.value for reason in SectionReason],
        "content_scope": queue.content_scope,
        "content_blocker": queue.content_blocker,
        # the annotation module grants no content read: asking is refused (HB-L6)
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


def _policyguard(catalog: MetricsCatalog, reading: Reading) -> dict[str, Any]:
    metric_id = "policyguard.blocks_total"
    unexpected = sorted(set(reading.values) - set(POLICYGUARD_CLASSES))
    if unexpected:
        # a class off the sealed set is a drifted emitter; paint no count
        reading = Reading.unavailable("unexpected_label")
    return {
        "metric_id": metric_id,
        "metric_status": catalogued(catalog, metric_id).status,
        "window": WINDOW,
        "source_available": reading.available,
        "source_reason": reading.reason,
        "allowed_classes": list(POLICYGUARD_CLASSES),
        "classes": [
            {"class": cls, "count": reading.values.get(cls, 0) if reading.available else None}
            for cls in POLICYGUARD_CLASSES
        ],
        "note": (
            "PolicyGuard blocks patient-facing text by violation class (invariant 2: no "
            "diagnosis/treatment/prognosis, one question per turn, B1 Turkish, siz "
            f"register), summed over every profile for the last {WINDOW}. Read from the "
            "metrics scrape at serve time; without one, no count is shown (invariant 17)."
        ),
    }


def _acceptance(catalog: MetricsCatalog, taxonomy: Taxonomy) -> dict[str, Any]:
    metric_id = "note.acceptance_rate"
    rows: list[dict[str, Any]] = []
    for branch in taxonomy.branches:
        if not taxonomy.cluster_of(branch).intake:
            # pre-visit intake produces no note for a non-intake branch (Acil Tıp)
            continue
        rows.append(
            {
                "branch_id": branch.id,
                "name_tr": branch.name_tr,
                "cluster": branch.cluster,
                "delivered": 0,
                "accepted": 0,
                # a rate is a labelled measurement (corpus + date), never a bare number
                "measurement": None,
            }
        )
    return {
        "metric_id": metric_id,
        "metric_status": _planned(catalog, metric_id),
        "rows": rows,
        "note": (
            "Note acceptance is a count of accepted-plus-edited notes over notes "
            "delivered, rolled up by specialty — a measurement, never an accuracy "
            "or sensitivity claim (invariant 20). note.acceptance_rate is planned "
            "and no note has been delivered, so every branch is an empty state "
            "(invariant 17)."
        ),
    }


def quality_safety_payload(
    *,
    catalog: MetricsCatalog,
    taxonomy: Taxonomy,
    policyguard: Reading,
    generated_at: datetime,
) -> dict[str, Any]:
    """The composite, from the catalogue, the taxonomy and one reading. Pure."""
    return {
        "generated_at": generated_at.date().isoformat(),
        "triage_events": _triage(catalog),
        "false_red_queue": _false_red(),
        "policyguard_classes": _policyguard(catalog, policyguard),
        "acceptance_by_specialty": _acceptance(catalog, taxonomy),
    }


async def quality_safety_read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    loaded = get_state(request).taxonomy()
    if loaded is None:
        raise taxonomy_unconfigured()
    # synchronous httpx, off the event loop; the query table is this module's
    reading = await run_in_threadpool(
        read_counts,
        prom_from_env(os.environ),
        QUALITY_SAFETY_QUERIES,
        QUALITY_SAFETY_LABELS,
        "policyguard_blocks",
    )
    return quality_safety_payload(
        catalog=load_catalog(),
        taxonomy=loaded.taxonomy,
        policyguard=reading,
        generated_at=datetime.now(UTC),
    )
