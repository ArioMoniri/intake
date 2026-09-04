import { describe, expect, it } from "vitest";

import { getTestAccount } from "./dev/accounts";
import type { RestorableSession } from "./auth/sessionSnapshot";
import { accountFromSnapshot, visibleTabs } from "./session";

describe("visibleTabs — the consent gate (02 §4)", () => {
  it("hides wellbeing entirely without consent", () => {
    const mehmet = getTestAccount("mehmet");
    expect(mehmet).toBeDefined();
    expect(visibleTabs(mehmet!.consents)).toEqual(["today", "visits", "records", "me"]);
  });

  it("shows wellbeing once consented, in rail position four", () => {
    const ayse = getTestAccount("ayse");
    expect(ayse).toBeDefined();
    expect(visibleTabs(ayse!.consents)).toEqual(["today", "visits", "records", "wellbeing", "me"]);
  });

  it("signed-out state shows the base rail", () => {
    expect(visibleTabs(null)).toEqual(["today", "visits", "records", "me"]);
  });

  it("me is always last — settings never mid-rail", () => {
    for (const consents of [
      null,
      { core: true, voice: true, wellbeing: true, documents: true, health: true },
      { core: true, voice: false, wellbeing: false, documents: false, health: false },
    ]) {
      const tabs = visibleTabs(consents);
      expect(tabs[tabs.length - 1]).toBe("me");
    }
  });
});

describe("accountFromSnapshot — rehydrating an OTP session after a reload", () => {
  const base: RestorableSession = {
    patientId: "pt_7f3c",
    maskedPhone: "+90 555 ··· ·· 89",
    displayName: null,
    visits: [],
  };

  it("prefers the hospital display name once the feed has supplied it", () => {
    expect(accountFromSnapshot({ ...base, displayName: "Ayşe Yılmaz" }).name).toBe("Ayşe Yılmaz");
  });

  it("falls back to the masked phone, never the raw number, before the feed answers", () => {
    // The raw number is not in the snapshot at all, so the only fallback the
    // restore can reach is the mask — which is exactly the pre-sync display.
    expect(accountFromSnapshot(base).name).toBe(base.maskedPhone);
  });

  it("is an otp account carrying nothing invented and no consent", () => {
    const account = accountFromSnapshot(base);
    expect(account.kind).toBe("otp");
    expect(account.id).toBe(base.patientId);
    expect(account.ageYears).toBeNull();
    expect(account.carriedFacts).toEqual([]);
    expect(account.records).toEqual([]);
    // Consents are NOT restored: a reload is not a fresh grant. Every scope is
    // off, exactly as signInOtp leaves a new account (invariant 4, INT-132).
    expect(account.consents).toEqual({
      core: false,
      voice: false,
      wellbeing: false,
      documents: false,
      health: false,
    });
  });
});
