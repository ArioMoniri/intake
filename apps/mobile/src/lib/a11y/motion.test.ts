import { describe, expect, it } from "vitest";

import {
  loopingDecorationEnabled,
  modalAnimation,
  motionMs,
  screenAnimation,
  scrollAnimated,
} from "./motion";

describe("reduce-motion policy", () => {
  it("screen transitions fade normally and vanish under reduce-motion", () => {
    expect(screenAnimation(false)).toBe("fade");
    expect(screenAnimation(true)).toBe("none");
  });

  it("durations collapse to zero, not to a shorter movement", () => {
    expect(motionMs(false, 120)).toBe(120);
    expect(motionMs(true, 120)).toBe(0);
  });

  it("never returns a negative duration", () => {
    expect(motionMs(false, -5)).toBe(0);
  });

  it("stops looping decoration — SC 2.2.2, the listening pulse", () => {
    expect(loopingDecorationEnabled(false)).toBe(true);
    expect(loopingDecorationEnabled(true)).toBe(false);
  });

  it("makes programmatic scrolling instantaneous", () => {
    expect(scrollAnimated(false)).toBe(true);
    expect(scrollAnimated(true)).toBe(false);
  });

  it("presents modals without a transition", () => {
    expect(modalAnimation(false)).toBe("fade");
    expect(modalAnimation(true)).toBe("none");
  });
});
