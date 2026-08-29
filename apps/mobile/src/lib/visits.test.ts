/**
 * INT-134 — visit creation over the production taxonomy: validation,
 * the local build, the list split with optional dates, the new-visit form
 * reducer (SMS paste-parse included) and the fail-closed OCR gate.
 */
import { describe, expect, it } from "vitest";

import { SEED_BRANCHES, branchById } from "./taxonomy/branches";
import type { ParsedMhrsSms } from "./taxonomy/mhrsSms";
import {
  buildLocalVisit,
  emptyNewVisitForm,
  newVisitFormReducer,
  ocrImportAvailable,
  splitVisits,
  validateNewVisit,
  type NewVisitInput,
} from "./visits";

const kardiyoloji = branchById(SEED_BRANCHES, "kardiyoloji");
const anesteziyoloji = branchById(SEED_BRANCHES, "anesteziyoloji");
if (!kardiyoloji || !anesteziyoloji) {
  throw new Error("seed is missing the branches this suite is built on");
}

const INPUT: NewVisitInput = {
  hospital: "Ankara Şehir Hastanesi",
  branchId: "kardiyoloji",
  branchNameTr: "Kardiyoloji",
  visitType: "first",
  date: "2026-09-15",
};

describe("validateNewVisit (taxonomy-backed)", () => {
  it("accepts a complete input, and one without a date", () => {
    expect(validateNewVisit(INPUT)).toEqual({ ok: true });
    expect(validateNewVisit({ ...INPUT, date: null })).toEqual({ ok: true });
  });

  it("requires hospital, branch and visit type", () => {
    expect(validateNewVisit({ ...INPUT, hospital: "  " })).toEqual({
      ok: false,
      reason: "missing_fields",
    });
    expect(validateNewVisit({ ...INPUT, branchId: null })).toEqual({
      ok: false,
      reason: "missing_fields",
    });
    expect(validateNewVisit({ ...INPUT, visitType: null })).toEqual({
      ok: false,
      reason: "missing_fields",
    });
  });

  it("rejects a non-ISO or impossible date", () => {
    expect(validateNewVisit({ ...INPUT, date: "15.09.2026" })).toEqual({
      ok: false,
      reason: "bad_date",
    });
    expect(validateNewVisit({ ...INPUT, date: "2026-02-31" })).toEqual({
      ok: false,
      reason: "bad_date",
    });
  });
});

describe("buildLocalVisit", () => {
  it("derives the department label from the branch's tr name (invariant 5)", () => {
    const visit = buildLocalVisit({ ...INPUT, hospital: "  Hastane  " }, 7);
    expect(visit).toEqual({
      id: "v-local-7",
      hospital: "Hastane",
      department: "Kardiyoloji",
      branchId: "kardiyoloji",
      visitType: "first",
      date: "2026-09-15",
      noteStatus: null,
    });
  });

  it("keeps a missing date missing", () => {
    expect(buildLocalVisit({ ...INPUT, date: null }, 1).date).toBeNull();
  });
});

describe("splitVisits", () => {
  const visit = (id: string, date: string | null) => ({ id, date });

  it("buckets by date and keeps a dateless visit visible as upcoming", () => {
    const { upcoming, past } = splitVisits(
      [visit("a", "2026-09-20"), visit("b", "2026-01-01"), visit("c", null)],
      "2026-08-28",
    );
    expect(upcoming.map((v) => v.id)).toEqual(["a", "c"]);
    expect(past.map((v) => v.id)).toEqual(["b"]);
  });
});

describe("the new-visit form reducer", () => {
  it("picks a branch and clears a visit type the branch does not book", () => {
    let state = emptyNewVisitForm();
    state = newVisitFormReducer(state, { type: "pick_branch", branch: kardiyoloji });
    state = newVisitFormReducer(state, { type: "pick_visit_type", visitType: "followup" });
    expect(state.branchId).toBe("kardiyoloji");
    expect(state.visitType).toBe("followup");

    state = newVisitFormReducer(state, { type: "pick_branch", branch: anesteziyoloji });
    // anesteziyoloji books preop only — a stale followup would be a lie
    expect(state.visitType).toBeNull();
  });

  it("applies a fully parsed SMS and drops the raw text", () => {
    const parsed: ParsedMhrsSms = {
      dateIso: "2026-09-03",
      time: "14:30",
      hospital: "ANKARA BILKENT SEHIR HASTANESI",
      branchId: "kardiyoloji",
      branchText: "KARDIYOLOJI",
    };
    let state = newVisitFormReducer(emptyNewVisitForm(), {
      type: "set_sms",
      value: "the pasted message",
    });
    state = newVisitFormReducer(state, { type: "apply_sms", parsed, branches: SEED_BRANCHES });
    expect(state.hospital).toBe("ANKARA BILKENT SEHIR HASTANESI");
    expect(state.branchId).toBe("kardiyoloji");
    expect(state.date).toBe("2026-09-03");
    expect(state.smsNotice).toBe("filled");
    // the raw SMS never outlives the parse (client-side only, never persisted)
    expect(state.sms).toBe("");
  });

  it("an unknown branch surfaces the friendly picker notice, never a crash", () => {
    const parsed: ParsedMhrsSms = {
      dateIso: "2026-09-07",
      time: "11:20",
      hospital: "BURSA DEVLET HASTANESI",
      branchId: null,
      branchText: "CILDIYE",
    };
    const state = newVisitFormReducer(emptyNewVisitForm(), {
      type: "apply_sms",
      parsed,
      branches: SEED_BRANCHES,
    });
    expect(state.branchId).toBeNull();
    expect(state.hospital).toBe("BURSA DEVLET HASTANESI");
    expect(state.date).toBe("2026-09-07");
    expect(state.smsNotice).toBe("unknown_branch");
  });

  it("a matched branch without a date asks for the date", () => {
    const parsed: ParsedMhrsSms = {
      dateIso: null,
      time: null,
      hospital: null,
      branchId: "noroloji",
      branchText: "NOROLOJI",
    };
    const state = newVisitFormReducer(emptyNewVisitForm(), {
      type: "apply_sms",
      parsed,
      branches: SEED_BRANCHES,
    });
    expect(state.branchId).toBe("noroloji");
    expect(state.smsNotice).toBe("no_date");
  });

  it("an unreadable message says so and changes nothing else", () => {
    const parsed: ParsedMhrsSms = {
      dateIso: null,
      time: null,
      hospital: null,
      branchId: null,
      branchText: null,
    };
    const before = newVisitFormReducer(emptyNewVisitForm(), {
      type: "set_hospital",
      value: "Elle girilen hastane",
    });
    const state = newVisitFormReducer(before, {
      type: "apply_sms",
      parsed,
      branches: SEED_BRANCHES,
    });
    expect(state.hospital).toBe("Elle girilen hastane");
    expect(state.smsNotice).toBe("unreadable");
  });
});

describe("ocrImportAvailable (acceptance: OCR path behind documents consent)", () => {
  it("is closed without the documents consent", () => {
    expect(ocrImportAvailable(null)).toBe(false);
    expect(ocrImportAvailable({ documents: false })).toBe(false);
  });

  it("stays closed even WITH the consent while no licence-verified OCR exists", () => {
    // files/03 §4.9.2(f): no OCR component reaches the PHI path without a
    // licence_verified_at entry read from the raw LICENSE blob. The gate is
    // consent AND engine; today the engine half is honestly false.
    expect(ocrImportAvailable({ documents: true })).toBe(false);
  });
});
