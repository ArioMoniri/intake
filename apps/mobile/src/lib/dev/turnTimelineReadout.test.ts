/**
 * INT-497 — the dev-only readout of the turn timeline.
 *
 * It is how the device session after the hosted lanes deploy produces the
 * "after" table in docs/evidence/INT-497.md: an engineer reads the numbers off
 * the screen. Like voiceDiagnostic.ts, the `__DEV__` gate lives in a pure
 * function, so production is "the line never exists", not "styled away".
 */
import { describe, expect, it } from "vitest";

import { t } from "@/lib/i18n";

import type { TimelineSummary } from "../dialogue/turnTimeline";
import { turnTimelineReadout } from "./turnTimelineReadout";

const SUMMARY: TimelineSummary = {
  turns: 6,
  tappedTurns: 1,
  firstAudioP50Ms: 612.4,
  firstAudioP95Ms: 1033,
  endpointP50Ms: 470,
  joinMaxMs: 3.2,
  joinP95Ms: 2,
  asrP50Ms: 640,
  asrP95Ms: 910,
};

describe("turnTimelineReadout", () => {
  it("renders nothing in production, whatever was measured", () => {
    expect(turnTimelineReadout(SUMMARY, false)).toBeNull();
  });

  it("renders nothing before the first turn — no line of dashes on a fresh session", () => {
    expect(turnTimelineReadout({ ...SUMMARY, turns: 0 }, true)).toBeNull();
  });

  it("names each figure from the catalogue and rounds to whole milliseconds", () => {
    const lines = turnTimelineReadout(SUMMARY, true)!;
    expect(lines[0]).toBe(t("devVoice.timeline.title"));
    expect(lines[1]).toContain(t("devVoice.timeline.firstAudio"));
    expect(lines[1]).toContain("612 ms");
    expect(lines[1]).toContain("1033 ms");
    expect(lines[2]).toContain(t("devVoice.timeline.join"));
    expect(lines[2]).toContain("3 ms");
    expect(lines[3]).toContain(t("devVoice.timeline.asr"));
    expect(lines[3]).toContain("640 ms");
  });

  it("never groups digits and never splits a number from its unit", () => {
    const lines = turnTimelineReadout({ ...SUMMARY, firstAudioP95Ms: 12_345 }, true)!;
    expect(lines[1]).toContain("12345 ms");
  });

  it("shows an absent measurement as absent, never as zero", () => {
    const lines = turnTimelineReadout(
      { ...SUMMARY, firstAudioP50Ms: null, firstAudioP95Ms: null, joinMaxMs: null, asrP50Ms: null },
      true,
    )!;
    expect(lines.join(" ")).not.toMatch(/\b0 ms/);
    expect(lines[1]).toContain("—");
  });
});
