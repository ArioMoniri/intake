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
 *
 * INT-338 (MOTION-9; motion-verification.md §1.1 C12, §1.2 P15, §2.1 #3 and
 * #16, §3 S-6 and C-6) adds the section sheet, the app's one RN `Modal`:
 *
 * - the platform never animates it. Its own fade is a UIKit cross-dissolve
 *   on iOS and `config_shortAnimTime` on Android, and neither is the app's to
 *   bound, so the app owns the entrance (the one 120 ms fade) and every exit
 *   is instant;
 * - a privacy close and a RED close are therefore 0 ms at every setting,
 *   with no switch of `animationType` needed before `visible` turns false;
 * - a RED closes the sheet only when the patient is shown it: the decision is
 *   keyed on the presentation mode, so DEFERRED_CLINICIAN closes nothing.
 *
 * The close timing on a device is recorded in docs/evidence/INT-338.md.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, expectTypeOf, it } from "vitest";

import { modalAnimation } from "../a11y/motion";
import {
  resolveRed,
  type RedLocation,
  type RedPresentation,
  type RedRegister,
  type RedScriptCatalog,
} from "../livekit/red";
import { reducedMotion } from "../prefs/appearance";
import { motion } from "../theme";
import { enterFor } from "./fade";
import { RED_LOCATIONS, RED_REGISTERS, redPresentationMode } from "./red";
import { closesSheetOnRed } from "./sheetOnRed";
import {
  ROUTE_CLASSES,
  SHEET_CLOSE_REASONS,
  modalTransition,
  routeClassOf,
  sheetClose,
  tabTransition,
  transitionFor,
  type ModalTransition,
  type SheetClose,
} from "./transitions";

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
    // Its siblings in the visits stack are ordinary hierarchy.
    for (const route of ["(tabs)/visits/[visitId]/index", "(tabs)/visits/[visitId]/review"]) {
      expect(routeClassOf(route), route).toBe("hierarchy");
    }
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

/* ------------------------------------------------------------------ */
/* MOTION-9 — the section sheet (INT-338)                              */
/* ------------------------------------------------------------------ */

const MOBILE = join(SRC, "..");
const RN = join(MOBILE, "node_modules", "react-native");

/** Every reduce-motion setting: the app switch × the OS answer (null: none yet). */
const SETTINGS = [false, true].flatMap((app) =>
  [false, true, null].map((os) => ({ app, os, reduce: reducedMotion(app, os) })),
);

