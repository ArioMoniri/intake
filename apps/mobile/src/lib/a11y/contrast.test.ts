/**
 * Which palette the OS contrast request selects (INT-422,
 * docs/design/system-refresh.md §3).
 *
 * - `high`: the OS asked for more contrast (iOS Increase Contrast, Android
 *   High contrast text).
 * - `standard`: it did not, or it has not answered yet.
 *
 * Unknown is `standard`, the opposite direction from the glass policy's
 * unknown-is-solid, and for a measured reason: both palettes clear every
 * floor theme.test.ts holds (AA everywhere, AAA for clinical text, 3:1 for
 * boundaries), so the standard palette is never below the floor while the OS
 * is still answering, and an unknown-is-high rule would repaint every
 * patient's first frame.
 */
import { describe, expect, it } from "vitest";

import { contrastMode } from "./contrast";

describe("contrastMode", () => {
  it("the OS asking for more contrast selects the high-contrast palette", () => {
    expect(contrastMode(true)).toBe("high");
  });

  it("the OS not asking selects the standard palette", () => {
    expect(contrastMode(false)).toBe("standard");
  });

  it("an OS that has not answered yet selects the standard palette, which meets every floor", () => {
    expect(contrastMode(null)).toBe("standard");
  });
});
