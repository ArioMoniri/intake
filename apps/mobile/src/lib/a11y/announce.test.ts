import { describe, expect, it } from "vitest";

import {
  iosAnnouncement,
  lineStep,
  nextAnnouncement,
  politenessOf,
  spokenLine,
  type Politeness,
} from "./announce";

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

  it("never speaks an empty or blank message, and treats it as nothing shown", () => {
    // An empty string reaching VoiceOver is a silent interruption: it cuts
    // off whatever was being read and says nothing in its place.
    expect(nextAnnouncement(null, "")).toEqual({ speak: null, remember: null });
    expect(nextAnnouncement("Okunuyor", "   ")).toEqual({ speak: null, remember: null });
    // ...and, like null, it clears the memory, so the line coming back is news.
    expect(nextAnnouncement(null, "Okunuyor").speak).toBe("Okunuyor");
  });
});

describe("politenessOf — an error interrupts, a status waits (INT-362)", () => {
  it("an error is assertive", () => {
    expect(politenessOf("error")).toBe("assertive");
  });

  it("a status is polite", () => {
    expect(politenessOf("status")).toBe("polite");
  });

  it("a warning is assertive — time is running out, it cannot wait its turn (INT-363)", () => {
    expect(politenessOf("warning")).toBe("assertive");
  });
});

describe("a warning is urgent but is not an error (INT-363, SC 2.2.1)", () => {
  const HATA = "Hata";
  const WARNING = "Hâlâ burada mısınız? Bilgilerinizi korumak için oturum birazdan kapanacak.";

  it("is spoken exactly as shown — the patient did nothing wrong, so no error word", () => {
    expect(spokenLine("warning", WARNING, HATA)).toBe(WARNING);
  });

  it("interrupts on iOS and cannot be cut off by the focus move that follows it", () => {
    expect(lineStep(null, WARNING, "ios", politenessOf("warning")).post).toEqual({
      text: WARNING,
      options: { queue: false, priority: "high" },
    });
  });

  it("posts nothing on Android, where the line's live region carries it", () => {
    expect(lineStep(null, WARNING, "android", politenessOf("warning")).post).toBeNull();
  });
});

describe("spokenLine — an error is heard as one (SC 3.3.1)", () => {
  const HATA = "Hata";

  it("a status is spoken exactly as it is shown", () => {
    expect(spokenLine("status", "Okunuyor", HATA)).toBe("Okunuyor");
  });

  it("an error is spoken with the error word first; the visible copy is not touched", () => {
    // A screen reader meets the line with no colour and no position to tell
    // it apart from a hint, so the word is added to what is SPOKEN only.
    expect(spokenLine("error", "Bu adı kontrol edin.", HATA)).toBe("Hata: Bu adı kontrol edin.");
  });

  it("an error whose visible copy already names itself is not named twice", () => {
    expect(spokenLine("error", "Hata · Onayınız kaydedilemedi.", HATA)).toBe(
      "Hata · Onayınız kaydedilemedi.",
    );
  });

  it("an empty line stays empty, so there is nothing to announce", () => {
    expect(spokenLine("error", "", HATA)).toBe("");
    expect(spokenLine("status", "  ", HATA)).toBe("");
  });
});

describe("iosAnnouncement — the half VoiceOver hears", () => {
  it("iOS gets the words, and an error interrupts what is being read", () => {
    expect(iosAnnouncement("ios", "Hata: Bu adı kontrol edin.", "assertive")).toEqual({
      text: "Hata: Bu adı kontrol edin.",
      options: { queue: false, priority: "high" },
    });
  });

  it("iOS queues a status behind current speech", () => {
    expect(iosAnnouncement("ios", "Okunuyor", "polite")).toEqual({
      text: "Okunuyor",
      options: { queue: true, priority: "low" },
    });
  });

  it("Android posts nothing: the line's own live region is what TalkBack reads", () => {
    // A second, imperative announcement on top of the live region is the
    // double reading the dialogue test forbids.
    expect(iosAnnouncement("android", "Okunuyor", "polite")).toBeNull();
    expect(iosAnnouncement("android", "Hata: Bu adı kontrol edin.", "assertive")).toBeNull();
  });

  it("web posts nothing: the live region is rendered as aria-live there", () => {
    expect(iosAnnouncement("web", "Okunuyor", "polite")).toBeNull();
  });

  it("nothing to say, nothing posted", () => {
    expect(iosAnnouncement("ios", null, "assertive")).toBeNull();
  });
});

describe("lineStep — one line across its renders", () => {
  /** Drive one line through a sequence of renders; return what VoiceOver hears. */
  function heard(os: string, politeness: Politeness, renders: (string | null)[]): string[] {
    let previous: string | null = null;
    const posts: string[] = [];
    for (const message of renders) {
      const { post, remember } = lineStep(previous, message, os, politeness);
      previous = remember;
      if (post !== null) {
        posts.push(post.text);
      }
    }
    return posts;
  }

  it("announces once per change — never for an unchanged or an empty message", () => {
    expect(
      heard("ios", "assertive", ["A", "A", "A", "B", "B", null, "", "A", "A", "   ", "A"]),
    ).toEqual(["A", "B", "A", "A"]);
  });

  it("carries the politeness through to the post", () => {
    expect(lineStep(null, "Okunuyor", "ios", "polite").post?.options).toEqual({
      queue: true,
      priority: "low",
    });
    expect(lineStep(null, "Hata: X", "ios", "assertive").post?.options).toEqual({
      queue: false,
      priority: "high",
    });
  });

  it("on Android the same sequence posts nothing, and still tracks what is shown", () => {
    expect(heard("android", "assertive", ["A", "B", null, "A"])).toEqual([]);
    expect(lineStep(null, "A", "android", "assertive").remember).toBe("A");
  });
});
