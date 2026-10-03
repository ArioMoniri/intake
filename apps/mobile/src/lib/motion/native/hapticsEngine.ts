/**
 * INT-340: the device half of the haptic policy (MOTION-11). It plays one
 * `HapticCall` that `hapticFor` (../haptics.ts) has already decided; every
 * rule about whether to play lives there and in ../hapticGate.ts, where the
 * node suite can hold it.
 *
 * This is the only file in the app that reaches the haptics module, and it
 * does so through a lazy `import()`, so no node-tested path can pull the
 * native module in. ../appHaptics.ts reaches this file the same way.
 * e2e/motion.spec.ts pins both.
 *
 * - iOS plays the UIFeedbackGenerator calls, which stay silent when the
 *   patient turns System Haptics off.
 * - Android plays View.performHapticFeedback alone. It follows the phone's
 *   touch-feedback setting and needs no VIBRATE permission, which the build
 *   blocks (app.config.ts). The module's other three calls drive the
 *   Vibrator on Android, so they are never made there.
 * - A call built for the other platform is refused rather than translated.
 *
 * The caller never awaits this before rendering, and the gate swallows any
 * rejection (an Android below API 30/34 refuses the newer constants).
 */
import { Platform } from "react-native";

import type { HapticEngine } from "../hapticGate";
import type {
  AndroidHapticCall,
  AndroidHapticType,
  HapticCall,
  HapticPlatform,
  IosHapticCall,
} from "../haptics";

type HapticsModule = typeof import("expo-haptics");

let loaded: Promise<HapticsModule> | null = null;

function hapticsModule(): Promise<HapticsModule> {
  loaded ??= import("expo-haptics");
  return loaded;
}

const platform: HapticPlatform =
  Platform.OS === "ios" ? "ios" : Platform.OS === "android" ? "android" : "other";

async function playIos(m: HapticsModule, call: IosHapticCall): Promise<void> {
  switch (call.method) {
    case "selectionAsync":
      return m.selectionAsync();
    case "impactAsync":
      return m.impactAsync(m.ImpactFeedbackStyle.Light);
    case "notificationAsync":
      return m.notificationAsync(m.NotificationFeedbackType.Success);
  }
}

/** Each policy value, as the module's own enum member: a rename fails `tsc` here. */
function androidType(m: HapticsModule, type: AndroidHapticType) {
  const types = {
    "segment-tick": m.AndroidHaptics.Segment_Tick,
    "toggle-on": m.AndroidHaptics.Toggle_On,
    "toggle-off": m.AndroidHaptics.Toggle_Off,
    "context-click": m.AndroidHaptics.Context_Click,
    confirm: m.AndroidHaptics.Confirm,
  } satisfies Record<AndroidHapticType, unknown>;
  return types[type];
}

async function playAndroid(m: HapticsModule, call: AndroidHapticCall): Promise<void> {
  await m.performAndroidHapticsAsync(androidType(m, call.type));
}

export const hapticsEngine: HapticEngine = {
  platform,
  async play(call: HapticCall): Promise<void> {
    if (call.platform !== platform) {
      return;
    }
    const m = await hapticsModule();
    if (call.platform === "ios") {
      await playIos(m, call);
    } else {
      await playAndroid(m, call);
    }
  },
};
