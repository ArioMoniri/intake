/**
 * INT-491: three alternative bodies for the stage orb, behind a flag.
 *
 * The owner asked to explore the orb (4 Oct 2026). The variants are a fluid
 * blob, a particle field and a refined glass lens. Each one draws the same
 * state from `orbStateFor`, through the same ADR-039 S1 policy, so every
 * bound the sphere keeps, each variant keeps too:
 *
 * - breathing at most 1.06x, a voice swell of at most +10 % (listening only);
 * - no breath under 1.2 s and no full turn under 3 s;
 * - still under Reduce Motion and while a RED is presented;
 * - nothing drawn past the orb's own circle before the breath.
 *
 * The flag is off by default: an unset, empty or unknown value is the
 * ADR-039 sphere, drawn exactly as before.
 */
import { describe, expect, it } from "vitest";

import { ORB_STATES } from "@/lib/motion/orb";

import { STAGE_ORB_BOUNDS, stageOrbMotion, type StageOrbMotion } from "./orb";
import {
  DRAWN_VARIANTS,
  ORB_VARIANTS,
  ORB_VARIANT_OFF,
  VARIANT_EXTENT,
  VARIANT_LIMITS,
  bodyExtent,
  fieldDots,
  orbVariantFrom,
  orbVariantPlan,
  planTurns,
  type VariantPlan,
} from "./orbVariants";

const LIVE = { reduce: false, redPresented: false } as const;
const MOVING = ["speaking", "listening", "thinking"] as const;
const SURFACES = [{ glass: true }, { glass: false }] as const;

/** Every plan: each drawn variant, in every state, on both surfaces. */
function everyPlan(context: { reduce: boolean; redPresented: boolean }) {
  return DRAWN_VARIANTS.flatMap((variant) =>
    ORB_STATES.flatMap((state) =>
      SURFACES.map((surface) => ({
        variant,
        state,
        surface,
        plan: orbVariantPlan(variant, stageOrbMotion(state, context), surface),
      })),
    ),
  );
}

/** Does anything in the plan move? */
function moves(plan: VariantPlan): boolean {
  return (
    planTurns(plan).length > 0 ||
    plan.breathe !== null ||
    plan.levelGain > 0 ||
    (plan.body.kind === "blob" && plan.body.lobes.some((lobe) => lobe.pulse !== null))
  );
}

describe("the flag: off unless a known variant is named", () => {
  it("the variants are the sphere and the three new bodies", () => {
    expect(ORB_VARIANTS).toEqual(["classic", "blob", "field", "lens"]);
    expect(DRAWN_VARIANTS).toEqual(["blob", "field", "lens"]);
    expect(ORB_VARIANT_OFF).toBe("classic");
  });

  it("unset, empty, off, unknown or not a string is the ADR-039 sphere", () => {
    for (const raw of [undefined, null, "", "  ", "off", "classic", "orb", "blobby", 1, true, {}]) {
      expect(orbVariantFrom(raw), String(raw)).toBe(ORB_VARIANT_OFF);
    }
  });

  it("a known name selects its variant, whatever its case or spacing", () => {
    expect(orbVariantFrom("blob")).toBe("blob");
    expect(orbVariantFrom(" Field ")).toBe("field");
    expect(orbVariantFrom("LENS")).toBe("lens");
  });
});

