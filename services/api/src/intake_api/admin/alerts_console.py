"""The alerts feed behind ``GET /admin/alerts`` (INT-481; files/08 §3).

The staging host runs Prometheus and Alertmanager on its internal network.
What is firing reaches the admin console through the API's admin surface and
nowhere else: the browser never talks to Alertmanager (files/08 §0b F1). This
module is that one read, built the way :mod:`intake_api.admin.ops_prom` reads
Prometheus:

- **One fixed request.** ``GET {base}/api/v2/alerts`` with no parameters, which
  is Alertmanager's default: active, silenced, inhibited and unprocessed
  alerts. Nothing in the caller's request reaches it.
- **A plain origin from the environment.** ``INTAKE_OPS_ALERTMANAGER_URL`` is
  scheme and host[:port], optionally followed by a single ``/``, and nothing
  else: no credentials, no path, no query, no fragment. Unset, there is no
  client and nothing is dialled; malformed, the same, under its own reason.
- **Every failure is one machine code**: ``alertmanager_unreachable``,
  ``alertmanager_http_<status>`` or ``alertmanager_bad_response``. The
  server's own text is never echoed.

**Unknown is a state (invariant 17).** When the source cannot answer, the
document says ``unknown`` with the code, ``counts`` is ``null`` (never zeros,
because "nothing is firing" and "nobody could ask" are different statements),
``alerts`` is empty and ``withheld`` is 0.

**Ids only (invariant 6).** Per alert the reader takes ``labels.alertname``,
``labels.severity``, the labels in :data:`ALERT_LABEL_KEYS`, ``status.state``
and ``startsAt``, and nothing else. ``annotations`` (summary, description and
runbook text), ``generatorURL`` (the PromQL and an internal address),
``fingerprint``, ``receivers``, ``endsAt`` and ``updatedAt`` are never read, so
they cannot be returned. An alert whose name is not id-shaped, whose state is
not one of :data:`STATES` or whose start is not an RFC 3339 instant is
*withheld*: counted, never painted. A painted label whose value is not
id-shaped is dropped on its own and the alert is still painted.

``counts`` buckets the painted alerts by severity whatever their state (a
silenced page is still a page), so ``counts`` plus ``withheld`` is every alert
Alertmanager returned. The list is ordered page, ticket, other, then oldest
start first, then by name, and holds at most :data:`MAX_PAINTED` alerts. The
overflow is withheld, so the cap drops the least severe, newest alerts first.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Final
from urllib.parse import urlsplit

import httpx

from intake_api.admin.ops_prom import ID_LABEL

__all__ = [
    "ALERTNAME",
    "ALERTS_SCHEMA",
    "ALERT_LABEL_KEYS",
    "ENV_ALERTMANAGER_URL",
    "MAX_PAINTED",
    "SEVERITIES",
    "STATES",
    "AlertmanagerClient",
    "AlertmanagerUnavailable",
    "alertmanager_client_from_env",
    "build_alerts_console",
    "load_alerts_console",
]

ALERTS_SCHEMA: Final = "intake.admin.alerts.v1"
ENV_ALERTMANAGER_URL: Final = "INTAKE_OPS_ALERTMANAGER_URL"
MAX_PAINTED: Final = 200
_TIMEOUT_S: Final = 5.0
_ALERTS_PATH: Final = "/api/v2/alerts"

#: The label keys a painted alert may carry besides its name and severity: the
#: keys the committed rule files (``infra/observability/*-rules.yaml``) declare,
#: plus ``component`` (a synthetic probe's target id). Closed: a key outside it
#: is not painted, and a test holds it to the rule files so a new rule label
#: cannot vanish from the console unnoticed.
ALERT_LABEL_KEYS: Final = frozenset({"service", "slo", "component", "budget_id", "scope", "period"})

#: An alert name the console paints: Prometheus's alert-name grammar, bounded.
ALERTNAME: Final = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,127}")
#: Alertmanager API v2 ``status.state`` values.
STATES: Final = ("active", "suppressed", "unprocessed")
#: The severity buckets, in display order. ``other`` takes any value that is
#: not ``page`` or ``ticket``, and a missing label.
SEVERITIES: Final = ("page", "ticket", "other")

#: RFC 3339 date-time. Alertmanager emits up to nine fractional digits and a
#: ``Z`` or a numeric offset; the fraction is read and discarded.
_RFC3339: Final = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?"
    r"(?:([Zz])|([+-])([0-9]{2}):([0-9]{2}))"
)


class AlertmanagerUnavailable(Exception):
    """Alertmanager could not answer. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _shaped(body: object) -> list[Mapping[str, Any]]:
    """The v2 alert list: objects, each with a ``labels`` and a ``status`` object."""
    if not isinstance(body, list):
        raise AlertmanagerUnavailable("alertmanager_bad_response")
    for row in body:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("labels"), dict)
            or not isinstance(row.get("status"), dict)
        ):
            raise AlertmanagerUnavailable("alertmanager_bad_response")
    return body


