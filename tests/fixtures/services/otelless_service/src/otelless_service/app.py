"""A fixture service that mounts the endpoints and skips the shared OTel setup.

The negative control for invariant 15's second requirement: before INT-021 this
shape passed ``make check``, because the only gate read pyproject.toml and the
declaration was complete. Spans and logs from a service like this never reach
:class:`intake_platform.otel.RedactingSpanExporter`, so nothing scrubs them.
"""

from __future__ import annotations

from fastapi import FastAPI
from intake_platform.health import mount_health
from intake_platform.metrics import mount_http_metrics


def create_app() -> FastAPI:
    app = FastAPI(title="otelless-service")
    mount_http_metrics(app, "otelless_service")
    mount_health(app)
    return app
