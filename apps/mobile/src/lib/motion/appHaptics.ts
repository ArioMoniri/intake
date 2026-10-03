/**
 * The app's one haptic gate (INT-340, MOTION-11), over the device adapter.
 *
 * The adapter (native/hapticsEngine.ts) is loaded lazily, on the first request
 * the gate lets through, so this module stays safe to import from anything a
 * node test imports — lib/profile/store.ts reports a third party through it.
 *
 * Who talks to it:
 * - a handler: `haptic(event, request)`, one line beside the state change it
 *   acknowledges, never awaited;
 * - a press whose outcome the server confirms later: `appHaptics.action()`,
 *   passed on to the `success` request;
 * - every owner of the microphone or the voice session: `appHaptics.register`
 *   in a mount effect, released on unmount;
 * - the companion declaration: `appHaptics.markSilentOrThirdParty()`;
 * - the RED layer (INT-135): `appHaptics.presentRed(register)` while it shows.
 */
import { createHapticGate, type HapticGate, type HapticRequest } from "./hapticGate";
import type { HapticEvent } from "./haptics";

export const appHaptics: HapticGate = createHapticGate({
  loadEngine: () => import("./native/hapticsEngine").then((native) => native.hapticsEngine),
});

/** Ask for one haptic. Fire and forget: the visual never waits on it. */
export function haptic(event: HapticEvent, request: HapticRequest): void {
  void appHaptics.request(event, request);
}
