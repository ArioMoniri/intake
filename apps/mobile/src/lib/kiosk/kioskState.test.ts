/**
 * INT-143 — kiosk-mode policy (pure half).
 *
 * The whole clinic-device policy is a set of pure functions plus one reducer so
 * it is provable in node with no device: the 60-second idle wipe, the wipe on
 * background, the tamper rule that fails closed, the clinic-PIN verification
 * that fails closed when nothing is provisioned, the large-type floor and the
 * no-persistence decision. The native halves (managed-config read, guided-
 * access / screen-pinning probe, the real setTimeout, AppState) live in
 * nativeKiosk.ts behind a lazy import and are not exercised here.
 *
 * INT-363 adds the idle warning (WCAG 2.2 SC 2.2.1): the pure warn/extend/wipe
 * machine, and the clock that drives it, run here on a fake clock. The adapter
 * only hands that clock the platform's timer.
 */
import { describe, expect, it } from "vitest";

import {
  CLINIC_PIN_MAX_LENGTH,
  CLINIC_PIN_MIN_LENGTH,
  KIOSK_IDLE_WARNING_MS,
  KIOSK_IDLE_WIPE_MS,
  KIOSK_MAX_PIN_FAILURES,
  decodeKioskProvisioning,
  hashClinicPin,
  initialKioskMode,
  isKioskProvisioned,
  isWellFormedPin,
  kioskFontScale,
  kioskIdleDue,
  kioskIdleReducer,
  kioskIdleStart,
  kioskReducer,
  kioskSuppressesPersistence,
  mustWipeOn,
  pinLockedOut,
  startKioskIdleClock,
  tamperDetected,
  verifyClinicPin,
  type KioskIdlePhase,
  type KioskIdleState,
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
    const record = {
      enabled: true,
      pinSalt: salt,
      pinHash: hashClinicPin("7788", salt, 5),
      rounds: 5,
    };
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
    const tampered = kioskReducer(kioskReducer(initialKioskMode, { type: "arm", pinOk: true }), {
      type: "tamper",
    });
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

/* ------------------------------------------------------------------ */
/* INT-363 — WCAG 2.2 SC 2.2.1 Timing Adjustable: warn, then extend    */
/* ------------------------------------------------------------------ */

/**
 * WCAG 2.2 SC 2.2.1, the "Extend" option: the user is warned before time
 * expires and given at least 20 seconds to extend the time limit with a simple
 * action, and may extend it at least ten times. Written out here rather than
 * imported, so the constant under test cannot vouch for itself.
 */
const WCAG_EXTEND_FLOOR_MS = 20_000;
const WCAG_MIN_EXTENSIONS = 10;

const T = KIOSK_IDLE_WIPE_MS;
const W = KIOSK_IDLE_WARNING_MS;

/**
 * The fake clock: advance the pure machine to `to`, firing a tick at each
 * moment it comes due — exactly what the adapter's one-shot timer does — and
 * record every phase it enters on the way.
 */
function advance(
  state: KioskIdleState,
  to: number,
): { state: KioskIdleState; entered: [KioskIdlePhase, number][] } {
  const entered: [KioskIdlePhase, number][] = [];
  let current = state;
  for (let due = kioskIdleDue(current); due !== null && due <= to; due = kioskIdleDue(current)) {
    const next = kioskIdleReducer(current, { type: "tick", at: due });
    if (next.phase !== current.phase) {
      entered.push([next.phase, due]);
    }
    current = next;
  }
  return { state: current, entered };
}

describe("the idle warning — WCAG 2.2 SC 2.2.1 (INT-363)", () => {
  it("gives at least the 20 seconds SC 2.2.1 names, and the wipe still falls at 60 s", () => {
    expect(W).toBeGreaterThanOrEqual(WCAG_EXTEND_FLOOR_MS);
    expect(T).toBe(60_000);
    // the warning must come after some real use, not with the first touch
    expect(T - W).toBeGreaterThan(0);
    expect(T - W).toBeGreaterThanOrEqual(W);
  });

  it("warns at T − W and not a millisecond before", () => {
    const start = kioskIdleStart(0);
    expect(kioskIdleDue(start)).toBe(T - W);
    const early = kioskIdleReducer(start, { type: "tick", at: T - W - 1 });
    expect(early).toBe(start); // an early timer changes nothing; the adapter re-arms
    const warned = kioskIdleReducer(start, { type: "tick", at: T - W });
    expect(warned).toEqual({ phase: "warning", since: T - W });
  });

  it("with no action the wipe falls at T — the old 60 s — and only after the warning", () => {
    const { state, entered } = advance(kioskIdleStart(0), 10 * T);
    expect(entered).toEqual([
      ["warning", T - W],
      ["wiped", T],
    ]);
    expect(state.phase).toBe("wiped");
  });

  it("the grace runs from when the warning is SHOWN, so a late timer cannot shorten it", () => {
    const late = T - W + 7_000; // the JS thread was busy when the warning came due
    const warned = kioskIdleReducer(kioskIdleStart(0), { type: "tick", at: late });
    expect(warned).toEqual({ phase: "warning", since: late });
    expect(kioskIdleReducer(warned, { type: "tick", at: late + W - 1 }).phase).toBe("warning");
    expect(kioskIdleReducer(warned, { type: "tick", at: late + W }).phase).toBe("wiped");
  });

  it("one action — extend — returns to active and restarts the full timeout", () => {
    const warned = advance(kioskIdleStart(0), T - W).state;
    expect(warned.phase).toBe("warning");
    const at = T - W + 12_000;
    const extended = kioskIdleReducer(warned, { type: "extend", at });
    expect(extended).toEqual({ phase: "active", since: at });
    // the next warning is a whole T − W away, and the wipe a whole T
    expect(advance(extended, at + 10 * T).entered).toEqual([
      ["warning", at + T - W],
      ["wiped", at + T],
    ]);
  });

  it("can be extended again and again — ten times and more, never wiping", () => {
    let state = kioskIdleStart(0);
    for (let round = 0; round < WCAG_MIN_EXTENSIONS + 2; round += 1) {
      const due = kioskIdleDue(state)!;
      const step = advance(state, due);
      expect(step.entered).toEqual([["warning", due]]);
      // the patient answers in the grace's very last millisecond
      const lastMoment = due + W - 1;
      expect(advance(step.state, lastMoment).state.phase).toBe("warning");
      state = kioskIdleReducer(step.state, { type: "extend", at: lastMoment });
      expect(state.phase).toBe("active");
    }
  });

  it("a touch anywhere during the warning counts too — the patient is plainly here", () => {
    const warned = advance(kioskIdleStart(0), T - W).state;
    expect(kioskIdleReducer(warned, { type: "activity", at: T - 1 })).toEqual({
      phase: "active",
      since: T - 1,
    });
  });

  it("ordinary use keeps the clock from ever warning", () => {
    let state = kioskIdleStart(0);
    for (let at = 5_000; at <= 10 * T; at += 5_000) {
      state = advance(state, at).state;
      state = kioskIdleReducer(state, { type: "activity", at });
      expect(state.phase).toBe("active");
    }
  });

  it("after the wipe nothing is due until the next patient touches the screen", () => {
    const wiped = advance(kioskIdleStart(0), T).state;
    expect(wiped.phase).toBe("wiped");
    expect(kioskIdleDue(wiped)).toBeNull();
    expect(kioskIdleReducer(wiped, { type: "tick", at: 100 * T })).toBe(wiped);
    const next = kioskIdleReducer(wiped, { type: "activity", at: 100 * T });
    expect(next).toEqual({ phase: "active", since: 100 * T });
    expect(kioskIdleDue(next)).toBe(100 * T + T - W);
  });
});

/** A hand-cranked stand-in for setTimeout / clearTimeout / Date.now. */
function fakeTimers() {
  let now = 0;
  let nextId = 1;
  const pending = new Map<number, { at: number; fire: () => void }>();
  return {
    timers: {
      now: () => now,
      schedule: (fire: () => void, delayMs: number) => {
        const id = nextId;
        nextId += 1;
        pending.set(id, { at: now + delayMs, fire });
        return id;
      },
      cancel: (id: number) => {
        pending.delete(id);
      },
    },
    /** Move the clock to `to`, firing every timer that comes due on the way, in order. */
    tick(to: number) {
      for (;;) {
        const due = [...pending.entries()]
          .filter(([, p]) => p.at <= to)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (due === undefined) {
          break;
        }
        pending.delete(due[0]);
        now = due[1].at;
        due[1].fire();
      }
      now = to;
    },
    armed: () => pending.size,
  };
}

describe("the idle clock the adapter runs — the machine on a fake clock (INT-363)", () => {
  it("reports the warning at T − W and the wipe at T, each once", () => {
    const clock = fakeTimers();
    const phases: [KioskIdlePhase, number][] = [];
    startKioskIdleClock((phase) => phases.push([phase, clock.timers.now()]), clock.timers);
    clock.tick(T - W - 1);
    expect(phases).toEqual([]);
    clock.tick(T);
    expect(phases).toEqual([
      ["warning", T - W],
      ["wiped", T],
    ]);
    clock.tick(10 * T);
    expect(phases).toHaveLength(2);
    expect(clock.armed()).toBe(0); // nothing is left running after the wipe
  });

  it("extend during the warning returns to active and re-arms the full timeout", () => {
    const clock = fakeTimers();
    const phases: KioskIdlePhase[] = [];
    const idle = startKioskIdleClock((phase) => phases.push(phase), clock.timers);
    clock.tick(T - W + 15_000);
    idle.extend();
    expect(phases).toEqual(["warning", "active"]);
    clock.tick(T - W + 15_000 + T - W - 1);
    expect(phases).toEqual(["warning", "active"]);
    clock.tick(T - W + 15_000 + T);
    expect(phases).toEqual(["warning", "active", "warning", "wiped"]);
  });

  it("a touch restarts the clock without announcing anything", () => {
    const clock = fakeTimers();
    const phases: KioskIdlePhase[] = [];
    const idle = startKioskIdleClock((phase) => phases.push(phase), clock.timers);
    clock.tick(T - W - 1);
    idle.touch();
    clock.tick(2 * (T - W) - 2);
    expect(phases).toEqual([]);
    expect(clock.armed()).toBe(1); // re-armed, never stacked
  });

  it("stop tears the timer down, so a stopped clock can never wipe", () => {
    const clock = fakeTimers();
    const phases: KioskIdlePhase[] = [];
    const idle = startKioskIdleClock((phase) => phases.push(phase), clock.timers);
    idle.stop();
    expect(clock.armed()).toBe(0);
    idle.touch();
    idle.extend();
    clock.tick(10 * T);
    expect(phases).toEqual([]);
  });
});
