import { describe, expect, it } from "vitest";

import { buildLocalVisit, validateNewVisit } from "./visits";

describe("new-visit validation (INT-193 working form)", () => {
  it("accepts a complete input", () => {
    expect(
      validateNewVisit({ hospital: "Ankara Şehir Hastanesi", department: "Kardiyoloji", date: "2026-09-15" }),
    ).toEqual({ ok: true });
  });

  it("rejects missing hospital or department before date shape", () => {
    expect(validateNewVisit({ hospital: " ", department: "KBB", date: "2026-09-15" })).toEqual({
      ok: false,
      reason: "missing_fields",
    });
    expect(validateNewVisit({ hospital: "X", department: "", date: "nonsense" })).toEqual({
      ok: false,
      reason: "missing_fields",
    });
  });

  it("rejects a non-ISO date", () => {
    expect(validateNewVisit({ hospital: "X", department: "Y", date: "15.09.2026" })).toEqual({
      ok: false,
      reason: "bad_date",
    });
  });
});

describe("buildLocalVisit", () => {
  it("trims fields, sequences ids, starts with no note", () => {
    const visit = buildLocalVisit(
      { hospital: "  Hastane  ", department: " Bölüm ", date: " 2026-09-15 " },
      7,
    );
    expect(visit).toEqual({
      id: "v-local-7",
      hospital: "Hastane",
      department: "Bölüm",
      date: "2026-09-15",
      noteStatus: null,
    });
  });
});
