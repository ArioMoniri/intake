/**
 * INT-143 — the device half of kiosk mode. Everything native lives here so the
 * policy (kioskState.ts) and the barrel stay node-importable; KioskGate.tsx and
 * session.tsx reach this file ONLY through a lazy `import()`, the same pattern
 * the integrity probe and the offline backend use.
 *
 * Two device capabilities kiosk mode needs are NOT available in the Expo
 * managed runtime, and both are the dev-build native layer gated on HB-A3
 * (developer accounts + EAS dev build) and filed by files/10 §4.7 as its own
 * issue:
 *
 *   1. MDM managed app configuration — iOS `com.apple.configuration.managed`
 *      (NSUserDefaults) and Android `RestrictionsManager` — which is where a
 *      clinic provisions the kiosk PIN. No Expo module reads it, so
 *      `readKioskProvisioning` returns null and the device is treated as a
 *      normal phone (fail closed: kiosk cannot be faked into existence).
 *   2. The lockdown state — iOS `UIAccessibilityIsGuidedAccessEnabled`,
 *      Android `ActivityManager.getLockTaskModeState`, or the MDM launcher's
 *      own signal. No Expo module reads it, so `probeLockdown` reports
 *      `needs_dev_build`, which `tamperDetected` treats as a tamper (fail
 *      closed: a provisioned kiosk never silently runs unlocked).
 *
 * No dev-only override, demo value or default PIN is offered here
 * (HUMAN_BLOCKERS.md Rule 2): the mechanism is wired and it fails closed with
 * the content empty until the native layer supplies the real values.
 */
import { AppState, type AppStateStatus } from "react-native";

import {
  decodeKioskProvisioning,
  startKioskIdleClock,
  type KioskIdleClock,
  type KioskIdlePhase,
  type KioskLockdown,
  type KioskProvisioning,
} from "./kioskState";

/**
 * Read the MDM-provisioned kiosk configuration. Returns null in the managed
 * runtime (no managed-config bridge). When the dev-build native module lands it
 * hands its raw value to `decodeKioskProvisioning`, which fails closed on
 * anything malformed — so this function never returns a half-built record.
 */
export async function readKioskProvisioning(): Promise<KioskProvisioning | null> {
  const raw = await readManagedConfig();
  return decodeKioskProvisioning(raw);
}

/**
 * The managed-config source. No Expo module exposes MDM AppConfig, so there is
 * nothing to read in this runtime; the dev-build native module replaces this.
 */
async function readManagedConfig(): Promise<unknown> {
  return null;
}

/**
 * Probe the device lockdown. `needs_dev_build` is the honest managed-runtime
 * answer — Guided Access / lock-task state is native-only — and it fails closed
 * to a tamper on a provisioned kiosk.
 */
export async function probeLockdown(): Promise<KioskLockdown> {
  return "needs_dev_build";
}

/**
 * A running kiosk watch: `touch()` restarts the idle clock, `extend()` is the
 * warning's one action, `stop()` tears everything down.
 */
export type KioskWatch = KioskIdleClock;

/**
 * Watch for the two wipe triggers. The platform timer lives HERE, in a `.ts`
 * module: e2e/a11y.spec.ts BK13 keeps timers out of screens and components,
 * and requires a time limit's timer to be the one it hands to its warning
 * machine (INT-363, WCAG 2.2 SC 2.2.1). The machine — `startKioskIdleClock` in
 * kioskState.ts, tested on a fake clock — decides everything; this file only
 * supplies `Date.now` and the one-shot timer.
 *
 * - `onIdlePhase("warning")` fires after 40 s without a touch: show and
 *   announce the warning. `onIdlePhase("active")` follows a touch or the
 *   extend action. `onIdlePhase("wiped")` fires when the warning has stood its
 *   full 20 s unanswered: wipe the session, stay armed for the next patient.
 * - `onBackground` fires when the app leaves the foreground — wipe AND flag a
 *   tamper, because a locked-down kiosk should not be backgroundable. No
 *   warning precedes it: leaving the app is not a time limit.
 */
export function watchKiosk(handlers: {
  onIdlePhase: (phase: KioskIdlePhase) => void;
  onBackground: () => void;
}): KioskWatch {
  const clock = startKioskIdleClock(handlers.onIdlePhase, {
    now: () => Date.now(),
    schedule: (fire: () => void, delayMs: number) => setTimeout(fire, delayMs),
    cancel: (handle: ReturnType<typeof setTimeout>) => clearTimeout(handle),
  });

  const onAppState = (status: AppStateStatus): void => {
    if (status === "background" || status === "inactive") {
      handlers.onBackground();
    }
  };

  const subscription = AppState.addEventListener("change", onAppState);

  return {
    touch() {
      clock.touch();
    },
    extend() {
      clock.extend();
    },
    stop() {
      clock.stop();
      subscription.remove();
    },
  };
}
