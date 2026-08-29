import { describe, expect, it } from "vitest";

import { nextAnnouncement } from "./announce";

describe("nextAnnouncement", () => {
  it("speaks a new message", () => {
    expect(nextAnnouncement(null, "Sizi dinliyoruz.")).toEqual({
      speak: "Sizi dinliyoruz.",
      remember: "Sizi dinliyoruz.",
    });
  });

  it("says the same message once, not on every re-render", () => {
    expect(nextAnnouncement("Sizi dinliyoruz.", "Sizi dinliyoruz.")).toEqual({
      speak: null,
      remember: "Sizi dinliyoruz.",
    });
  });

  it("stays quiet when there is no status", () => {
    expect(nextAnnouncement("Sizi dinliyoruz.", null)).toEqual({ speak: null, remember: null });
  });

  it("A → null → A announces A twice — the bug this module exists for", () => {
    // speaking → confirming (no status) → speaking is the ordinary dialogue
    // path; forgetting to clear on null silently ate the second announcement.
    const first = nextAnnouncement(null, "Vizite konuşuyor");
    expect(first.speak).toBe("Vizite konuşuyor");
    const gap = nextAnnouncement(first.remember, null);
    expect(gap.speak).toBeNull();
    const again = nextAnnouncement(gap.remember, "Vizite konuşuyor");
    expect(again.speak).toBe("Vizite konuşuyor");
  });
});
