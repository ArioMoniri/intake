import { describe, expect, it } from "vitest";

import { getTestAccount } from "./dev/accounts";
import { visibleTabs } from "./session";

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
