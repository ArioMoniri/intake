/**
 * Where capture protection is in force, as the glass policy needs to know it
 * (INT-477; ADR-039 amendment, owner, 4 Oct 2026: "solid").
 *
 * Liquid Glass was unreliable on the capture-protected screens (INT-131's
 * expo-screen-capture guard) and the cause is not known (docs/evidence/
 * INT-466.md, INT-472.md). The owner chose solid chrome there. Two answers
 * make that hold at every moment:
 *
 * - **The route.** A protected screen is solid from its first frame. Its own
 *   guard runs in an effect, after its first frame has committed, so the
 *   navigators scope each screen by its route name (`captureScope`) and the
 *   tab rail reads the route it sits over (`focusedRoutePath`). The route list
 *   is checked against the source (captureProtection.test.ts): every route
 *   that calls `useClinicalScreenPrivacy()` is on it, and nothing else is.
 * - **The window.** Protection is window-wide and can outlive focus: a tab
 *   screen stays mounted after its first visit and keeps its protection. While
 *   any screen holds it, every glass surface in the window is solid. The guard
 *   holds the window before it asks the OS for protection, and lets go only
 *   after the release has settled (`protectScreen`).
 *
 * Pure, with no React Native import, so the whole policy is node-testable.
 * The device half is lib/auth/screenPrivacy.ts.
 */

/**
 * Routes that hold capture protection, named by their path under `src/app`
 * without the extension, exactly as the navigators name them (the same names
 * lib/motion/transitions takes).
 */
export const CAPTURE_PROTECTED_ROUTES: ReadonlySet<string> = new Set([
  "(tabs)/records",
  "(tabs)/wellbeing",
  "(tabs)/visits/[visitId]/intake",
  "(tabs)/visits/[visitId]/issue-link",
  "(tabs)/visits/[visitId]/review",
  "(tabs)/visits/[visitId]/shares",
]);

/** Exact match: no prefix, no bare name. */
export function isCaptureProtectedRoute(route: string): boolean {
  return CAPTURE_PROTECTED_ROUTES.has(route);
}

/**
 * A scope's answer: its parent's, or its own route's. A scope can add
 * protection and can never remove it.
 */
export function captureScope(outer: boolean, route: string): boolean {
  return outer || isCaptureProtectedRoute(route);
}

/** A navigator route, as much of it as the focus walk needs. */
export interface RouteNode {
  readonly name: string;
  readonly state?: {
    readonly index?: number;
    readonly routes: readonly RouteNode[];
  };
}

/**
 * The focused route's path under a group: `(tabs)` + `visits` +
 * `[visitId]/shares` → `(tabs)/visits/[visitId]/shares`. A nested stack whose
 * focus is not yet known stops the walk at its parent; the window store then
 * decides, from the screen's own guard.
 */
export function focusedRoutePath(group: string, route: RouteNode): string {
  const names = [route.name];
  let nested = route.state;
  while (nested !== undefined && typeof nested.index === "number") {
    const child = nested.routes[nested.index];
    if (child === undefined) {
      break;
    }
    names.push(child.name);
    nested = child.state;
  }
  return [group, ...names].join("/");
}

/** Whether a protected screen holds the window, for useSyncExternalStore. */
export interface CaptureProtectionStore {
  /** Hold the window; the returned release counts once, however often called. */
  hold(): () => void;
  subscribe(listener: () => void): () => void;
  getSnapshot(): boolean;
}

export function createCaptureProtectionStore(): CaptureProtectionStore {
  let holders = 0;
  /** One entry per subscription, so the same callback twice counts twice. */
  const subscriptions = new Set<{ readonly listener: () => void }>();

  function publish(): void {
    for (const { listener } of [...subscriptions]) {
      listener();
    }
  }

  return {
    hold() {
      holders += 1;
      if (holders === 1) {
        publish();
      }
      let held = true;
      return () => {
        if (!held) {
          return;
        }
        held = false;
        holders -= 1;
        if (holders === 0) {
          publish();
        }
      };
    },
    subscribe(listener) {
      const entry = { listener };
      subscriptions.add(entry);
      return () => {
        subscriptions.delete(entry);
      };
    },
    getSnapshot() {
      return holders > 0;
    },
  };
}

/** The app's one window store: the screen guard holds it, the glass reads it. */
export const captureProtection: CaptureProtectionStore = createCaptureProtectionStore();

/** The OS capture guard, as protectScreen needs it. */
export interface CaptureGuard {
  prevent(): Promise<void>;
  allow(): Promise<void>;
}

/** A guard call that throws synchronously still settles as a rejection. */
function settle(call: () => Promise<void>): Promise<void> {
  try {
    return call();
  } catch (error) {
    return Promise.reject(error);
  }
}

/**
 * Protect a mounted screen; the returned cleanup releases it.
 *
 * The window is held before protection is asked for, so the chrome is solid
 * before the window is protected. It is let go only after the release has
 * settled, so glass never returns to a window that is still protected. With
 * no guard (no capture surface, as on web) the screen is still held: the
 * declaration decides the chrome, not the OS answer. A refused request keeps
 * the hold for the same reason; a refused release still lets go, so glass is
 * never withheld for good.
 */
export function protectScreen(
  guard: CaptureGuard | null,
  store: CaptureProtectionStore,
): () => void {
  const release = store.hold();
  if (guard === null) {
    return release;
  }
  settle(() => guard.prevent()).catch(() => undefined);
  return () => {
    settle(() => guard.allow())
      .catch(() => undefined)
      .finally(release);
  };
}
