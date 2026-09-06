/**
 * INT-143 — kiosk-mode policy (the pure half).
 *
 * A clinic runs the same Expo app on a shared waiting-room device in "kiosk
 * mode": entering and leaving it are gated by a staff-held clinic PIN, the
 * session is wiped after 60 s idle and whenever the app is backgrounded, no
 * draft or answer is written to disk, the layout is large-type for a device
 * read at arm's length, and a lockdown that breaks raises a tamper alert
 * rather than degrading silently (files/10 §4, §9 "Check-in / kiosk";
 * files/06 §6; docs/security/threat-model.md `kiosk`).
 *
 * Everything here is pure and node-testable — no react-native, no expo, no
 * clock — the same split lib/prefs/appearance.ts and lib/auth/integrityState.ts
 * make. The native halves (the MDM managed-config read that provisions the
 * PIN, the guided-access / screen-pinning probe, the idle timer and the
 * AppState listener) live in nativeKiosk.ts behind a lazy import, and both
 * fail closed until the dev-build native layer exists (HB-A3; files/10 §4.7).
 *
 * NO value here is invented (CLAUDE.md invariant 17, HUMAN_BLOCKERS.md Rule 1):
 * the clinic PIN is provisioned per clinic through MDM as a salted hash, never
 * a literal in this repo, and with nothing provisioned every gate refuses.
 */
import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex, hexToBytes, utf8ToBytes } from "@noble/ciphers/utils.js";

import { LARGE_TEXT_SCALE } from "../prefs/appearance";

/**
 * The idle auto-wipe interval. 60 s is the title's number and files/10 §4's
 * ("session auto-wipe after 60 s idle"): long enough that a patient reading a
 * question is not interrupted, short enough that the next patient never
 * inherits the last one's data.
 */
export const KIOSK_IDLE_WIPE_MS = 60_000;

/** A clinic PIN is 4–12 digits; the length is provisioned per clinic. */
export const CLINIC_PIN_MIN_LENGTH = 4;
export const CLINIC_PIN_MAX_LENGTH = 12;

/**
 * KDF rounds for the provisioned PIN hash. This is NOT the primary control — a
 * numeric PIN's key space is tiny, so brute force is bounded by `pinFailures`
 * backoff and by the device being MDM-locked, not by the KDF. The hash exists
 * so the clear PIN is never stored on the device or in this repo; the rounds
 * are carried in the provisioning record so a clinic can raise them without a
 * code change.
 */
export const KIOSK_PIN_KDF_ROUNDS = 4096;

/** Failed PIN attempts after which the gate refuses further tries until reset. */
export const KIOSK_MAX_PIN_FAILURES = 5;

/**
 * The lockdown signal from the device (native probe fills it): iOS Guided
 * Access, Android screen pinning / lock-task, or an MDM kiosk launcher.
 * `needs_dev_build` is the honest managed-runtime ceiling — no native probe
 * exists — and it is treated as a tamper, never as "probably fine".
 */
export type KioskLockdown = "locked" | "unlocked" | "unknown" | "needs_dev_build";

/**
 * The kiosk provisioning read from MDM managed config. `null` means the device
 * is not a kiosk (a normal phone), which is the managed-runtime default.
 */
export interface KioskProvisioning {
  readonly enabled: boolean;
  /** Hex salt for the PIN hash (≥ 16 hex chars = 8 bytes). */
  readonly pinSalt: string;
  /** Hex SHA-256 hash (64 chars) of the salted, iterated PIN. */
  readonly pinHash: string;
  /** KDF iteration count the hash was produced with. */
  readonly rounds: number;
}

/** A digits-only PIN whose length is in the provisioned range. */
export function isWellFormedPin(pin: string): boolean {
  return new RegExp(`^[0-9]{${CLINIC_PIN_MIN_LENGTH},${CLINIC_PIN_MAX_LENGTH}}$`).test(pin);
}

/**
 * Salted, iterated SHA-256 of a PIN → hex. Deterministic for the same
 * (pin, salt, rounds); the salt is mixed in first so the same PIN under two
 * clinics produces two hashes. `@noble/hashes` is the pure-JS family the auth
 * and offline paths already use, so it behaves identically in node and on the
 * device.
 */
