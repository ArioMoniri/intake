/**
 * The paired row's form rule, proved without a device.
 *
 * The defect this suite pins was seen on the simulator: on the consent screen
 * the leading label column collapsed to one or two characters while the
 * trailing pill kept its intrinsic width, so a purpose name came down the
 * screen one letter at a time. The stylesheet had no flex contract at all —
 * `flex: 1` on the labels, nothing on the pill, no minimum anywhere — so Yoga
 * was free to give the label whatever was left.
 *
 * Two things therefore have to be true, and a test that proves only the first
 * proves nothing: the row must change form when the label and the control can
 * no longer share a line, AND a row that legitimately fits must stay beside.
 * A predicate that stacked everything would satisfy 00 §2 and destroy the
 * screen, so every threshold assertion below is paired with a near-miss that
 * differs from it in exactly one variable.
 *
 * The Turkish strings are read from the catalogue rather than copied, so a
 * copy owner who lengthens a consent label or a pill state re-derives these
 * bounds instead of silently invalidating them.
 */
import { describe, expect, it } from "vitest";

import { tr } from "@/lib/i18n/tr";
import { APP_STEPS, LARGE_TEXT_SCALE } from "@/lib/prefs/appearance";
import { scaledSize } from "@/lib/theme";
import { MIN_TAP } from "./target";
import {
  BREAK_OPPORTUNITY,
  LABEL_COLUMN_FLEX,
  REFERENCE_ROW_WIDTH,
  TRAILING_SLOT_FLEX,
  labelColumnStyle,
  longestUnbreakableToken,
  minLabelWidth,
  pairedRowMetrics,
  pairedRowStacks,
  textWidth,
  trailingReserve,
} from "./pairedRow";

const text = (key: string): string => {
  const value = (tr as Record<string, string>)[key];
  expect(value, `${key} is missing from the tr catalogue`).toBeDefined();
  return value;
};

/** Every leading label a consent row carries, with its nesting. */
const CONSENT_ROWS = [
  { key: "consent.core", inset: false },
  { key: "consent.voice", inset: false },
  { key: "consent.wellbeing", inset: false },
  { key: "consent.documents", inset: false },
  { key: "consent.satisfaction", inset: false },
  { key: "consent.research", inset: false },
  { key: "consent.learning.personal", inset: false },
  { key: "consent.learning.service", inset: false },
  { key: "consent.lane.affect", inset: true },
  { key: "consent.lane.linguistic", inset: true },
] as const;

/** The four words the trailing pill can show (components/ConsentList.tsx). */
const SETTLED_PILLS = ["consent.on", "consent.off"] as const;
const LONG_PILLS = ["consent.state.stale", "consent.state.pending"] as const;

describe("glyph model", () => {
  it("breaks only where a renderer may break, and not on '.' or '@'", () => {
    expect(text("consent.lane.affect").split(BREAK_OPPORTUNITY)).toHaveLength(4);
    expect("e-Nabız".split(BREAK_OPPORTUNITY)).toEqual(["e", "Nabız"]);
    // A share recipient is one token: assuming a break at "." or "@" would
    // under-reserve, and under-reserving is what squeezes a word.
    expect(longestUnbreakableToken("ad.soyad@hastane.gov.tr")).toBe("ad.soyad@hastane.gov.tr");
  });

  it("finds the widest token, not merely the one with the most letters", () => {
    // "iyileştirme" has more characters than "Hizmeti"; it also has four
    // narrow ones, and the answer has to be in dp rather than in letters.
    expect(longestUnbreakableToken(text("consent.learning.service"))).toBe("iyileştirme");
    expect(textWidth("mm", 17)).toBeGreaterThan(textWidth("iiii", 17));
    expect(textWidth("Kapalı", 34)).toBeCloseTo(textWidth("Kapalı", 17) * 2, 6);
  });
});

describe("minimum readable width", () => {
  it("is at least the label's own longest word — a narrower column breaks it", () => {
    for (const { key } of CONSENT_ROWS) {
      const label = text(key);
      for (const step of APP_STEPS) {
        expect(minLabelWidth(label, step), `${key} @ ${step}`).toBeGreaterThanOrEqual(
          textWidth(longestUnbreakableToken(label), scaledSize("body", step)),
        );
      }
    }
  });

  it("is never zero, which is what the rows allowed", () => {
    for (const { key } of CONSENT_ROWS) {
      expect(minLabelWidth(text(key), 1.0), key).toBeGreaterThan(0);
    }
  });

  it("rises with the patient's scale — the column is never clamped back", () => {
    const label = text("consent.voice");
    for (let i = 1; i < APP_STEPS.length; i += 1) {
      expect(minLabelWidth(label, APP_STEPS[i])).toBeGreaterThan(
        minLabelWidth(label, APP_STEPS[i - 1]),
      );
    }
  });
});