const CATALOG: RedScriptCatalog = {
  authorised: {
    primary: "CALL_112",
    show112: true,
    actionTr: "Hemen 112'yi arayın.",
    doNotsTr: [],
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

type ScriptId = "authorised" | "withheld";

/** A presentation through the only real constructor, `resolveRed`. */
function presented(register: RedRegister, location: RedLocation, scriptId: ScriptId) {
  const p: RedPresentation | null = resolveRed(
    { kind: "red_trigger", ruleId: "life_threat.chest_pain", register, location, scriptId },
    CATALOG,
  );
  if (p === null) {
    throw new Error(`no presentation for ${scriptId}`);
  }
  return p;
}

/** Every RED the sheet could meet: register × location × script × setting. */
const RED_ROWS = RED_REGISTERS.flatMap((register) =>
  RED_LOCATIONS.flatMap((location) =>
    (["authorised", "withheld"] as const).flatMap((scriptId) =>
      SETTINGS.map((setting) => ({ register, location, scriptId, ...setting })),
    ),
  ),
);

function label(row: (typeof RED_ROWS)[number]): string {
  return `${row.register}/${row.location}/${row.scriptId}, app ${row.app}, os ${row.os}`;
}

/** What `animationType` a sheet can carry, whoever built it. */
interface Presented {
  readonly animationType: ModalTransition["animationType"] | ReturnType<typeof modalAnimation>;
}

/**
 * How long a closed sheet stays on screen after the commit that hides it, as
 * far as the app can bound it. React Native dismisses with the
 * `animationType` the Modal carries, so a type other than `"none"` runs the
 * platform's own fade, whose length no prop sets: unbounded here. Otherwise
 * what remains is the content's own exit.
 */
function closeMs(open: Presented, close: SheetClose): number {
  const platform = open.animationType === "none" ? 0 : Number.POSITIVE_INFINITY;
  return Math.max(platform, close.exitMs);
}

describe("section sheet transition policy (MOTION-9)", () => {
  it("a privacy close is instant at every reduce-motion setting", () => {
    expect(SETTINGS).toHaveLength(6);
    for (const { app, os, reduce } of SETTINGS) {
      const setting = `app ${app}, os ${os}`;
      const close = sheetClose("privacy", { reduce });
      expect(close, setting).toEqual({ reason: "privacy", animationType: "none", exitMs: 0 });
      // C12: the type the platform dismisses with must already be "none" in
      // the commit BEFORE the one that sets visible=false. The sheet carries
      // "none" from the moment it opens, so there is nothing to switch, and a
      // third-party flag has nothing to hold on.
      expect(modalTransition({ reduce }).animationType, setting).toBe("none");
      expect(closeMs(modalTransition({ reduce }), close), setting).toBe(0);
    }
    // Near miss: the sheet as it stood before INT-338 took its type from the
    // reduce-motion answer, so with motion on, a privacy close ran the
    // platform's fade and the medication names stayed readable through it.
    const before: Presented = { animationType: modalAnimation(false) };
    expect(closeMs(before, sheetClose("privacy", { reduce: false }))).toBe(
      Number.POSITIVE_INFINITY,
    );
  });

  it("a modal closes without a transition when a RED is presented", () => {
    const shown = RED_ROWS.filter((row) => redPresentationMode(row.register) !== "none");
    // ALERT, CALM and SILENT × 3 locations × 2 scripts × 6 settings.
    expect(shown).toHaveLength(3 * 3 * 2 * 6);
    for (const row of shown) {
      const p = presented(row.register, row.location, row.scriptId);
      expect(closesSheetOnRed(p, { reduce: row.reduce }), label(row)).toBe(true);
      const close = sheetClose("red", { reduce: row.reduce });
      expect(close, label(row)).toEqual({ reason: "red", animationType: "none", exitMs: 0 });
      expect(closeMs(modalTransition({ reduce: row.reduce }), close), label(row)).toBe(0);
    }
    // S-6: the decision is keyed on what the patient is shown, never on "a
    // RED event arrived" — for every register, location, script and setting.
    for (const row of RED_ROWS) {
      const p = presented(row.register, row.location, row.scriptId);
      expect(closesSheetOnRed(p, { reduce: row.reduce }), label(row)).toBe(
        redPresentationMode(row.register) !== "none",
      );
    }
  });

  it("DEFERRED_CLINICIAN never closes a modal", () => {
    const deferred = RED_ROWS.filter((row) => row.register === "DEFERRED_CLINICIAN");
    expect(deferred).toHaveLength(3 * 2 * 6);
    for (const row of deferred) {
      const p = presented(row.register, row.location, row.scriptId);
      expect(closesSheetOnRed(p, { reduce: row.reduce }), label(row)).toBe(false);
      // Near miss: at the same location, script and setting, every register
      // the patient does see closes it, so the "no" is the register's doing.
      for (const register of RED_REGISTERS.filter((r) => r !== "DEFERRED_CLINICIAN")) {
        const seen = presented(register, row.location, row.scriptId);
        expect(closesSheetOnRed(seen, { reduce: row.reduce }), register).toBe(true);
      }
    }
  });

  it("reduce-motion presents modals without a transition", () => {
    for (const { app, os, reduce } of SETTINGS.filter((s) => s.reduce)) {
      // Nothing is registered: the sheet is simply there on its first frame,
      // and gone on the frame after it closes.
      expect(modalTransition({ reduce }), `app ${app}, os ${os}`).toEqual({
        animationType: "none",
        enter: undefined,
        exitMs: 0,
      });
    }
    // An unknown OS answer is reduced (INT-331), so it too presents still.
    expect(SETTINGS.filter((s) => s.reduce)).toHaveLength(5);
    // C-7: built on the kept primitive, which gives the same answer.
    expect(modalTransition({ reduce: true }).animationType).toBe(modalAnimation(true));
  });

  it("an owned sheet enters within fadeMs and exits instantly", () => {
    const owned = modalTransition({ reduce: false });
    // The one fade (02 §5.2a): opacity only, no delay, out-eased, the token.
    expect(owned).toEqual({
      animationType: "none",
      enter: enterFor({ reduce: false }),
      exitMs: motion.duration.instant,
    });
    expect(owned.enter).toEqual({
      property: "opacity",
      durationMs: motion.duration.fade,
      delayMs: 0,
      easing: motion.easing.out,
    });
    expect(owned.enter!.durationMs).toBeLessThanOrEqual(motion.fadeMs);
    // Owned in both directions, at every setting: the platform's fade never
    // runs, so the only motion is the app's own 120 ms entrance.
    for (const { reduce } of SETTINGS) {
      expect(modalTransition({ reduce }).animationType).toBe("none");
    }
    // Every close is instant, whatever closed it, at every setting.
    expect(SHEET_CLOSE_REASONS).toEqual(["user", "privacy", "red"]);
    for (const reason of SHEET_CLOSE_REASONS) {
      for (const { app, os, reduce } of SETTINGS) {
        const close = sheetClose(reason, { reduce });
        expect(close.reason).toBe(reason);
        expect(closeMs(modalTransition({ reduce }), close), `${reason}, app ${app}, os ${os}`).toBe(
          0,
        );
      }
    }
    // The types say it too: an owned modal that moves does not compile.
    expectTypeOf<ModalTransition["animationType"]>().toEqualTypeOf<"none">();
    expectTypeOf<ModalTransition["exitMs"]>().toEqualTypeOf<0>();
    expectTypeOf<SheetClose["animationType"]>().toEqualTypeOf<"none">();
    expectTypeOf<SheetClose["exitMs"]>().toEqualTypeOf<0>();
    expectTypeOf<SheetClose["reason"]>().toEqualTypeOf<"user" | "privacy" | "red">();
  });

  // The premise for owning the fade, read from the library that ships: the
  // platform's own modal fade has a length the app cannot set, and "none"
  // presents and dismisses with no animation at all. A React Native upgrade
  // that changes either fails here and sends the sheet back to be measured.
  it("the platform's modal fade is not the app's to bound, and none presents and dismisses unanimated", () => {
    const ios = readFileSync(
      join(
        RN,
        "React",
        "Fabric",
        "Mounting",
        "ComponentViews",
        "Modal",
        "RCTModalHostViewComponentView.mm",
      ),
      "utf8",
    );
    // "fade" is a UIKit cross-dissolve; "none" is presented unanimated…
    expect(ios).toMatch(
      /ModalHostViewAnimationType::Fade:\s*return std::make_tuple\(YES, UIModalTransitionStyleCrossDissolve\)/,
    );
    expect(ios).toMatch(/ModalHostViewAnimationType::None:\s*return std::make_tuple\(NO,/);
    // …both ways, from that one flag…
    expect(ios).toMatch(
      /presentViewController:self\.viewController\s+animated:_shouldAnimatePresentation/,
    );
    expect(ios).toMatch(
      /dismissViewController:self\.viewController\s+animated:_shouldAnimatePresentation/,
    );
    // …and nothing sets the cross-dissolve's length: UIKit owns it.
    expect(ios).not.toMatch(/duration/i);

    const modal = join(RN, "ReactAndroid", "src", "main");
    const host = readFileSync(
      join(modal, "java", "com", "facebook", "react", "views", "modal", "ReactModalHostView.kt"),
      "utf8",
    );
    expect(host).toMatch(/"fade" -> R\.style\.Theme_FullScreenDialogAnimatedFade/);
    expect(host).toMatch(/else -> R\.style\.Theme_FullScreenDialog\b/);
    const res = join(modal, "res", "views", "modal");
    const themes = readFileSync(join(res, "values", "themes.xml"), "utf8");
    // The theme "none" takes carries no window animation at all…
    const plain = /<style name="Theme\.FullScreenDialog">([\s\S]*?)<\/style>/.exec(themes);
    expect(plain).not.toBeNull();
    expect(plain![1]).not.toMatch(/windowAnimationStyle/);
    // …while "fade" runs the platform's short animation time in both
    // directions (200 ms in AOSP; the device's own resource decides).
    for (const anim of ["catalyst_fade_in.xml", "catalyst_fade_out.xml"]) {
      expect(readFileSync(join(res, "anim", anim), "utf8"), anim).toMatch(
        /android:duration="@android:integer\/config_shortAnimTime"/,
      );
    }
  });
});
