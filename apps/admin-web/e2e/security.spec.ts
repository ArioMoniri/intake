/**
 * INT-192 — Security module, console side (files/08 §3, §7; files/10 §7, §9;
 * INT-205, INT-180, INT-016, INT-018).
 *
 * Acceptance, verbatim: *"Wazuh/Falco/CrowdSec summaries; egress denials;
 * audit-chain status; pen-test findings tracker"*.
 *
 * **What this runs against.** `e2e/fixtures/security.payload.json` is the
 * `GET /admin/security` composite, recorded from the real sources by
 * `scripts/dev/record_security_fixture.py` (the same "record, do not hand-mock"
 * discipline as models/compliance/protocols/safety/experience):
 *
 * - the SIEM summaries are `intake_platform.siem.feed.load_console_feed`
 *   (INT-205), which returns `None` — *not configured* — until the Wazuh
 *   manager's alert stream is mounted, so the recorded state is the platform's
 *   own "the SIEM was never wired up" state rather than "nothing was detected";
 * - the egress-denial count is the catalogued `sec.egress_denied_total`
 *   (INT-018), which the console reads from a metrics scrape at serve time and
 *   which this repo does not record, so the recorded state is source-unavailable
 *   rather than a bare zero;
 * - the audit-chain status is the verdict
 *   `intake_platform.audit_verifier.job.run_daily_verification` (INT-016)
 *   reaches with no anchor, `anchor_missing` (HB-I12 is open: no anchor
 *   publisher exists), fail-closed — and only the verdict: the console carries
 *   no chain head (HB-I12; INT-180, INT-565);
 * - the pen-test tracker has no assessment recorded (files/10 §7: the first
 *   external pen-test is before the P2 pilot), so `findings` is genuinely empty.
 *
 * Asserting on the presentation tree the renderer returns — not a DOM — matches
 * the repo's node lane.
 *
 * **The negative controls.** Every property the acceptance and the invariants
 * turn on is paired with a near-miss the renderer must refuse: a SIEM count
 * shown while the feed is not wired (the "not detected vs never configured"
 * confusion), a signal / severity / detector source outside its sealed set, an
 * egress count shown as observed while the scrape is unavailable, an audit chain
 * attested green with no external anchor (a pass by omission, files/10 §2), a
 * chain head on the console, a finding status / severity outside its sealed set,
 * findings shown with no assessment recorded, and a finding id that is not
 * id-shaped (the finding's prose reappearing on a console, invariant 6). The
 * emptyable surfaces are exercised with rows constructed inline, exactly as
 * safety.spec.ts and experience.spec.ts do.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  AuditChainAttestedWithoutAnchor,
  ChainHeadOnConsole,
  EgressCountWithoutScrape,
  FindingsWithoutAssessment,
  renderAuditChainStatus,
  renderEgressDenials,
  renderPentestTracker,
  renderSecurityModule,
  renderSiemSummaries,
  SecurityContentLeaked,
  SiemSummaryWithoutFeed,
  UnknownAuditOutcome,
  UnknownDetectorSource,
  UnknownFindingSeverity,
  UnknownFindingStatus,
  UnknownSecuritySignal,
  UnknownSeverity,
  type AuditChainPayload,
  type EgressDenialsPayload,
  type PentestPayload,
  type SecurityPayload,
  type SiemPayload,
} from "../src/security/module";

const FIXTURES = join(__dirname, "fixtures");

function payload(): SecurityPayload {
  return JSON.parse(
    readFileSync(join(FIXTURES, "security.payload.json"), "utf8"),
  ) as SecurityPayload;
}

/** A well-formed SIEM feed WITH alerts wired — the shape the console carries
 * once the Wazuh manager's stream is mounted (the fixture is not configured). */
function siemWithFeed(overrides: Partial<SiemPayload> = {}): SiemPayload {
  const base = payload().siem;
  return {
    ...base,
    feed_configured: true,
    feed_version: "a".repeat(64),
    total: 7,
    refused: 1,
    by_signal: { auth_anomaly: 4, container_runtime: 2, unclassified: 1 },
    by_severity: { SEV1: 1, SEV3: 4, SEV4: 2 },
    detectors: base.detectors.map((d) =>
      d.detector === "crowdsec"
        ? { ...d, configured: false, count: null }
        : { ...d, configured: true, count: d.detector === "wazuh" ? 5 : 2 },
    ),
    ...overrides,
  };
}

