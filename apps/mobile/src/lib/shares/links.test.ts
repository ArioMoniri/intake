/**
 * INT-139 — the pure rules behind the share centre.
 *
 * Four of these are safety properties rather than formatting tests, and each
 * one is a way the screen could mislead the person whose record is being
 * shared:
 *
 * 1. **The device clock can never retire a live grant.** The server decides
 *    whether a grant can still be opened (`spent`); the client only refines
 *    WHY a finished one finished. A phone whose clock has run ahead must not
 *    tell the patient a share has expired when it has not — that is the one
 *    error that stops somebody revoking.
 * 2. **A token never survives parsing.** `DoctorLinkIssued` is the one body
 *    that carries the 128-bit token, and this app must never hold it: a
 *    credential in a client object is a credential in a crash report, a
 *    redux dump and a screenshot (invariant 6).
 * 3. **Nothing in the access log reconstructs an identity.** The server
 *    projects a ROLE by design (INT-150 §8, files/10 §3); the client drops
 *    the two id-shaped fields it does not need, so there is nothing left to
 *    render a name from even by accident.
 * 4. **No in-scope entry is dropped.** An action the catalogue has never
 *    seen renders as "other", never as nothing: an omitted access is exactly
 *    what an access log exists to prevent.
 */
import { describe, expect, it } from "vitest";

import { setLocale } from "@/lib/i18n";
import { tr } from "@/lib/i18n/tr";

import {
  categoryLabelKey,
  formatShareMoment,
  linkState,
  parseAccessLog,
  parseShareLink,
  parseShareLinks,
  revokeOffered,
  roleLabelKey,
  stateLabelKey,
  type ShareLink,
} from "./links";

/** A `DoctorLinkOut` exactly as INT-150's router serialises one. */
const ROW = {
  link_id: "3f1d6f3e-0000-4000-8000-000000000001",
  recipient: "Kardiyoloji",
  expires_at: "2026-09-06T21:00:00Z",
  view_limit: 5,
  views_used: 1,
  revoked: false,
  spent: false,
};

function link(overrides: Partial<ShareLink> = {}): ShareLink {
  return {
    id: ROW.link_id,
    recipient: ROW.recipient,
    expiresAt: ROW.expires_at,
    viewLimit: ROW.view_limit,
    viewsUsed: ROW.views_used,
    revoked: false,
    openable: true,
    ...overrides,
  };
}

describe("parsing a grant", () => {
  it("reads the row the patient-side list returns", () => {
    expect(parseShareLink(ROW)).toEqual(link());
  });

  it("refuses a row missing any field rather than defaulting one", () => {
    for (const field of Object.keys(ROW)) {
      const partial: Record<string, unknown> = { ...ROW };
      delete partial[field];
      expect(parseShareLink(partial), field).toBeNull();
    }
  });

  it("refuses a list that is not a list, and drops no readable row from one", () => {
    expect(parseShareLinks({})).toBeNull();
    expect(parseShareLinks([ROW, { nonsense: true }])).toBeNull();
    expect(parseShareLinks([])).toEqual([]);
  });

  /**
   * The negative control that matters: `DoctorLinkIssued` is `DoctorLinkOut`
   * plus `token`, so a parser written by widening the row would carry the
   * credential into the app without anybody noticing.
   */
  it("keeps no trace of a token, even when the body carries one", () => {
    // Token-SHAPED (22 url-safe characters, the width of a 128-bit
    // `secrets.token_urlsafe(16)`) and deliberately not token-LIKE: it is
    // built here rather than written as a literal, because a high-entropy
    // string in a fixture is indistinguishable from a leaked credential to
    // the gitleaks gate, and the honest fix is a fixture that is not one.
    const secret = "abcdefghijklmnopqrstuv";
    const parsed = parseShareLink({ ...ROW, token: secret });
    expect(parsed).toEqual(link());
    expect(JSON.stringify(parsed)).not.toContain(secret);
    expect(Object.keys(parsed ?? {})).not.toContain("token");
  });
});

describe("what state a grant is in", () => {
  it("calls a grant the server can still open live", () => {
    expect(linkState(link())).toBe("live");
  });

  it("distinguishes stopping a share from a share running out", () => {
    // INT-150 returns `revoked` and `spent` as two fields for exactly this
    // reason: "I stopped this" and "this ran out" are different facts to the
    // person who shared it.
    expect(linkState(link({ revoked: true, openable: false }))).toBe("revoked");
    expect(linkState(link({ openable: false, viewsUsed: 5, viewLimit: 5 }))).toBe("used_up");
    expect(linkState(link({ openable: false, viewsUsed: 1, viewLimit: 5 }))).toBe("expired");
  });

  it("keeps `revoked` ahead of every other finished reason", () => {
    // A grant that was revoked AND ran out is reported as revoked: the
    // patient acted, and the screen should say what they did.
    expect(linkState(link({ revoked: true, openable: false, viewsUsed: 5 }))).toBe("revoked");
  });

  /**
   * The near-miss a naive implementation passes: recompute the state from
   * `expiresAt` against `Date.now()`. It agrees with the server on every
   * fixture and disagrees exactly when the device clock is wrong — and the
   * disagreement is in the dangerous direction.
   */
  it("never retires a grant the server says is still openable, whatever the clock says", () => {
    const longPast = link({ expiresAt: "2020-01-01T00:00:00Z", openable: true });
    expect(linkState(longPast)).toBe("live");
    const overspent = link({ viewsUsed: 99, viewLimit: 5, openable: true });
    expect(linkState(overspent)).toBe("live");
  });

  it("gives every state a label the catalogue carries", () => {
    for (const state of ["live", "revoked", "expired", "used_up"] as const) {
      expect(tr[stateLabelKey(state)]).toBeTruthy();
    }
  });
});

