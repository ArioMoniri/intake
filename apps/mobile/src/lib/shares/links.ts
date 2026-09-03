/**
 * INT-139 — the pure rules behind *Paylaşımlarınız*, with no network in
 * them, so every property below is provable in node.
 *
 * The seam reads INT-150's two patient-side bodies — `DoctorLinkOut` and
 * `AccessLogEntryOut` — and narrows both. Two narrowings are deliberate and
 * neither is an oversight:
 *
 * - **`DoctorLinkIssued` carries a 128-bit bearer credential and this app
 *   never holds one.** The parser here reads seven named fields; the eighth
 *   is not one of them, so there is nothing for a screen to render, a crash
 *   report to capture or a clipboard to take (invariant 6). This app also
 *   never calls the route that returns it.
 * - **The log row's `resource_ref` and `entry_hash` are dropped.** They are
 *   id-shaped, a patient can act on neither, and dropping them at the seam
 *   is what makes "the log shows a role, never a person" (files/10 §3) a
 *   property of the data rather than a rule the UI has to remember.
 *
 * The one rule with real safety weight is `linkState`: the SERVER decides
 * whether a grant can still be opened, and this module only names why a
 * finished one finished. A client that recomputed expiry from its own clock
 * would agree on every fixture and disagree exactly when the phone's clock
 * is wrong — telling the patient a live share has expired, which is the one
 * error that stops somebody revoking.
 */
import { getLocale, type MessageKey } from "@/lib/i18n";

/** A grant over the visit's note, as the patient sees it. */
export interface ShareLink {
  id: string;
  /** The label the patient typed when they issued it. Their own words. */
  recipient: string;
  expiresAt: string;
  viewLimit: number;
  viewsUsed: number;
  /** The patient actively stopped it. */
  revoked: boolean;
  /**
   * The server's verdict that this grant can still be opened — INT-150's
   * `spent`, inverted so the field reads as what it permits. It is the only
   * authority on the question; nothing here overrides it.
   */
  openable: boolean;
}

export type ShareLinkState = "live" | "revoked" | "expired" | "used_up";

/** What the log projects: a category, a role, and when. Never a person. */
export type AccessCategory =
  | "record_viewed"
  | "record_shared"
  | "record_updated"
  | "consent_changed"
  | "account_security"
  | "data_request"
  | "preferences_changed"
  | "staff_review"
  | "system_integrity"
  | "other";

export type AccessorRole =
  "self" | "guardian" | "clinician" | "clinic_staff" | "system" | "unknown";

export interface AccessEntry {
  seq: number;
  occurredAt: string;
  category: AccessCategory;
  role: AccessorRole;
}

const CATEGORIES: readonly AccessCategory[] = [
  "record_viewed",
  "record_shared",
  "record_updated",
  "consent_changed",
  "account_security",
  "data_request",
  "preferences_changed",
  "staff_review",
  "system_integrity",
  "other",
];

const ROLES: readonly AccessorRole[] = [
  "self",
  "guardian",
  "clinician",
  "clinic_staff",
  "system",
  "unknown",
];

const STATE_KEY: Record<ShareLinkState, MessageKey> = {
  live: "shares.state.live",
  revoked: "shares.state.revoked",
  expired: "shares.state.expired",
  used_up: "shares.state.usedUp",
};

const CATEGORY_KEY: Record<AccessCategory, MessageKey> = {
  record_viewed: "shares.log.category.recordViewed",
  record_shared: "shares.log.category.recordShared",
  record_updated: "shares.log.category.recordUpdated",
  consent_changed: "shares.log.category.consentChanged",
  account_security: "shares.log.category.accountSecurity",
  data_request: "shares.log.category.dataRequest",
  preferences_changed: "shares.log.category.preferencesChanged",
  staff_review: "shares.log.category.staffReview",
  system_integrity: "shares.log.category.systemIntegrity",
  other: "shares.log.category.other",
};

const ROLE_KEY: Record<AccessorRole, MessageKey> = {
  self: "shares.log.role.self",
  guardian: "shares.log.role.guardian",
  clinician: "shares.log.role.clinician",
  clinic_staff: "shares.log.role.clinicStaff",
  system: "shares.log.role.system",
  unknown: "shares.log.role.unknown",
};