function egressWithScrape(overrides: Partial<EgressDenialsPayload> = {}): EgressDenialsPayload {
  return { ...payload().egress_denials, source_available: true, denied_total: 0, ...overrides };
}

function auditIntact(overrides: Partial<AuditChainPayload> = {}): AuditChainPayload {
  return {
    ...payload().audit_chain,
    outcome: "intact",
    ok: true,
    anchor_available: true,
    ...overrides,
  };
}

function pentestWithFindings(overrides: Partial<PentestPayload> = {}): PentestPayload {
  return {
    ...payload().pentest,
    last_assessment: "2026-07-15",
    assessment_state: "assessed",
    findings: [
      {
        finding_id: "PT-2026-001",
        severity: "high",
        status: "open",
        sla_days: 7,
        age_days: 3,
        breached: false,
        discovered_on: "2026-07-15",
      },
      {
        finding_id: "PT-2026-002",
        severity: "medium",
        status: "resolved",
        sla_days: 30,
        age_days: 12,
        breached: false,
        discovered_on: "2026-07-15",
      },
    ],
    ...overrides,
  };
}

describe("SIEM summaries (Wazuh / Falco / CrowdSec)", () => {
  it("shows the honest not-configured state: no feed means no count, never a zero (inv 17)", () => {
    const view = renderSiemSummaries(payload().siem);
    expect(view.metricId).toEqual("siem_alerts_ingested_total");
    expect(view.feedConfigured).toBe(false);
    expect(view.total).toBeNull();
    expect(view.refused).toBeNull();
    expect(view.bySignal).toEqual([]);
    expect(view.bySeverity).toEqual([]);
    // all three named detectors are present, each unavailable with a reason
    expect(view.detectors.map((d) => d.detector)).toEqual(["wazuh", "falco", "crowdsec"]);
    for (const d of view.detectors) {
      expect(d.configured).toBe(false);
      expect(d.count).toBeNull();
      expect(d.reason.length).toBeGreaterThan(0);
    }
  });

  it("paints counts by signal and severity once the feed is wired", () => {
    const view = renderSiemSummaries(siemWithFeed());
    expect(view.feedConfigured).toBe(true);
    expect(view.total).toEqual("7");
    expect(view.refused).toEqual("1");
    expect(view.bySignal.find((b) => b.key === "auth_anomaly")?.count).toEqual("4");
    expect(view.bySeverity.find((b) => b.key === "SEV3")?.count).toEqual("4");
    expect(view.detectors.find((d) => d.detector === "wazuh")?.count).toEqual("5");
    // crowdsec has no console feed loader in this repo — still unavailable
    expect(view.detectors.find((d) => d.detector === "crowdsec")?.configured).toBe(false);
  });

  it("renders counts as non-grouped atoms a reader cannot misread (inv 22)", () => {
    const view = renderSiemSummaries(
      siemWithFeed({ total: 1200, by_signal: { auth_anomaly: 1200 } }),
    );
    expect(view.total).toEqual("1200");
    expect(view.total).not.toMatch(/[,. ]/);
  });

  it("refuses a count shown while the feed is not configured (not-detected vs never-wired)", () => {
    const tampered: SiemPayload = { ...payload().siem, feed_configured: false, total: 5 };
    expect(() => renderSiemSummaries(tampered)).toThrow(SiemSummaryWithoutFeed);
  });

  it("refuses a per-detector count while that detector is not configured", () => {
    const base = payload().siem;
    const detectors = base.detectors.map((d) =>
      d.detector === "wazuh" ? { ...d, configured: false, count: 3 } : d,
    );
    const tampered: SiemPayload = { ...siemWithFeed(), detectors };
    expect(() => renderSiemSummaries(tampered)).toThrow(SiemSummaryWithoutFeed);
  });

  it("refuses a signal outside the sealed enum", () => {
    const tampered = siemWithFeed({ by_signal: { made_up_signal: 3 } });
    expect(() => renderSiemSummaries(tampered)).toThrow(UnknownSecuritySignal);
  });

  it("refuses a severity outside the sealed ladder", () => {
    const tampered = siemWithFeed({ by_severity: { SEV9: 3 } });
    expect(() => renderSiemSummaries(tampered)).toThrow(UnknownSeverity);
  });

  it("refuses a detector source outside the sealed set", () => {
    const base = siemWithFeed();
    const detectors = [
      ...base.detectors,
      { detector: "splunk", configured: true, count: 1, reason: "" },
    ];
    expect(() => renderSiemSummaries({ ...base, detectors })).toThrow(UnknownDetectorSource);
  });
});

