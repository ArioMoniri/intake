/**
 * The RED motion contract (INT-333, MOTION-4;
 * docs/design/motion/motion-verification.md §4 MOTION-4, §3 S-1, S-5, S-6;
 * files/02 §5.3; CLAUDE.md invariant 21).
 *
 * Every combination is enumerated rather than sampled: 4 registers ×
 * 3 locations × 2 reduce-motion answers, each with the pack authorising 112
 * and not. The near-miss controls are the presentations a caller could build
 * by hand to get round `resolveRed` (ON_SITE with 112 authorised), and the
 * UNKNOWN answers that would show a 112 control and then take it away.
 *
 * What only a device can show — event to first RED frame, fired mid-push —
 * belongs to INT-135's DoD, where the RED UI lands. Nothing here is a timing.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, expectTypeOf, it } from "vitest";

import {
  resolveRed,
  type RedLocation,
  type RedPresentation,
  type RedRegister,
  type RedScriptCatalog,
} from "../livekit/red";
import {
  RED_LOCATIONS,
  RED_REGISTERS,
  redAffordances,
  redFirstPaint,
  redPresentationMode,
  redYield,
  type LocationAnswer,
  type RedMotion,
} from "./red";

const CATALOG: RedScriptCatalog = {
  authorised: {
    primary: "CALL_112",
    show112: true,
    actionTr: "Hemen 112'yi arayın.",
    doNotsTr: ["Araç kullanmayın."],
    whyTr: null,
  },
  withheld: {
    primary: "GO_TO_IN_HOUSE_ACIL",
    show112: false,
    actionTr: "En yakın görevliye hemen haber verin.",
    doNotsTr: [],
    whyTr: null,
  },
};

/** A presentation through the only real constructor, `resolveRed`. */
function presented(
  register: RedRegister,
  location: RedLocation,
  scriptId: "authorised" | "withheld" = "authorised",
): RedPresentation {
  const p = resolveRed(
    { kind: "red_trigger", ruleId: "life_threat.chest_pain", register, location, scriptId },
    CATALOG,
  );
  if (p === null) {
    throw new Error(`no presentation for ${scriptId}`);
  }
  return p;
}

interface Row {
  readonly register: RedRegister;
  readonly location: RedLocation;
  readonly reduce: boolean;
  readonly scriptId: "authorised" | "withheld";
}

const ROWS: readonly Row[] = RED_REGISTERS.flatMap((register) =>
  RED_LOCATIONS.flatMap((location) =>
    [false, true].flatMap((reduce) =>
      (["authorised", "withheld"] as const).map((scriptId) => ({
        register,
        location,
        reduce,
        scriptId,
      })),
    ),
  ),
);

const ANSWERS: readonly LocationAnswer[] = ["unanswered", "inHospital", "notInHospital"];

const TAKEOVER = RED_REGISTERS.filter((r) => r === "ALERT" || r === "CALM");

