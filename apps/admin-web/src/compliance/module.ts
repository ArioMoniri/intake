/**
 * Compliance module — the console side (INT-189, files/08 §4).
 *
 * Like the models module, this turns the `/admin/compliance/*` bodies into
 * exactly what the page paints and decides nothing the server did not already
 * decide. What it *does* add is a set of refusals that mirror the server's
 * invariants, so a stale tab, a cached response or a tampered body cannot buy
 * the page a property the server would never have served:
 *
 * - **A transfer with no lawful basis cannot be painted** (`MissingLawfulBasis`).
 *   The register auto-fills from the egress feed, and every row must cite the
 *   basis the transfer rests on (invariant 18); a blank one is a defect, not a
 *   blank cell.
 * - **A cell that would evaluate in a spreadsheet cannot be painted**
 *   (`UnsafeExportCell`). The server sanitises every evidence cell (invariant
 *   47); the renderer holds it to that, so a payload that slipped a raw formula
 *   through is refused rather than rendered.
 * - **Chain material cannot reach the page** (`ChainMaterialLeaked`). The audit
 *   search is ids only; a 64-hex value or a hash-shaped field is the shape of a
 *   chain hash the console must never hold (HB-I12), so it is refused.
 */

/* ------------------------------------------------------------------ */
/* Wire contract — the recorded shape of GET /admin/compliance/*        */
/* ------------------------------------------------------------------ */

export interface VendorRegisterRow {
  readonly host: string;
  readonly port: number;
  readonly purpose_id: string;
  readonly purpose: string;
  readonly category: string;
  readonly basis: string;
  readonly retention: string;
  readonly recipients: string;
  readonly data_class: string;
  readonly first_seen: string;
  readonly last_seen: string;
  readonly transfer_count: number;
  readonly bytes_out: number;
  readonly notification_due: string;
  readonly notification_window_open: boolean;
}

export interface VendorRegisterPayload {
  readonly rows: readonly VendorRegisterRow[];
}

export interface ConsentCoverageRow {
  readonly scope: string;
  readonly version: string;
  readonly granted: number;
  readonly withdrawn: number;
}

export interface ConsentCoveragePayload {
  readonly rows: readonly ConsentCoverageRow[];
}

export interface AuditSearchRow {
  readonly seq: number;
  readonly occurred_at_utc: string;
  readonly actor: string;
  readonly action: string;
}

export interface AuditSearchPayload {
  readonly rows: readonly AuditSearchRow[];
}

export interface DsarQueueRow {
  readonly request_id: string;
  readonly kind: string;
  readonly status: string;
  readonly received_at: string;
  readonly due_at: string;
  readonly grace_ends_at: string | null;
  readonly overdue: boolean;
}

export interface DsarQueuePayload {
  readonly rows: readonly DsarQueueRow[];
}

export interface EvidenceSection {
  readonly title: string;
  readonly columns: readonly string[];
  readonly rows: readonly (readonly string[])[];
}

export interface EvidencePayload {
  readonly generated_at: string;
  readonly legal_refs: readonly string[];
  readonly digest: string;
  readonly sections: readonly EvidenceSection[];
}

export interface CompliancePayload {
  readonly vendor_register: VendorRegisterPayload;
  readonly consents: ConsentCoveragePayload;
  readonly audit_search: AuditSearchPayload;
  readonly dsar: DsarQueuePayload;
  readonly evidence: EvidencePayload;
}

/* ------------------------------------------------------------------ */
/* Presentation tree — what the page paints                            */
/* ------------------------------------------------------------------ */

export interface RegisterCell {
  readonly label: string;
  readonly value: string;
}

export interface VendorRow {
  readonly host: string;
  readonly recipients: string;
  readonly cells: readonly RegisterCell[];
  /** "due by <date>" while the window is open, "window elapsed" once past. */
  readonly notification: string;
  /** The deadline itself, for a page that words the notification in its own language. */
  readonly notificationDue: string;
  readonly notificationOverdue: boolean;
}

export interface AuditRow {
  readonly seq: number;
  readonly occurredAt: string;
  readonly actor: string;
  readonly action: string;
}

export interface DsarRow {
  readonly requestId: string;
  readonly kind: string;
  readonly status: string;
  readonly dueAt: string;
  readonly overdue: boolean;
}

export interface ConsentRow {
  readonly scope: string;
  readonly version: string;
  readonly granted: number;
  readonly withdrawn: number;
}

export interface EvidenceSectionPresentation {
  readonly title: string;
  readonly columns: readonly string[];
  readonly rows: readonly (readonly string[])[];
}

export interface EvidencePresentation {
  readonly generatedAt: string;
  readonly legalRefs: readonly string[];
  readonly digest: string;
  readonly sections: readonly EvidenceSectionPresentation[];
}

export interface CompliancePresentation {
  readonly vendorRegister: readonly VendorRow[];
  readonly consents: readonly ConsentRow[];
  readonly auditSearch: readonly AuditRow[];
  readonly dsar: readonly DsarRow[];
  readonly evidence: EvidencePresentation;
}

/* ------------------------------------------------------------------ */
/* Refusals — the properties a stale or tampered payload cannot buy    */
/* ------------------------------------------------------------------ */

