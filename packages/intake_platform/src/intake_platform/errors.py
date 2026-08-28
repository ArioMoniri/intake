"""GlitchTip error reporting, flag-gated and scrubbed (INT-023; files/10 §3).

files/10 §3 calls the crash reporter "the leak nobody mentioned": sentry-sdk
(the protocol GlitchTip speaks) serialises local variables into events by
default, so a local named ``pcm`` posts patient voice to the tracker on any
audio-path exception, and request bodies carry transcripts. This module
exists so no service wires the SDK by hand:

- :func:`setup_error_reporting` activates ONLY when ``INTAKE_GLITCHTIP_DSN``
  is set AND the ``error_reporting`` flag is on; sentry-sdk is an OPTIONAL
  import guarded like the OTLP exporter in :mod:`intake_platform.otel` — when
  absent the function logs and no-ops, never raises.
- Every event passes :func:`scrub_event` before send: request bodies dropped
  entirely, message/exception strings through
  :func:`intake_platform.redaction.redact_text`, frame locals dropped, and
  extra/tags restricted to the same attribute allow-list as the log layer
  (:data:`intake_platform.otel.ALLOWED_LOG_ATTRIBUTES`).
- ``include_local_variables=False`` is forced (files/10 §3 names it a live
  defect class) and ``traces_sample_rate=0.0`` — traces belong to OTel.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from intake_platform.flags import FlagProvider, default_provider
from intake_platform.otel import ALLOWED_LOG_ATTRIBUTES
from intake_platform.redaction import redact_text

__all__ = ["ERROR_REPORTING_FLAG", "scrub_event", "setup_error_reporting"]

logger = logging.getLogger(__name__)

ERROR_REPORTING_FLAG = "error_reporting"


def _scrub_value(value: Any) -> Any:
    return redact_text(value) if isinstance(value, str) else value


def _whitelist_attributes(attributes: Any) -> dict[str, Any]:
    """Same closed allow-list as the log layer: an attribute key not on the
    list never reaches the tracker; surviving strings are redacted."""
    if not isinstance(attributes, dict):
        return {}
    return {
        key: _scrub_value(value)
        for key, value in attributes.items()
        if key in ALLOWED_LOG_ATTRIBUTES
    }


def _scrub_exception(exception: Any) -> None:
    if not isinstance(exception, dict):
        return
    for value in exception.get("values") or []:
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("value"), str):
            value["value"] = redact_text(value["value"])
        stacktrace = value.get("stacktrace")
        frames = stacktrace.get("frames") if isinstance(stacktrace, dict) else None
        for frame in frames or []:
            if isinstance(frame, dict):
                # locals are the pcm-buffer leak; include_local_variables is
                # already False, this drops anything that slips through.
                frame.pop("vars", None)


def _scrub_breadcrumbs(breadcrumbs: Any) -> None:
    if not isinstance(breadcrumbs, dict):
        return
    for crumb in breadcrumbs.get("values") or []:
        if not isinstance(crumb, dict):
            continue
        if isinstance(crumb.get("message"), str):
            crumb["message"] = redact_text(crumb["message"])
        if "data" in crumb:
            crumb["data"] = _whitelist_attributes(crumb["data"])


def scrub_event(event: dict[str, Any], hint: Any) -> dict[str, Any]:
    """``before_send`` hook, kept a pure function so it is testable without
    the SDK. Mutates and returns ``event`` (the sentry-sdk contract)."""
    event.pop("request", None)  # bodies, headers, cookies, URLs: all dropped
    event.pop("user", None)
    if isinstance(event.get("message"), str):
        event["message"] = redact_text(event["message"])
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        if isinstance(logentry.get("message"), str):
            logentry["message"] = redact_text(logentry["message"])
        if isinstance(logentry.get("params"), list):
            logentry["params"] = [_scrub_value(param) for param in logentry["params"]]
    _scrub_exception(event.get("exception"))
    _scrub_breadcrumbs(event.get("breadcrumbs"))
    if "extra" in event:
        event["extra"] = _whitelist_attributes(event["extra"])
    if "tags" in event:
        event["tags"] = _whitelist_attributes(event["tags"])
    return event


def setup_error_reporting(flags: FlagProvider | None = None) -> bool:
    """Activate GlitchTip reporting when configured, flagged on, and the SDK
    is present. Returns True only when the SDK was actually initialised."""
    dsn = os.environ.get("INTAKE_GLITCHTIP_DSN")
    if not dsn:
        return False
    provider = flags if flags is not None else default_provider()
    if not provider.get_bool(ERROR_REPORTING_FLAG, False):
        logger.info("INTAKE_GLITCHTIP_DSN set but the error_reporting flag is off")
        return False
    options: dict[str, Any] = {
        "dsn": dsn,
        "before_send": scrub_event,
        "include_local_variables": False,  # files/10 §3: pcm locals = voice
        "send_default_pii": False,
        "max_request_body_size": "never",
        "attach_stacktrace": False,
        "traces_sample_rate": 0.0,  # traces belong to OTel, not the tracker
        "environment": os.environ.get("INTAKE_ENV", "dev"),
    }
    try:
        import sentry_sdk
    except ImportError:
        logger.info(
            "INTAKE_GLITCHTIP_DSN set but sentry-sdk is not installed; error reporting stays off"
        )
        return False
    sentry_sdk.init(**options)
    logger.info("error reporting active (GlitchTip, scrubbed)")
    return True
