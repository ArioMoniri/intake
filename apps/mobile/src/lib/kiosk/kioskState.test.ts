/**
 * INT-143 — kiosk-mode policy (pure half).
 *
 * The whole clinic-device policy is a set of pure functions plus one reducer so
 * it is provable in node with no device: the 60-second idle wipe, the wipe on
 * background, the tamper rule that fails closed, the clinic-PIN verification
 * that fails closed when nothing is provisioned, the large-type floor and the
 * no-persistence decision. The native halves (managed-config read, guided-
 * access / screen-pinning probe, the idle timer, AppState) live in
 * nativeKiosk.ts behind a lazy import and are not exercised here.
 */
import { describe, expect, it } from "vitest";

import {
  CLINIC_PIN_MAX_LENGTH,
  CLINIC_PIN_MIN_LENGTH,
  KIOSK_IDLE_WIPE_MS,
  KIOSK_MAX_PIN_FAILURES,
  decodeKioskProvisioning,
  hashClinicPin,
  initialKioskMode,
  isKioskProvisioned,
  isWellFormedPin,
  kioskFontScale,
  kioskReducer,
  kioskSuppressesPersistence,
  mustWipeOn,
  pinLockedOut,
  tamperDetected,
  verifyClinicPin,
  type KioskProvisioning,
} from "./kioskState";
import { LARGE_TEXT_SCALE } from "../prefs/appearance";

/** Build a provisioning record for a known PIN, the way an MDM provisioning
 * tool would — a salted, iterated hash, never the PIN itself. */
function provisionFor(pin: string, saltHex = "0011223344556677", rounds = 3): KioskProvisioning {
  return { enabled: true, pinSalt: saltHex, pinHash: hashClinicPin(pin, saltHex, rounds), rounds };
}

describe("the auto-wipe interval", () => {
  it("is 60 seconds, matching the title and files/10 §4", () => {
    expect(KIOSK_IDLE_WIPE_MS).toBe(60_000);
  });
});

describe("wipe triggers (acceptance: wipe on idle/background)", () => {
  it("wipes on idle and on background — the two triggers that clear the last patient", () => {
    expect(mustWipeOn("idle")).toBe(true);
    expect(mustWipeOn("background")).toBe(true);
  });

  it("does not wipe on foreground or ordinary interaction", () => {
    expect(mustWipeOn("foreground")).toBe(false);
    expect(mustWipeOn("interaction")).toBe(false);
  });
});

describe("no persistence in kiosk mode (invariant 3/6 reinforced)", () => {
  it("suppresses draft persistence exactly while kiosk is active", () => {
    expect(kioskSuppressesPersistence(true)).toBe(true);
    expect(kioskSuppressesPersistence(false)).toBe(false);
  });
});

describe("tamper detection fails closed (acceptance: tamper alert, no silent degrade)", () => {
  it("only a confirmed lockdown clears the alert", () => {
    expect(tamperDetected("locked")).toBe(false);
  });

  it("an unlocked, unknown or unprobeable device is a tamper — never a silent pass", () => {
    expect(tamperDetected("unlocked")).toBe(true);
    expect(tamperDetected("unknown")).toBe(true);
    // the managed-runtime ceiling: no native probe available => treated as tamper
    expect(tamperDetected("needs_dev_build")).toBe(true);
  });
});

describe("clinic PIN (acceptance: entering/leaving gated, not patient-reachable)", () => {
  it("accepts only a well-formed numeric PIN in range", () => {
    expect(isWellFormedPin("1234")).toBe(true);
    expect(isWellFormedPin("12".repeat(CLINIC_PIN_MAX_LENGTH))).toBe(false); // too long
    expect(isWellFormedPin("1".repeat(CLINIC_PIN_MIN_LENGTH - 1))).toBe(false); // too short
    expect(isWellFormedPin("12a4")).toBe(false); // non-digit
    expect(isWellFormedPin(" 1234 ")).toBe(false); // whitespace
    expect(isWellFormedPin("")).toBe(false);
  });

  it("hashing is deterministic and salt-bound", () => {
    expect(hashClinicPin("1234", "aabbccddeeff0011", 3)).toBe(
      hashClinicPin("1234", "aabbccddeeff0011", 3),
    );
    expect(hashClinicPin("1234", "aabbccddeeff0011", 3)).not.toBe(
      hashClinicPin("1234", "ffeeddccbbaa0011", 3),
    );
    // the PIN never appears in its own hash
    expect(hashClinicPin("1234", "aabbccddeeff0011", 3)).not.toContain("1234");
  });

  it("verifies the right PIN against a provisioned hash and rejects the wrong one", () => {
    const provisioning = provisionFor("2468");
    expect(verifyClinicPin("2468", provisioning)).toBe(true);
    expect(verifyClinicPin("2469", provisioning)).toBe(false);
    expect(verifyClinicPin("24680", provisioning)).toBe(false);
  });

  it("FAILS CLOSED when nothing is provisioned — nobody enters or leaves without a real PIN", () => {
    // The core rule the whole feature rests on: with no provisioned PIN
    // (the managed-runtime state — no MDM config to read) verification always
    // fails, so kiosk mode can neither be armed nor left, and never on a
    // guessed value.
    expect(verifyClinicPin("2468", null)).toBe(false);
    expect(verifyClinicPin("", null)).toBe(false);
    expect(verifyClinicPin("0000", null)).toBe(false);
  });
});