describe("ADR-039 S1 bounds hold for every variant", () => {
  it("the bounds are the ADR's own, not a copy", () => {
    expect(VARIANT_LIMITS.maxBreatheScale).toBe(STAGE_ORB_BOUNDS.maxBreatheScale);
    expect(VARIANT_LIMITS.maxLevelGain).toBe(STAGE_ORB_BOUNDS.maxLevelGain);
    expect(VARIANT_LIMITS.minBreathePeriodS).toBe(STAGE_ORB_BOUNDS.minBreathePeriodS);
    expect(VARIANT_LIMITS.minTurnPeriodS).toBe(STAGE_ORB_BOUNDS.minTurnPeriodS);
    expect(VARIANT_LIMITS.maxBreatheScale).toBeLessThanOrEqual(1.06);
    expect(VARIANT_LIMITS.maxLevelGain).toBeLessThanOrEqual(0.1);
  });

  it("breath at most 1.06x, swell at most +10 %, periods no shorter than the ADR's", () => {
    for (const { variant, state, plan } of everyPlan(LIVE)) {
      const at = `${variant}/${state}`;
      if (plan.breathe !== null) {
        expect(plan.breathe.scale, at).toBeLessThanOrEqual(1.06);
        expect(plan.breathe.scale, at).toBeGreaterThan(1);
        expect(plan.breathe.periodS, at).toBeGreaterThanOrEqual(1.2);
      }
      expect(plan.levelGain, at).toBeLessThanOrEqual(0.1);
      for (const turn of planTurns(plan)) {
        expect(turn.periodS, at).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("no two turning parts repeat their pattern near 0.2 Hz: they turn one way and drift slowly", () => {
    // Two parts turning against each other repeat at the sum of their
    // rates: the sphere's 10 s and 16 s layers would do so every 6.2 s
    // (0.16 Hz). Turning one way they repeat at the difference.
    const BEAT_CEILING_HZ = 0.15;
    for (const { variant, state, plan } of everyPlan(LIVE)) {
      const rates = planTurns(plan).map((turn) => 1 / turn.periodS);
      for (const [i, a] of rates.entries()) {
        for (const b of rates.slice(i + 1)) {
          expect(Math.abs(a - b), `${variant}/${state}`).toBeLessThan(BEAT_CEILING_HZ);
        }
      }
    }
    // Near miss: the sphere's layers, turned against each other while
    // listening, would sit inside Apple's band.
    expect(1 / 10 + 1 / 16).toBeGreaterThan(BEAT_CEILING_HZ);
  });

  it("nothing is drawn past the orb's own circle, so the breath is the only growth", () => {
    expect(VARIANT_EXTENT).toBe(0.5);
    for (const { variant, state, plan } of everyPlan(LIVE)) {
      const extent = bodyExtent(plan.body);
      expect(extent, `${variant}/${state}`).toBeLessThanOrEqual(VARIANT_EXTENT);
      // The whole drawing, at the top of a breath and the loudest voice, is
      // never more than the ADR allows the sphere: 1.06 x 1.10 of its circle.
      const breath = plan.breathe?.scale ?? 1;
      const top = (extent / VARIANT_EXTENT) * breath * (1 + plan.levelGain);
      expect(top, `${variant}/${state}`).toBeLessThanOrEqual(
        STAGE_ORB_BOUNDS.maxBreatheScale * (1 + STAGE_ORB_BOUNDS.maxLevelGain),
      );
    }
  });

  it("a blob lobe's pulse stays inside the circle too", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      if (plan.body.kind !== "blob") continue;
      for (const lobe of plan.body.lobes) {
        expect(lobe.offset + lobe.radius, state).toBeLessThanOrEqual(VARIANT_EXTENT);
        if (lobe.pulse !== null) {
          expect(lobe.pulse + lobe.radius, state).toBeLessThanOrEqual(VARIANT_EXTENT);
        }
      }
    }
  });

  it("every particle sits inside the circle, and the field stays small enough to draw", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      if (plan.body.kind !== "field") continue;
      let count = 0;
      for (const orbit of plan.body.orbits) {
        for (const dot of fieldDots(orbit)) {
          count += 1;
          expect(Math.hypot(dot.x, dot.y) + dot.radius, state).toBeLessThanOrEqual(VARIANT_EXTENT);
          expect(dot.light, state).toBeGreaterThan(0);
          expect(dot.light, state).toBeLessThanOrEqual(1);
        }
      }
      expect(count, state).toBeLessThanOrEqual(VARIANT_LIMITS.maxDots);
      expect(count, state).toBeGreaterThan(0);
    }
  });
});

