"""Record the `GET /admin/security` body admin-web renders (INT-192).

`apps/admin-web/e2e/security.spec.ts` needs a payload to render. As with
`record_models_fixture.py`, `record_protocols_fixture.py`,
`record_safety_fixture.py` and `record_experience_fixture.py`, there are two
ways to give it one and only one is honest: hand-write a mock, or project the
payload out of the real sources. A hand-written mock is a second, hand-kept
copy of the SIEM feed, the verifier's outcomes and the metric ids — it would
keep passing on the day any of those changed and the console stopped matching
them (CLAUDE.md invariant 17: render real data or a genuine empty state, never
demo data).

So every field below is read from a real source at record time:

- **SIEM summaries** are ``intake_platform.siem.feed.load_console_feed``
  (INT-205). It reads the Wazuh manager's alert stream and returns ``None``
  when the stream is absent — *not configured*, which is deliberately distinct
  from "nothing detected". This repo mounts no stream, so the recorded state is
  the platform's own not-configured state: ``feed_configured = False``, every
  count ``None``, every detector unavailable with a reason. The signal and
  severity vocabularies are ``intake_platform.siem.Signal`` / ``Severity``, so
  the console cannot drift from the enums that seal them, and the detector set
  is the acceptance's three (Wazuh / Falco / CrowdSec) — Wazuh and Falco share
  the ``load_console_feed`` path; CrowdSec's bouncer decisions have no console
  feed loader in this repo (its scenarios are committed under
  ``infra/security/edge/crowdsec``), so it is unavailable for a distinct,
  recorded reason rather than silently absent. The two metric ids
  (``siem_alerts_ingested_total`` / ``siem_alerts_refused_total``) are resolved
  through ``observability/metrics_catalog.yaml`` and raise on a miss
  (invariant 15).

- **Egress denials** are the catalogued ``sec.egress_denied_total`` (INT-018;
  invariants 14/19). The console reads this counter from a metrics scrape at
  serve time, and this repo records no scrape, so the recorded state is
  ``source_available = False`` with the count ``None`` — never a bare 0, which
  would read as "no denials" when it means "no data". The catalogue's own
  paging target ("0 (any increase pages)") is read from the catalog, not copied
  here.

- **Audit-chain status** is
  ``intake_platform.audit_verifier.job.run_daily_verification`` (INT-016;
  invariant 4), called for real over an empty store with no anchor. Its honest
  verdict is ``anchor_missing`` — the chain may agree with itself, but nothing
  independent says so, and HB-I8 is open (no anchor publisher exists yet), so
  the gauge is 0 and the run is fail-closed. The outcome vocabulary is
  ``VerifierOutcome``. This reads the chain; it never writes it (invariant 4).

- **Pen-test findings tracker** has no assessment recorded: files/10 §7 puts
  the first external pen-test before the P2 pilot, so ``findings`` is genuinely
  empty and ``assessment_state`` is ``none_recorded`` (invariant 17). The
  vulnerability SLA (files/10 §7: critical 72 h / high 7 d / medium 30 d) is the
  clock a future finding will be judged against, and the ``sec.vulns_open`` /
  ``sec.vuln_age_days`` metric ids are resolved through the catalog (invariant
  15). The severity and status vocabularies are the tracker's own closed sets,
  so a value off them is refused rather than rendered.

No accuracy claim appears anywhere (invariant 20): every figure is a security
count or an integrity verdict. No PHI: the sources carry ids, counts and
hashes only (invariant 6).

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from intake_platform.audit import InMemoryAuditStore
from intake_platform.audit_verifier.job import VerifierOutcome, run_daily_verification
from intake_platform.siem import Severity, Signal, load_console_feed

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "security.payload.json"
METRICS_CATALOG = Path("observability") / "metrics_catalog.yaml"

#: The acceptance's three detectors. Wazuh and Falco share the load_console_feed
#: path; CrowdSec is the edge bouncer, whose decisions have no console feed
#: loader in this repo.
_DETECTORS = ("wazuh", "falco", "crowdsec")

#: The tracker's closed vocabularies. Not a code enum (no pen-test has been
#: conducted, so no finding type exists to model) — the closed sets the console
#: holds a finding to, so a drifted body is refused rather than rendered.
_FINDING_SEVERITIES = ("critical", "high", "medium", "low", "info")
_FINDING_STATUSES = ("open", "remediating", "resolved", "accepted_risk", "false_positive")

#: files/10 §7: vulnerability SLA critical 72 h (= 3 d) / high 7 d / medium 30 d.
#: Low/info carry no stated SLA, so none is invented for them.
_SLA_DAYS_BY_SEVERITY = {"critical": 3, "high": 7, "medium": 30}


class _NoAnchor:
    """The external witness in its current state: none is published.

    HB-I8 is open — no anchor publisher exists — so ``anchored_head`` returns
    ``None``, which the verifier treats as a refusal (``anchor_missing``), never
    as "skip the check". Satisfies :class:`~intake_platform.audit_verifier.job.AnchorSource`.
    """

    def anchored_head(self) -> str | None:
        return None


def _catalog() -> dict[str, dict[str, Any]]:
    """Map every catalogued metric id/name to its full entry.

    Referencing a metric the catalog does not list would be a claim about a
    series that does not exist (invariant 15), so the helpers below resolve
    through this map and raise on a miss.
    """
    raw = yaml.safe_load(METRICS_CATALOG.read_text(encoding="utf-8"))
    catalog: dict[str, dict[str, Any]] = {}
    for metric in raw["metrics"]:
        if "id" in metric:
            catalog[str(metric["id"])] = metric
        catalog[str(metric["name"])] = metric
    return catalog


def _metric(catalog: dict[str, dict[str, Any]], metric_id: str) -> dict[str, Any]:
    if metric_id not in catalog:
        raise KeyError(
            f"metric {metric_id!r} is not in {METRICS_CATALOG} — the console may only "
            f"reference a catalogued series (CLAUDE.md invariant 15)"
        )
    return catalog[metric_id]


def _status(catalog: dict[str, dict[str, Any]], metric_id: str) -> str:
    return str(_metric(catalog, metric_id).get("status", "live"))


def _siem_section(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # the real feed: absent alert stream -> None -> not configured. Distinct
    # from "nothing detected", which is the whole reason the feed returns None.
    feed = load_console_feed()
    configured = feed is not None

    if feed is None:
        total: int | None = None
        refused: int | None = None
        by_signal: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_source: dict[str, int] = {}
    else:
        total = feed.counts.total
        refused = feed.counts.refused
        by_signal = {signal.value: n for signal, n in feed.counts.by_signal.items()}
        by_severity = {severity.value: n for severity, n in feed.counts.by_severity.items()}
        by_source = {}
        for alert in feed.alerts:
            by_source[alert.source.value] = by_source.get(alert.source.value, 0) + 1

    detectors: list[dict[str, Any]] = []
    for detector in _DETECTORS:
        if detector == "crowdsec":
            detectors.append(
                {
                    "detector": detector,
                    "configured": False,
                    "count": None,
                    "reason": (
                        "the CrowdSec bouncer's decisions have no console feed loader in this "
                        "repository; its scenarios are committed under "
                        "infra/security/edge/crowdsec and enforced at the edge (INT-203)"
                    ),
                }
            )
        elif configured:
            detectors.append(
                {
                    "detector": detector,
                    "configured": True,
                    "count": by_source.get(detector, 0),
                    "reason": "",
                }
            )
        else:
            detectors.append(
                {
                    "detector": detector,
                    "configured": False,
                    "count": None,
                    "reason": (
                        "the Wazuh manager's alert stream is not mounted, so load_console_feed "
                        "returns None (not configured) rather than an empty feed (INT-205)"
                    ),
                }
            )

    return {
        "metric_id": "siem_alerts_ingested_total",
        "refused_metric_id": "siem_alerts_refused_total",
        "metric_status": _status(catalog, "siem_alerts_ingested_total"),
        "feed_configured": configured,
        "feed_version": feed.version if feed is not None else None,
        "total": total,
        "refused": refused,
        "allowed_signals": [signal.value for signal in Signal],
        "allowed_severities": [severity.value for severity in Severity],
        "allowed_sources": list(_DETECTORS),
        "by_signal": by_signal,
        "by_severity": by_severity,
        "detectors": detectors,
        "note": (
            "Wazuh / Falco / CrowdSec alert summaries from intake_platform.siem.feed."
            "load_console_feed (INT-205), counted by signal and severity. The feed returns "
            "not-configured (None) until the alert stream is mounted, so the console shows that "
            "state rather than a 0 — 'nothing detected' and 'never wired up' must not look the "
            "same (invariant 17). Signals and severities are sealed to the platform's own enums, "
            "and every alert carries ids, not narrative (invariant 6)."
        ),
    }


def _egress_section(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry = _metric(catalog, "sec.egress_denied_total")
    return {
        "metric_id": "sec.egress_denied_total",
        "metric_status": _status(catalog, "sec.egress_denied_total"),
        # the console reads this counter from a metrics scrape at serve time;
        # this repo records none, so the tile is source-unavailable, not 0.
        "source_available": False,
        "denied_total": None,
        "target": str(entry.get("target", "")),
        "note": (
            "Denied egress attempts from the PHI path (sec.egress_denied_total, INT-018; "
            "invariants 14/19). The allow-list is default-deny and the PHI path reaches no "
            "external model or speech vendor at all; the catalogue target is 0 and any increase "
            "pages. Read from a metrics scrape at serve time — with no scrape recorded here the "
            "tile is source-unavailable, never a bare 0 (invariant 17)."
        ),
    }


def _audit_chain_section(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # the real verifier over an empty store with no anchor: outcome
    # anchor_missing, ok False, gauge 0 — the honest fail-closed state (HB-I8).
    report = run_daily_verification(InMemoryAuditStore(), anchor=_NoAnchor(), worm_sink=None)
    return {
        "metric_id": "sec.audit_chain_ok",
        "metric_status": _status(catalog, "sec.audit_chain_ok"),
        "allowed_outcomes": [outcome.value for outcome in VerifierOutcome],
        "outcome": report.outcome.value,
        "ok": report.ok,
        "entry_count": report.entry_count,
        "first_bad_seq": report.first_bad_seq,
        "local_head": report.local_head,
        "anchor_head": report.anchor_head,
        "anchor_available": report.anchor_head is not None,
        "reason": report.reason,
        "verified_at": datetime.now(UTC).date().isoformat(),
        "note": (
            "Daily audit hash-chain verification (sec.audit_chain_ok, INT-016; invariant 4). "
            "1 means verified against the EXTERNALLY ANCHORED head, never merely that the store "
            "agrees with itself — a truncation and a full re-forge both survive a self-check "
            "(files/10 §2). HB-I8 is open (no anchor publisher exists), so the delivered state is "
            "anchor_missing, fail-closed: the mechanism is built and the gate refuses to attest. "
            "Read-only on this surface (invariant 4)."
        ),
    }


def _pentest_section(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # resolve the metric ids so a rename fails the recording, not the console.
    ingested = _status(catalog, "sec.vulns_open")
    _metric(catalog, "sec.vuln_age_days")
    return {
        "metric_id": "sec.vulns_open",
        "age_metric_id": "sec.vuln_age_days",
        "metric_status": ingested,
        # files/10 §7: the first external pen-test is before the P2 pilot. None
        # has been conducted, so the tracker is genuinely empty — distinct from
        # "assessed, nothing found" (invariant 17).
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


def build_payload() -> dict[str, Any]:
    catalog = _catalog()
    return {
        "generated_at": datetime.now(UTC).date().isoformat(),
        "siem": _siem_section(catalog),
        "egress_denials": _egress_section(catalog),
        "audit_chain": _audit_chain_section(catalog),
        "pentest": _pentest_section(catalog),
    }


def main() -> int:
    payload = build_payload()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    siem = payload["siem"]
    audit = payload["audit_chain"]
    print(
        f"recorded {FIXTURE} — "
        f"siem feed_configured={siem['feed_configured']} "
        f"({len(siem['detectors'])} detectors); "
        f"egress source_available={payload['egress_denials']['source_available']}; "
        f"audit-chain outcome={audit['outcome']} ok={audit['ok']}; "
        f"pentest {len(payload['pentest']['findings'])} findings "
        f"({payload['pentest']['assessment_state']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
