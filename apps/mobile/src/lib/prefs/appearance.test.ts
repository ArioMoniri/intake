/**
 * INT-260 — the appearance policy, proved without a device.
 *
 * Everything the settings screen decides lives in ./appearance as pure
 * functions, for the same reason lib/theme.ts is pure: there is no React
 * renderer in this suite (vitest runs in node and collects `.test.ts` files
 * only), so a rule that lives in a component is a rule nothing can prove.
 *
 * The load-bearing assertion is `text scales once, never twice`. The app
 * value REPLACES the OS value; it never multiplies it. Composition is what
 * `allowFontScaling={false}` exists to prevent, and with the [0.5, 2.0] clamp
 * in theme.ts it would also give a patient already at OS 2.0 a control that
 * does nothing. Both halves are asserted below against a composing
 * implementation, not merely described.
 */
import { describe, expect, it } from "vitest";

import { scaledSize } from "../theme";
import {
  APPEARANCE_SLOT,
  APP_STEPS,
  CTA_MIN_HEIGHT,
  DEFAULT_APPEARANCE,
  LARGE_TEXT_SCALE,
  decodeAppearance,
  effectiveFontScale,
  encodeAppearance,
  glassBarClearance,
  glassBarFloor,
  RAIL_LABEL_MAX_SCALE,
  isLargeText,
  nearestStep,
  railCollapses,
  reducedMotion,
  resolveScheme,
  type AppearancePrefs,
  type TextStep,
} from "./appearance";

const STEPS: readonly TextStep[] = [0, 1, 2, 3, 4];
/** OS settings a real phone can report, including both ends of the clamp. */
const OS_SCALES = [0.5, 0.85, 1.0, 1.2, 1.35, 1.6, 2.0, 3.0] as const;

describe("the five steps (R5 — discrete, not a slider)", () => {
  it("is exactly the recorded ladder", () => {
    // typeScale is seven fixed integers and scaledSize rounds (theme.ts), so a
    // continuous control would imply precision the token system does not have.
    expect([...APP_STEPS]).toEqual([0.9, 1.0, 1.3, 1.6, 2.0]);
  });

  it("spans the clamp, so the override can never shrink a 2.0 patient's text", () => {
    // The top step MUST equal the clamp ceiling: if the ladder stopped at 1.5,
    // a patient already at OS 2.0 who touched the control would lose size.
    expect(Math.max(...APP_STEPS)).toBe(2.0);
    expect(Math.min(...APP_STEPS)).toBeGreaterThanOrEqual(0.5);
  });

  it("is strictly increasing, so the control reads left to right", () => {
    for (let i = 1; i < APP_STEPS.length; i += 1) {
      expect(APP_STEPS[i]).toBeGreaterThan(APP_STEPS[i - 1]);
    }
  });

  it("every step lands on a distinct rendered body size", () => {
    // A step the eye cannot tell from its neighbour is a control that lies.
    const sizes = APP_STEPS.map((step) => scaledSize("body", step));
    expect(new Set(sizes).size).toBe(APP_STEPS.length);
  });
});

describe("text scales once, never twice (R4 — override, not composition)", () => {
  it("null follows the phone exactly", () => {
    for (const os of OS_SCALES) {
      expect(effectiveFontScale(null, os)).toBe(os);
    }
  });

  it("a chosen step REPLACES the OS value, whatever the OS value is", () => {
    for (const step of STEPS) {
      for (const os of OS_SCALES) {
        expect(effectiveFontScale(step, os)).toBe(APP_STEPS[step]);
      }
    }
  });

  it("the smallest step at OS 2.0 is 0.9 — a composing build could not produce this", () => {
    // 0.9 × 2.0 = 1.8, and clamped composition gives 1.8 too; only a REPLACING
    // implementation can return 0.9 here. This is the discriminating case.
    expect(effectiveFontScale(0, 2.0)).toBe(0.9);
    expect(effectiveFontScale(0, 3.0)).toBe(0.9);
  });

  it("the largest step is the clamp ceiling and not beyond it", () => {
    // Composition at OS 2.0 would want 4.0 and be clamped to 2.0, which LOOKS
    // right — so the test that matters is the size, at every OS setting.
    for (const os of OS_SCALES) {
      expect(scaledSize("body", effectiveFontScale(4, os))).toBe(scaledSize("body", 2.0));
    }
  });

  it("no step and OS pair can render larger than the OS maximum alone", () => {
    const ceiling = scaledSize("hero", 2.0);
    for (const step of STEPS) {
      for (const os of OS_SCALES) {
        expect(scaledSize("hero", effectiveFontScale(step, os))).toBeLessThanOrEqual(ceiling);
      }
    }
  });

  it("the control is never inert: at OS 2.0 four of the five steps still change the size", () => {
    // The failure `transcript-first` admitted to. With composition + the clamp,
    // a patient at OS 2.0 sees one size for every step.
    const sizes = APP_STEPS.map((_, index) =>
      scaledSize("body", effectiveFontScale(index as TextStep, 2.0)),
    );
    expect(new Set(sizes).size).toBe(APP_STEPS.length);
  });
});