describe("egress denials (allow-list default-deny counter)", () => {
  it("shows source-unavailable honestly: no scrape means no count, never a zero (inv 17)", () => {
    const view = renderEgressDenials(payload().egress_denials);
    expect(view.metricId).toEqual("sec.egress_denied_total");
    expect(view.sourceAvailable).toBe(false);
    expect(view.deniedTotal).toBeNull();
  });

  it("paints the denial count once a scrape is available — including a genuine zero", () => {
    const view = renderEgressDenials(egressWithScrape({ denied_total: 0 }));
    expect(view.sourceAvailable).toBe(true);
    expect(view.deniedTotal).toEqual("0");
  });

  it("renders a nonzero count as a non-grouped atom (inv 22)", () => {
    const view = renderEgressDenials(egressWithScrape({ denied_total: 4200 }));
    expect(view.deniedTotal).toEqual("4200");
    expect(view.deniedTotal).not.toMatch(/[,. ]/);
  });

  it("refuses a count presented as observed while the scrape is unavailable", () => {
    const tampered: EgressDenialsPayload = {
      ...payload().egress_denials,
      source_available: false,
      denied_total: 3,
    };
    expect(() => renderEgressDenials(tampered)).toThrow(EgressCountWithoutScrape);
  });
});

describe("audit-chain status (hash-chain verified against the external anchor)", () => {
  it("shows the honest fail-closed state: no anchor, so not attested (files/10 §2; HB-I12)", () => {
    const view = renderAuditChainStatus(payload().audit_chain);
    expect(view.metricId).toEqual("sec.audit_chain_ok");
    expect(view.outcome).toEqual("anchor_missing");
    expect(view.ok).toBe(false);
    expect(view.anchorAvailable).toBe(false);
  });

  it("shows an intact chain once it verifies against the anchored head", () => {
    const view = renderAuditChainStatus(auditIntact());
    expect(view.outcome).toEqual("intact");
    expect(view.ok).toBe(true);
    expect(view.anchorAvailable).toBe(true);
  });

  it("refuses a green attestation with no external anchor — a pass by omission (files/10 §2)", () => {
    // near-miss: the chain agrees with itself (ok true) but nothing independent
    // says so (anchor_missing) — exactly the truncate-and-re-forge the anchor exists to catch
    const tampered: AuditChainPayload = {
      ...payload().audit_chain,
      outcome: "anchor_missing",
      ok: true,
      anchor_available: false,
    };
    expect(() => renderAuditChainStatus(tampered)).toThrow(AuditChainAttestedWithoutAnchor);
  });

  it("refuses an ok=true chain with no anchor available", () => {
    const tampered: AuditChainPayload = { ...auditIntact(), anchor_available: false };
    expect(() => renderAuditChainStatus(tampered)).toThrow(AuditChainAttestedWithoutAnchor);
  });

  it("refuses an outcome outside the sealed set", () => {
    const tampered: AuditChainPayload = { ...payload().audit_chain, outcome: "probably_fine" };
    expect(() => renderAuditChainStatus(tampered)).toThrow(UnknownAuditOutcome);
  });

  it("refuses a chain head on the console, by key or by shape (HB-I12; INT-180)", () => {
    // the head is published outside the blast radius this console sits in
    const keyed = { ...auditIntact(), local_head: "b".repeat(64) } as AuditChainPayload;
    expect(() => renderAuditChainStatus(keyed)).toThrow(ChainHeadOnConsole);
    const hidden: AuditChainPayload = { ...auditIntact(), reason: `head ${"c".repeat(64)}` };
    expect(() => renderAuditChainStatus(hidden)).toThrow(ChainHeadOnConsole);
    // near-miss: a shorter hex run (a 128-bit digest) is not a head
    const digest: AuditChainPayload = { ...auditIntact(), reason: `digest ${"c".repeat(32)}` };
    expect(renderAuditChainStatus(digest).ok).toBe(true);
  });
});

