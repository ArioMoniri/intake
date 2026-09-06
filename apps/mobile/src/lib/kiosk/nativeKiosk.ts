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
  KIOSK_IDLE_WIPE_MS,
  decodeKioskProvisioning,
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

/** A running kiosk watch: `touch()` resets the idle clock; `stop()` tears down. */
export interface KioskWatch {
  touch(): void;
  stop(): void;
}

/**
 * Watch for the two wipe triggers. The idle clock (a timer) lives HERE, in a
 * `.ts` module, on purpose: e2e/a11y.spec.ts BK13 pins that no `.tsx` under
 * app/ or components/ owns a timer but otp.tsx, so the 60 s idle wipe cannot
 * sit in the gate component.
 *
 * - `onIdle` fires KIOSK_IDLE_WIPE_MS after the last `touch()` — wipe the
 *   session, stay armed for the next patient.
 * - `onBackground` fires when the app leaves the foreground — wipe AND flag a
 *   tamper, because a locked-down kiosk should not be backgroundable.
 */
export function watchKiosk(handlers: { onIdle: () => void; onBackground: () => void }): KioskWatch {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const armTimer = (): void => {
    if (timer !== null) {
      clearTimeout(timer);
    }
    timer = setTimeout(handlers.onIdle, KIOSK_IDLE_WIPE_MS);
  };

  const onAppState = (status: AppStateStatus): void => {
    if (status === "background" || status === "inactive") {
      handlers.onBackground();
    }
  };

  const subscription = AppState.addEventListener("change", onAppState);
  armTimer();

  return {
    touch() {
      armTimer();
    },
    stop() {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      subscription.remove();
    },
  };
}