describe("flex contract", () => {
  it("the trailing control never shrinks; the label may, but not past its floor", () => {
    expect(TRAILING_SLOT_FLEX.flexShrink).toBe(0);
    expect(TRAILING_SLOT_FLEX.flexGrow).toBe(0);
    expect(LABEL_COLUMN_FLEX.flexShrink).toBe(1);
    expect(LABEL_COLUMN_FLEX.flexGrow).toBe(1);
    expect(LABEL_COLUMN_FLEX.flexBasis).toBe(0);
    const style = labelColumnStyle(text("consent.voice"), 1.6);
    expect(style.minWidth).toBe(minLabelWidth(text("consent.voice"), 1.6));
    expect(style.minWidth).toBeGreaterThan(0);
  });

  it("the trailing control keeps a target at or above the floor at every scale", () => {
    // A FIXED floor, not a scaled one: a control must not follow the text down
    // through MIN_TAP for a patient who asked for smaller type.
    for (const step of APP_STEPS) {
      expect(trailingReserve(text("consent.on"), step), String(step)).toBeGreaterThanOrEqual(
        MIN_TAP,
      );
    }
    expect(trailingReserve(text("consent.on"), 0.5)).toBeGreaterThanOrEqual(MIN_TAP);
  });
});

describe("form change", () => {
  it("the reported row stops fitting at the DEFAULT text size", () => {
    // Not a large-text edge case. On the narrowest phone the app supports,
    // "Sesli görüşme" beside "Metin hazırlanıyor" — what every row shows while
    // INT-210 leaves the consent texts empty — needs more room than the row
    // has at fontScale 1.0, with no accessibility setting touched.
    const shape = {
      label: text("consent.voice"),
      trailingText: text("consent.state.pending"),
      chevron: true,
    };
    const atDefault = pairedRowMetrics(shape, 1.0);
    expect(atDefault.form).toBe("stacked");
    expect(atDefault.reason).toBe("no-room");
    expect(atDefault.required).toBeGreaterThan(atDefault.available);
  });

  it("NEAR-MISS (c): the same row, one rung smaller, is still a row", () => {
    // Only the SCALE differs from the assertion above. Without this, a rule
    // that stacked that row unconditionally would pass.
    const shape = {
      label: text("consent.voice"),
      trailingText: text("consent.state.pending"),
      chevron: true,
    };
    const smaller = pairedRowMetrics(shape, 0.9);
    expect(smaller.form).toBe("beside");
    expect(smaller.reason).toBe("fits");
    expect(smaller.required).toBeLessThanOrEqual(smaller.available);
  });

  it("NEAR-MISS (a): at one scale, only the trailing word decides it", () => {
    // Same label, same rung, same device. A predicate that ignored the
    // geometry, or that stacked on the scale alone, fails here.
    const label = text("consent.learning.service");
    const beside = pairedRowMetrics(
      { label, trailingText: text("consent.off"), chevron: true },
      1.3,
    );
    expect(beside.form).toBe("beside");
    expect(beside.reason).toBe("fits");
    const stacked = pairedRowMetrics(
      { label, trailingText: text("consent.state.pending"), chevron: true },
      1.3,
    );
    expect(stacked.form).toBe("stacked");
    expect(stacked.reason).toBe("no-room");
  });

  it("NEAR-MISS (d): at one scale and one pill, only the label decides it", () => {
    // Same pill, same rung, same chevron — a shorter purpose name still fits
    // where a longer one does not. This is what proves the floor is derived
    // per row rather than taken from a corpus-wide constant.
    const pill = text("consent.state.pending");
    expect(
      pairedRowMetrics({ label: text("consent.core"), trailingText: pill, chevron: true }, 1.0)
        .form,
    ).toBe("beside");
    expect(
      pairedRowMetrics({ label: text("consent.voice"), trailingText: pill, chevron: true }, 1.0)
        .form,
    ).toBe("stacked");
  });

  it("NEAR-MISS (b): settled consent rows stay beside at the ordinary scales", () => {
    // The way this could go vacuously right. At 0.9 and 1.0 — the two rungs
    // most patients actually read at — every row showing "Açık" or "Kapalı"
    // is a row, and stacking it would be a regression dressed as a fix.
    for (const { key, inset } of CONSENT_ROWS) {
      for (const pill of SETTLED_PILLS) {
        for (const step of [0.9, 1.0]) {
          expect(
            pairedRowStacks(
              { label: text(key), trailingText: text(pill), chevron: true, inset },
              step,
            ),
            `${key} / ${pill} @ ${step}`,
          ).toBe(false);
        }
      }
    }
  });

  it("a long pill takes every consent row out of the beside form well below the ceiling", () => {
    // "Yeniden onay gerekli" and "Metin hazırlanıyor" are ordinary states, and
    // the second is what every row shows today. Each such row must have left
    // the beside form before the app-wide ceiling, or the scale term would be
    // doing all the work and the geometry term none of it.
    for (const { key, inset } of CONSENT_ROWS) {
      for (const pill of LONG_PILLS) {
        const metrics = pairedRowMetrics(
          { label: text(key), trailingText: text(pill), chevron: true, inset },
          1.3,
        );
        expect(metrics.form, `${key} / ${pill}`).toBe("stacked");
        expect(metrics.reason, `${key} / ${pill}`).toBe("no-room");
      }
    }
  });

  it("stacks at the app-wide ceiling even where the geometry still fits", () => {
    // The scale term, isolated: this row has room at 1.6 and changes form
    // anyway, because SwitchRow and Segmented do and a settings group cannot
    // have one row that stayed behind. Delete the ceiling and this fails.
    const shape = { label: text("consent.research"), trailingText: text("consent.on") };
    expect(pairedRowMetrics(shape, 1.3).form).toBe("beside");
    const ceiling = pairedRowMetrics(shape, LARGE_TEXT_SCALE);
    expect(ceiling.required).toBeLessThanOrEqual(ceiling.available);
    expect(ceiling.form).toBe("stacked");
    expect(ceiling.reason).toBe("large-text");
  });

  it("a measured width wins over the reference device", () => {
    const shape = {
      label: text("consent.voice"),
      trailingText: text("consent.state.pending"),
    };
    expect(pairedRowMetrics(shape, 1.3, null).form).toBe("stacked");
    expect(pairedRowMetrics(shape, 1.3, 700).form).toBe("beside");
    expect(pairedRowMetrics(shape, 1.3, null).available).toBeLessThan(
      pairedRowMetrics(shape, 1.3, 700).available,
    );
  });

  it("an inset sub-row, and a row with a leading icon, both have less room", () => {
    const shape = { label: text("consent.lane.affect"), trailingText: text("consent.on") };
    const plain = pairedRowMetrics({ ...shape, inset: false }, 1.0).available;
    expect(pairedRowMetrics({ ...shape, inset: true }, 1.0).available).toBeLessThan(plain);
    // A share row really does carry an icon well AND a trailing state, so the
    // well has to come off the row before the label and the control divide it.
    expect(pairedRowMetrics({ ...shape, leading: 48 }, 1.0).available).toBe(plain - 48);
  });
});

describe("one clamp, one multiplier", () => {
  it("takes theme.ts's clamp and never adds a second one", () => {
    const shape = {
      label: text("consent.voice"),
      trailingText: text("consent.on"),
      chevron: true,
    };
    expect(pairedRowMetrics(shape, 3.0)).toEqual(pairedRowMetrics(shape, 2.0));
    expect(pairedRowMetrics(shape, 0.1)).toEqual(pairedRowMetrics(shape, 0.5));
  });

  it("the chevron scales with the words beside it", () => {
    const shape = {
      label: text("consent.voice"),
      trailingText: text("consent.on"),
      chevron: true,
    };
    expect(pairedRowMetrics(shape, 1.0).chevronSize).toBeLessThan(
      pairedRowMetrics(shape, 2.0).chevronSize,
    );
  });
});

describe("the reference device", () => {
  it("is the narrowest phone the repo already commits to", () => {
    // e2e/shares.spec.ts checks every row it adds at 320, and app.json is
    // portrait-only with supportsTablet:false and an android block. A floor
    // derived on a wider phone is not a floor.
    expect(REFERENCE_ROW_WIDTH).toBe(320);
  });
});
