"""A fixture service that satisfies all four of CLAUDE.md invariant 15.

Never imported — tests/observability/test_invariant_15.py reads it with ``ast``
through :func:`intake_platform.health.scan_service_sources`. It exists so the
gate's PASS case is exercised by something other than the real tree, and so the
negative-control fixtures next to it differ by exactly one requirement.
"""

from __future__ import annotations

from fastapi import FastAPI
from intake_platform.health import mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import setup_otel


def create_app() -> FastAPI:
    setup_otel("good_service")
    app = FastAPI(title="good-service")
    mount_http_metrics(app, "good_service")
    mount_health(app)
    return app
