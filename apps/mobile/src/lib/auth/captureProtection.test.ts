/**
 * INT-477 (GitHub #817; ADR-039 amendment, owner, 4 Oct 2026: "solid"):
 * every capture-protected screen draws solid chrome, never Liquid Glass and
 * never a blur, in both themes.
 *
 * Two answers decide it, one for each moment:
 * - the route: a protected screen is solid from its first frame, before its
 *   own protection effect has run. The routes are discovered from the
 *   source, so a new protected screen cannot be left off the list;
 * - the window: protection is window-wide and can outlive focus (a tab screen
 *   stays mounted after its first visit, and keeps its protection), so while
 *   any screen holds it, every glass surface in the window is solid.
 *
 * The vitest lane has no renderer, so "never mounts a glass view" is proved
 * as the policy each glass host asks (lib/a11y/glass) plus the wiring that
 * reaches it (e2e/captureChrome.spec.ts).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { glassMode, navBarChrome } from "@/lib/a11y/glass";

import {
  CAPTURE_PROTECTED_ROUTES,
  captureScope,
  createCaptureProtectionStore,
  focusedRoutePath,
  isCaptureProtectedRoute,
  protectScreen,
  type CaptureGuard,
} from "./captureProtection";

const SRC = join(__dirname, "..", "..");
const APP = join(SRC, "app");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** Comments removed: a file may name the guard in prose without calling it. */
const code = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/** A call of the guard; its own declaration is not one. */
const CALLS_GUARD = /(?<!function\s)\buseClinicalScreenPrivacy\(\)/;

/** `src/app/(tabs)/records.tsx` → `(tabs)/records`, as the navigators name it. */
function routeName(path: string): string {
  return relative(APP, path)
    .split(sep)
    .join("/")
    .replace(/\.tsx$/, "");
}

const ROUTE_FILES = walk(APP).filter((p) => p.endsWith(".tsx") && !p.endsWith("_layout.tsx"));

const GUARDED_ROUTES = ROUTE_FILES.filter((p) => CALLS_GUARD.test(code(readFileSync(p, "utf8"))))
  .map(routeName)
  .sort();

/** The OS offers glass and the patient allows transparency: glass would show. */
const OFFERED = { liquidGlass: true, reduceTransparency: false } as const;

describe("the routes that hold capture protection, discovered from the source", () => {
  it("non-vacuity: the six clinical routes are found", () => {
    expect(GUARDED_ROUTES).toEqual(
      expect.arrayContaining([
        "(tabs)/records",
        "(tabs)/wellbeing",
        "(tabs)/visits/[visitId]/intake",
        "(tabs)/visits/[visitId]/issue-link",
        "(tabs)/visits/[visitId]/review",
        "(tabs)/visits/[visitId]/shares",
      ]),
    );
  });

  it("every route that calls the guard is on the list, and the list holds nothing else", () => {
    expect([...CAPTURE_PROTECTED_ROUTES].sort()).toEqual(GUARDED_ROUTES);
  });

  it("the guard's one caller outside a route is the kiosk PIN screen, which draws no glass", () => {
    const callers = walk(SRC)
      .filter((p) => /\.tsx?$/.test(p) && !/\.test\.ts$/.test(p) && !p.startsWith(APP))
      .filter((p) => CALLS_GUARD.test(code(readFileSync(p, "utf8"))))
      .map((p) => relative(SRC, p).split(sep).join("/"));
    expect(callers).toEqual(["components/KioskGate.tsx"]);
  });

  it("a route matches exactly: no prefix, no bare name, no sibling", () => {
    expect(isCaptureProtectedRoute("(tabs)/records")).toBe(true);
    expect(isCaptureProtectedRoute("(tabs)/visits/[visitId]/review")).toBe(true);
    for (const near of [
      "records",
      "(tabs)/records/extra",
      "(tabs)/visits",
      "(tabs)/visits/[visitId]",
      "(tabs)/visits/[visitId]/index",
      "(tabs)/visits/new",
      "(tabs)/today",
    ]) {
      expect(isCaptureProtectedRoute(near), near).toBe(false);
    }
  });
});

