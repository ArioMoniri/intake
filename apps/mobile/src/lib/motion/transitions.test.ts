/**
 * Native-stack and tab transition policy (INT-330, MOTION-1;
 * docs/design/motion/motion-verification.md §3 S-1, §4 MOTION-1).
 *
 * Three things are pinned here, all without a device:
 *
 * - every stack fade runs the fade token (120 ms), never the iOS default of
 *   500 ms. react-native-screens defers a push or pop requested while a
 *   transition is in flight until that transition completes, so an unpinned
 *   stack could hold a RED behind it past 02 §8.1's 300 ms preemption budget;
 * - legal text never moves: the routes that render the docs/legal payload
 *   take no transition in either direction, at any reduce-motion setting —
 *   and they are discovered from the source, not from a list kept here;
 * - the intake cannot be swiped away (its header back control is the exit).
 *
 * What only a device can show — the measured push/pop timing on iOS and
 * Android — is recorded in docs/evidence/INT-330.md, never asserted here.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { motion } from "../theme";
import { ROUTE_CLASSES, routeClassOf, tabTransition, transitionFor } from "./transitions";

const SRC = join(__dirname, "..", "..");
const APP = join(SRC, "app");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** `src/app/(auth)/consent.tsx` → `(auth)/consent`: the name routeClassOf takes. */
function routeName(path: string): string {
  return relative(APP, path)
    .split(sep)
    .join("/")
    .replace(/\.tsx$/, "");
}

const ROUTE_FILES = walk(APP).filter((p) => p.endsWith(".tsx") && !p.endsWith("_layout.tsx"));

/** Every route a navigator can show: each screen file, plus each group a parent stack pushes. */
const ROUTES: readonly string[] = [
  ...ROUTE_FILES.map(routeName),
  ...walk(APP)
    .filter((p) => p.endsWith("_layout.tsx") && relative(APP, p) !== "_layout.tsx")
    .map((p) => routeName(p).replace(/\/_layout$/, "")),
].sort();

const FADE = motion.duration.fade;
const NON_LEGAL = ROUTE_CLASSES.filter((c) => c !== "legal");

