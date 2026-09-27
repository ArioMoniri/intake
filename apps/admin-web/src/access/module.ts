/**
 * INT-366 — the access review, as the console paints it (files/08 §2.7).
 *
 * `GET /admin/access/review` (`intake.admin.access_review.v1`, produced by
 * `services/api/src/intake_api/admin/access_console.py`) is turned into exactly
 * what the page shows, and nothing the server did not decide is added. What
 * this projection does add is a set of refusals, so a stale tab, a cached body
 * or a tampered one cannot buy the page a property the server never served:
 *
 * - **A lapsed review cannot look current** (`AccessReviewInconsistent`). The
 *   read-only roles must follow from the review's age — none at or under 100
 *   days, `platform_owner` and `tenant_admin` above it or with no review — and
 *   each section's `overdue` flag from its own age.
 * - **No name, mail or other directory prose** (`AccessDirectoryLeaked`). A
 *   holder row carries exactly the server's id-shaped field set; an extra key
 *   (`email`, `firstName`, …) or a value that is not id-shaped is refused
 *   (invariant 6).
 * - **No chain material** (`AccessChainMaterialLeaked`). A 64-hex value is the
 *   shape of an audit-chain hash the console must never hold (HB-I12); the
 *   section digest is 128 bits (32 hex) precisely so it cannot be one.
 *
 * Day counts leave as strings with one decimal and the unit joined by a
 * no-break space (invariant 22).
 */

import { NBSP } from "../ops/guards";

export const ACCESS_REVIEW_SCHEMA = "intake.admin.access_review.v1";
const ID = /^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/;
const DIGEST = /^[0-9a-f]{32}$/;
const HEX64 = /\b[0-9a-f]{64}\b/;
const MAX_AGE_DAYS = 100;
const READ_ONLY = ["platform_owner", "tenant_admin"] as const;

// --- the wire ---------------------------------------------------------------------------

export interface SectionPayload {
  section: string;
  signer_role: string;
  signer_tenant: string | null;
  countersigner: "different_organisation" | "second_person";
  holders: string[];
  review_digest: string;
  last_signed_at: string | null;
  age_days: number | null;
  overdue: boolean;
}

export interface HolderPayload {
  subject: string;
  username: string | null;
  enabled: boolean;
  roles: string[];
  tenant: string | null;
  org: string | null;
  sections: string[];
  created_at: string;
  last_login_at: string | null;
  days_since_activity: number;
  days_until_auto_disable: number;
  last_console_action_at: string | null;
  last_reviewed_at: string | null;
}

export interface PendingOffboardingPayload {
  offboarding_id: string;
  subject: string;
  reason_class: string;
  pending_systems: string[];
  failed_systems: string[];
}

export interface AccessReviewPayload {
  schema: typeof ACCESS_REVIEW_SCHEMA;
  generated_at: string;
  policy: {
    review_max_age_days: number;
    auto_disable_after_days: number;
    read_only_roles: string[];
  };
  status: { review_age_days: number | null; never_reviewed: boolean; read_only_roles: string[] };
  sections: SectionPayload[];
  holders: HolderPayload[];
  pending_offboardings: PendingOffboardingPayload[];
}

// --- refusals -----------------------------------------------------------------------------

export class AccessPayloadRefused extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = new.target.name;
  }
}
export class AccessReviewInconsistent extends AccessPayloadRefused {}
export class AccessDirectoryLeaked extends AccessPayloadRefused {}
export class AccessChainMaterialLeaked extends AccessPayloadRefused {}

const HOLDER_KEYS = [
  "created_at",
  "days_since_activity",
  "days_until_auto_disable",
  "enabled",
  "last_console_action_at",
  "last_login_at",
  "last_reviewed_at",
  "org",
  "roles",
  "sections",
  "subject",
  "tenant",
  "username",
].join(",");

function id(value: unknown, what: string): string {
  if (typeof value !== "string" || !ID.test(value)) {
    throw new AccessDirectoryLeaked(
      "value_not_id_shaped",
      `${what} is not id-shaped (invariant 6)`,
    );
  }
  return value;
}

function optionalId(value: unknown, what: string): string | null {
  return value === null ? null : id(value, what);
}

function days(value: number | null, unit: string): string | null {
  return value === null || !Number.isFinite(value) ? null : `${value.toFixed(1)}${NBSP}${unit}`;
}

// --- the view -----------------------------------------------------------------------------