function record(payload: unknown): Record<string, unknown> | null {
  return typeof payload === "object" && payload !== null && !Array.isArray(payload)
    ? (payload as Record<string, unknown>)
    : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function flag(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

/**
 * One grant, or null. Null is never "an empty grant": a row this cannot read
 * is a row the patient must not be shown a guess about.
 */
export function parseShareLink(payload: unknown): ShareLink | null {
  const row = record(payload);
  if (row === null) {
    return null;
  }
  const id = text(row.link_id);
  const recipient = text(row.recipient);
  const expiresAt = text(row.expires_at);
  const viewLimit = count(row.view_limit);
  const viewsUsed = count(row.views_used);
  const revoked = flag(row.revoked);
  const spent = flag(row.spent);
  if (
    id === null ||
    recipient === null ||
    expiresAt === null ||
    viewLimit === null ||
    viewsUsed === null ||
    revoked === null ||
    spent === null
  ) {
    return null;
  }
  return { id, recipient, expiresAt, viewLimit, viewsUsed, revoked, openable: !spent };
}

/**
 * The whole list, or null. One unreadable row fails the read rather than
 * shortening the list: a share silently missing from this screen is the
 * exact harm the screen exists to prevent.
 */
export function parseShareLinks(payload: unknown): ShareLink[] | null {
  if (!Array.isArray(payload)) {
    return null;
  }
  const rows: ShareLink[] = [];
  for (const item of payload) {
    const parsed = parseShareLink(item);
    if (parsed === null) {
      return null;
    }
    rows.push(parsed);
  }
  return rows;
}

/**
 * What state a grant is in, from the server's verdict plus its own numbers.
 *
 * Order is the design: `revoked` outranks every other finished reason,
 * because "I stopped this" is what the patient did and "this ran out" is
 * what happened to it — INT-150 returns the two as separate fields for that
 * reason and this preserves the distinction. And `openable` short-circuits
 * everything below it, so no arithmetic on this device can retire a grant
 * the server says is still live.
 */
export function linkState(link: ShareLink): ShareLinkState {
  if (link.revoked) {
    return "revoked";
  }
  if (link.openable) {
    return "live";
  }
  return link.viewsUsed >= link.viewLimit ? "used_up" : "expired";
}

/**
 * Whether to offer the control that stops a grant.
 *
 * The signature is the invariant. INT-150 §6 declares revoke under `core`
 * alone — deliberately NOT under `share:previsit_note` — so that a patient
 * who withdrew consent to share can still stop the sharing they already
 * started. This function takes a grant and nothing else, so there is no
 * consent value in scope for a future edit to gate it on.
 *
 * It stays offered on expired and used-up grants too. If the server's
 * verdict or this device's reading of it were ever wrong, stopping the share
 * is still the patient's to do, and a revoke of a finished grant costs
 * nothing: the route is idempotent.
 */
export function revokeOffered(link: ShareLink): boolean {
  return !link.revoked;
}

export function stateLabelKey(state: ShareLinkState): MessageKey {
  return STATE_KEY[state];
}

export function categoryLabelKey(category: AccessCategory): MessageKey {
  return CATEGORY_KEY[category];
}

export function roleLabelKey(role: AccessorRole): MessageKey {
  return ROLE_KEY[role];
}

/**
 * One log row: the sequence, the instant, what happened and in which role.
 *
 * A category or role this build has never seen becomes `other` / `unknown`
 * rather than failing the row — the server's own projection makes the same
 * choice for the same reason, and an access nobody is told about is worse
 * than an access described vaguely.
 */
function parseAccessEntry(payload: unknown): AccessEntry | null {
  const row = record(payload);
  if (row === null) {
    return null;
  }
  const seq = count(row.seq);
  const occurredAt = text(row.occurred_at_utc);
  const category = text(row.category);
  const role = text(row.accessor_role);
  if (seq === null || occurredAt === null || category === null || role === null) {
    return null;
  }
  return {
    seq,
    occurredAt,
    category: (CATEGORIES as readonly string[]).includes(category)
      ? (category as AccessCategory)
      : "other",
    role: (ROLES as readonly string[]).includes(role) ? (role as AccessorRole) : "unknown",
  };
}

/** The whole log, or null. Same rule as the grants: never a shorter list. */
export function parseAccessLog(payload: unknown): AccessEntry[] | null {
  if (!Array.isArray(payload)) {
    return null;
  }
  const rows: AccessEntry[] = [];
  for (const item of payload) {
    const parsed = parseAccessEntry(item);
    if (parsed === null) {
      return null;
    }
    rows.push(parsed);
  }
  return rows;
}

/**
 * An instant, printed as a day with the month as a word plus a 24-hour
 * clock time — used for both the end of a grant and a row in the log.
 *
 * It prints an instant rather than a bare day because a bare day would have
 * to choose a calendar. INT-150 anchors expiry to the start of the visit
 * date in Türkiye plus 72 h, so a grant ends at local midnight and the UTC
 * instant representing that falls on the previous date: one reading
 * understates the access the patient still has and the other overstates it.
 * The instant states neither.
 *
 * No number here is a clinical quantity, and none is grouped: a month name
 * separates the day from the year, so no thousands separator can appear
 * between digits (invariant 22).
 */
export function formatShareMoment(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat(getLocale() === "tr" ? "tr-TR" : "en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(at);
}
