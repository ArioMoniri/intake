"""INT-205 — the console feed the Security module (files/08 §3, INT-192) renders.

Shape borrowed from services/api/src/intake_api/taxonomy_feed.py, including the
part that matters most: **a missing stream reads as ``None``, never as an empty
list**. An empty Security module that means "nothing was detected" and one that
means "the SIEM was never wired up" must not look the same on a screen someone
uses to decide whether an incident is happening.

The feed carries a ``version`` — the sha256 of the raw bytes it was built from
— so the console can cache and so an evidence export can say which bytes it
saw. It also carries counts by signal and by severity, because those are what
the module leads with, and counting on this side means the console never has to
walk alerts to draw a tile.

Nothing here reaches the network. The Wazuh manager writes ``alerts.json``; this
reads it. The scrub happens on our side of that file on purpose: a control that
lives in the vendor's configuration is a control the vendor's next upgrade can
reset.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from intake_platform.siem.errors import AlertRefused
from intake_platform.siem.models import SecurityAlert, Severity, Signal
from intake_platform.siem.normalise import normalise_alert
from intake_platform.siem.rules import RuleCatalogue, load_rule_catalogue

__all__ = [
    "ALERTS_PATH_ENV",
    "ConsoleFeed",
    "FeedCounts",
    "default_alerts_path",
    "load_console_feed",
]

_LOG = logging.getLogger(__name__)

#: Where the manager's alert stream is mounted. A path, not a threshold and not
#: a secret, so a default is honest here.
ALERTS_PATH_ENV = "INTAKE_SIEM_ALERTS_PATH"
_DEFAULT_ALERTS_PATH = Path(".cache") / "siem" / "alerts.json"

_SEVERITY_ORDER = {severity: rank for rank, severity in enumerate(Severity)}


def default_alerts_path() -> Path:
    return Path(os.environ.get(ALERTS_PATH_ENV, str(_DEFAULT_ALERTS_PATH)))


class FeedCounts(BaseModel):
    """What the Security module's tiles show, counted once on this side."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    refused: int = Field(ge=0)
    by_signal: dict[Signal, int]
    by_severity: dict[Severity, int]


class ConsoleFeed(BaseModel):
    """A scrubbed, ordered view of the alert stream at one point in time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: sha256 of the bytes this feed was built from
    version: str = Field(pattern=r"^[0-9a-f]{64}$")
    alerts: tuple[SecurityAlert, ...]
    counts: FeedCounts


def _catalogue(repo_root: Path) -> RuleCatalogue:
    security = repo_root / "infra" / "security"
    return load_rule_catalogue(
        security / "wazuh" / "rules" / "intake_rules.xml",
        security / "falco" / "rules" / "intake_rules.yaml",
    )


def load_console_feed(
    path: Path | None = None, *, repo_root: Path | None = None
) -> ConsoleFeed | None:
    """Read the alert stream and return the scrubbed feed, or ``None``.

    ``None`` means "not configured": the stream is absent or unreadable. Every
    other failure — an unparseable line, an alert that cannot be scrubbed — is
    counted in ``refused`` and does not stop the feed, because one malformed
    line must not blind the console to the rest.
    """
    stream = default_alerts_path() if path is None else path
    root = Path(__file__).resolve().parents[5] if repo_root is None else repo_root
    try:
        raw = stream.read_bytes()
    except OSError as exc:
        _LOG.warning(
            "siem alert stream unreadable", extra={"path": str(stream), "error": type(exc).__name__}
        )
        return None

    catalogue = _catalogue(root)
    alerts: list[SecurityAlert] = []
    refused = 0
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # The line itself is never logged: an unparseable line from a
            # monitor that reads every log on the box is exactly the line most
            # likely to hold something we may not repeat (invariant 6).
            refused += 1
            continue
        if not isinstance(payload, dict):
            refused += 1
            continue
        try:
            alerts.append(normalise_alert(payload, catalogue))
        except (AlertRefused, ValueError):
            refused += 1

    alerts.sort(key=lambda alert: (_SEVERITY_ORDER[alert.severity], alert.observed_at))
    counts = FeedCounts(
        total=len(alerts),
        refused=refused,
        by_signal={signal: sum(1 for a in alerts if a.signal is signal) for signal in Signal},
        by_severity={
            severity: sum(1 for a in alerts if a.severity is severity) for severity in Severity
        },
    )
    return ConsoleFeed(version=hashlib.sha256(raw).hexdigest(), alerts=tuple(alerts), counts=counts)
