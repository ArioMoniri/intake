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
  invariants 14/19). The route reads this counter from the metrics scrape at
  serve time over a stated window (INT-565), and this repo records no scrape,
  so the recorded state is ``source_available = False``, the reason
  ``prometheus_unconfigured`` and the count ``None`` — never a bare 0, which
  would read as "no denials" when it means "no data". The catalogue's own
  paging target ("0 (any increase pages)") is read from the catalog, not copied
  here.

- **Audit-chain status** is the verdict the daily verifier reaches with no
  anchor: ``anchor_missing``, because HB-I12 is open and no anchor publisher
  exists, so nothing independent can attest the chain. The console carries no
  chain hash and reads no chain (HB-I12: the head is published outside the
  ``platform_admin`` blast radius, which the console sits inside; INT-180's
  ``test_no_admin_response_carries_a_chain_hash``). The API does not import the
  verifier (INT-565: importing it registers ``sec_audit_chain_ok`` at 0 in the
  importing process, which the security rules read as a broken chain);
  ``tests/admin/test_security_console.py`` holds the builder's verdict equal to
  ``run_daily_verification``'s with no anchor (invariant 4).

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

INT-565: the body is built by ``GET /admin/security``'s own builder,
``intake_api.admin.security_console.security_payload``, so the fixture and the
route cannot drift.

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from intake_api.admin.console_sources import Reading, load_catalog
from intake_api.admin.security_console import security_payload
from intake_platform.siem import load_console_feed

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "security.payload.json"
METRICS_CATALOG = Path("observability") / "metrics_catalog.yaml"


def build_payload() -> dict[str, Any]:
    """The route's own builder over this repository's sources: no mounted alert
    stream and no scrape."""
    return security_payload(
        catalog=load_catalog(METRICS_CATALOG),
        feed=load_console_feed(),
        egress=Reading.unavailable("prometheus_unconfigured"),
        generated_at=datetime.now(UTC),
    )


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