describe("leaving the phone setting behind does not resize the screen under the finger", () => {
  it("picks the step nearest the size the patient is already reading", () => {
    // Turning "Telefon ayarını kullanın" off must not JUMP: the first app
    // value is whatever is closest to what is already on screen, so the
    // switch changes where the size comes from and not the size.
    expect(nearestStep(1.0)).toBe(1);
    expect(nearestStep(0.85)).toBe(0);
    expect(nearestStep(1.35)).toBe(2);
    expect(nearestStep(2.0)).toBe(4);
    expect(nearestStep(3.0)).toBe(4);
    expect(nearestStep(0.1)).toBe(0);
  });

  it("every ladder value maps to its own index", () => {
    for (const step of STEPS) {
      expect(nearestStep(APP_STEPS[step])).toBe(step);
    }
  });

  it("a tie resolves to the LARGER step — accessibility never rounds down", () => {
    // 1.15 is exactly between 1.0 and 1.3.
    expect(nearestStep(1.15)).toBe(2);
  });
});

describe("the large-text form change (00 §2: change FORM, never clamp text harder)", () => {
  it("the threshold is 1.6 — a step the control can actually reach", () => {
    expect(LARGE_TEXT_SCALE).toBe(1.6);
    expect(APP_STEPS).toContain(LARGE_TEXT_SCALE);
  });

  it("collapses at and above the threshold, never below", () => {
    expect(isLargeText(1.0)).toBe(false);
    expect(isLargeText(1.3)).toBe(false);
    expect(isLargeText(1.59)).toBe(false);
    expect(isLargeText(1.6)).toBe(true);
    expect(isLargeText(2.0)).toBe(true);
  });

  it("is reachable from the OS alone, not only from the app control", () => {
    // theme.ts has claimed this collapse since INT-130; the control is what
    // makes it one tap away, but an OS setting of 1.6 already gets there.
    expect(isLargeText(effectiveFontScale(null, 1.7))).toBe(true);
    expect(isLargeText(effectiveFontScale(3, 1.0))).toBe(true);
  });
});

describe("the rail's own threshold, which is lower than the content one", () => {
  it("drops the captions above 1.2, measured rather than guessed", () => {
    // theme.ts claimed 1.6 since INT-130 and nothing implemented it. Measured
    // on the simulator at 1.3: the `micro` caption renders at 14 pt, five
    // Turkish labels do not fit the pill's width, and "Profilim" was clipped
    // mid-word. The rail is the tightest horizontal box in the app and needs
    // its own number; 1.6 stays the CONTENT threshold (isLargeText).
    expect(RAIL_LABEL_MAX_SCALE).toBe(1.2);
    expect(railCollapses(1.0)).toBe(false);
    expect(railCollapses(1.2)).toBe(false);
    expect(railCollapses(1.3)).toBe(true);
    expect(railCollapses(2.0)).toBe(true);
  });

  it("collapses at or before the content threshold, never after it", () => {
    // If the rail outlived isLargeText, a screen would stack its controls
    // while the chrome under it still tried to hold five captions.
    expect(RAIL_LABEL_MAX_SCALE).toBeLessThan(LARGE_TEXT_SCALE);
    for (const step of APP_STEPS) {
      if (isLargeText(step)) {
        expect(railCollapses(step), String(step)).toBe(true);
      }
    }
  });

  it("every step above the smallest two collapses it", () => {
    expect(APP_STEPS.filter((step) => railCollapses(step))).toEqual([1.3, 1.6, 2.0]);
  });
});

