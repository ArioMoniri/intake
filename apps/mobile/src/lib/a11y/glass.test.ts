/**
 * Which material a glass surface renders (docs/design/apple-native/spec.md
 * §0 rule 2, §1.1).
 *
 * Three modes, decided in one place:
 * - `liquid`: the system's Liquid Glass (iOS 26 and later);
 * - `blur`: BlurView under the tint wash (Android, iOS below 26, web);
 * - `solid`: the surface token, when the patient asked the OS for less
 *   transparency, or when the OS has not answered yet.
 *
 * `isLiquidGlassAvailable()` stays true under Reduce Transparency (its own
 * doc comment says so), so availability alone cannot decide. The unknown case
 * fails closed to solid, as reduce motion fails closed to reduced (INT-331):
 * the surface a patient who needs contrast can read is the one shown first.
 *
 * INT-477 (ADR-039 amendment; owner, 4 Oct 2026: "solid"): capture protection
 * outranks both. A capture-protected screen draws solid chrome whatever the OS
 * offers, because Liquid Glass was unreliable there and the cause is unknown.
 */
import { describe, expect, it } from "vitest";

import { glassMode, navBarChrome, type GlassMode } from "./glass";

describe("glassMode", () => {
  const table: [liquidGlass: boolean, reduceTransparency: boolean | null, mode: GlassMode][] = [
    [true, false, "liquid"],
    [false, false, "blur"],
    [true, true, "solid"],
    [false, true, "solid"],
    // The OS has not answered, or refused to: solid, never a guess at glass.
    [true, null, "solid"],
    [false, null, "solid"],
  ];

  it.each(table)(
    "liquid glass available %s, reduce transparency %s → %s",
    (liquidGlass, reduceTransparency, mode) => {
      expect(glassMode({ liquidGlass, reduceTransparency, captureProtected: false })).toBe(mode);
    },
  );

  it("Reduce Transparency outranks availability: system glass is never forced on", () => {
    // The near miss: a policy that asked only "is Liquid Glass available?"
    // would answer liquid here, and the patient who turned transparency down
    // would still get a see-through rail.
    expect(
      glassMode({ liquidGlass: true, reduceTransparency: true, captureProtected: false }),
    ).not.toBe("liquid");
  });

  it.each(table)(
    "capture protection (INT-477): available %s, reduce transparency %s → solid, whatever the OS says",
    (liquidGlass, reduceTransparency) => {
      expect(glassMode({ liquidGlass, reduceTransparency, captureProtected: true })).toBe("solid");
    },
  );

  it("near miss: the same inputs without capture protection still give Liquid Glass", () => {
    // The OS offers glass and the patient allows transparency: only the
    // protection turns it off, so a policy that ignored it would draw glass.
    const offered = { liquidGlass: true, reduceTransparency: false } as const;
    expect(glassMode({ ...offered, captureProtected: false })).toBe("liquid");
    expect(glassMode({ ...offered, captureProtected: true })).toBe("solid");
  });

  it("near miss: capture protection is no blur either, on an OS without Liquid Glass", () => {
    const offered = { liquidGlass: false, reduceTransparency: false } as const;
    expect(glassMode({ ...offered, captureProtected: false })).toBe("blur");
    expect(glassMode({ ...offered, captureProtected: true })).toBe("solid");
  });

  it("the three modes are the whole vocabulary", () => {
    const seen = new Set(table.map(([, , mode]) => mode));
    expect([...seen].sort()).toEqual(["blur", "liquid", "solid"]);
  });
});

/**
 * The navigation bar over a scrolling screen (INT-451 follow-up, captured on
 * the INT451-16e simulator, iOS 26.1). A full-bar `GlassView` let the content
 * that scrolls under the bar draw straight through it: the card's title and
 * date sat on top of the back chevron and the bar title. A clear bar asking
 * UIKit for its scroll-edge effect did the same in Expo Go, because the effect
 * did not attach to the screen's scroller. The bar's own system chrome
 * material frosted the content in both schemes, so iOS 26 takes that.
 */
describe("navBarChrome: the bar over a scroller always separates from it", () => {
  it("iOS 26 (liquid): the system chrome material, drawn by UIKit", () => {
    expect(navBarChrome("liquid")).toEqual({ background: "systemMaterial" });
  });

  it("blur (iOS below 26, Android): the app's blur and wash", () => {
    expect(navBarChrome("blur")).toEqual({ background: "blur" });
  });

  it("solid (Reduce Transparency, or no answer yet): the page ground, nothing see-through", () => {
    expect(navBarChrome("solid")).toEqual({ background: "solid" });
  });

  it("near miss: no mode leaves the bar clear or paints Liquid Glass across it", () => {
    const backgrounds = (["liquid", "blur", "solid"] as const).map(
      (m) => navBarChrome(m).background,
    );
    expect(backgrounds).not.toContain("none");
    expect(backgrounds).not.toContain("glass");
  });
});
