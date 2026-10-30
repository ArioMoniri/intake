/**
 * INT-583 — keep this device's new-sign-in registration fresh while the
 * patient is signed in.
 *
 * Mounted by the signed-in tabs shell. It registers silently and only when
 * the permission is already granted: it never shows the system prompt (that
 * is the Cihazlarınız button's alone). The native module is reached lazily,
 * so this hook adds nothing native to whatever imports it.
 *
 * `accountId` is null for no account and for a synthetic dev account, which
 * holds no server session to register against. `sharedDevice` is kiosk mode.
 */
import { useEffect } from "react";

export function usePushRegistration(accountId: string | null, sharedDevice: boolean): void {
  useEffect(() => {
    if (accountId === null || sharedDevice) {
      return;
    }
    void import("./native")
      .then((push) => push.registerPushSilently(sharedDevice))
      .catch(() => {
        // best-effort: the next app start tries again, and nothing is shown
      });
  }, [accountId, sharedDevice]);
}
