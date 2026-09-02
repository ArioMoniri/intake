/**
 * Device-integrity signal (INT-131, files/10 §4: jailbreak/root detection
 * as a SOFT signal — degrade to typed mode + warn, never a hard block).
 *
 * expo-device's isRootedExperimentalAsync is the honest ceiling of what a
 * managed runtime can see (basic root/jailbreak artefacts). A thorough
 * checker (Play Integrity verdicts, App Attest, frida/hook detection) needs
 * the dev-build native layer — where this probe is unavailable the state is
 * reported as needs_dev_build, the same honest pattern as INT-208 health.
 */
import * as Device from "expo-device";
import { Platform } from "react-native";

import type { DeviceIntegrity } from "./integrityState";

export { voiceAllowedForIntegrity, type DeviceIntegrity } from "./integrityState";

export async function checkDeviceIntegrity(): Promise<DeviceIntegrity> {
  if (Platform.OS !== "ios" && Platform.OS !== "android") {
    return "needs_dev_build";
  }
  try {
    const rooted = await Device.isRootedExperimentalAsync();
    return rooted ? "compromised" : "ok";
  } catch {
    return "needs_dev_build";
  }
}