describe("pen-test findings tracker", () => {
  it("shows the genuine empty state: no assessment recorded yet (files/10 §7; inv 17)", () => {
    const view = renderPentestTracker(payload().pentest);
    expect(view.metricId).toEqual("sec.vulns_open");
    expect(view.assessmentState).toEqual("none_recorded");
    expect(view.lastAssessment).toBeNull();
    expect(view.empty).toBe(true);
    expect(view.findings).toEqual([]);
    // the SLA table is present so a future finding has a clock to be judged against
    expect(view.slaDaysBySeverity.length).toBeGreaterThan(0);
  });

  it("paints findings with status once an assessment exists", () => {
    const view = renderPentestTracker(pentestWithFindings());
    expect(view.empty).toBe(false);
    expect(view.lastAssessment).toEqual("2026-07-15");
    expect(view.findings.map((f) => f.findingId)).toEqual(["PT-2026-001", "PT-2026-002"]);
    expect(view.findings.find((f) => f.findingId === "PT-2026-001")?.status).toEqual("open");
  });

  it("refuses findings shown with no assessment recorded (empty vs not-conducted)", () => {
    const tampered: PentestPayload = {
      ...payload().pentest,
      assessment_state: "none_recorded",
      last_assessment: null,
      findings: [
        {
          finding_id: "PT-2026-001",
          severity: "high",
          status: "open",
          sla_days: 7,
          age_days: 3,
          breached: false,
          discovered_on: "2026-07-15",
        },
      ],
    };
    expect(() => renderPentestTracker(tampered)).toThrow(FindingsWithoutAssessment);
  });

  it("refuses a finding status outside the sealed set", () => {
    const tampered = pentestWithFindings({
      findings: [
        {
          finding_id: "PT-2026-003",
          severity: "high",
          status: "sorted_it_out",
          sla_days: 7,
          age_days: 1,
          breached: false,
          discovered_on: "2026-07-15",
        },
      ],
    });
    expect(() => renderPentestTracker(tampered)).toThrow(UnknownFindingStatus);
  });

  it("refuses a finding severity outside the sealed set", () => {
    const tampered = pentestWithFindings({
      findings: [
        {
          finding_id: "PT-2026-004",
          severity: "apocalyptic",
          status: "open",
          sla_days: 3,
          age_days: 1,
          breached: false,
          discovered_on: "2026-07-15",
        },
      ],
    });
    expect(() => renderPentestTracker(tampered)).toThrow(UnknownFindingSeverity);
  });

  it("refuses a finding id that is not id-shaped — the finding's prose reappearing (inv 6)", () => {
    const tampered = pentestWithFindings({
      findings: [
        {
          finding_id: "SQLi in the göğüs ağrısı intake endpoint",
          severity: "high",
          status: "open",
          sla_days: 7,
          age_days: 1,
          breached: false,
          discovered_on: "2026-07-15",
        },
      ],
    });
    expect(() => renderPentestTracker(tampered)).toThrow(SecurityContentLeaked);
  });
});

describe("the whole module composes", () => {
  it("renders every surface from the recorded composite", () => {
    const view = renderSecurityModule(payload());
    expect(view.siem.metricId).toEqual("siem_alerts_ingested_total");
    expect(view.egressDenials.metricId).toEqual("sec.egress_denied_total");
    expect(view.auditChain.metricId).toEqual("sec.audit_chain_ok");
    expect(view.pentest.metricId).toEqual("sec.vulns_open");
    // the recorded composite is every surface in its honest empty / fail-closed state
    expect(view.siem.feedConfigured).toBe(false);
    expect(view.egressDenials.sourceAvailable).toBe(false);
    expect(view.auditChain.ok).toBe(false);
    expect(view.pentest.empty).toBe(true);
  });
});
