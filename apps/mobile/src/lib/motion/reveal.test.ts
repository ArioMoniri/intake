/**
 * Content reveal (INT-342, MOTION-13;
 * docs/design/motion/motion-verification.md §1.2 P6 and P7 as revised, §2.2
 * `reveal.skeletonDelayMs`, §4 MOTION-13).
 *
 * A screen that waits for its data gives the data one slot. While the data is
 * on its way the slot holds a skeleton, and the commit that brings the data
 * replaces the skeleton with the content. Six properties are pinned here,
 * without a device:
 *
 * - content that was already there when the slot mounted never animates;
 * - the skeleton is hidden for the first `motion.reveal.skeletonDelayMs`, so a
 *   load that lands inside that window never shows it;
 * - one element in one slot: no sequence, no stagger, no second entrance;
 * - the skeleton leaves in the commit that brings the content, with no exit
 *   and nothing chained to the end of an animation;
 * - reduce-motion keeps the delay (a wait is not movement) and drops the one
 *   fade there is, the content's entrance;
 * - the skeleton is static: it steps in once and never changes again.
 *
 * The policy is pure and is called directly. How the device runs a plan is
 * the small frame model below, the device-free approach of
 * transients.test.ts. e2e/motion.spec.ts ties the model to the Reanimated
 * adapter and to the two screens by reading their source.
 */
import { describe, expect, expectTypeOf, it } from "vitest";

import { reducedMotion } from "../prefs/appearance";
import { motion } from "../theme";
import { revealPlan, type RevealPlan, type SkeletonPlan } from "./reveal";

/** The one fade a reveal may run: the content's entrance (fade.ts). */
const FADE = {
  property: "opacity",
  durationMs: motion.duration.fade,
  delayMs: 0,
  easing: motion.easing.out,
} as const;

/** Every reduce-motion setting: the app switch × the OS answer (null: none yet). */
const SETTINGS = [false, true].flatMap((app) =>
  [false, true, null].map((os) => ({
    setting: `app ${app}, os ${os}`,
    reduce: reducedMotion(app, os),
  })),
);

/** Loads that land inside the delay, at it, just past it, and long after it. */
const LOADS = [1, 50, 150, 299, 300, 301, 450, 1000, 3000] as const;

/* ------------------------------------------------------------------ */
/* The frame model                                                     */
/* ------------------------------------------------------------------ */

/**
 * What the model reads from a plan. It is wider than `RevealPlan`, whose
 * literal types would refuse the near misses written down below.
 */
interface Timeline {
  readonly skeleton: {
    readonly delayMs: number;
    readonly stepMs: number;
    readonly exitMs: number;
  };
  readonly enter: { readonly delayMs: number; readonly durationMs: number } | undefined;
}

interface Drawn {
  readonly name: "skeleton" | "content";
  /** Its opacity on this frame. 0 is on the tree and unseen. */
  readonly opacity: number;
}

/** Opacity `t` ms into a 0 → 1 change that waits `delay` ms and then runs `duration` ms. */
function progress(t: number, delay: number, duration: number): number {
  if (t < delay) {
    return 0;
  }
  return duration <= 0 ? 1 : Math.min(1, (t - delay) / duration);
}

/**
 * The slot `t` ms after the commit that mounts it, when the content lands in
 * the commit at `readyAt` ms (0: it was in the mounting commit itself).
 *
 * The skeleton and the content are the two branches of one conditional, so
 * React removes one in the commit that mounts the other. The only thing that
 * keeps a removed element on screen is an exit, for `exitMs`.
 */
function slotAt(plan: Timeline, readyAt: number, t: number): Drawn[] {
  const drawn: Drawn[] = [];
  if (readyAt > 0 && t < readyAt + plan.skeleton.exitMs) {
    const { delayMs, stepMs } = plan.skeleton;
    drawn.push({ name: "skeleton", opacity: progress(t, delayMs, stepMs) });
  }
  if (t >= readyAt) {
    const { enter } = plan;
    const opacity =
      enter === undefined ? 1 : progress(t - readyAt, enter.delayMs, enter.durationMs);
    drawn.push({ name: "content", opacity });
  }
  return drawn;
}

/** Every frame, one per millisecond, from the mount until well after the content has settled. */
function frames(plan: Timeline, readyAt: number): Drawn[][] {
  const end = readyAt + motion.reveal.skeletonDelayMs + motion.duration.fade;
  return Array.from({ length: end + 1 }, (_, t) => slotAt(plan, readyAt, t));
}

function seen(drawn: Drawn): boolean {
  return drawn.opacity > 0;
}

/** Part-way through a change: the only frames on which something is moving. */
function moving(drawn: Drawn): boolean {
  return drawn.opacity > 0 && drawn.opacity < 1;
}

/** How many times a sequence of values changes. */
function changes(values: readonly number[]): number {
  return values.filter((value, i) => i > 0 && value !== values[i - 1]).length;
}

