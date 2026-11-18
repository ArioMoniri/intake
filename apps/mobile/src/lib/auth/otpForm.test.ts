/**
 * INT-601 (design audit A6): the SMS-code boxes.
 *
 * Measured on main: six fixed 48 pt boxes in a row that cannot wrap. In a
 * 320 pt window the first box was drawn from x = -4 and the last ended at 324;
 * at text step 2.0 the digit was 48 pt inside a 48 pt box; and the countdown
 * read "kalan süre: 58" with no unit.
 */
import { describe, expect, it } from "vitest";

import { NBSP } from "../health/format";
import { t } from "../i18n";
import { APP_STEPS, LARGE_TEXT_SCALE } from "../prefs/appearance";
import { scaledControl, scaledSize, spacing } from "../theme";
import {
  OTP_BOX,
  OTP_NARROWEST_WINDOW,
  otpAvailableWidth,
  otpLayout,
  resendWaitLine,
} from "./otpForm";
import { OTP_LENGTH } from "./phone";

/** Android at the "Large" display size (360 dp scaled) and the iPhone SE class. */
const WINDOWS = [320, 360, 375, 390, 402, 430] as const;

/** Width the six boxes take in rows of `perRow`, gaps included. */
function rowWidth(layout: ReturnType<typeof otpLayout>): number {
  return layout.perRow * layout.box + (layout.perRow - 1) * layout.gap;
}

describe("otpAvailableWidth — the card's inner width in a window", () => {
  it("takes the screen gutter, the card border and the card padding off both sides", () => {
    expect(otpAvailableWidth(320, 1.0)).toBe(320 - 2 * spacing.screen - 2 - 2 * spacing.lg);
  });

  it("the stand-in before measurement is the narrowest window, so the first frame fits", () => {
    expect(OTP_NARROWEST_WINDOW).toBe(Math.min(...WINDOWS));
  });

  it("uses the tight card padding at the large-text scale, as Card does", () => {
    expect(otpAvailableWidth(320, LARGE_TEXT_SCALE)).toBe(
      320 - 2 * spacing.screen - 2 - 2 * spacing.md,
    );
  });
});

describe("otpLayout — the boxes fit, scale and change form", () => {
  it("fits every window from 320 pt up, at every step the app offers", () => {
    for (const window of WINDOWS) {
      for (const step of APP_STEPS) {
        const available = otpAvailableWidth(window, step);
        const layout = otpLayout(available, step);
        expect(rowWidth(layout), `${window}pt @${step}`).toBeLessThanOrEqual(available);
        expect(layout.perRow * Math.ceil(OTP_LENGTH / layout.perRow)).toBe(OTP_LENGTH);
      }
    }
  });

  it("the regression: a 320 pt window no longer gets six 48 pt boxes", () => {
    const available = otpAvailableWidth(320, 1.0);
    // The old row: 6 × 48 + 5 × 8 = 328, wider than the whole window.
    expect(6 * 48 + 5 * spacing.sm).toBeGreaterThan(available);
    expect(rowWidth(otpLayout(available, 1.0))).toBeLessThanOrEqual(available);
  });

  it("keeps one row of six where six boxes of the minimum width fit", () => {
    const layout = otpLayout(otpAvailableWidth(390, 1.0), 1.0);
    expect(layout.perRow).toBe(6);
    expect(layout.box).toBeGreaterThanOrEqual(OTP_BOX.min);
    expect(layout.box).toBeLessThanOrEqual(OTP_BOX.max);
  });

  it("near miss: drops to two rows of three where six would be narrower than the minimum", () => {
    const layout = otpLayout(otpAvailableWidth(320, 1.0), 1.0);
    expect(layout.perRow).toBe(3);
    expect(layout.box).toBeGreaterThanOrEqual(OTP_BOX.min);
  });

  it("changes form at LARGE_TEXT_SCALE, as the rail and the segmented control do", () => {
    const wide = otpAvailableWidth(430, LARGE_TEXT_SCALE);
    expect(otpLayout(wide, LARGE_TEXT_SCALE).perRow).toBe(3);
    expect(otpLayout(otpAvailableWidth(430, 1.0), 1.0).perRow).toBe(6);
  });

  it("scales with Dynamic Type: the digit, the box height and the box grow together", () => {
    const at = (step: number) => otpLayout(otpAvailableWidth(390, step), step);
    expect(at(2.0).fontSize).toBe(scaledSize("title", 2.0));
    expect(at(2.0).height).toBe(scaledControl(OTP_BOX.height, 2.0));
    expect(at(2.0).height).toBeGreaterThan(at(1.0).height);
    for (const step of APP_STEPS) {
      const layout = at(step);
      // The digit never fills its box: there is room above and beside it.
      expect(layout.box, `@${step}`).toBeGreaterThan(layout.fontSize);
      expect(layout.height, `@${step}`).toBeGreaterThan(layout.fontSize);
    }
  });
});

describe("resendWaitLine — the countdown carries its unit", () => {
  it("names the unit after the number, as one non-breaking atom", () => {
    expect(resendWaitLine(58, "tr")).toBe(
      `${t("auth.otp.resendWait", "tr")} 58${NBSP}${t("auth.otp.resendUnit", "tr")}`,
    );
    expect(t("auth.otp.resendUnit", "tr")).toBe("saniye");
    expect(t("auth.otp.resendUnit", "en")).toBe("seconds");
  });

  it("near miss: the bare numeral build 7 showed is not what renders", () => {
    expect(resendWaitLine(58, "tr")).not.toMatch(/58$/);
    expect(resendWaitLine(58, "en")).toMatch(/58 seconds$/);
  });

  it("uses no digit grouping, whatever the number", () => {
    expect(resendWaitLine(1200, "tr")).toContain(`1200${NBSP}`);
  });
});