describe("provisioning decode fails closed", () => {
  it("treats an absent or non-kiosk config as 'not a kiosk device'", () => {
    expect(decodeKioskProvisioning(null)).toBeNull();
    expect(decodeKioskProvisioning(undefined)).toBeNull();
    expect(decodeKioskProvisioning("")).toBeNull();
    expect(decodeKioskProvisioning({})).toBeNull();
    expect(decodeKioskProvisioning({ enabled: false })).toBeNull();
    expect(isKioskProvisioned(null)).toBe(false);
  });

  it("refuses a malformed record rather than half-arming a kiosk", () => {
    expect(decodeKioskProvisioning({ enabled: true })).toBeNull(); // no pin material
    expect(
      decodeKioskProvisioning({ enabled: true, pinSalt: "short", pinHash: "x", rounds: 3 }),
    ).toBeNull();
    expect(
      decodeKioskProvisioning({
        enabled: true,
        pinSalt: "00112233445566778899aabb",
        pinHash: "nothex",
        rounds: 3,
      }),
    ).toBeNull();
    expect(
      decodeKioskProvisioning({
        enabled: true,
        pinSalt: "00112233445566778899aabb",
        pinHash: "a".repeat(64),
        rounds: 0,
      }),
    ).toBeNull();
  });

  it("accepts a well-formed record (object or JSON string) and round-trips its PIN", () => {
    const salt = "00112233445566778899aabbccddeeff";
    const record = { enabled: true, pinSalt: salt, pinHash: hashClinicPin("7788", salt, 5), rounds: 5 };
    const fromObject = decodeKioskProvisioning(record);
    expect(fromObject).not.toBeNull();
    expect(isKioskProvisioned(fromObject)).toBe(true);
    expect(verifyClinicPin("7788", fromObject)).toBe(true);

    const fromString = decodeKioskProvisioning(JSON.stringify(record));
    expect(verifyClinicPin("7788", fromString)).toBe(true);
  });
});

describe("large-type privacy layout (acceptance: large-type layout)", () => {
  it("runs at no less than the large-text form threshold, whatever the base scale", () => {
    // INT-136 measured 52/248 Turkish labels overflowing at the largest step;
    // a shared standing kiosk is read from farther away, so it floors at the
    // large-text threshold and rises with the OS/app setting, never below it.
    expect(kioskFontScale(1.0)).toBe(LARGE_TEXT_SCALE);
    expect(kioskFontScale(0.9)).toBe(LARGE_TEXT_SCALE);
    expect(kioskFontScale(2.0)).toBe(2.0);
    expect(kioskFontScale(LARGE_TEXT_SCALE)).toBe(LARGE_TEXT_SCALE);
  });
});

describe("the kiosk-mode reducer — PIN gates entering and leaving", () => {
  it("starts off", () => {
    expect(initialKioskMode.phase).toBe("off");
    expect(initialKioskMode.pinFailures).toBe(0);
  });

  it("arms only on a correct clinic PIN", () => {
    const armed = kioskReducer(initialKioskMode, { type: "arm", pinOk: true });
    expect(armed.phase).toBe("armed");
    expect(armed.pinFailures).toBe(0);
  });

  it("a wrong PIN does not arm, and counts toward lockout", () => {
    const still = kioskReducer(initialKioskMode, { type: "arm", pinOk: false });
    expect(still.phase).toBe("off");
    expect(still.pinFailures).toBe(1);
  });

  it("leaving kiosk mode needs the PIN too — a patient cannot disarm it", () => {
    const armed = kioskReducer(initialKioskMode, { type: "arm", pinOk: true });
    const patientTries = kioskReducer(armed, { type: "disarm", pinOk: false });
    expect(patientTries.phase).toBe("armed");
    const staffLeaves = kioskReducer(armed, { type: "disarm", pinOk: true });
    expect(staffLeaves.phase).toBe("off");
  });

  it("a lockdown loss while armed moves to tampered, never a silent degrade", () => {
    const armed = kioskReducer(initialKioskMode, { type: "arm", pinOk: true });
    const tampered = kioskReducer(armed, { type: "tamper" });
    expect(tampered.phase).toBe("tampered");
  });

  it("recovery from tampered needs BOTH the PIN and a restored lockdown", () => {
    const tampered = kioskReducer(
      kioskReducer(initialKioskMode, { type: "arm", pinOk: true }),
      { type: "tamper" },
    );
    expect(kioskReducer(tampered, { type: "recover", pinOk: true, lockdownOk: false }).phase).toBe(
      "tampered",
    );
    expect(kioskReducer(tampered, { type: "recover", pinOk: false, lockdownOk: true }).phase).toBe(
      "tampered",
    );
    expect(kioskReducer(tampered, { type: "recover", pinOk: true, lockdownOk: true }).phase).toBe(
      "armed",
    );
  });

  it("locks out after too many failed attempts", () => {
    let state = initialKioskMode;
    for (let i = 0; i < KIOSK_MAX_PIN_FAILURES; i += 1) {
      state = kioskReducer(state, { type: "arm", pinOk: false });
    }
    expect(pinLockedOut(state)).toBe(true);
    expect(pinLockedOut(initialKioskMode)).toBe(false);
  });
});
