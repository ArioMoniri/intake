/**
 * INT-249 — the patient never waits on synthesis to READ the question.
 *
 * The ask-ahead contract (INT-235, useDialogueSession.ts) is that the turn
 * advances the moment the mic closes and the question TEXT is on screen from
 * the reducer, while TTS catches up behind it. That contract already held in
 * the code, and nothing pinned it: no React Native render tests exist in this
 * app, so a regression that wrapped the bubble body in a `session.playing`
 * gate would have passed the entire suite while turning every slow synthesis
 * into a blank bubble. INT-249's whole premise is a lane that takes eight
 * seconds to answer, so the guarantee that the eight seconds cost audio and
 * not text is the one that has to be nailed down.
 *
 * Same technique as a11y.spec.ts and the rest of e2e/: React Native has no
 * DOM, so what is provable without a device is what the source declares.
 * The three declarations that carry the guarantee:
 *
 *   1. The bubble body is built from the question catalog alone — the
 *      playback flag is not an input to it.
 *   2. Both the live and the settled bubble render that body unconditionally,
 *      and in the live bubble the body precedes the status row.
 *   3. "Soru hazırlanıyor…" is the status row's caption swapping with
 *      "Önvizit konuşuyor", never a stand-in for the question.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");
const DIALOGUE_INTAKE = join(MOBILE, "src", "components", "DialogueIntake.tsx");

const src = readFileSync(DIALOGUE_INTAKE, "utf8");

/** The `renderAgentBubble` closure, which owns everything asserted here. */
function agentBubble(): string {
  const start = src.indexOf("const renderAgentBubble");
  expect(start, "renderAgentBubble not found — this spec needs re-aiming").toBeGreaterThan(-1);
  const end = src.indexOf("const renderEntry", start);
  expect(end).toBeGreaterThan(start);
  return src.slice(start, end);
}

/** Every index at which `needle` occurs in `haystack`. */
function indicesOf(haystack: string, needle: string): number[] {
  const found: number[] = [];
  for (let at = haystack.indexOf(needle); at !== -1; at = haystack.indexOf(needle, at + 1)) {
    found.push(at);
  }
  return found;
}

describe("ask-ahead: the question text does not wait for audio", () => {
  it("builds the bubble body from the catalog, never from the playback flag", () => {
    const bubble = agentBubble();
    const from = bubble.indexOf("let body");
    const to = bubble.indexOf("const name =");
    expect(from).toBeGreaterThan(-1);
    expect(to).toBeGreaterThan(from);
    // Everything between the declaration of `body` and the point it is
    // finished is catalog lookups. A `playing` reference in here would mean
    // the words themselves depend on whether audio started.
    expect(bubble.slice(from, to)).not.toMatch(/playing/);
  });

  it("renders the body in the settled bubble and in the live one alike", () => {
    expect(indicesOf(agentBubble(), "{body}")).toHaveLength(2);
  });

  it("puts the body ahead of the status row inside the live bubble", () => {
    const bubble = agentBubble();
    const stateRow = bubble.indexOf("styles.stateRow");
    expect(stateRow).toBeGreaterThan(-1);
    const bodies = indicesOf(bubble, "{body}");
    // The live bubble is the second `{body}`; the status row follows it, so
    // the spinner and its caption sit UNDER the question rather than over it.
    expect(bodies[1]).toBeLessThan(stateRow);
  });

  it("keeps every {body} out of a playback-gated expression", () => {
    const bubble = agentBubble();
    for (const at of indicesOf(bubble, "{body}")) {
      // The JSX line that renders the body carries no condition at all.
      const lineStart = bubble.lastIndexOf("\n", at) + 1;
      const lineEnd = bubble.indexOf("\n", at);
      const line = bubble.slice(lineStart, lineEnd === -1 ? undefined : lineEnd).trim();
      expect(line).toBe("{body}");
    }
  });

  it('renders "Soru hazırlanıyor…" as a status swap, never instead of the question', () => {
    // Both preparing strings are the false arm of a ternary whose true arm is
    // the speaking string, and both live in the status row / live-region
    // status — not in the bubble body.
    for (const [preparing, speaking] of [
      ["dialogue.preparing", "dialogue.speakingHint"],
      ["a11y.dialogue.preparing", "a11y.dialogue.speaking"],
    ]) {
      const uses = indicesOf(src, `t("${preparing}")`);
      expect(uses.length, `${preparing} is unused`).toBeGreaterThan(0);
      for (const at of uses) {
        // Look back over the enclosing expression for its partner.
        const window = src.slice(Math.max(0, at - 200), at);
        expect(window, `${preparing} must swap with ${speaking}`).toContain(`t("${speaking}")`);
        expect(window).toContain("session.playing");
      }
    }
  });
});
