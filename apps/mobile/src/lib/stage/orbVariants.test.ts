/**
 * INT-491: the stage orb's body (ADR-039 amendment, owner 16 Oct 2026:
 * "orb=lens").
 *
 * The owner chose the refined glass lens as the orb. It draws the state from
 * `orbStateFor` through the same ADR-039 S1 policy, so every bound the sphere
 * kept, the lens keeps too:
 *
 * - breathing at most 1.06x, a voice swell of at most +10 % (listening only);
 * - no breath under 1.2 s and no full turn under 3 s;
 * - still under Reduce Motion and while a RED is presented;
 * - its two rim lights turn one way, so their pattern never repeats in the
 *   band S1 cites from Apple.
 *
 * The flag stays for development only: unset, empty or unknown is the lens;
 * `classic` names the earlier sphere. The blob and the particle field the
 * exploration also built are not shipped (the owner said no), and no runtime
 * code is left for them.
 */
import { describe, expect, it } from "vitest";

import { ORB_STATES } from "@/lib/motion/orb";

import { OSCILLATION_BAND_HZ, STAGE_ORB_BOUNDS, stageOrbMotion, type StageOrbMotion } from "./orb";
import {
  ORB_VARIANTS,
  ORB_VARIANT_DEFAULT,
  lensPlan,
  lensTurns,
  orbVariantFrom,
  type LensPlan,
} from "./orbVariants";

const LIVE = { reduce: false, redPresented: false } as const;
const MOVING = ["speaking", "listening", "thinking"] as const;
const SURFACES = [{ glass: true }, { glass: false }] as const;

/** Every lens plan: in every state, on both surfaces. */
function everyPlan(context: { reduce: boolean; redPresented: boolean }) {
  return ORB_STATES.flatMap((state) =>
    SURFACES.map((surface) => ({
      state,
      surface,
      plan: lensPlan(stageOrbMotion(state, context), surface),
    })),
  );
}

/** Does anything in the plan move? */
function moves(plan: LensPlan): boolean {
  return lensTurns(plan).length > 0 || plan.breathe !== null || plan.levelGain > 0;
}

describe("the orb is the lens; the flag only names the earlier sphere", () => {
  it("the bodies are the lens and the sphere; the blob and the field are gone", () => {
    expect(ORB_VARIANTS).toEqual(["lens", "classic"]);
    expect(ORB_VARIANT_DEFAULT).toBe("lens");
  });

  it("unset, empty, unknown or not a string is the lens", () => {
    for (const raw of [undefined, null, "", "  ", "off", "orb", "blob", "field", 1, true, {}]) {
      expect(orbVariantFrom(raw), String(raw)).toBe("lens");
    }
  });

  it("only the name `classic`, in any case or spacing, draws the sphere", () => {
    expect(orbVariantFrom("classic")).toBe("classic");
    expect(orbVariantFrom(" Classic ")).toBe("classic");
    expect(orbVariantFrom("LENS")).toBe("lens");
  });
});

describe("ADR-039 S1 bounds hold for the lens", () => {
  it("breath at most 1.06x, swell at most +10 %, periods no shorter than the ADR's", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      if (plan.breathe !== null) {
        expect(plan.breathe.scale, state).toBeLessThanOrEqual(STAGE_ORB_BOUNDS.maxBreatheScale);
        expect(plan.breathe.scale, state).toBeLessThanOrEqual(1.06);
        expect(plan.breathe.periodS, state).toBeGreaterThanOrEqual(1.2);
      }
      expect(plan.levelGain, state).toBeLessThanOrEqual(STAGE_ORB_BOUNDS.maxLevelGain);
      expect(plan.levelGain, state).toBeLessThanOrEqual(0.1);
      for (const turn of lensTurns(plan)) {
        expect(turn.periodS, state).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("the rim lights turn one way, and their pattern repeats below the band", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      const rates = lensTurns(plan).map((turn) => 1 / turn.periodS);
      for (const [i, a] of rates.entries()) {
        for (const b of rates.slice(i + 1)) {
          expect(Math.abs(a - b), state).toBeLessThan(OSCILLATION_BAND_HZ.low);
        }
      }
    }
  });

  it("the crisp edge is a hairline, a small fraction of the orb's size", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      expect(plan.rim, state).toBeGreaterThan(0);
      expect(plan.rim, state).toBeLessThan(0.05);
    }
  });
});

describe("the lens maps listening, speaking and thinking to motion", () => {
  it("only speaking, listening and thinking move; idle, rest and retry are still", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      expect(moves(plan), state).toBe((MOVING as readonly string[]).includes(state));
    }
  });

  it("only listening follows the voice level", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      expect(plan.levelGain > 0, state).toBe(state === "listening");
    }
  });

  it("thinking sweeps fastest, speaking breathes fastest", () => {
    const plan = (state: (typeof MOVING)[number]) =>
      lensPlan(stageOrbMotion(state, LIVE), { glass: true });
    const fastest = (p: LensPlan) => Math.min(...lensTurns(p).map((t) => t.periodS));
    expect(fastest(plan("thinking"))).toBeLessThan(fastest(plan("speaking")));
    expect(fastest(plan("speaking"))).toBeLessThan(fastest(plan("listening")));
    expect(plan("speaking").breathe!.periodS).toBeLessThan(plan("listening").breathe!.periodS);
    expect(plan("thinking").breathe).toBeNull();
  });

  it("the glow follows the state as the sphere's does", () => {
    for (const { state, plan } of everyPlan(LIVE)) {
      expect(plan.glowOpacity, state).toBe(stageOrbMotion(state, LIVE).glowOpacity);
    }
  });
});

describe("Reduce Motion and RED make the lens still", () => {
  it("Reduce Motion: no sweep, no breath, no voice level, in every state", () => {
    for (const { state, plan } of everyPlan({ ...LIVE, reduce: true })) {
      expect(moves(plan), state).toBe(false);
      expect(plan.visible, state).toBe(state !== "hidden");
    }
  });

  it("RED: no sweep, no breath, no voice level, at any setting", () => {
    for (const reduce of [false, true]) {
      for (const { state, plan } of everyPlan({ reduce, redPresented: true })) {
        expect(moves(plan), state).toBe(false);
      }
    }
  });

  it("a plan built from a still motion is still", () => {
    const still: StageOrbMotion = {
      visible: true,
      rotationPeriodS: null,
      breathe: null,
      levelGain: 0,
      glowOpacity: 0.5,
    };
    expect(moves(lensPlan(still, { glass: true }))).toBe(false);
  });

  it("near miss: with no RED and no Reduce Motion, the listening lens does move", () => {
    const plan = lensPlan(stageOrbMotion("listening", LIVE), { glass: true });
    expect(moves(plan)).toBe(true);
    expect(lensTurns(plan).length).toBeGreaterThan(0);
    expect(plan.breathe).not.toBeNull();
    expect(plan.levelGain).toBeGreaterThan(0);
  });

  it("hidden draws nothing", () => {
    expect(lensPlan(stageOrbMotion("hidden", LIVE), { glass: true }).visible).toBe(false);
  });
});

describe("glass: the clear lens only over glass", () => {
  it("the clear lens is drawn only where glass is drawn at all", () => {
    for (const { state, surface, plan } of everyPlan(LIVE)) {
      expect(plan.lens, `${state}/${surface.glass}`).toBe(surface.glass);
    }
  });

  it("a solid surface (Reduce Transparency, a capture-protected screen) draws no glass", () => {
    for (const state of ORB_STATES) {
      expect(lensPlan(stageOrbMotion(state, LIVE), { glass: false }).lens, state).toBe(false);
    }
  });
});
