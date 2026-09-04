/**
 * The restorable session snapshot, proved without a device.
 *
 * The same posture as appearance.test.ts: the SecureStore I/O lives in a
 * separate module (sessionSnapshotStore.ts) that vitest never loads; the shape
 * — what is stored, and how a foreign or corrupt record is refused — lives here
 * in pure functions, so a rule that would otherwise hide in a component is a
 * rule this suite can pin.
 *
 * Load-bearing assertions:
 *  - the encoded record carries the patient's masked identity and their
 *    upcoming visits and NOTHING else (invariant 6 / the inventory annotation):
 *    no `phone`, no raw number, no free-form extra key;
 *  - an absent, unreadable or foreign record reads as null (no session
 *    restored), never a half-built account the shell cannot show.
 */
import { describe, expect, it } from "vitest";

import type { VisitFixture } from "../dev/accounts";
import {
  SESSION_SNAPSHOT_SLOT,
  decodeSnapshot,
  encodeSnapshot,
  type RestorableSession,
} from "./sessionSnapshot";

const VISIT: VisitFixture = {
  id: "acb-10023-2026-09-10-1300",
  hospital: "Acıbadem Maslak",
  department: "Kardiyoloji · 13:00",
  branchId: null,
  visitType: null,
  date: "2026-09-10",
  noteStatus: null,
};

const SNAPSHOT: RestorableSession = {
  patientId: "pt_7f3c",
  maskedPhone: "+90 555 ··· ·· 89",
  displayName: "Ayşe Yılmaz",
  visits: [VISIT],
};

describe("the stored shape (restore snapshot)", () => {
  it("the slot is versioned, so a shape change never reads an old record", () => {
    expect(SESSION_SNAPSHOT_SLOT).toMatch(/\.v\d+$/);
  });

  it("round-trips a full snapshot including the mapped feed visits", () => {
    expect(decodeSnapshot(encodeSnapshot(SNAPSHOT))).toEqual(SNAPSHOT);
  });

  it("round-trips a not-yet-named account (name falls back later, not here)", () => {
    const anon: RestorableSession = { ...SNAPSHOT, displayName: null };
    expect(decodeSnapshot(encodeSnapshot(anon))).toEqual(anon);
  });

  it("the encoded record carries identity + visits and nothing else", () => {
    // Inventory annotation {category: patient display identity + upcoming
    // appointments; purpose: keep the home screen intact across a relaunch
    // without re-reading the hospital feed; basis: the core-scope sync that
    // produced it; retention: until sign-out or uninstall; recipients: none —
    // device-only, encrypted, never synced}. The raw phone is masked upstream
    // and is not a key here; assert the exact key set rather than the absence
    // of a name.
    const encoded: unknown = JSON.parse(encodeSnapshot(SNAPSHOT));
    expect(Object.keys(encoded as object).sort()).toEqual(
      ["displayName", "maskedPhone", "patientId", "visits"].sort(),
    );
    const visit: unknown = (encoded as { visits: unknown[] }).visits[0];
    expect(Object.keys(visit as object).sort()).toEqual(
      ["branchId", "date", "department", "hospital", "id", "noteStatus", "visitType"].sort(),
    );
  });

  it("never stores a phone under any spelling", () => {
    const encoded = encodeSnapshot(SNAPSHOT);
    for (const key of ["phone", "rawPhone", "e164", "msisdn"]) {
      expect(encoded).not.toContain(`"${key}"`);
    }
  });
});

describe("an absent, unreadable or foreign record restores no session", () => {
  it("reads as null rather than a half-built account", () => {
    for (const raw of [null, "", "{", "[]", '"x"', "null", "3", "true"]) {
      expect(decodeSnapshot(raw)).toBeNull();
    }
  });

  it("refuses a record missing the tokenized patient id", () => {
    expect(decodeSnapshot(JSON.stringify({ maskedPhone: "+90 …", visits: [] }))).toBeNull();
  });

  it("refuses a record missing the masked phone (the fallback name)", () => {
    expect(decodeSnapshot(JSON.stringify({ patientId: "pt_1", visits: [] }))).toBeNull();
  });

  it("refuses an empty-string id or masked phone", () => {
    expect(
      decodeSnapshot(JSON.stringify({ patientId: "", maskedPhone: "+90 …", visits: [] })),
    ).toBeNull();
    expect(
      decodeSnapshot(JSON.stringify({ patientId: "pt_1", maskedPhone: "", visits: [] })),
    ).toBeNull();
  });
});

describe("the visits list is rebuilt defensively", () => {
  it("an absent or non-array visits field reads as no visits", () => {
    expect(
      decodeSnapshot(JSON.stringify({ patientId: "pt_1", maskedPhone: "+90 …" }))?.visits,
    ).toEqual([]);
    expect(
      decodeSnapshot(JSON.stringify({ patientId: "pt_1", maskedPhone: "+90 …", visits: "no" }))
        ?.visits,
    ).toEqual([]);
  });

  it("drops a malformed visit and keeps the well-formed ones", () => {
    const raw = JSON.stringify({
      patientId: "pt_1",
      maskedPhone: "+90 …",
      visits: [
        VISIT,
        { id: "x" }, // missing hospital/department
        { hospital: "H", department: "D" }, // missing id
        42,
        null,
      ],
    });
    expect(decodeSnapshot(raw)?.visits).toEqual([VISIT]);
  });

  it("coerces a non-string display name to null rather than rejecting the record", () => {
    const raw = JSON.stringify({ ...SNAPSHOT, displayName: 7 });
    expect(decodeSnapshot(raw)?.displayName).toBeNull();
    expect(decodeSnapshot(raw)?.patientId).toBe(SNAPSHOT.patientId);
  });

  it("coerces an out-of-taxonomy visit type or note status to null", () => {
    const raw = JSON.stringify({
      patientId: "pt_1",
      maskedPhone: "+90 …",
      visits: [{ ...VISIT, visitType: "telepathy", noteStatus: "invented" }],
    });
    const [restored] = decodeSnapshot(raw)?.visits ?? [];
    expect(restored?.visitType).toBeNull();
    expect(restored?.noteStatus).toBeNull();
  });

  it("keeps a real visit type and note status the taxonomy recognises", () => {
    const raw = JSON.stringify({
      patientId: "pt_1",
      maskedPhone: "+90 …",
      visits: [{ ...VISIT, branchId: "kardiyoloji", visitType: "first", noteStatus: "draft" }],
    });
    const [restored] = decodeSnapshot(raw)?.visits ?? [];
    expect(restored?.branchId).toBe("kardiyoloji");
    expect(restored?.visitType).toBe("first");
    expect(restored?.noteStatus).toBe("draft");
  });
});