describe("each variant maps listening, speaking and thinking to motion", () => {
  it("only speaking, listening and thinking move; idle, rest and retry are still", () => {
    for (const { variant, state, plan } of everyPlan(LIVE)) {
      expect(moves(plan), `${variant}/${state}`).toBe(
        (MOVING as readonly string[]).includes(state),
      );
    }
  });

  it("only listening follows the voice level", () => {
    for (const { variant, state, plan } of everyPlan(LIVE)) {
      expect(plan.levelGain > 0, `${variant}/${state}`).toBe(state === "listening");
    }
  });

  it("thinking turns fastest and speaking breathes fastest, as the sphere does", () => {
    for (const variant of DRAWN_VARIANTS) {
      const plan = (state: (typeof MOVING)[number]) =>
        orbVariantPlan(variant, stageOrbMotion(state, LIVE), { glass: true });
      const fastest = (p: VariantPlan) => Math.min(...planTurns(p).map((t) => t.periodS));
      expect(fastest(plan("thinking")), variant).toBeLessThan(fastest(plan("speaking")));
      expect(fastest(plan("speaking")), variant).toBeLessThan(fastest(plan("listening")));
      expect(plan("speaking").breathe!.periodS, variant).toBeLessThan(
        plan("listening").breathe!.periodS,
      );
      expect(plan("thinking").breathe, variant).toBeNull();
    }
  });

  it("the speaking blob's lobes pulse with the breath; still lobes do not", () => {
    const speaking = orbVariantPlan("blob", stageOrbMotion("speaking", LIVE), { glass: true });
    expect(speaking.body.kind).toBe("blob");
    if (speaking.body.kind === "blob") {
      expect(speaking.body.lobes.every((lobe) => lobe.pulse !== null)).toBe(true);
    }
    const thinking = orbVariantPlan("blob", stageOrbMotion("thinking", LIVE), { glass: true });
    if (thinking.body.kind === "blob") {
      expect(thinking.body.lobes.every((lobe) => lobe.pulse === null)).toBe(true);
    }
  });

  it("the glow follows the state as the sphere's does", () => {
    for (const { variant, state, plan } of everyPlan(LIVE)) {
      expect(plan.glowOpacity, `${variant}/${state}`).toBe(stageOrbMotion(state, LIVE).glowOpacity);
    }
  });
});

describe("Reduce Motion and RED make every variant still", () => {
  it("Reduce Motion: no turn, no breath, no pulse, no voice level, in every variant and state", () => {
    for (const { variant, state, plan } of everyPlan({ ...LIVE, reduce: true })) {
      expect(moves(plan), `${variant}/${state}`).toBe(false);
      expect(plan.visible, `${variant}/${state}`).toBe(state !== "hidden");
    }
  });

  it("RED: no turn, no breath, no pulse, no voice level, at any setting", () => {
    for (const reduce of [false, true]) {
      for (const { variant, state, plan } of everyPlan({ reduce, redPresented: true })) {
        expect(moves(plan), `${variant}/${state}`).toBe(false);
      }
    }
  });

  it("a plan built from a still motion is still whatever the variant", () => {
    const still: StageOrbMotion = {
      visible: true,
      rotationPeriodS: null,
      breathe: null,
      levelGain: 0,
      glowOpacity: 0.5,
    };
    for (const variant of DRAWN_VARIANTS) {
      expect(moves(orbVariantPlan(variant, still, { glass: true })), variant).toBe(false);
    }
  });

  it("near miss: with the flag on and no RED, the listening variant does move", () => {
    for (const variant of DRAWN_VARIANTS) {
      const plan = orbVariantPlan(variant, stageOrbMotion("listening", LIVE), { glass: true });
      expect(moves(plan), variant).toBe(true);
      expect(planTurns(plan).length, variant).toBeGreaterThan(0);
      expect(plan.breathe, variant).not.toBeNull();
      expect(plan.levelGain, variant).toBeGreaterThan(0);
    }
  });

  it("hidden draws nothing", () => {
    for (const variant of DRAWN_VARIANTS) {
      expect(orbVariantPlan(variant, stageOrbMotion("hidden", LIVE), { glass: true }).visible).toBe(
        false,
      );
    }
  });
});

describe("glass: the lens variant's clear lens only, and never on a solid surface", () => {
  it("only the lens variant draws the clear lens, and only where glass is drawn at all", () => {
    for (const { variant, state, surface, plan } of everyPlan(LIVE)) {
      expect(plan.lens, `${variant}/${state}/${surface.glass}`).toBe(
        variant === "lens" && surface.glass,
      );
    }
  });

  it("a solid surface (Reduce Transparency, a capture-protected screen) draws no glass in any variant", () => {
    for (const { variant, state, plan } of everyPlan(LIVE)) {
      const solid = orbVariantPlan(variant, stageOrbMotion(state, LIVE), { glass: false });
      expect(solid.lens, `${variant}/${state}`).toBe(false);
      expect(plan.body.kind, variant).toBe(solid.body.kind);
    }
  });
});
