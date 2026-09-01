"""INT-172 — the invariant-15 shell around a weekly batch job.

CLAUDE.md invariant 15 asks every service for ``/healthz``, ``/readyz``,
``/metrics``, ``/version``, OTel through the shared setup, an SLO file and a
synthetic probe. ``services/learning`` is a weekly job rather than a
request-serving API (files/09 §4: "runs weekly as an Inspector → Architect
pipeline"), and the contract still applies: the job is a process an operator
has to be able to see, and a scrape endpoint is how the counters in
:mod:`intake_learning.inspector`, :mod:`intake_learning.architect` and
:mod:`intake_learning.evidence` reach the console signals files/10 §9's
learning row asks for.

``/readyz`` answers **503 today**, and that is the honest answer rather than a
gap. Readiness for this service means "a scheduled run could promote a
finding", and it could not: files/09 §4 requires an effect size and states no
floor for one, so :meth:`PromotionThresholds.from_blueprint` raises. A job
that reported itself ready while structurally unable to produce a proposal
would be the wrong answer, and it is the answer a boolean stub would give.

This module is the only part of the package that mounts anything. The
``proposal_scope`` gate scopes its strict import allow-list to the pipeline
modules for that reason: the shell is shared platform code every service
mounts, and the pipeline is what invariant 12 constrains.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel

from intake_learning.architect import AwaitingHumanValue, PromotionThresholds

__all__ = ["create_app"]

logger = logging.getLogger("intake_learning")

_otel_installed = False


def _setup_observability() -> None:
    """Shared OTel setup + JSON logging, once per process (invariant 15)."""
    global _otel_installed
    if _otel_installed:
        return
    setup_otel("learning")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    _otel_installed = True


async def _promotion_thresholds_ready() -> bool:
    """Can a scheduled run promote anything at all?

    Named ``promotion_thresholds`` so the 503 body says which value is
    missing. The check reads no configuration and reaches no network: the
    answer is a property of what the blueprint states.
    """
    try:
        PromotionThresholds.from_blueprint()
    except AwaitingHumanValue:
        return False
    return True


def create_app() -> FastAPI:
    _setup_observability()
    app = FastAPI(title="intake-learning")
    mount_http_metrics(app, "learning")
    mount_health(
        app,
        readiness=[ReadinessCheck("promotion_thresholds", _promotion_thresholds_ready)],
    )
    return app