export function hashClinicPin(pin: string, saltHex: string, rounds: number): string {
  let digest = sha256(concat(hexToBytes(saltHex), utf8ToBytes(pin)));
  for (let i = 1; i < rounds; i += 1) {
    digest = sha256(digest);
  }
  return bytesToHex(digest);
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

/** Constant-time comparison of two equal-length hex strings. */
function timingSafeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

/**
 * Verify an entered PIN against the provisioned hash.
 *
 * FAILS CLOSED: with no provisioning (the managed-runtime state — no MDM
 * config to read) this always returns false, so kiosk mode can neither be
 * armed nor left, and never on a guessed or defaulted value (HUMAN_BLOCKERS.md
 * Rule 1 / Rule 2). A malformed entry is rejected before hashing.
 */
export function verifyClinicPin(entered: string, provisioning: KioskProvisioning | null): boolean {
  if (provisioning === null || !provisioning.enabled) {
    return false;
  }
  if (!isWellFormedPin(entered)) {
    return false;
  }
  const candidate = hashClinicPin(entered, provisioning.pinSalt, provisioning.rounds);
  return timingSafeEqualHex(candidate, provisioning.pinHash);
}

/** Whether this device is provisioned to run as a kiosk at all. */
export function isKioskProvisioned(provisioning: KioskProvisioning | null): boolean {
  return provisioning !== null && provisioning.enabled;
}

/**
 * Decode a managed-config value into a provisioning record, or `null` when it
 * is absent, disabled or malformed — fail closed to "not a kiosk device"
 * rather than half-arming one. Accepts a parsed object or a JSON string, since
 * MDM AppConfig delivers either depending on platform.
 */
export function decodeKioskProvisioning(raw: unknown): KioskProvisioning | null {
  let value: unknown = raw;
  if (typeof value === "string") {
    if (value.trim().length === 0) {
      return null;
    }
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  if (record.enabled !== true) {
    return null;
  }
  const { pinSalt, pinHash, rounds } = record;
  if (typeof pinSalt !== "string" || !/^[0-9a-f]{16,}$/i.test(pinSalt)) {
    return null;
  }
  if (typeof pinHash !== "string" || !/^[0-9a-f]{64}$/i.test(pinHash)) {
    return null;
  }
  if (typeof rounds !== "number" || !Number.isInteger(rounds) || rounds < 1 || rounds > 1_000_000) {
    return null;
  }
  return { enabled: true, pinSalt, pinHash, rounds };
}

/**
 * Tamper detection. A provisioned kiosk must sit under a confirmed lockdown;
 * anything short of `locked` — unlocked, unknown, or unprobeable — is a tamper
 * and must raise the alert. There is deliberately no "assume fine" branch:
 * failing open here is exactly the harm the alert exists to prevent.
 */
export function tamperDetected(lockdown: KioskLockdown): boolean {
  return lockdown !== "locked";
}

/**
 * The kiosk text scale: a floor at the large-text form threshold
 * (`LARGE_TEXT_SCALE`, 1.6 — the same number lib/prefs/appearance.ts uses to
 * switch a screen's FORM), rising with the OS/app setting but never below it.
 * INT-136 measured 52/248 Turkish labels overflowing the row at the largest
 * step, so screens must already survive this size; a shared standing device
 * read at arm's length always runs there.
 */
export function kioskFontScale(baseScale: number): number {
  return Math.max(baseScale, LARGE_TEXT_SCALE);
}

/**
 * No persistence in kiosk mode: while the kiosk is active the offline draft
 * store is bypassed entirely, so no answer or draft reaches disk (invariant 3
 * reinforced for the typed draft, invariant 6 no ids in logs). session.tsx
 * reads this rather than re-deciding inline.
 */
export function kioskSuppressesPersistence(kioskActive: boolean): boolean {
  return kioskActive;
}

/** Lifecycle events the native adapter reports up to the gate. */
export type KioskActivity = "idle" | "background" | "foreground" | "interaction";

/**
 * The two activities that must wipe the session so the next patient inherits
 * nothing: the 60 s idle timeout, and the app being backgrounded (files/10 §4
 * pairs the background event with the tamper alert, because a locked-down
 * kiosk should not be backgroundable at all).
 */
export function mustWipeOn(activity: KioskActivity): boolean {
  return activity === "idle" || activity === "background";
}

/** The kiosk lifecycle. `off` = normal app (staff mode); `armed` = patient
 * kiosk session; `tampered` = lockdown lost, blocked behind an alert. */
export type KioskPhase = "off" | "armed" | "tampered";

export interface KioskModeState {
  readonly phase: KioskPhase;
  readonly pinFailures: number;
}

export const initialKioskMode: KioskModeState = { phase: "off", pinFailures: 0 };

export type KioskEvent =
  | { type: "arm"; pinOk: boolean }
  | { type: "disarm"; pinOk: boolean }
  | { type: "tamper" }
  | { type: "recover"; pinOk: boolean; lockdownOk: boolean };

/**
 * The kiosk state machine. Every phase transition that leaves or enters the
 * patient-facing state runs through a PIN check the caller has already
 * performed with `verifyClinicPin`; a failed check counts toward lockout and
 * changes nothing else. A tamper can interrupt an armed session at any time;
 * recovery requires BOTH a correct PIN and a restored lockdown, so a staff
 * member cannot dismiss the alert without the device actually being re-locked.
 */
export function kioskReducer(state: KioskModeState, event: KioskEvent): KioskModeState {
  switch (event.type) {
    case "arm":
      if (state.phase !== "off") {
        return state;
      }
      return event.pinOk
        ? { phase: "armed", pinFailures: 0 }
        : { ...state, pinFailures: state.pinFailures + 1 };
    case "disarm":
      if (state.phase !== "armed") {
        return state;
      }
      return event.pinOk
        ? { phase: "off", pinFailures: 0 }
        : { ...state, pinFailures: state.pinFailures + 1 };
    case "tamper":
      return state.phase === "armed" ? { ...state, phase: "tampered" } : state;
    case "recover":
      if (state.phase !== "tampered") {
        return state;
      }
      return event.pinOk && event.lockdownOk
        ? { phase: "armed", pinFailures: 0 }
        : { ...state, pinFailures: state.pinFailures + 1 };
    default:
      return state;
  }
}

/** Too many failed PIN attempts: the gate refuses further tries until reset. */
export function pinLockedOut(state: KioskModeState): boolean {
  return state.pinFailures >= KIOSK_MAX_PIN_FAILURES;
}