/**
 * INT-284 — the same "reserved number vs rendered number" defect INT-260 fixed
 * for the tab rail, on the screens where the rail unmounts and a glass bar
 * owns the bottom edge instead.
 */
describe("the glass bar's clearance", () => {
  /**
   * iPhone 16 Pro home-indicator inset, and the bar height measured on it at
   * the largest step with a one-line CTA (docs/evidence/INT-284.md §3).
   */
  const IPHONE_16_PRO_BOTTOM = 34;
  const MEASURED_AT_2_0 = 131;

  it("the constant the tree used to carry is smaller than the bar it reserved for", () => {
    // `GLASS_BAR_CLEARANCE = 128`, chosen when a body line was 17 pt.
    const floor = glassBarFloor(2.0, IPHONE_16_PRO_BOTTOM);
    expect(floor).toBeGreaterThan(128);
    // The floor is the bar's own anatomy, not an estimate of it: padding,
    // one CTA, and the home-indicator zone the bar swallows. Within a point
    // of what the device rendered.
    expect(Math.abs(floor - MEASURED_AT_2_0)).toBeLessThanOrEqual(1);
  });

  it("a clearance never sits below the bar it clears", () => {
    for (const scale of APP_STEPS) {
      for (const inset of [0, 20, IPHONE_16_PRO_BOTTOM]) {
        expect(glassBarClearance(null, scale, inset)).toBeGreaterThan(glassBarFloor(scale, inset));
      }
    }
  });

  it("once the bar has measured itself, the measurement is what counts", () => {
    // A wrapped CTA label, a second button, the dialogue's whole
    // strip-plus-CTAs-plus-composer stack: no formula over the type scale
    // sees any of them, which is why `DIALOGUE_BAR_CLEARANCE` was
    // `GLASS_BAR_CLEARANCE + 176` — a guess with a plus sign in it.
    // "Hekiminize gönderin" wraps at 2.0 and takes the bar to about 178.
    for (const measured of [178, 420]) {
      expect(glassBarClearance(measured, 1.0, IPHONE_16_PRO_BOTTOM)).toBeGreaterThan(measured);
      expect(glassBarClearance(measured, 2.0, IPHONE_16_PRO_BOTTOM)).toBeGreaterThan(measured);
    }
  });

  it("a bar that has not laid out yet still clears the home indicator", () => {
    expect(glassBarFloor(1.0, IPHONE_16_PRO_BOTTOM)).toBeGreaterThan(IPHONE_16_PRO_BOTTOM);
  });

  it("a nonsense measurement falls back to the floor rather than to nothing", () => {
    // onLayout fires with 0 on some first passes; trusting it would put the
    // last row flush under the bar for a frame and, if it never fired
    // again, permanently.
    expect(glassBarClearance(0, 2.0, IPHONE_16_PRO_BOTTOM)).toBe(
      glassBarClearance(null, 2.0, IPHONE_16_PRO_BOTTOM),
    );
  });

  it("more text never buys less room", () => {
    for (let i = 1; i < APP_STEPS.length; i += 1) {
      expect(glassBarClearance(null, APP_STEPS[i], IPHONE_16_PRO_BOTTOM)).toBeGreaterThanOrEqual(
        glassBarClearance(null, APP_STEPS[i - 1], IPHONE_16_PRO_BOTTOM),
      );
    }
  });

  it("the CTA floor is the button's own number, not a copy of it", () => {
    // components/Themed.tsx reads this same export for `primaryButton`'s
    // minHeight — that is the whole point of it living here.
    expect(CTA_MIN_HEIGHT).toBe(56);
    expect(glassBarFloor(0.5, 0)).toBeGreaterThanOrEqual(CTA_MIN_HEIGHT);
  });
});

