/**
 * Biometric gate primitives (INT-131, files/10 §2: biometric gate on app
 * open and before note/share screens) — capability-detected so Expo Go and
 * devices without biometrics degrade gracefully: the gate passes through
 * where no factor EXISTS (nothing to gate with), and blocks only when a
 * present factor refuses. Uses expo-local-authentication.
 */
import * as LocalAuthentication from "expo-local-authentication";
import { Platform } from "react-native";

export type BiometricCapability = "available" | "unenrolled" | "unavailable";

export async function biometricCapability(): Promise<BiometricCapability> {
  if (Platform.OS !== "ios" && Platform.OS !== "android") {
    return "unavailable";
  }
  try {
    if (!(await LocalAuthentication.hasHardwareAsync())) {
      return "unavailable";
    }
    return (await LocalAuthentication.isEnrolledAsync()) ? "available" : "unenrolled";
  } catch {
    return "unavailable";
  }
}

export type GateResult = "granted" | "denied" | "no_factor";

/** Prompt where a factor exists; report honestly where none does. */
export async function requireBiometric(prompt: string): Promise<GateResult> {
  if ((await biometricCapability()) !== "available") {
    return "no_factor";
  }
  try {
    const result = await LocalAuthentication.authenticateAsync({ promptMessage: prompt });
    return result.success ? "granted" : "denied";
  } catch {
    return "denied";
  }
}
