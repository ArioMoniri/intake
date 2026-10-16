/**
 * A RED holds every haptic (INT-551; ADR-033 Q2's fail-closed default, motion
 * S-3; files/02 §5.3; lib/motion/hapticGate.ts).
 *
 * The gate already knows what a RED means for a haptic: `presentRed` holds
 * every request while an ALERT or CALM takeover stands, and a SILENT RED makes
 * silence permanent, because a buzz on the table is the cue 02 §5.3 names.
 * Until INT-551 nothing told the gate a RED was there, so a server-confirmed
 * success could still be felt under a takeover, and haptics went on after a
 * SILENT RED.
 *
 * This is the one caller: a subscriber on the app's RED store, mounted once by
 * the root layout. It follows the register the patient is shown:
 * - ALERT, CALM: presented to the gate, so every haptic is held while it stands;
 * - SILENT: the session is marked silent, which nothing clears;
 * - no RED, or DEFERRED_CLINICIAN (the patient's screen is unchanged): nothing.
 *
 * It runs inside the store's notify pass, synchronously, and the gate loads no
 * engine for it, so it adds no wait to the RED's first paint. It reads the
 * trigger's register, never the screen model, so it cannot throw into the pass
 * that also notifies the RED layer. Pure: the store and the gate are passed
 * in, and hapticHold.test.ts drives the real ones.
 */
import type { HapticGate } from "../motion/hapticGate";
import type { RedStore } from "./store";

type ShownRegister = "ALERT" | "CALM" | "SILENT";

/** Follow the store until the returned function is called (on unmount). */
export function holdHapticsUnderRed(
  store: Pick<RedStore, "getSnapshot" | "subscribe">,
  gate: Pick<HapticGate, "presentRed" | "markSilentOrThirdParty">,
): () => void {
  let shown: ShownRegister | null = null;
  let release: (() => void) | null = null;

  const follow = () => {
    const state = store.getSnapshot();
    const register =
      state !== null && state.trigger.register !== "DEFERRED_CLINICIAN"
        ? state.trigger.register
        : null;
    if (register === shown) {
      return;
    }
    shown = register;
    const previous = release;
    release = null;
    if (register === "SILENT") {
      gate.markSilentOrThirdParty();
    } else if (register !== null) {
      release = gate.presentRed(register);
    }
    // The new hold is in place before the old one goes: no gap between them.
    previous?.();
  };

  follow();
  const unsubscribe = store.subscribe(follow);
  return () => {
    unsubscribe();
    release?.();
    release = null;
  };
}
