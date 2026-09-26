/**
 * INT-371: the typed lane's "kendi sözlerinizle" invitation (`intake.open.hint`)
 * shows once per session, at the first open question the patient meets, and
 * not under every open question after it.
 */
import { describe, expect, it } from "vitest";

import { openHintAnchor, showsOpenHint } from "./openHint";

/** Walk a session through its steps the way StepFlow does: anchor, then render. */
function walk(steps: readonly { id: string; open: boolean }[]): string[] {
  let anchor: string | null = null;
  const shown: string[] = [];
  for (const step of steps) {
    anchor = openHintAnchor(anchor, step.id, step.open);
    if (showsOpenHint(anchor, step.id, step.open)) {
      shown.push(step.id);
    }
  }
  return shown;
}

describe("the open-question invitation, once per session", () => {
  it("shows at the first open question and at no later one", () => {
    const shown = walk([
      { id: "complaint", open: true },
      { id: "duration", open: true },
      { id: "severity", open: false },
      { id: "character", open: true },
    ]);
    expect(shown).toEqual(["complaint"]);
  });

  it("a session that starts past step one still gets it once", () => {
    // The voice→typed hand-off resumes at the first UNanswered step, which
    // can be any step; the invitation follows the patient, not step one.
    const shown = walk([
      { id: "severity", open: false },
      { id: "character", open: true },
      { id: "trigger", open: true },
    ]);
    expect(shown).toEqual(["character"]);
  });

  it("returning to the anchored question shows it again in the same place, never elsewhere", () => {
    const shown = walk([
      { id: "complaint", open: true },
      { id: "duration", open: true },
      { id: "complaint", open: true },
      { id: "duration", open: true },
    ]);
    expect(shown).toEqual(["complaint", "complaint"]);
  });

  it("a closed question never takes the anchor, and never shows the invitation", () => {
    expect(openHintAnchor(null, "severity", false)).toBeNull();
    expect(showsOpenHint(null, "severity", false)).toBe(false);
    expect(walk([{ id: "severity", open: false }])).toEqual([]);
  });

  it("the anchor, once set, is never moved by a later question", () => {
    expect(openHintAnchor("complaint", "duration", true)).toBe("complaint");
    expect(openHintAnchor("complaint", "severity", false)).toBe("complaint");
  });
});
