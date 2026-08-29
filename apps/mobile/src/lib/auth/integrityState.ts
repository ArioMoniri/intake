/**
 * Device-integrity state (INT-131) — pure and node-testable; the probe that
 * fills it lives in integrity.ts (expo-bound). Kept apart so session state
 * stays importable in node tests without native modules.
 */

export type DeviceIntegrity = "ok" | "compromised" | "unknown" | "needs_dev_build";

/** The intake rule (10 §4): voice only on a device the signal does not
 * flag. Unknown states stay voice-eligible — the signal is soft; only a
 * positive flag degrades to typed + warn. */
export function voiceAllowedForIntegrity(state: DeviceIntegrity): boolean {
  return state !== "compromised";
}