export interface SectionView {
  section: string;
  signerRole: string;
  signerTenant: string | null;
  external: boolean;
  holders: number;
  digest: string;
  lastSignedAt: string | null;
  age: string | null;
  overdue: boolean;
}

export interface HolderView {
  subject: string;
  username: string | null;
  enabled: boolean;
  roles: string[];
  tenant: string | null;
  lastLoginAt: string | null;
  idle: string;
  untilDisable: string;
  dormant: boolean;
  lastConsoleActionAt: string | null;
  lastReviewedAt: string | null;
}

export interface OffboardingView {
  id: string;
  subject: string;
  reason: string;
  pending: string[];
  failed: string[];
}

export interface AccessView {
  generatedAt: string;
  age: string | null;
  neverReviewed: boolean;
  readOnly: string[];
  sections: SectionView[];
  holders: HolderView[];
  offboardings: OffboardingView[];
}

export function renderAccessReview(payload: AccessReviewPayload, dayUnit: string): AccessView {
  if (payload.schema !== ACCESS_REVIEW_SCHEMA) {
    throw new AccessPayloadRefused("schema_mismatch", "not an access-review document");
  }
  if (HEX64.test(JSON.stringify(payload))) {
    throw new AccessChainMaterialLeaked(
      "chain_material",
      "a 64-hex value reached the page (HB-I12)",
    );
  }
  const { status } = payload;
  const age = status.review_age_days;
  const lapsed = age === null || age > MAX_AGE_DAYS;
  const expected = lapsed ? [...READ_ONLY] : [];
  if (
    status.never_reviewed !== (age === null) ||
    [...status.read_only_roles].sort().join(",") !== expected.join(",")
  ) {
    throw new AccessReviewInconsistent(
      "read_only_inconsistent",
      "the read-only roles do not follow from the review's age (files/08 §2.7)",
    );
  }
  const sections = payload.sections.map((section): SectionView => {
    const sectionLapsed = section.age_days === null || section.age_days > MAX_AGE_DAYS;
    if (section.overdue !== sectionLapsed) {
      throw new AccessReviewInconsistent(
        "overdue_inconsistent",
        `${section.section}: overdue does not follow from its age`,
      );
    }
    if (!DIGEST.test(section.review_digest)) {
      throw new AccessPayloadRefused("digest_malformed", `${section.section}: digest shape`);
    }
    return {
      section: id(section.section, "section"),
      signerRole: id(section.signer_role, "signer role"),
      signerTenant: optionalId(section.signer_tenant, "signer tenant"),
      external: section.countersigner === "different_organisation",
      holders: section.holders.map((subject) => id(subject, "holder")).length,
      digest: section.review_digest,
      lastSignedAt: section.last_signed_at,
      age: days(section.age_days, dayUnit),
      overdue: section.overdue,
    };
  });
  const holders = payload.holders.map((holder): HolderView => {
    if (Object.keys(holder).sort().join(",") !== HOLDER_KEYS) {
      throw new AccessDirectoryLeaked(
        "holder_fields",
        "a holder row carries a field outside the id-shaped set (invariant 6)",
      );
    }
    return {
      subject: id(holder.subject, "subject"),
      username: optionalId(holder.username, "username"),
      enabled: holder.enabled,
      roles: holder.roles.map((role) => id(role, "role")),
      tenant: optionalId(holder.tenant, "tenant"),
      lastLoginAt: holder.last_login_at,
      idle: days(holder.days_since_activity, dayUnit) ?? "",
      untilDisable: days(holder.days_until_auto_disable, dayUnit) ?? "",
      dormant: holder.enabled && holder.days_until_auto_disable <= 0,
      lastConsoleActionAt: holder.last_console_action_at,
      lastReviewedAt: holder.last_reviewed_at,
    };
  });
  const offboardings = payload.pending_offboardings.map((item): OffboardingView => ({
    id: id(item.offboarding_id, "offboarding id"),
    subject: id(item.subject, "subject"),
    reason: id(item.reason_class, "reason"),
    pending: item.pending_systems.map((system) => id(system, "system")),
    failed: item.failed_systems.map((system) => id(system, "system")),
  }));
  return {
    generatedAt: payload.generated_at,
    age: days(age, dayUnit),
    neverReviewed: status.never_reviewed,
    readOnly: [...status.read_only_roles].sort(),
    sections,
    holders,
    offboardings,
  };
}
