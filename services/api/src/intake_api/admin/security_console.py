"""The Security module's console composite (INT-565; files/08 §3; files/10 §7, §9).

``GET /admin/security`` is the body ``apps/admin-web/src/security`` renders
(INT-192): SIEM summaries, egress denials, the audit chain's status and the
pen-test findings tracker, each from a source the API already holds.

- **SIEM** is ``intake_platform.siem.load_console_feed`` (INT-205). An absent
  alert stream is *not configured*, which is deliberately not "nothing
  detected": no count is shown until the stream is mounted.
- **Egress denials** are ``sec.egress_denied_total`` read from the metrics
  scrape at serve time over a stated window; unread, the tile says why and
  shows no number — a bare 0 would read as "no denials" (invariant 17).
- **The audit chain's status** is the daily verifier's verdict for this
  deployment, stated without reading the chain. HB-I12: the head is published
  outside the ``platform_admin`` blast radius and this surface sits inside it,
  so no admin response carries a chain hash (INT-180's
  ``test_no_admin_response_carries_a_chain_hash``) and this module never reads
  the store. Verification is the daily job's (INT-016), under the read-only
  role outside the writer, and no anchor is published while HB-I12 is open —
  so the verdict is ``anchor_missing``, fail-closed. The outcome vocabulary
  comes from :mod:`intake_platform.admin.console_vocab`, because importing the
  verifier module would export its gauge from this process.
- **Pen-test findings**: no assessment is recorded (the first external test
  is before the P2 pilot, files/10 §7), so the tracker is empty against the
  vulnerability SLA it will be judged by.

Counts and ids only, never a chain hash (invariant 6; HB-I12); no accuracy
claim (invariant 20).
:func:`security_payload` is pure; ``scripts/dev/record_security_fixture.py``
records the e2e fixture through it.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import AdminRole, AdminWiring
from intake_platform.admin.console_vocab import AUDIT_VERIFIER_OUTCOMES
from intake_platform.siem import ConsoleFeed, Severity, Signal, load_console_feed
from intake_platform.slo import MetricsCatalog

from intake_api.admin.console_sources import (
    WINDOW,
    Reading,
    catalogued,
    load_catalog,
    prom_from_env,
    read_counts,
)
from intake_api.admin.deps import AdminCaller

__all__ = [
    "SECURITY_LABELS",
    "SECURITY_QUERIES",
    "security_payload",
    "security_read",
]

#: The acceptance's three detectors. Wazuh and Falco share the console feed;
#: CrowdSec is the edge bouncer, whose decisions have no console feed loader.
_DETECTORS: Final = ("wazuh", "falco", "crowdsec")

#: The tracker's closed vocabularies: a value off them is refused, not rendered.
_FINDING_SEVERITIES: Final = ("critical", "high", "medium", "low", "info")
_FINDING_STATUSES: Final = ("open", "remediating", "resolved", "accepted_risk", "false_positive")

#: files/10 §7: critical 72 h (3 d) / high 7 d / medium 30 d. None is invented
#: for low and info, which carry no stated SLA.
_SLA_DAYS_BY_SEVERITY: Final = {"critical": 3, "high": 7, "medium": 30}

#: The only PromQL this composite runs. A caller cannot add to it.
SECURITY_QUERIES: Final = {
    "egress_denied": f"sum(increase(sec_egress_denied_total[{WINDOW}]))",
}
SECURITY_LABELS: Final = {"egress_denied": frozenset[str]()}

_ANCHOR_MISSING: Final = "anchor_missing"


def _detector(name: str, feed: ConsoleFeed | None) -> dict[str, Any]:
    if name == "crowdsec":
        return {
            "detector": name,
            "configured": False,
            "count": None,
            "reason": (
                "the CrowdSec bouncer's decisions have no console feed loader in this "
                "repository; its scenarios are committed under "
                "infra/security/edge/crowdsec and enforced at the edge (INT-203)"
            ),
        }
    if feed is None:
        return {
            "detector": name,
            "configured": False,
            "count": None,
            "reason": (
                "the Wazuh manager's alert stream is not mounted, so load_console_feed "
                "returns None (not configured) rather than an empty feed (INT-205)"
            ),
        }
    count = sum(1 for alert in feed.alerts if alert.source.value == name)
    return {"detector": name, "configured": True, "count": count, "reason": ""}


def _siem(catalog: MetricsCatalog, feed: ConsoleFeed | None) -> dict[str, Any]:
    return {
        "metric_id": "siem_alerts_ingested_total",
        "refused_metric_id": catalogued(catalog, "siem_alerts_refused_total").name,
        "metric_status": catalogued(catalog, "siem_alerts_ingested_total").status,
        "feed_configured": feed is not None,
        "feed_version": feed.version if feed is not None else None,
        "total": feed.counts.total if feed is not None else None,
        "refused": feed.counts.refused if feed is not None else None,
        "allowed_signals": [signal.value for signal in Signal],
        "allowed_severities": [severity.value for severity in Severity],
        "allowed_sources": list(_DETECTORS),
        "by_signal": (
            {} if feed is None else {k.value: n for k, n in feed.counts.by_signal.items()}
        ),
        "by_severity": (
            {} if feed is None else {k.value: n for k, n in feed.counts.by_severity.items()}
        ),
        "detectors": [_detector(name, feed) for name in _DETECTORS],
        "note": (
            "Wazuh / Falco / CrowdSec alert summaries from intake_platform.siem.feed."
            "load_console_feed (INT-205), counted by signal and severity. The feed returns "
            "not-configured (None) until the alert stream is mounted, so the console shows that "
            "state rather than a 0 — 'nothing detected' and 'never wired up' must not look the "
            "same (invariant 17). Signals and severities are sealed to the platform's own enums, "
            "and every alert carries ids, not narrative (invariant 6)."
        ),
    }


def _egress(catalog: MetricsCatalog, reading: Reading) -> dict[str, Any]:
    entry = catalogued(catalog, "sec.egress_denied_total")
    return {
        "metric_id": "sec.egress_denied_total",
        "metric_status": entry.status,
        "window": WINDOW,
        "source_available": reading.available,
        "source_reason": reading.reason,
        "denied_total": reading.values.get("", 0) if reading.available else None,
        "target": entry.target or "",
        "note": (
            "Denied egress attempts from the PHI path (sec.egress_denied_total, INT-018; "
            "invariants 14/19), summed over the last "
            f"{WINDOW}. The allow-list is default-deny and the PHI path reaches no external "
            "model or speech vendor at all; the catalogue target is 0 and any increase pages. "
            "Read from the metrics scrape at serve time — without one the tile is "
            "source-unavailable, never a bare 0 (invariant 17)."
        ),
    }


def _audit_chain(catalog: MetricsCatalog) -> dict[str, Any]:
    if _ANCHOR_MISSING not in AUDIT_VERIFIER_OUTCOMES:
        raise AssertionError("the verifier's outcome vocabulary lost anchor_missing")
    return {
        "metric_id": "sec.audit_chain_ok",
        "metric_status": catalogued(catalog, "sec.audit_chain_ok").status,
        "allowed_outcomes": list(AUDIT_VERIFIER_OUTCOMES),
        "outcome": _ANCHOR_MISSING,
        "ok": False,
        "anchor_available": False,
        "reason": (
            "no externally anchored head is published (HB-I12), so nothing independent can "
            "attest the chain: a self-consistent chain survives both a truncation and a full "
            "re-forge, and reporting it intact would be a pass by omission (files/10 §2)"
        ),
        "note": (
            "Daily audit hash-chain verification (sec.audit_chain_ok, INT-016; invariant 4). "
            "1 means verified against the EXTERNALLY ANCHORED head, never merely that the store "
            "agrees with itself — a truncation and a full re-forge both survive a self-check "
            "(files/10 §2). HB-I12 is open (no anchor publisher exists), so the verdict is "
            "anchor_missing, fail-closed. The console carries no chain hash and reads no chain: "
            "the head is published outside the platform_admin blast radius, and this surface "
            "sits inside it."
        ),
    }


def _pentest(catalog: MetricsCatalog) -> dict[str, Any]:
    return {
        "metric_id": "sec.vulns_open",
        "age_metric_id": catalogued(catalog, "sec.vuln_age_days").spec_id,
        "metric_status": catalogued(catalog, "sec.vulns_open").status,
        # no external pen-test has been conducted: genuinely empty, which is not
        # "assessed, nothing found" (invariant 17)
        "assessment_state": "none_recorded",
        "last_assessment": None,
        "allowed_severities": list(_FINDING_SEVERITIES),
        "allowed_statuses": list(_FINDING_STATUSES),
        "sla_days_by_severity": dict(_SLA_DAYS_BY_SEVERITY),
        "findings": [],
        "note": (
            "Pen-test findings tracked to closure against the vulnerability SLA (files/10 §7, §9; "
            "sec.vulns_open / sec.vuln_age_days). The first external pen-test is before the P2 "
            "pilot, so no assessment is recorded and the list is genuinely empty (invariant 17); "
            "the SLA (critical 72 h / high 7 d / medium 30 d) is the clock a future finding is "
            "judged against. Findings carry ids and status, never a finding's prose (invariant 6)."
        ),
    }


def security_payload(
    *,
    catalog: MetricsCatalog,
    feed: ConsoleFeed | None,
    egress: Reading,
    generated_at: datetime,
) -> dict[str, Any]:
    """The composite, from sources the caller read. Pure."""
    return {
        "generated_at": generated_at.date().isoformat(),
        "siem": _siem(catalog, feed),
        "egress_denials": _egress(catalog, egress),
        "audit_chain": _audit_chain(catalog),
        "pentest": _pentest(catalog),
    }


async def security_read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    feed = await run_in_threadpool(load_console_feed)
    egress = await run_in_threadpool(
        read_counts, prom_from_env(os.environ), SECURITY_QUERIES, SECURITY_LABELS, "egress_denied"
    )
    return security_payload(
        catalog=load_catalog(), feed=feed, egress=egress, generated_at=datetime.now(UTC)
    )
