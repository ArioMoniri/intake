/**
 * INT-564 — the Compliance page's server-side loader (INT-189's five reads).
 *
 * The same order as every rendered console page (`../ops/load`): no API base
 * or no bearer means nothing is dialled; each `GET /admin/compliance/*` read
 * goes with the caller's bearer through the INT-180 gate (role matrix: the
 * compliance officer, the auditor, the platform owner; every read audited),
 * and the first refusal ends the load. The audit search asks for the last 24
 * hours only — the page never pulls the whole chain. A body the view-model
 * refuses (a transfer with no lawful basis, an evaluable export cell, a chain
 * hash) is `unavailable`, never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import {
  ChainMaterialLeaked,
  MissingLawfulBasis,
  UnsafeExportCell,
  renderComplianceModule,
  type CompliancePayload,
  type CompliancePresentation,
} from "./module";

export type ComplianceState = RefusedState | { kind: "console"; view: CompliancePresentation };

const DAY_MS = 24 * 60 * 60 * 1000;

/** The five reads, in the order the page shows them. */
export function compliancePaths(now: Date): Record<keyof CompliancePayload, `/admin/${string}`> {
  const since = encodeURIComponent(new Date(now.getTime() - DAY_MS).toISOString());
  return {
    vendor_register: "/admin/compliance/vendor-register",
    consents: "/admin/compliance/consents",
    dsar: "/admin/compliance/dsar",
    audit_search: `/admin/compliance/audit-search?since=${since}`,
    evidence: "/admin/compliance/evidence-export",
  };
}

export async function loadCompliance(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
  now: Date;
}): Promise<ComplianceState> {
  const { config, authorization, fetch, now } = args;
  const bodies: Partial<Record<keyof CompliancePayload, unknown>> = {};
  for (const [key, path] of Object.entries(compliancePaths(now)) as Array<
    [keyof CompliancePayload, `/admin/${string}`]
  >) {
    const admitted = await admit({ config, authorization, fetch, path });
    if (admitted.kind !== "admitted") return admitted;
    bodies[key] = admitted.body;
  }
  try {
    return { kind: "console", view: renderComplianceModule(bodies as CompliancePayload) };
  } catch (error) {
    if (
      error instanceof MissingLawfulBasis ||
      error instanceof UnsafeExportCell ||
      error instanceof ChainMaterialLeaked ||
      error instanceof TypeError
    ) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}
