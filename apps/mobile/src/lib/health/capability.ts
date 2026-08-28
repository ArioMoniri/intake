/**
 * Capability detection (INT-200), kept pure so the fallback matrix is
 * unit-testable in node: which connector serves this runtime, and whether
 * the patient's device-local health consent is on. The Expo Go rule is the
 * load-bearing one — native health modules cannot exist there, so the stub
 * answers `needs_dev_build` instead of crashing on a missing module.
 */
import type { ConsentState } from "../dev/accounts";

export type ConnectorKind = "expo_go_stub" | "healthkit" | "health_connect" | "unsupported";

/** The two runtime facts the decision needs; wiring injects the real ones. */
export interface RuntimeEnvironment {
  /** Platform.OS at the call site. */
  readonly os: string;
  /** Constants.executionEnvironment: "storeClient" is Expo Go. */
  readonly executionEnvironment: string;
}

export function selectConnectorKind(env: RuntimeEnvironment): ConnectorKind {
  if (env.os !== "ios" && env.os !== "android") {
    return "unsupported";
  }
  if (env.executionEnvironment === "storeClient") {
    return "expo_go_stub";
  }
  return env.os === "ios" ? "healthkit" : "health_connect";
}

/**
 * The section gate: health data is read only after the patient's explicit
 * device-local consent (invariant 4 posture — every read checks a scope).
 */
export function healthConsentOn(consents: ConsentState | null): boolean {
  return consents?.health === true;
}
