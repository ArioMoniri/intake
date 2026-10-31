/**
 * INT-598 — Vizitlerim's chips show the note's real state (GitHub #1015).
 *
 * Found in INT-594. `visits/index.tsx` read the raw `noteStatus` for its
 * chips and for each card's accessible name. A hospital-feed visit always
 * carries null there (api.ts `syncVisits`), so an OTP account's list never
 * showed a status. The visit detail already resolved status with
 * `effectiveStatus`: the draft on the phone, and a sent note only once the
 * server confirmed it (INT-587). Bugün does too after INT-594. The list now
 * uses the same rule, per row, against the note outbox.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";
import { effectiveStatus, emptyNoteState, type NoteState } from "../src/lib/intake/note";

const MOBILE = join(__dirname, "..");
const screen = readFileSync(join(MOBILE, "src", "app", "(tabs)", "visits", "index.tsx"), "utf8");

function answered(): NoteState {
  return { ...emptyNoteState(), answers: [{ questionId: "chief_complaint", values: ["öksürük"] }] };
}

function sentByPatient(): NoteState {
  return { ...answered(), status: "sent" };
}

describe("the rule a row's chip follows (effectiveStatus)", () => {
  it("a feed visit with nothing on the phone carries no chip", () => {
    expect(effectiveStatus(null, undefined, false)).toBeNull();
    expect(effectiveStatus(null, emptyNoteState(), false)).toBeNull();
  });

  it("a feed visit with answers on the phone reads Taslak — the chip OTP lists never showed", () => {
    expect(effectiveStatus(null, answered(), false)).toBe("draft");
    expect(tr["status.draft"]).toBe("Taslak");
    expect(en["status.draft"]).toBe("Draft");
  });

  it("near miss: a note the patient sent that the server has not confirmed stays Taslak", () => {
    expect(effectiveStatus(null, sentByPatient(), false)).toBe("draft");
  });

  it("near miss: a confirmed delivery without the patient's send is not Gönderildi", () => {
    expect(effectiveStatus(null, answered(), true)).toBe("draft");
  });

  it("a note the server confirmed reads Gönderildi", () => {
    expect(effectiveStatus(null, sentByPatient(), true)).toBe("sent");
    expect(tr["status.sent"]).toBe("Gönderildi");
  });

  it("keeps a visit's own ladder step where it has one (dev fixtures)", () => {
    expect(effectiveStatus("filed", undefined, false)).toBe("filed");
    expect(effectiveStatus("viewed", answered(), false)).toBe("viewed");
  });
});

describe("Vizitlerim resolves every row with that rule", () => {
  it("each row reads its own outbox verdict and the draft on the phone", () => {
    expect(screen).toContain('useDelivery(visit.id)?.stage === "delivered"');
    expect(screen).toContain("effectiveStatus(visit.noteStatus, note, delivered)");
    expect(screen).toMatch(/notes\[visit\.id\]/);
  });

  it("the chip and the card's spoken name both carry the resolved status", () => {
    expect(screen).toContain("statusOverride={status}");
    expect(screen).toContain("cardLabel(visit, status)");
    expect(screen).toMatch(/status === null \? null : t\(statusLabelKey\(status\)\)/);
  });

  it("near miss: the raw feed value never decides what a row shows", () => {
    expect(screen).not.toMatch(/visit\.noteStatus\s*===/);
    expect(screen).not.toMatch(/statusLabelKey\(visit\.noteStatus\)/);
    // and the pattern does see the line the list shipped with
    expect("visit.noteStatus === null ? null : t(statusLabelKey(visit.noteStatus))").toMatch(
      /visit\.noteStatus\s*===/,
    );
  });

  it("the calendar's day list renders the same rows", () => {
    expect(screen).toContain("dayVisits.map(renderVisit)");
    expect(screen).toContain("upcoming.map(renderVisit)");
    expect(screen).toContain("past.map(renderVisit)");
  });
});
