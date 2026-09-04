/**
 * INT-189 — Compliance module, console side (files/08 §4).
 *
 * Acceptance, verbatim: *"vendor-transfer register auto-filled from egress logs
 * with notification due-dates (5 business days rule); evidence export bundles
 * for audits"*.
 *
 * **What this runs against.** `e2e/fixtures/compliance.payload.json` is the
 * composite of the five `GET /admin/compliance/*` bodies, recorded from the API
 * by `scripts/dev/record_compliance_fixture.py` (the same "record from the
 * server, do not hand-mock" discipline as models.spec.ts). Asserting on the
 * presentation tree the renderer returns — not a DOM — matches the repo's node
 * lane (there is no browser runner; see models.spec.ts).
 *
 * **The negative controls.** Every property the acceptance and the invariants
 * turn on is paired with a near-miss the renderer must refuse: a register row
 * with no lawful basis, an evidence cell that would evaluate in a spreadsheet,
 * and an audit-search row carrying a chain-hash shape.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ChainMaterialLeaked,
  MissingLawfulBasis,
  UnsafeExportCell,
  renderAuditSearch,
  renderComplianceModule,
  renderEvidenceBundle,
  renderVendorRegister,
  type CompliancePayload,
} from "../src/compliance/module";

const FIXTURES = join(__dirname, "fixtures");

function payload(): CompliancePayload {
  return JSON.parse(
    readFileSync(join(FIXTURES, "compliance.payload.json"), "utf8"),
  ) as CompliancePayload;
}

describe("vendor-transfer register auto-filled from egress logs", () => {
  it("paints one row per observed transfer, carrying the inventory shape", () => {
    const rows = renderVendorRegister(payload().vendor_register);
    expect(rows.length).toBeGreaterThan(0);
    const pypi = rows.find((r) => r.host === "pypi.org")!;
    expect(pypi).toBeDefined();
    const labels = pypi.cells.map((c) => c.label);
    for (const field of ["purpose", "category", "basis", "retention", "recipient"]) {
      expect(labels).toContain(field);
    }
    // every inventory cell carries a value — no blank basis, no blank retention
    for (const cell of pypi.cells) {
      expect(cell.value.trim()).not.toEqual("");
    }
  });

  it("shows the five-business-day notification due-date per row", () => {
    const rows = renderVendorRegister(payload().vendor_register);
    const pypi = rows.find((r) => r.host === "pypi.org")!;
    // first seen Tue 2026-09-01 → due Tue 2026-09-08 (weekend skipped)
    expect(pypi.notification).toContain("2026-09-08");
  });

  it("renders bytes as a non-grouped atom, no separator to misread (inv 22)", () => {
    const rows = renderVendorRegister(payload().vendor_register);
    const bytes = rows[0]!.cells.find((c) => c.label === "bytes")!.value;
    expect(bytes).toMatch(/^\d+ bytes$/);
  });

  it("refuses a register row with no lawful basis", () => {
    // near-miss: a stale or tampered body cannot paint a transfer with no basis
    const live = payload().vendor_register;
    const tampered = {
      rows: [{ ...live.rows[0]!, basis: "" }],
    };
    expect(() => renderVendorRegister(tampered)).toThrow(MissingLawfulBasis);
  });
});

describe("evidence export bundle for audits", () => {
  it("carries the four sections and the KVKK legal refs", () => {
    const bundle = renderEvidenceBundle(payload().evidence);
    expect(bundle.legalRefs).toEqual(["KVKK-9", "TRANSFER-2024"]);
    expect(bundle.sections.map((s) => s.title)).toEqual([
      "vendor_transfer_register",
      "consent_coverage",
      "dsar_sla",
      "audit_chain",
    ]);
    expect(bundle.digest.length).toBeGreaterThan(0);
  });

  it("refuses a cell that would evaluate in a spreadsheet", () => {
    // near-miss: a body whose sanitisation was bypassed cannot be rendered
    const live = payload().evidence;
    const tampered = {
      ...live,
      sections: live.sections.map((section, i) =>
        i === 0 ? { ...section, rows: [['=HYPERLINK("http://evil")', "x"]] } : section,
      ),
    };
    expect(() => renderEvidenceBundle(tampered)).toThrow(UnsafeExportCell);
  });
});

describe("audit search is ids only", () => {
  it("paints administrative rows with no chain material", () => {
    const rows = renderAuditSearch(payload().audit_search);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.action.startsWith("admin.")).toBe(true);
      expect(row).not.toHaveProperty("resourceRef");
      expect(row).not.toHaveProperty("entryHash");
    }
  });

  it("refuses a row carrying an audit chain hash shape", () => {
    const tampered = {
      rows: [
        {
          seq: 1,
          occurred_at_utc: "2026-09-04T09:00:00+00:00",
          actor: "a".repeat(64), // a 64-hex actor is chain-hash shaped
          action: "admin.models.read.success",
        },
      ],
    };
    expect(() => renderAuditSearch(tampered)).toThrow(ChainMaterialLeaked);
  });
});

describe("the whole module composes", () => {
  it("renders every surface from the recorded composite", () => {
    const view = renderComplianceModule(payload());
    expect(view.vendorRegister.length).toBeGreaterThan(0);
    expect(view.evidence.sections.length).toEqual(4);
    expect(Array.isArray(view.auditSearch)).toBe(true);
    expect(Array.isArray(view.dsar)).toBe(true);
    expect(Array.isArray(view.consents)).toBe(true);
  });
});