describe("RED motion contract (MOTION-4)", () => {
  it("the tuples cover every register and location the schema defines", () => {
    expectTypeOf<(typeof RED_REGISTERS)[number]>().toEqualTypeOf<RedRegister>();
    expectTypeOf<(typeof RED_LOCATIONS)[number]>().toEqualTypeOf<RedLocation>();
    expect(RED_REGISTERS).toHaveLength(4);
    expect(RED_LOCATIONS).toHaveLength(3);
  });

  it("every register × location × reduce-motion renders with 0 ms entrance, 0 ms delay and no loop", () => {
    const combos = new Set(ROWS.map((r) => `${r.register}/${r.location}/${r.reduce}`));
    expect(combos.size).toBe(24);
    for (const row of ROWS) {
      const { motion } = redFirstPaint(presented(row.register, row.location, row.scriptId), row);
      const label = JSON.stringify(row);
      expect(motion.enterMs, label).toBe(0);
      expect(motion.delayMs, label).toBe(0);
      expect(motion.loop, label).toBe(false);
      expect(motion.flash, label).toBe(false);
      expect(motion.stagger, label).toBe(false);
    }
    // The answer does not depend on reduce-motion: there is nothing to reduce.
    for (const register of RED_REGISTERS) {
      for (const location of RED_LOCATIONS) {
        const p = presented(register, location);
        expect(redFirstPaint(p, { reduce: true })).toEqual(redFirstPaint(p, { reduce: false }));
      }
    }
    // By type as well as by value: a RED that moves does not compile.
    expectTypeOf<RedMotion["enterMs"]>().toEqualTypeOf<0>();
    expectTypeOf<RedMotion["delayMs"]>().toEqualTypeOf<0>();
    expectTypeOf<RedMotion["loop"]>().toEqualTypeOf<false>();
  });

  it("RED exit is 0 ms", () => {
    for (const row of ROWS) {
      const { motion } = redFirstPaint(presented(row.register, row.location, row.scriptId), row);
      expect(motion.exitMs, JSON.stringify(row)).toBe(0);
    }
    expectTypeOf<RedMotion["exitMs"]>().toEqualTypeOf<0>();
  });

  it("no RED register has an auto-dismiss or a timed exit", () => {
    for (const row of ROWS) {
      const { motion } = redFirstPaint(presented(row.register, row.location, row.scriptId), row);
      expect(motion.autoDismissMs, JSON.stringify(row)).toBeNull();
      expect(motion.dismissByGesture, JSON.stringify(row)).toBe(false);
    }
    expectTypeOf<RedMotion["autoDismissMs"]>().toEqualTypeOf<null>();
  });

  it("ALERT and CALM paint first as a root layer, never as a navigation or a modal", () => {
    for (const register of TAKEOVER) {
      expect(redPresentationMode(register), register).toBe("rootLayer");
      for (const location of RED_LOCATIONS) {
        const paint = redFirstPaint(presented(register, location), { reduce: false });
        expect(paint.mode).toBe("rootLayer");
        // The plan carries no route, href, stack option or modal presentation:
        // a caller has nothing to navigate to or present.
        expect(Object.keys(paint).sort()).toEqual(["affordances", "mode", "motion", "yields"]);
        const flat = JSON.stringify(paint);
        expect(flat).not.toMatch(/"(?:route|href|pathname|presentation|animation|animationType)"/);
        // Everything else on screen yields in the same commit.
        expect(paint.yields).toEqual({
          snapTransients: true,
          stopAmbient: true,
          closeModals: true,
          orb: "unmount",
        });
      }
    }
    // The contract is pure: it reaches no navigator, modal, animation or
    // haptics module, only the RED types.
    const source = readFileSync(join(__dirname, "red.ts"), "utf8");
    const imports = [...source.matchAll(/^import\s+(type\s+)?[^;]*?from\s+["']([^"']+)["']/gm)];
    expect(imports.map((m) => [Boolean(m[1]), m[2]])).toEqual([[true, "../livekit/red"]]);
  });

  it("SILENT renders in flow and freezes the orb at idle", () => {
    expect(redPresentationMode("SILENT")).toBe("inFlow");
    for (const location of RED_LOCATIONS) {
      const paint = redFirstPaint(presented("SILENT", location), { reduce: false });
      expect(paint.mode).toBe("inFlow");
      expect(paint.yields.orb).toBe("idle");
      expect(paint.yields.snapTransients).toBe(true);
      expect(paint.yields.closeModals).toBe(true);
    }
  });

  it("DEFERRED_CLINICIAN is invisible to the motion layer: no orb change, no modal close, no banner clear", () => {
    expect(redPresentationMode("DEFERRED_CLINICIAN")).toBe("none");
    for (const location of RED_LOCATIONS) {
      for (const scriptId of ["authorised", "withheld"] as const) {
        const p = presented("DEFERRED_CLINICIAN", location, scriptId);
        const paint = redFirstPaint(p, { reduce: false });
        expect(paint.mode).toBe("none");
        expect(paint.yields).toEqual({
          snapTransients: false,
          stopAmbient: false,
          closeModals: false,
          orb: "unchanged",
        });
        // "renders none of them" (02 §5.3): no action at any answer.
        for (const answer of ANSWERS) {
          expect(redAffordances(p, answer), `${location}/${scriptId}/${answer}`).toEqual({
            call112: false,
            askLocation: false,
          });
        }
      }
    }
    // Near miss: every register the patient does see yields, so the "none"
    // above is the register's doing, not a contract that never yields.
    for (const register of RED_REGISTERS.filter((r) => r !== "DEFERRED_CLINICIAN")) {
      const paint = redFirstPaint(presented(register, "REMOTE"), { reduce: false });
      expect(paint.yields.closeModals, register).toBe(true);
    }
  });

  it("ON_SITE never mounts a 112 control, even transiently", () => {
    for (const register of RED_REGISTERS) {
      for (const answer of ANSWERS) {
        const p = presented(register, "ON_SITE");
        expect(redAffordances(p, answer).call112, `${register}/${answer}`).toBe(false);
        expect(redAffordances(p, answer).askLocation, `${register}/${answer}`).toBe(false);
      }
    }
    // Near miss: a presentation assembled by hand, round `resolveRed`'s clamp,
    // with the pack's authorisation left on. Still no 112.
    const bypass: RedPresentation = {
      ruleId: "life_threat.chest_pain",
      register: "ALERT",
      location: "ON_SITE",
      script: CATALOG.authorised,
      show112: true,
    };
    expect(redFirstPaint(bypass, { reduce: false }).affordances.call112).toBe(false);
    for (const answer of ANSWERS) {
      expect(redAffordances(bypass, answer).call112, answer).toBe(false);
    }
  });

  it("UNKNOWN mounts no location action until the question is answered", () => {
    const shown: readonly RedRegister[] = [...TAKEOVER, "SILENT"];
    for (const register of shown) {
      const p = presented(register, "UNKNOWN");
      // The pack authorises 112, and still nothing mounts before the answer.
      expect(p.show112).toBe(true);
      expect(redFirstPaint(p, { reduce: false }).affordances).toEqual({
        call112: false,
        askLocation: true,
      });
      expect(redAffordances(p, "inHospital")).toEqual({ call112: false, askLocation: false });
      expect(redAffordances(p, "notInHospital")).toEqual({ call112: true, askLocation: false });
      // The pack narrows: without its authorisation, no 112 after any answer.
      const withheld = presented(register, "UNKNOWN", "withheld");
      expect(redAffordances(withheld, "notInHospital").call112).toBe(false);
    }
    // REMOTE is known: 112 on the first frame when authorised, never asked.
    for (const register of TAKEOVER) {
      expect(redFirstPaint(presented(register, "REMOTE"), { reduce: false }).affordances).toEqual({
        call112: true,
        askLocation: false,
      });
    }
  });

  it("an answer never removes a 112 control the patient has already seen", () => {
    for (const register of RED_REGISTERS) {
      for (const location of RED_LOCATIONS) {
        for (const scriptId of ["authorised", "withheld"] as const) {
          const p = presented(register, location, scriptId);
          const before = redFirstPaint(p, { reduce: false }).affordances.call112;
          for (const answer of ANSWERS) {
            const after = redAffordances(p, answer).call112;
            // Mounted then hidden is the one transition that must not exist.
            expect(before && !after, `${register}/${location}/${scriptId}/${answer}`).toBe(false);
          }
        }
      }
    }
  });

  it("RED actions commit on press with instant feedback and no long-press", () => {
    for (const row of ROWS) {
      const { motion } = redFirstPaint(presented(row.register, row.location, row.scriptId), row);
      expect(motion.actions, JSON.stringify(row)).toEqual({
        commitOn: "press",
        feedbackMs: 0,
        longPress: false,
      });
    }
  });

  it("no RED register permits a haptic", () => {
    for (const row of ROWS) {
      const { motion } = redFirstPaint(presented(row.register, row.location, row.scriptId), row);
      expect(motion.haptic, JSON.stringify(row)).toBe(false);
    }
    expectTypeOf<RedMotion["haptic"]>().toEqualTypeOf<false>();
  });

  it("the first paint is decided from the presentation alone, synchronously", () => {
    for (const row of ROWS) {
      const p = presented(row.register, row.location, row.scriptId);
      const paint = redFirstPaint(p, row);
      // A plain value, never a promise or a callback to wait on.
      expect(paint).not.toBeInstanceOf(Promise);
      expect(typeof (paint as unknown as { then?: unknown }).then).toBe("undefined");
      // The same input gives the same answer: nothing reads a clock or state.
      expect(redFirstPaint(p, row)).toEqual(paint);
    }
  });

  // INT-551: the dialogue's orb reads the yield by register, from the store,
  // and must read the very table the first paint is sized from.
  it("redYield is the first paint's yield, for every register, location and script", () => {
    for (const row of ROWS) {
      const paint = redFirstPaint(presented(row.register, row.location, row.scriptId), row);
      expect(redYield(row.register), JSON.stringify(row)).toEqual(paint.yields);
    }
    expect(redYield("ALERT").orb).toBe("unmount");
    expect(redYield("CALM").orb).toBe("unmount");
    expect(redYield("SILENT").orb).toBe("idle");
    expect(redYield("DEFERRED_CLINICIAN").orb).toBe("unchanged");
  });
});
