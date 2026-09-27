/**
 * INT-360 — WCAG 2.2 SC 1.3.4 Orientation: the two pure rules behind a layout
 * that follows the device (lib/a11y/orientation.ts).
 */
import { describe, expect, it } from "vitest";

import { ALL_ORIENTATIONS, shortSide } from "./orientation";

/** The values React Native's `<Modal supportedOrientations>` accepts (Libraries/Modal/Modal.js). */
const MODAL_ORIENTATIONS = [
  "portrait",
  "portrait-upside-down",
  "landscape",
  "landscape-left",
  "landscape-right",
];

describe("ALL_ORIENTATIONS — what a Modal must name to rotate with the app", () => {
  it("lists every orientation the app declares, both landscapes included", () => {
    // app.json's "default" writes all four into UISupportedInterfaceOrientations
    // (@expo/config-plugins ios/Orientation). A Modal that names fewer is a lock.
    expect([...ALL_ORIENTATIONS].sort()).toEqual(
      ["portrait", "portrait-upside-down", "landscape-left", "landscape-right"].sort(),
    );
  });

  it("names only values React Native's Modal accepts", () => {
    const unknown = ALL_ORIENTATIONS.filter((o) => !MODAL_ORIENTATIONS.includes(o));
    expect(unknown).toEqual([]);
  });

  it("cannot be narrowed at run time by a caller that shares it", () => {
    // Typed mutable for the Modal prop; frozen so one Modal cannot lock another.
    expect(Object.isFrozen(ALL_ORIENTATIONS)).toBe(true);
    expect(() => (ALL_ORIENTATIONS as string[]).pop()).toThrow(TypeError);
  });
});

describe("shortSide — the bound a figure may grow to in either orientation", () => {
  it("takes the shorter side, whichever way the phone is held", () => {
    // A 6.1-inch phone and the smallest iPhone, both ways round.
    expect(shortSide({ width: 390, height: 844 })).toBe(390);
    expect(shortSide({ width: 844, height: 390 })).toBe(390);
    expect(shortSide({ width: 320, height: 568 })).toBe(320);
    expect(shortSide({ width: 568, height: 320 })).toBe(320);
  });

  it("is the width in portrait, so no portrait layout changes", () => {
    // The gauge was bounded by the window width before INT-360. In portrait
    // that IS the short side, so the value a portrait patient sees is the same.
    const portrait = { width: 402, height: 874 };
    expect(shortSide(portrait)).toBe(portrait.width);
  });
});