@dataclass(frozen=True)
class AlertmanagerClient:
    base_url: str
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    timeout_s: float = _TIMEOUT_S

    def alerts(self) -> list[Mapping[str, Any]]:
        """Every alert Alertmanager holds, or one refusal."""
        url = f"{self.base_url.rstrip('/')}{_ALERTS_PATH}"
        try:
            with httpx.Client(
                transport=self.transport, timeout=self.timeout_s, follow_redirects=False
            ) as client:
                response = client.get(url)
        except httpx.HTTPError:
            raise AlertmanagerUnavailable("alertmanager_unreachable") from None
        if response.status_code // 100 != 2:
            raise AlertmanagerUnavailable(f"alertmanager_http_{response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise AlertmanagerUnavailable("alertmanager_bad_response") from None
        return _shaped(body)


def alertmanager_client_from_env(env: Mapping[str, str]) -> AlertmanagerClient | None:
    """The configured client, ``None`` when unset; anything but a plain origin raises.

    The refusal names the variable and never its value, which could carry a
    credential somebody pasted into it.
    """
    raw = env.get(ENV_ALERTMANAGER_URL, "").strip()
    if not raw:
        return None
    refusal = ValueError(
        f"{ENV_ALERTMANAGER_URL} must be a plain http(s) origin: scheme and host[:port], "
        "with no credentials, path, query or fragment"
    )
    if any(ch.isspace() or not ch.isprintable() for ch in raw):
        raise refusal
    parts = urlsplit(raw)
    try:
        port = parts.port  # a non-numeric or out-of-range port raises here
    except ValueError:
        raise refusal from None
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or port == 0
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise refusal
    return AlertmanagerClient(base_url=f"{parts.scheme}://{parts.netloc}")


def _stamp(instant: datetime) -> str:
    utc = instant.astimezone(UTC)
    return (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}"
        f"T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}Z"
    )


def _instant(raw: object) -> str | None:
    """An RFC 3339 instant as UTC whole seconds; ``None`` when it is not one."""
    if not isinstance(raw, str):
        return None
    match = _RFC3339.fullmatch(raw)
    if match is None:
        return None
    year, month, day, hour, minute, second, zulu, sign, off_h, off_m = match.groups()
    offset = timedelta(0)
    if not zulu:
        if int(off_h) > 23 or int(off_m) > 59:
            return None
        offset = timedelta(hours=int(off_h), minutes=int(off_m))
        offset = offset if sign == "+" else -offset
    try:
        instant = datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            tzinfo=timezone(offset),
        )
        return _stamp(instant)
    except (ValueError, OverflowError):
        return None


def _paint(alert: Mapping[str, Any]) -> dict[str, Any] | None:
    """One alert as the console shows it, or ``None`` to withhold it."""
    labels: Mapping[str, Any] = alert["labels"]
    status: Mapping[str, Any] = alert["status"]
    name = labels.get("alertname")
    if not isinstance(name, str) or ALERTNAME.fullmatch(name) is None:
        return None
    state = status.get("state")
    if not isinstance(state, str) or state not in STATES:
        return None
    starts_at = _instant(alert.get("startsAt"))
    if starts_at is None:
        return None
    severity = labels.get("severity")
    painted: dict[str, str] = {}
    for key in sorted(ALERT_LABEL_KEYS):
        value = labels.get(key)
        if isinstance(value, str) and ID_LABEL.fullmatch(value) is not None:
            painted[key] = value
    return {
        "alertname": name,
        "severity": severity if severity in ("page", "ticket") else "other",
        "state": state,
        "starts_at": starts_at,
        "labels": painted,
    }


def _order(alert: Mapping[str, Any]) -> tuple[int, str, str, str, tuple[tuple[str, str], ...]]:
    # severity, oldest first, name; then state and labels so that two alerts
    # of one rule (one per service, say) do not swap places between builds
    return (
        SEVERITIES.index(alert["severity"]),
        alert["starts_at"],
        alert["alertname"],
        alert["state"],
        tuple(alert["labels"].items()),
    )


def _unknown(reason: str) -> dict[str, Any]:
    return {
        "source": {"state": "unknown", "reason": reason},
        "counts": None,
        "alerts": [],
        "withheld": 0,
    }


def build_alerts_console(
    *,
    client: AlertmanagerClient | None,
    now: datetime,
    misconfigured: bool = False,
) -> dict[str, Any]:
    """The whole ``intake.admin.alerts.v1`` document."""
    envelope = {"schema": ALERTS_SCHEMA, "generated_at": _stamp(now)}
    if client is None:
        reason = "alertmanager_misconfigured" if misconfigured else "alertmanager_unconfigured"
        return {**envelope, **_unknown(reason)}
    try:
        received: Sequence[Mapping[str, Any]] = client.alerts()
    except AlertmanagerUnavailable as failure:
        return {**envelope, **_unknown(failure.code)}
    readable = [painted for painted in map(_paint, received) if painted is not None]
    shown = sorted(readable, key=_order)[:MAX_PAINTED]
    counts = dict.fromkeys(SEVERITIES, 0)
    for alert in shown:
        counts[alert["severity"]] += 1
    return {
        **envelope,
        "source": {"state": "ok", "reason": None},
        "counts": counts,
        "alerts": shown,
        "withheld": len(received) - len(shown),
    }


def load_alerts_console(now: datetime, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Wire the feed from the process environment.

    A malformed ``INTAKE_OPS_ALERTMANAGER_URL`` is not a crash and not a guess:
    the source reads ``alertmanager_misconfigured`` and nothing is dialled.
    """
    env = os.environ if env is None else env
    try:
        client, misconfigured = alertmanager_client_from_env(env), False
    except ValueError:
        client, misconfigured = None, True
    return build_alerts_console(client=client, now=now, misconfigured=misconfigured)