/** A register row that cites no lawful basis (invariant 18). */
export class MissingLawfulBasis extends Error {
  constructor(host: string) {
    super(
      `refusing to render a transfer to '${host}' with no lawful basis: the register ` +
        `auto-fills from the egress feed and every row must cite the basis the transfer ` +
        `rests on (INT-189, invariant 18)`,
    );
    this.name = "MissingLawfulBasis";
  }
}

/** An evidence cell that a spreadsheet would evaluate (invariant 47). */
export class UnsafeExportCell extends Error {
  constructor(section: string) {
    super(
      `refusing to render an evidence cell that would evaluate when opened in a ` +
        `spreadsheet (section '${section}'): the server sanitises every cell (invariant ` +
        `47, files/08 §0c F13), so a raw formula here is a tampered or pre-sanitisation body`,
    );
    this.name = "UnsafeExportCell";
  }
}

/** A hash-shaped value in a surface that must carry none (HB-I12, invariant 6). */
export class ChainMaterialLeaked extends Error {
  constructor(where: string) {
    super(
      `refusing to render ${where}: it carries a value shaped like an audit chain hash, ` +
        `which the console must never hold (HB-I12)`,
    );
    this.name = "ChainMaterialLeaked";
  }
}

const FORMULA_LEADS = ["=", "+", "-", "@", "\t", "\r"];
const HEX64 = /\b[0-9a-f]{64}\b/;

function nonGrouped(value: number): string {
  return value.toLocaleString("en-GB", { useGrouping: false });
}

function renderVendorRow(row: VendorRegisterRow): VendorRow {
  if (row.basis.trim() === "") {
    throw new MissingLawfulBasis(row.host);
  }
  return {
    host: row.host,
    recipients: row.recipients,
    cells: [
      { label: "purpose", value: row.purpose },
      { label: "category", value: row.category },
      { label: "basis", value: row.basis },
      { label: "retention", value: row.retention },
      { label: "recipient", value: row.recipients },
      { label: "data class", value: row.data_class },
      { label: "first seen", value: row.first_seen },
      { label: "transfers", value: nonGrouped(row.transfer_count) },
      // quantity + unit as one non-breaking atom, no grouping separator (inv 22)
      { label: "bytes", value: `${nonGrouped(row.bytes_out)} bytes` },
    ],
    notification: row.notification_window_open
      ? `due by ${row.notification_due}`
      : `window elapsed (was due ${row.notification_due})`,
    notificationOverdue: !row.notification_window_open,
    notificationDue: row.notification_due,
  };
}

/** Build the vendor-transfer register rows, refusing any with no basis. */
export function renderVendorRegister(payload: VendorRegisterPayload): readonly VendorRow[] {
  return payload.rows.map(renderVendorRow);
}

/** Build the ids-only audit search rows, refusing any chain-hash shape. */
export function renderAuditSearch(payload: AuditSearchPayload): readonly AuditRow[] {
  return payload.rows.map((row) => {
    for (const value of [row.actor, row.action, String(row.seq), row.occurred_at_utc]) {
      if (HEX64.test(value)) {
        throw new ChainMaterialLeaked("an audit-search row");
      }
    }
    return {
      seq: row.seq,
      occurredAt: row.occurred_at_utc,
      actor: row.actor,
      action: row.action,
    };
  });
}

/** Build the DSAR queue rows, marking the ones past their m.13 deadline. */
export function renderDsarQueue(payload: DsarQueuePayload): readonly DsarRow[] {
  return payload.rows.map((row) => ({
    requestId: row.request_id,
    kind: row.kind,
    status: row.status,
    dueAt: row.due_at,
    overdue: row.overdue,
  }));
}

export function renderConsentCoverage(payload: ConsentCoveragePayload): readonly ConsentRow[] {
  return payload.rows.map((row) => ({
    scope: row.scope,
    version: row.version,
    granted: row.granted,
    withdrawn: row.withdrawn,
  }));
}

/** Build the evidence bundle, refusing any cell a spreadsheet would evaluate. */
export function renderEvidenceBundle(payload: EvidencePayload): EvidencePresentation {
  if (HEX64.test(payload.digest)) {
    // the digest is base64url by construction; a 64-hex here is chain-shaped
    throw new ChainMaterialLeaked("the evidence digest");
  }
  const sections = payload.sections.map((section) => {
    for (const row of section.rows) {
      for (const cell of row) {
        if (FORMULA_LEADS.some((lead) => cell.startsWith(lead))) {
          throw new UnsafeExportCell(section.title);
        }
      }
    }
    return { title: section.title, columns: section.columns, rows: section.rows };
  });
  return {
    generatedAt: payload.generated_at,
    legalRefs: payload.legal_refs,
    digest: payload.digest,
    sections,
  };
}

/**
 * Build the whole module from the five recorded bodies.
 *
 * A refusal in any surface propagates: a compliance console that painted a
 * transfer with no basis, an evaluable export cell, or a chain hash would be
 * worse than no console, so the page does not render past one.
 */
export function renderComplianceModule(payload: CompliancePayload): CompliancePresentation {
  return {
    vendorRegister: renderVendorRegister(payload.vendor_register),
    consents: renderConsentCoverage(payload.consents),
    auditSearch: renderAuditSearch(payload.audit_search),
    dsar: renderDsarQueue(payload.dsar),
    evidence: renderEvidenceBundle(payload.evidence),
  };
}
