/**
 * The chat composer's trailing control (INT-462; docs/design/library-patterns.md
 * P1 and P3; the owner's yes to a mic in the empty composer, 3 Oct 2026).
 *
 * One control sits inside the capsule's trailing edge, and which one it is
 * depends only on the draft and the turn:
 *
 * - a draft with words in it: send, in every phase (typing over a listen
 *   replaces it, as the composer always has);
 * - an empty draft while the agent speaks or confirms: the mic. It opens the
 *   microphone through the session's own path (barge-in while speaking, the
 *   spoken correction while confirming) and only when tapped;
 * - an empty draft while listening: stop, which is "Bitirdim";
 * - an empty draft while the dialogue settles: send, disabled, because there
 *   is no live question for the microphone to answer.
 *
 * The swap is instant (ADR-033: a morph would be a second animated element).
 */
import { describe, expect, it } from "vitest";

import { composerTrailing, type ComposerPhase } from "./composer";

const PHASES: readonly ComposerPhase[] = ["speaking", "listening", "confirming", "settling"];

describe("composerTrailing", () => {
  it("words in the draft: send, enabled, in every phase", () => {
    for (const phase of PHASES) {
      expect(composerTrailing({ draft: "başım ağrıyor", phase }), phase).toEqual({
        kind: "send",
        enabled: true,
      });
    }
  });

  it("an empty draft while the agent speaks: the mic, which barges in", () => {
    expect(composerTrailing({ draft: "", phase: "speaking" })).toEqual({
      kind: "mic",
      opens: "bargeIn",
    });
  });

  it("an empty draft on the confirm turn: the mic, which takes the spoken correction", () => {
    expect(composerTrailing({ draft: "", phase: "confirming" })).toEqual({
      kind: "mic",
      opens: "speakCorrection",
    });
  });

  it("an empty draft while listening: stop, never a second mic", () => {
    expect(composerTrailing({ draft: "", phase: "listening" })).toEqual({ kind: "stop" });
  });

  it("an empty draft while settling: send, disabled; there is no question to answer", () => {
    expect(composerTrailing({ draft: "", phase: "settling" })).toEqual({
      kind: "send",
      enabled: false,
    });
  });

  it("near miss: whitespace is an empty draft, so it never offers a send that sends nothing", () => {
    expect(composerTrailing({ draft: "   \n", phase: "speaking" }).kind).toBe("mic");
    expect(composerTrailing({ draft: "  ", phase: "settling" })).toEqual({
      kind: "send",
      enabled: false,
    });
  });

  it("the first character swaps the mic for send", () => {
    expect(composerTrailing({ draft: "", phase: "confirming" }).kind).toBe("mic");
    expect(composerTrailing({ draft: "e", phase: "confirming" }).kind).toBe("send");
  });
});