describe("a capture-protected screen never mounts a glass view", () => {
  it.each(GUARDED_ROUTES)(
    "%s is solid from its first frame, before its own protection has run",
    (route) => {
      // First frame: the window store is still empty, so the route alone
      // must decide.
      const store = createCaptureProtectionStore();
      expect(store.getSnapshot()).toBe(false);
      const mode = glassMode({
        ...OFFERED,
        captureProtected: captureScope(false, route) || store.getSnapshot(),
      });
      expect(mode).toBe("solid");
      // The nav bar over it draws neither the system material nor a blur.
      expect(navBarChrome(mode).background).toBe("solid");
    },
  );

  const GLASS_NAV_NEIGHBOURS = ["(tabs)/visits/[visitId]/index", "(tabs)/visits/new"];

  it.each(GLASS_NAV_NEIGHBOURS)(
    "near miss: %s, with the same glass nav bar and no protection, still gets glass",
    (route) => {
      const source = readFileSync(join(APP, `${route}.tsx`), "utf8");
      // The same chrome as the protected visit screens: the glass nav helper.
      expect(source).toMatch(/withGlassNav\(/);
      const mode = glassMode({ ...OFFERED, captureProtected: captureScope(false, route) });
      expect(mode).toBe("liquid");
      expect(navBarChrome(mode).background).toBe("systemMaterial");
    },
  );

  it("a scope can add protection and never remove it", () => {
    // A protected parent stays protected under any child route.
    expect(captureScope(true, "(tabs)/visits/[visitId]/index")).toBe(true);
    expect(captureScope(false, "(tabs)/visits")).toBe(false);
    expect(captureScope(false, "(tabs)/wellbeing")).toBe(true);
  });
});

describe("the window: protection outlives focus", () => {
  it("held while any screen holds it, released by the last one", () => {
    const store = createCaptureProtectionStore();
    expect(store.getSnapshot()).toBe(false);
    const records = store.hold();
    const review = store.hold();
    expect(store.getSnapshot()).toBe(true);
    review();
    expect(store.getSnapshot()).toBe(true);
    records();
    expect(store.getSnapshot()).toBe(false);
  });

  it("a release counts once: a second call cannot drop another screen's hold", () => {
    const store = createCaptureProtectionStore();
    const first = store.hold();
    store.hold();
    first();
    first();
    expect(store.getSnapshot()).toBe(true);
  });

  it("subscribers hear a change, and only a change", () => {
    const store = createCaptureProtectionStore();
    let calls = 0;
    const unsubscribe = store.subscribe(() => {
      calls += 1;
    });
    const a = store.hold();
    const b = store.hold();
    expect(calls).toBe(1);
    a();
    expect(calls).toBe(1);
    b();
    expect(calls).toBe(2);
    unsubscribe();
    store.hold();
    expect(calls).toBe(2);
  });

  it("a protected tab kept mounted behind another keeps the whole window solid", () => {
    // Records stays mounted after its first visit, and so does its
    // protection. Today's rail is then over a protected window.
    const store = createCaptureProtectionStore();
    const records = store.hold();
    const today = () =>
      glassMode({
        ...OFFERED,
        captureProtected: captureScope(false, "(tabs)/today") || store.getSnapshot(),
      });
    expect(today()).toBe("solid");
    records();
    expect(today()).toBe("liquid");
  });
});

/** A guard whose release the test settles by hand. */
function fakeGuard(store: ReturnType<typeof createCaptureProtectionStore>) {
  const seen: { heldAtPrevent: boolean | null; allowCalls: number } = {
    heldAtPrevent: null,
    allowCalls: 0,
  };
  let settle: (ok: boolean) => void = () => undefined;
  const guard: CaptureGuard = {
    prevent: () => {
      seen.heldAtPrevent = store.getSnapshot();
      return Promise.resolve();
    },
    allow: () => {
      seen.allowCalls += 1;
      return new Promise<void>((resolve, reject) => {
        settle = (ok) => (ok ? resolve() : reject(new Error("unavailable")));
      });
    },
  };
  return { guard, seen, settle: (ok: boolean) => settle(ok) };
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("protectScreen: the chrome is solid before protection, and until it is released", () => {
  it("the window is held before protection is asked for", () => {
    const store = createCaptureProtectionStore();
    const { guard, seen } = fakeGuard(store);
    protectScreen(guard, store);
    expect(seen.heldAtPrevent).toBe(true);
  });

  it("glass returns only after the release has settled", async () => {
    const store = createCaptureProtectionStore();
    const { guard, seen, settle } = fakeGuard(store);
    const cleanup = protectScreen(guard, store);
    cleanup();
    expect(seen.allowCalls).toBe(1);
    await flush();
    expect(store.getSnapshot()).toBe(true);
    settle(true);
    await flush();
    expect(store.getSnapshot()).toBe(false);
  });

  it("a release that fails still lets the window go: no glass is withheld for good", async () => {
    const store = createCaptureProtectionStore();
    const { guard, settle } = fakeGuard(store);
    protectScreen(guard, store)();
    settle(false);
    await flush();
    expect(store.getSnapshot()).toBe(false);
  });

  it("a request that fails keeps the screen solid: the declaration holds, not the OS answer", async () => {
    const store = createCaptureProtectionStore();
    const refusing: CaptureGuard = {
      prevent: () => Promise.reject(new Error("unavailable")),
      allow: () => Promise.resolve(),
    };
    const cleanup = protectScreen(refusing, store);
    await flush();
    expect(store.getSnapshot()).toBe(true);
    cleanup();
    await flush();
    expect(store.getSnapshot()).toBe(false);
  });

  it("no capture surface (web): held while mounted, released on unmount", () => {
    const store = createCaptureProtectionStore();
    const cleanup = protectScreen(null, store);
    expect(store.getSnapshot()).toBe(true);
    cleanup();
    expect(store.getSnapshot()).toBe(false);
  });
});

describe("the rail reads the route it sits over", () => {
  it("a tab with no stack of its own", () => {
    expect(focusedRoutePath("(tabs)", { name: "records" })).toBe("(tabs)/records");
    expect(focusedRoutePath("(tabs)", { name: "me/index" })).toBe("(tabs)/me/index");
  });

  it("the visits tab, through its stack to the focused screen", () => {
    const visits = {
      name: "visits",
      state: {
        index: 1,
        routes: [{ name: "[visitId]/index" }, { name: "[visitId]/shares" }],
      },
    };
    const path = focusedRoutePath("(tabs)", visits);
    expect(path).toBe("(tabs)/visits/[visitId]/shares");
    expect(isCaptureProtectedRoute(path)).toBe(true);
  });

  it("a stack whose focus is not yet known stops at the tab, and the window store decides", () => {
    const pending = { name: "visits", state: { routes: [{ name: "[visitId]/shares" }] } };
    expect(focusedRoutePath("(tabs)", pending)).toBe("(tabs)/visits");
  });
});
