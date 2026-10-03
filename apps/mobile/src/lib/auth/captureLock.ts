/**
 * The clinical capture lock (INT-478, GitHub #820; files/10 §4 MASVS:
 * FLAG_SECURE / screenshot blocking on clinical screens, INT-131).
 *
 * OS-level capture protection stays active while any protected screen is
 * mounted, and is released only when the last one goes. Every protected
 * screen used to pass expo-screen-capture the same key, and the library keeps
 * a set of keys, so the first protected screen to unmount released protection
 * for all of them: closing the doctor-link issue screen left the share centre
 * under it capturable. The lock counts the screens itself. It asks the OS once
 * for the first and releases once after the last.
 *
 * Pure, with no React Native import, so it is node-testable. The device half
 * is lib/auth/screenPrivacy.ts.
 */

/** The OS capture guard. */
export interface CaptureGuard {
  prevent(): Promise<void>;
  allow(): Promise<void>;
}

export interface CaptureLock {
  /** Hold protection for one screen; the returned release counts once. */
  acquire(): () => void;
  /** Whether any screen holds protection. */
  held(): boolean;
}

/**
 * Send one guard call. A runtime without the module (web, Expo Go) refuses,
 * by rejection or by a synchronous throw; either is a no-op, never a crash.
 * The count is the lock's own, so a refusal never changes it.
 */
function send(call: () => Promise<void>): void {
  try {
    call().catch(() => undefined);
  } catch {
    // capability-detect: unavailable in this runtime
  }
}

export function createCaptureLock(guard: CaptureGuard): CaptureLock {
  let holders = 0;
  return {
    acquire() {
      holders += 1;
      if (holders === 1) {
        send(() => guard.prevent());
      }
      let held = true;
      return () => {
        if (!held) {
          return;
        }
        held = false;
        holders -= 1;
        if (holders === 0) {
          send(() => guard.allow());
        }
      };
    },
    held() {
      return holders > 0;
    },
  };
}