/** Every value in a plan, however deep. */
function leaves(value: unknown): unknown[] {
  if (value !== null && typeof value === "object") {
    return Object.values(value).flatMap(leaves);
  }
  return [value];
}

function plansFor(reduce: boolean): readonly (readonly [string, RevealPlan])[] {
  return [
    ["available at mount", revealPlan({ availableAtMount: true, reduce })],
    ["on its way", revealPlan({ availableAtMount: false, reduce })],
  ];
}

describe("MOTION-13 — content reveal and a static skeleton", () => {
  it("content that was already available renders without animation", () => {
    for (const { setting, reduce } of SETTINGS) {
      const plan = revealPlan({ availableAtMount: true, reduce });
      expect(plan.enter, setting).toBeUndefined();
      // From its first frame the slot holds the content, fully drawn, and
      // nothing in it ever changes.
      const all = frames(plan, 0);
      expect(all.length, setting).toBeGreaterThan(motion.duration.fade);
      const other = all
        .map((frame, t) => ({ t, frame }))
        .filter(
          ({ frame }) =>
            frame.length !== 1 || frame[0].name !== "content" || frame[0].opacity !== 1,
        );
      expect(other, setting).toEqual([]);
    }

    // Near miss: the entrance that arriving content takes would be seen here.
    // Drawn on content that was already there, it starts at opacity 0.
    const arriving = revealPlan({ availableAtMount: false, reduce: false });
    expect(arriving.enter).toEqual(FADE);
    const [first] = frames(arriving, 0);
    expect(first).toEqual([{ name: "content", opacity: 0 }]);
    expect(frames(arriving, 0).flat().some(moving)).toBe(true);
  });

  it("a skeleton never appears for a load under skeletonDelayMs", () => {
    const delay = motion.reveal.skeletonDelayMs;
    expect(delay).toBe(300);
    for (const { setting, reduce } of SETTINGS) {
      const plan = revealPlan({ availableAtMount: false, reduce });
      expect(plan.skeleton.delayMs, setting).toBe(delay);
      // Every load that lands before the delay, to the millisecond, and the
      // one that lands on it: the commit that would show the skeleton is the
      // commit that removes it.
      for (let readyAt = 1; readyAt <= delay; readyAt += 1) {
        const shown = frames(plan, readyAt)
          .flat()
          .filter((drawn) => drawn.name === "skeleton" && seen(drawn));
        expect(shown, `${setting}, a load of ${readyAt} ms`).toEqual([]);
      }

      // Near miss: a load 1 ms past the delay does show it, from the delay
      // until the commit that brings the content.
      const slow = frames(plan, delay + 1);
      expect(slow[delay - 1], setting).toEqual([{ name: "skeleton", opacity: 0 }]);
      expect(slow[delay], setting).toEqual([{ name: "skeleton", opacity: 1 }]);
      expect(
        slow[delay + 1].map((drawn) => drawn.name),
        setting,
      ).toEqual(["content"]);
    }
  });

  it("reveal is one element in one slot", () => {
    for (const { setting, reduce } of SETTINGS) {
      for (const [when, plan] of plansFor(reduce)) {
        const label = `${setting}, ${when}`;
        // One skeleton and one entrance: no list of slots, no sequence, and
        // no offset that would stagger a second element behind the first.
        expect(Object.keys(plan).sort(), label).toEqual(["enter", "skeleton"]);
        expect(Array.isArray(plan.enter), label).toBe(false);
        if (plan.enter !== undefined) {
          expect(plan.enter, label).toEqual(FADE);
        }
        const loads = when === "available at mount" ? [0] : LOADS;
        for (const readyAt of loads) {
          // One element in the slot on every frame, and never two moving.
          const crowded = frames(plan, readyAt)
            .map((frame, t) => ({ t, drawn: frame.length, moving: frame.filter(moving).length }))
            .filter((f) => f.drawn !== 1 || f.moving > 1);
          expect(crowded, `${label}, a load of ${readyAt} ms`).toEqual([]);
        }
      }
    }

    // Near miss: a skeleton that fades out beside the arriving content puts
    // two elements in the slot, both drawn, on the frame of that commit.
    const plan = revealPlan({ availableAtMount: false, reduce: false });
    const fadingOut: Timeline = {
      ...plan,
      skeleton: { ...plan.skeleton, exitMs: motion.duration.fade },
    };
    expect(slotAt(fadingOut, 1000, 1000).map((drawn) => drawn.name)).toEqual([
      "skeleton",
      "content",
    ]);
  });

  it("the skeleton unmounts in the commit that mounts the content, never on an animation callback", () => {
    for (const { setting, reduce } of SETTINGS) {
      const plan = revealPlan({ availableAtMount: false, reduce });
      expect(plan.skeleton.exitMs, setting).toBe(0);
      // Whatever the skeleton is doing when the content lands (still hidden,
      // or shown), the commit that brings the content is the last frame it
      // is on the tree. Nothing about the skeleton decides when it goes.
      for (const readyAt of LOADS) {
        const all = frames(plan, readyAt);
        const at = `${setting}, a load of ${readyAt} ms`;
        expect(
          all[readyAt - 1].map((drawn) => drawn.name),
          at,
        ).toEqual(["skeleton"]);
        expect(
          all[readyAt].map((drawn) => drawn.name),
          at,
        ).toEqual(["content"]);
        const last = all.findLastIndex((frame) => frame.some((d) => d.name === "skeleton"));
        expect(last, at).toBe(readyAt - 1);
      }
      // The plan is data: no function anywhere in it, so there is no
      // callback for the host to chain the removal to.
      for (const [when, each] of plansFor(reduce)) {
        const functions = leaves(each).filter((leaf) => typeof leaf === "function");
        expect(functions, `${setting}, ${when}`).toEqual([]);
      }
    }

    // Near miss: removal on the end of a fade-out (an exit, then its
    // callback) keeps the skeleton on the tree beside the content for the
    // whole fade.
    const plan = revealPlan({ availableAtMount: false, reduce: false });
    const onCallback: Timeline = {
      ...plan,
      skeleton: { ...plan.skeleton, exitMs: motion.duration.fade },
    };
    const late = frames(onCallback, 500);
    const last = late.findLastIndex((frame) => frame.some((d) => d.name === "skeleton"));
    expect(last).toBe(500 + motion.duration.fade - 1);
  });

  it("reduce-motion keeps the delay and drops every fade", () => {
    const reduced = SETTINGS.filter((s) => s.reduce);
    // The app switch at any OS answer, the OS answer on its own, and "the OS
    // has not answered yet", which fails closed (INT-331).
    expect(reduced).toHaveLength(5);
    for (const { setting } of reduced) {
      for (const [when, plan] of plansFor(true)) {
        const label = `${setting}, ${when}`;
        // The wait is the same number…
        expect(plan.skeleton.delayMs, label).toBe(motion.reveal.skeletonDelayMs);
        // …and nothing fades: not the skeleton, not the content.
        expect(plan.skeleton.stepMs, label).toBe(0);
        expect(plan.enter, label).toBeUndefined();
        const loads = when === "available at mount" ? [0] : LOADS;
        for (const readyAt of loads) {
          const moved = frames(plan, readyAt).flat().filter(moving);
          expect(moved, `${label}, a load of ${readyAt} ms`).toEqual([]);
        }
      }
      // The delay still holds a slow load's skeleton back until it has passed.
      const slow = frames(revealPlan({ availableAtMount: false, reduce: true }), 3000);
      expect(slow[motion.reveal.skeletonDelayMs - 1][0].opacity, setting).toBe(0);
      expect(slow[motion.reveal.skeletonDelayMs][0].opacity, setting).toBe(1);
    }

    // Near miss: with motion on, the detector sees the one fade there is.
    const moved = frames(revealPlan({ availableAtMount: false, reduce: false }), 3000)
      .flat()
      .filter(moving);
    expect(moved.map((drawn) => drawn.name)).toEqual(
      Array.from({ length: motion.duration.fade - 1 }, () => "content"),
    );
    // Reduce-motion changes the entrance and nothing else.
    const on = revealPlan({ availableAtMount: false, reduce: false });
    const off = revealPlan({ availableAtMount: false, reduce: true });
    expect(off.skeleton).toEqual(on.skeleton);
  });

  it("the skeleton has no loop", () => {
    expectTypeOf<SkeletonPlan["loop"]>().toEqualTypeOf<false>();
    expectTypeOf<SkeletonPlan["shimmer"]>().toEqualTypeOf<false>();
    expectTypeOf<SkeletonPlan["stepMs"]>().toEqualTypeOf<0>();
    expectTypeOf<SkeletonPlan["exitMs"]>().toEqualTypeOf<0>();

    for (const { setting, reduce } of SETTINGS) {
      const plan = revealPlan({ availableAtMount: false, reduce });
      // Exactly these keys: no period, no iteration count, no sweep.
      expect(plan.skeleton, setting).toEqual({
        delayMs: motion.reveal.skeletonDelayMs,
        stepMs: motion.duration.instant,
        exitMs: motion.duration.instant,
        loop: false,
        shimmer: false,
      });

      // Over a ten-second wait it changes exactly once, hidden to shown, and
      // is then still.
      const wait = 10_000;
      const opacity = Array.from({ length: wait }, (_, t) => slotAt(plan, wait, t)[0].opacity);
      expect(changes(opacity), setting).toBe(1);
      expect(
        opacity.slice(motion.reveal.skeletonDelayMs).every((o) => o === 1),
        setting,
      ).toBe(true);
    }

    // Near miss: a skeleton that breathes on the app's own loop period (the
    // rejected shimmer) changes on nearly every frame, and is caught.
    const breathing = Array.from(
      { length: 10_000 },
      (_, t) => 0.5 + 0.5 * Math.cos((2 * Math.PI * t) / motion.loop.pulsePeriodMs),
    );
    expect(changes(breathing)).toBeGreaterThan(5_000);
  });
});
