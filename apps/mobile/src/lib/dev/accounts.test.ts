import { describe, expect, it } from "vitest";

import { getTestAccount, testAccounts } from "./accounts";

describe("synthetic test accounts", () => {
  it("exist for both consent postures", () => {
    const wellbeingStates = new Set(testAccounts.map((a) => a.consents.wellbeing));
    expect(wellbeingStates).toEqual(new Set([true, false]));
  });

  it("carry no TCKN-shaped data anywhere (synthetic-only guarantee)", () => {
    const serialized = JSON.stringify(testAccounts);
    // A Turkish national id is 11 consecutive digits; nothing in the
    // fixtures may even look like one.
    expect(serialized).not.toMatch(/\d{11}/);
  });

  it("visit dates are ISO dates and statuses are from the 02 §5.1 ladder", () => {
    const ladder = new Set(["draft", "sent", "viewed", "filed"]);
    for (const account of testAccounts) {
      for (const visit of account.visits) {
        expect(visit.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        if (visit.noteStatus !== null) {
          expect(ladder.has(visit.noteStatus), visit.id).toBe(true);
        }
      }
    }
  });

  it("looks up by id and misses safely", () => {
    expect(getTestAccount("ayse")?.name).toBe("Ayşe Yılmaz");
    expect(getTestAccount("nobody")).toBeUndefined();
  });
});