/**
 * The clause INT-150 §6 exists to protect, restated on the client. A patient
 * who withdrew consent to share must still be able to stop the sharing they
 * already started, so the decision to offer the control may not consult a
 * consent value — and the surest way to guarantee that is for the function to
 * have nothing else to consult.
 */
describe("when the revoke control is offered", () => {
  it("takes the grant and nothing else — no consent state can reach it", () => {
    expect(revokeOffered).toHaveLength(1);
  });

  it("is offered on every grant the patient has not already revoked", () => {
    expect(revokeOffered(link())).toBe(true);
    // Expired and used-up included: if the server's verdict or this device's
    // clock were ever wrong, stopping it is still the patient's to do.
    expect(revokeOffered(link({ openable: false }))).toBe(true);
    expect(revokeOffered(link({ openable: false, viewsUsed: 5 }))).toBe(true);
  });

  it("is withdrawn only once the grant is revoked", () => {
    expect(revokeOffered(link({ revoked: true }))).toBe(false);
  });
});

describe("the access log the patient reads", () => {
  const ENTRY = {
    seq: 7,
    occurred_at_utc: "2026-09-03T11:24:05Z",
    category: "record_viewed",
    accessor_role: "clinician",
    resource_ref: "doctor_link:3f1d6f3e-0000-4000-8000-000000000001",
    entry_hash: "9f2b1c" + "0".repeat(58),
  };

  it("reads the sequence, the instant, what happened and the role", () => {
    expect(parseAccessLog([ENTRY])).toEqual([
      {
        seq: 7,
        occurredAt: "2026-09-03T11:24:05Z",
        category: "record_viewed",
        role: "clinician",
      },
    ]);
  });

  /**
   * The patient sees that a clinician opened their note, not which person
   * (files/10 §3; INT-150 §8). `resource_ref` and `entry_hash` are the two
   * id-shaped fields on the row, and neither is anything a patient can act
   * on — dropping them at the seam means no later screen can render one.
   */
  it("carries neither of the id-shaped fields into the app", () => {
    const rows = parseAccessLog([ENTRY]) ?? [];
    expect(JSON.stringify(rows)).not.toContain("doctor_link:");
    expect(JSON.stringify(rows)).not.toContain(ENTRY.entry_hash);
    expect(Object.keys(rows[0])).toEqual(["seq", "occurredAt", "category", "role"]);
  });

  it("keeps an unrecognised action and an unrecognised role as a visible row", () => {
    const rows = parseAccessLog([
      { ...ENTRY, category: "something_new", accessor_role: "auditor" },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows?.[0].category).toBe("other");
    expect(rows?.[0].role).toBe("unknown");
  });

  it("refuses a malformed payload instead of showing a shorter log", () => {
    expect(parseAccessLog({})).toBeNull();
    expect(parseAccessLog([{ seq: 1 }])).toBeNull();
  });

  it("gives every category and every role a label the catalogue carries", () => {
    const categories = [
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
    ] as const;
    for (const category of categories) {
      expect(tr[categoryLabelKey(category)], category).toBeTruthy();
    }
    const roles = ["self", "guardian", "clinician", "clinic_staff", "system", "unknown"] as const;
    for (const role of roles) {
      expect(tr[roleLabelKey(role)], role).toBeTruthy();
    }
  });

  it("names no person in any role label", () => {
    // A role is a category of reader. If one of these ever became a name or
    // a title carrying one, the log would start reconstructing an identity.
    for (const role of ["clinician", "clinic_staff", "guardian"] as const) {
      expect(tr[roleLabelKey(role)]).not.toMatch(/[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+[A-ZÇĞİÖŞÜ]/);
    }
  });
});

/**
 * One formatter for both the end of a grant and an entry in the log, and it
 * prints an INSTANT rather than a day.
 *
 * A day would have to choose a calendar. INT-150 anchors expiry to the start
 * of the visit date in Türkiye plus 72 h, so a grant ends at midnight local
 * time — and the UTC instant representing that falls on the previous date.
 * Printing either bare day states something the patient can act on wrongly
 * in one direction or the other: the earlier day understates the access they
 * still have, the later one overstates it. The instant states neither.
 */
describe("instants", () => {
  it("renders the month as a word, so the line cannot be read in two orders", () => {
    setLocale("tr");
    expect(formatShareMoment("2026-09-06T21:00:00Z")).toContain("2026");
    expect(formatShareMoment("2026-09-06T21:00:00Z")).toMatch(/[A-Za-zÇĞİÖŞÜçğıöşü]{3,}/);
  });

  it("groups no digits anywhere it prints a number (invariant 22)", () => {
    for (const locale of ["tr", "en"] as const) {
      setLocale(locale);
      for (const iso of ["2026-09-06T21:00:00Z", "1999-12-31T23:59:00Z"]) {
        // A grouped year is the failure this forbids: "1.999" for 1999.
        expect(formatShareMoment(iso), `${locale} ${iso}`).not.toMatch(/\d[.,\u00a0\u202f ]\d{3}\b/);
      }
    }
    setLocale("tr");
  });

  it("prints the clock time on a 24-hour dial, so no meridiem word is needed", () => {
    setLocale("tr");
    const rendered = formatShareMoment("2026-09-03T14:24:00Z");
    expect(rendered).not.toMatch(/AM|PM/i);
    expect(rendered).toMatch(/\d{1,2}:\d{2}/);
  });

  it("refuses an unreadable instant rather than printing an invalid date", () => {
    expect(formatShareMoment("not-a-date")).toBe("");
  });
});