describe("native-stack transition policy (MOTION-1)", () => {
  it("every native stack fades for duration.fade", () => {
    for (const cls of NON_LEGAL) {
      const t = transitionFor(cls, { reduce: false });
      expect(t.animation, cls).toBe("fade");
      expect(t.animationDuration, cls).toBe(FADE);
    }
    // Concretely, on every route the app ships: a fade runs the token, and
    // nothing falls back to the platform's own 500 ms.
    expect(ROUTES.length).toBeGreaterThan(15);
    for (const route of ROUTES) {
      const t = transitionFor(routeClassOf(route), { reduce: false });
      expect(t.animationDuration, route).toBe(t.animation === "fade" ? FADE : 0);
    }
  });

  it("reduce-motion turns every navigator transition off", () => {
    for (const cls of ROUTE_CLASSES) {
      const stack = transitionFor(cls, { reduce: true });
      expect(stack.animation, cls).toBe("none");
      expect(stack.animationDuration, cls).toBe(0);
      const tab = tabTransition(cls, { reduce: true });
      expect(tab.animation, cls).toBe("none");
      expect(tab.transitionSpec.config.duration, cls).toBe(0);
    }
  });

  it("legal routes never animate, with or without reduce-motion", () => {
    for (const reduce of [false, true]) {
      expect(transitionFor("legal", { reduce })).toEqual({
        animation: "none",
        animationDuration: motion.duration.instant,
      });
      expect(tabTransition("legal", { reduce })).toEqual({
        animation: "none",
        transitionSpec: { animation: "timing", config: { duration: motion.duration.instant } },
      });
    }
    for (const route of [
      "(auth)/consent",
      "(tabs)/me/consents/index",
      "(tabs)/me/consents/[purpose]",
    ]) {
      expect(routeClassOf(route), route).toBe("legal");
    }
  });

  // P4(b): a hand-kept path list drifts, so the guard keys on the payload.
  // On the client, the docs/legal payload (version, hash, and the Turkish
  // text itself) lives in the consent ledger's `LoadedText`. A route renders
  // it when the route — or a component it renders — imports that module.
  it("every route that renders a docs/legal payload classifies as legal", () => {
    const ledger = readFileSync(join(SRC, "lib", "consent", "ledger.ts"), "utf8");
    // The premise: the ledger still owns the payload, body included.
    expect(ledger).toMatch(/export interface LoadedText \{[^}]*\bbody: string;/);

    const READS_LEDGER = /from\s+["'][^"']*\/consent\/ledger["']/;
    const component = (name: string) => join(SRC, "components", `${name}.tsx`);
    const closure = (file: string, seen = new Set<string>()): string[] => {
      if (seen.has(file)) {
        return [];
      }
      seen.add(file);
      const source = readFileSync(file, "utf8");
      const used = [...source.matchAll(/from\s+["']@\/components\/([A-Za-z0-9_]+)["']/g)].map((m) =>
        component(m[1]),
      );
      return [source, ...used.flatMap((c) => closure(c, seen))];
    };

    const hosts = ROUTE_FILES.filter((f) => closure(f).some((s) => READS_LEDGER.test(s)))
      .map(routeName)
      .sort();
    // Non-vacuity: the screen that prints the text body itself is found.
    const printsBody = ROUTE_FILES.filter((f) => /\.text\.body\b/.test(readFileSync(f, "utf8")))
      .map(routeName)
      .sort();
    expect(printsBody.length).toBeGreaterThan(0);
    expect(hosts).toEqual(expect.arrayContaining(printsBody));

    const unclassified = hosts.filter((r) => routeClassOf(r) !== "legal");
    expect(unclassified).toEqual([]);
  });

  it("the intake route fades and is gesture-locked", () => {
    expect(routeClassOf("(tabs)/visits/[visitId]/intake")).toBe("intake");
    expect(transitionFor("intake", { reduce: false })).toEqual({
      animation: "fade",
      animationDuration: FADE,
      gestureEnabled: false,
    });
    // The lock is not a motion preference: reduce-motion keeps it.
    expect(transitionFor("intake", { reduce: true }).gestureEnabled).toBe(false);
    // Only the intake is locked; every other class keeps the platform gesture.
    for (const cls of ROUTE_CLASSES.filter((c) => c !== "intake")) {
      expect(transitionFor(cls, { reduce: false }).gestureEnabled, cls).toBeUndefined();
    }
    // Its siblings in the visits stack are ordinary hierarchy — except Review
    // & send, which renders the share consent text since INT-587 and so takes
    // the legal class (the payload rule above finds it, and fails without it).
    for (const route of ["(tabs)/visits/[visitId]/index", "(tabs)/visits/[visitId]/shares"]) {
      expect(routeClassOf(route), route).toBe("hierarchy");
    }
    expect(routeClassOf("(tabs)/visits/[visitId]/review")).toBe("legal");
  });

  it("legal tab screens take no transition; other tabs take duration.fade", () => {
    const layout = readFileSync(join(APP, "(tabs)", "_layout.tsx"), "utf8");
    const tabs = [...layout.matchAll(/<Tabs\.Screen name="([^"]+)"/g)].map((m) => `(tabs)/${m[1]}`);
    expect(tabs.length).toBeGreaterThan(5);
    const legal = tabs.filter((r) => routeClassOf(r) === "legal");
    expect(legal.sort()).toEqual(["(tabs)/me/consents/[purpose]", "(tabs)/me/consents/index"]);
    for (const route of tabs) {
      const t = tabTransition(routeClassOf(route), { reduce: false });
      if (legal.includes(route)) {
        expect(t.animation, route).toBe("none");
        expect(t.transitionSpec.config.duration, route).toBe(0);
      } else {
        expect(t.animation, route).toBe("fade");
        expect(t.transitionSpec, route).toEqual({
          animation: "timing",
          config: { duration: FADE },
        });
      }
    }
  });

  it("no route class returns a slide, a modal presentation or a duration above fadeMs", () => {
    for (const cls of ROUTE_CLASSES) {
      for (const reduce of [false, true]) {
        const stack = transitionFor(cls, { reduce });
        expect(["fade", "none"], `${cls} stack`).toContain(stack.animation);
        expect(stack, `${cls} stack`).not.toHaveProperty("presentation");
        expect(stack.animationDuration).toBeGreaterThanOrEqual(0);
        expect(stack.animationDuration).toBeLessThanOrEqual(motion.fadeMs);

        const tab = tabTransition(cls, { reduce });
        expect(["fade", "none"], `${cls} tab`).toContain(tab.animation);
        expect(tab.transitionSpec.animation, `${cls} tab`).toBe("timing");
        expect(tab.transitionSpec.config.duration).toBeGreaterThanOrEqual(0);
        expect(tab.transitionSpec.config.duration).toBeLessThanOrEqual(motion.fadeMs);
      }
    }
  });
});
