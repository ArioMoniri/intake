import { describe, expect, it } from "vitest";

import {
  arrivedAt,
  iosAnnouncement,
  lineStep,
  newsStep,
  nextAnnouncement,
  politenessOf,
  spokenLine,
  type NewsMemory,
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

/*
 * INT-397 (SC 4.1.3). Three lines state how the patient's own action stands:
 * the note was sent, a consent change waits for a connection, a setting did
 * not save. Each stays on screen for as long as it is so, and is there again
 * on every visit. It is news once — when the store moves into it while the
 * screen is in front — and never on arrival.
 */
describe("newsStep — an outcome is news when it happens, not when it is found (INT-397)", () => {
  const SENT = "Notunuz gönderildi. Hekiminiz görüntülediğinde durumu burada görürsünüz.";
  const NOT_SAVED =
    "Hata: Değişikliğiniz henüz kaydedilmedi. Bağlantınızı kontrol edip yeniden deneyin.";

  /** One render: whether the outcome stands, and whether the screen is in front. */
  type Render = readonly [standing: boolean, inFront: boolean];

  /**
   * What VoiceOver hears across a screen's renders: the news rule decides
   * whether the line is news, and the line's own rule (lineStep) posts it —
   * the announcer passes `news ? spoken : null` to the iOS half.
   */
  function heardOutcome(spoken: string, first: boolean, renders: readonly Render[]): string[] {
    let memory: NewsMemory = arrivedAt(first);
    let previous: string | null = null;
    const posts: string[] = [];
    for (const [standing, inFront] of renders) {
      memory = newsStep(memory, standing, inFront);
      const { post, remember } = lineStep(
        previous,
        memory.news ? spoken : null,
        "ios",
        politenessOf("status"),
      );
      previous = remember;
      if (post !== null) {
        posts.push(post.text);
      }
    }
    return posts;
  }

  it("a line found standing on arrival is not news — a revisit is silent", () => {
    expect(newsStep(arrivedAt(true), true, true).news).toBe(false);
    // The review screen reopened after the note was sent, re-rendered twice.
    expect(
      heardOutcome(SENT, true, [
        [true, true],
        [true, true],
        [true, true],
      ]),
    ).toEqual([]);
  });

  it("the outcome arriving in front of the patient is news — just sent, just queued", () => {
    expect(newsStep(arrivedAt(false), true, true).news).toBe(true);
    expect(
      heardOutcome(SENT, false, [
        [false, true],
        [true, true],
      ]),
    ).toEqual([SENT]);
  });

  it("an outcome that arrives behind another screen is not news, then or when the screen returns", () => {
    // The visit detail sits under the review screen when the note is sent;
    // the review screen, in front, is where it is heard.
    const behind = newsStep(arrivedAt(false), true, false);
    expect(behind.news).toBe(false);
    expect(newsStep(behind, true, true).news).toBe(false);
    expect(
      heardOutcome(SENT, false, [
        [false, false],
        [true, false],
        [true, true],
        [true, true],
      ]),
    ).toEqual([]);
  });

  it("stays news while the outcome stands, so the line is not re-made after it is announced", () => {
    let memory = newsStep(arrivedAt(false), true, true);
    for (const inFront of [true, false, true]) {
      memory = newsStep(memory, true, inFront);
      expect(memory.news).toBe(true);
    }
    expect(newsStep(memory, false, true)).toEqual(arrivedAt(false));
  });

  it("announces once per change: each new failure is news again, a standing one is not", () => {
    // idle → saving → failed ×2 → saving (retry) → failed → idle: the line is
    // visible while saving, and only each move into `failed` is heard.
    const failed = (standing: boolean): Render => [standing, true];
    expect(
      heardOutcome(NOT_SAVED, false, [
        failed(false),
        failed(false),
        failed(true),
        failed(true),
        failed(false),
        failed(true),
        failed(false),
      ]),
    ).toEqual([NOT_SAVED, NOT_SAVED]);
  });

  it("settles in one step, so the screen can take it during render without looping", () => {
    // useNews stores the step's result with setState during render; a second
    // step over the same inputs must hand back the SAME memory.
    const memories: NewsMemory[] = [
      arrivedAt(false),
      arrivedAt(true),
      { stood: true, news: true },
      { stood: false, news: false },
    ];
    for (const memory of memories) {
      for (const standing of [false, true]) {
        for (const inFront of [false, true]) {
          const next = newsStep(memory, standing, inFront);
          expect(newsStep(next, standing, inFront)).toBe(next);
        }
      }
    }
    // ...and an unchanged screen is the same object, so nothing is set at all.
    const quiet = arrivedAt(false);
    expect(newsStep(quiet, false, true)).toBe(quiet);
  });
});