describe("theme override", () => {
  it("system follows the OS, and an absent OS answer reads as light", () => {
    expect(resolveScheme("system", "dark")).toBe("dark");
    expect(resolveScheme("system", "light")).toBe("light");
    expect(resolveScheme("system", null)).toBe("light");
    expect(resolveScheme("system", undefined)).toBe("light");
  });

  it("an explicit choice wins over the OS in both directions", () => {
    expect(resolveScheme("dark", "light")).toBe("dark");
    expect(resolveScheme("light", "dark")).toBe("light");
  });
});

describe("reduced motion", () => {
  it("is the OR of the OS setting and the app's own switch", () => {
    // OR, not override: a patient who set "Hareketi Azalt" in iOS must not
    // have it silently undone by an app default.
    expect(reducedMotion(false, false)).toBe(false);
    expect(reducedMotion(true, false)).toBe(true);
    expect(reducedMotion(false, true)).toBe(true);
    expect(reducedMotion(true, true)).toBe(true);
  });
});

describe("the stored shape", () => {
  it("defaults follow the device in every axis it can follow", () => {
    expect(DEFAULT_APPEARANCE).toEqual({
      textStep: null,
      theme: "system",
      reduceMotion: false,
      startMode: "voice",
    });
  });

  it("the slot is versioned, so a shape change never reads an old record", () => {
    expect(APPEARANCE_SLOT).toMatch(/\.v\d+$/);
  });

  it("round-trips every reachable combination", () => {
    for (const textStep of [null, ...STEPS]) {
      for (const theme of ["system", "light", "dark"] as const) {
        for (const reduceMotion of [false, true]) {
          for (const startMode of ["voice", "typed"] as const) {
            const prefs: AppearancePrefs = { textStep, theme, reduceMotion, startMode };
            expect(decodeAppearance(encodeAppearance(prefs))).toEqual(prefs);
          }
        }
      }
    }
  });

  it("an absent, unreadable or foreign record reads as the defaults", () => {
    // A device-local record is the ONLY copy; it must never be able to put the
    // app into a state the screen cannot show or the patient cannot undo.
    for (const raw of [null, "", "{", "[]", '"x"', "null", "3", '{"textStep":"big"}']) {
      expect(decodeAppearance(raw)).toEqual(DEFAULT_APPEARANCE);
    }
  });

  it("a step outside the ladder is refused rather than clamped", () => {
    // Clamping would silently move a patient to a size they did not choose.
    for (const bad of [-1, 5, 1.5, Number.NaN]) {
      expect(decodeAppearance(JSON.stringify({ ...DEFAULT_APPEARANCE, textStep: bad }))).toEqual(
        DEFAULT_APPEARANCE,
      );
    }
  });

  it("a partial record keeps the fields it does carry", () => {
    expect(decodeAppearance('{"textStep":3}')).toEqual({ ...DEFAULT_APPEARANCE, textStep: 3 });
    expect(decodeAppearance('{"theme":"dark"}')).toEqual({ ...DEFAULT_APPEARANCE, theme: "dark" });
    expect(decodeAppearance('{"reduceMotion":true}')).toEqual({
      ...DEFAULT_APPEARANCE,
      reduceMotion: true,
    });
    expect(decodeAppearance('{"startMode":"typed"}')).toEqual({
      ...DEFAULT_APPEARANCE,
      startMode: "typed",
    });
  });

  it("an unknown enum value falls back rather than reaching a screen", () => {
    expect(decodeAppearance('{"theme":"sepia"}')).toEqual(DEFAULT_APPEARANCE);
    expect(decodeAppearance('{"startMode":"telepathy"}')).toEqual(DEFAULT_APPEARANCE);
  });

  it("the encoded record carries preferences and nothing else", () => {
    // Invariant 6 / the inventory annotation: {category: device preference,
    // purpose: accessibility, basis: contract, retention: until uninstall or
    // reset, recipients: none}. No id, no visit, no clinical value — so this
    // asserts the exact key set rather than the absence of a list of names.
    const encoded: unknown = JSON.parse(encodeAppearance(DEFAULT_APPEARANCE));
    expect(Object.keys(encoded as object).sort()).toEqual(
      ["reduceMotion", "startMode", "textStep", "theme"].sort(),
    );
  });
});
