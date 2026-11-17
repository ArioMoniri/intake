/**
 * INT-143 — Kiosk mode: MDM lockdown, clinic PIN, 60 s auto-wipe, privacy
 * layout.
 *
 * Acceptance (docs/backlog/issues.yaml): *"no persistence; wipe on
 * idle/background; tamper alert; large-type layout"*.
 *
 * Same split every mobile e2e spec here makes: vitest runs on `node` with no
 * renderer (apps/mobile/vitest.config.ts), so nothing below draws a screen.
 * The POLICY is pure and has its own unit test next to it
 * (src/lib/kiosk/kioskState.test.ts). What THIS file proves is the JOURNEY
 * over the pure reducer — a device provisioned as a kiosk, armed by a clinic
 * PIN, wiped between patients, and blocked with a tamper alert when its
 * lockdown breaks — plus the WIRING: that session.tsx suppresses persistence
 * and wipes in kiosk mode, that the gate reaches the native probes through a
 * lazy import, that the idle timer lives off the .tsx surface the a11y timer
 * gate polices, and that no clinic PIN is ever stored in the clear.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  decodeKioskProvisioning,
  hashClinicPin,
  initialKioskMode,
  kioskReducer,
  tamperDetected,
  verifyClinicPin,
} from "@/lib/kiosk";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

describe("INT-143 kiosk journey (pure)", () => {
  const SALT = "00112233445566778899aabbccddeeff";
  const provisioning = decodeKioskProvisioning({
    enabled: true,
    pinSalt: SALT,
    pinHash: hashClinicPin("4242", SALT, 7),
    rounds: 7,
  });

  it("a provisioned device arms only with the clinic PIN, then serves the patient", () => {
    expect(provisioning).not.toBeNull();
    const staffPin = verifyClinicPin("4242", provisioning);
    const armed = kioskReducer(initialKioskMode, { type: "arm", pinOk: staffPin });
    expect(armed.phase).toBe("armed");
  });

  it("a patient cannot leave kiosk mode — a guessed PIN never verifies", () => {
    const armed = kioskReducer(initialKioskMode, { type: "arm", pinOk: true });
    const guessed = verifyClinicPin("0000", provisioning);
    expect(guessed).toBe(false);
    expect(kioskReducer(armed, { type: "disarm", pinOk: guessed }).phase).toBe("armed");
  });

  it("a lockdown loss surfaces a tamper state, and only a restored lockdown + PIN recovers it", () => {
    const armed = kioskReducer(initialKioskMode, { type: "arm", pinOk: true });
    // the app was backgrounded / guided access exited => lockdown no longer confirmed
    expect(tamperDetected("needs_dev_build")).toBe(true);
    const tampered = kioskReducer(armed, { type: "tamper" });
    expect(tampered.phase).toBe("tampered");
    const recovered = kioskReducer(tampered, {
      type: "recover",
      pinOk: verifyClinicPin("4242", provisioning),
      lockdownOk: !tamperDetected("locked"),
    });
    expect(recovered.phase).toBe("armed");
  });
});

describe("INT-143 no persistence + wipe wiring (session.tsx source-slice)", () => {
  const session = read(SRC, "lib", "session.tsx");

  it("consults the pure kiosk policy rather than re-deciding persistence inline", () => {
    expect(session).toMatch(/from\s+["']\.\/kiosk["']/);
    expect(session).toContain("kioskSuppressesPersistence");
  });

  it("exposes a kiosk flag and a session wipe the gate can drive", () => {
    expect(session).toContain("kioskActive");
    expect(session).toContain("setKioskActive");
    expect(session).toContain("wipeSession");
  });

  it("the wipe crypto-shreds the offline drafts (no residue for the next patient)", () => {
    // the wipe path clears the in-memory notes AND reaches the INT-142 shred.
    expect(session).toMatch(/wipeSession[\s\S]{0,400}shredDrafts/);
  });

  it("holds no plaintext draft or PIN: native at-rest calls stay out of session.tsx", () => {
    expect(session).not.toContain("expo-file-system");
    expect(session).not.toContain("expo-secure-store");
  });
});

describe("INT-143 the kiosk gate (source-slice)", () => {
  const gate = read(SRC, "components", "KioskGate.tsx");

  it("gates entering AND leaving on the clinic PIN", () => {
    expect(gate).toContain("verifyClinicPin");
    // both edges go through the reducer's arm/disarm
    expect(gate).toMatch(/type:\s*["']arm["']/);
    expect(gate).toMatch(/type:\s*["']disarm["']/);
  });

  it("surfaces a tamper alert and never silently degrades", () => {
    expect(gate).toContain("tamperDetected");
    expect(gate).toMatch(/tampered/);
    // the alert is announced, not carried by layout alone (SC 4.1.3/1.4.1),
    // on both platforms: the announcer sets the live region AND posts the
    // iOS announcement (INT-362)
    expect(gate).toMatch(/<AnnouncedText\b[^>]*\btone="error"/);
  });

  it("renders the large-type privacy layout and blocks screen capture", () => {
    expect(gate).toContain("kioskFontScale");
    expect(gate).toContain("useClinicalScreenPrivacy");
  });

  it("reaches the native probes through a lazy import, so the file stays node-safe", () => {
    expect(gate).toMatch(/import\(\s*["']@?[^"']*kiosk\/nativeKiosk/);
  });

  it("owns no timer itself — the idle clock lives in the .ts adapter (a11y BK13)", () => {
    // e2e/a11y.spec.ts pins that no .tsx under app/ or components/ owns a
    // timer but otp.tsx; the 60 s idle clock therefore lives in nativeKiosk.ts.
    expect(gate).not.toMatch(/setTimeout|setInterval/);
  });

  it("resets the idle clock on interaction without an app-authored gesture (a11y BK20)", () => {
    // onTouchStart is a plain touch responder, not a PanResponder/GestureDetector,
    // so it does not trip the "no path/multipoint gesture" criterion.
    expect(gate).toContain("onTouchStart");
  });

  it("stores no clinic PIN — it verifies against the provisioned hash and forgets", () => {
    expect(gate).not.toMatch(/SecureStore|setItemAsync/);
  });
});

describe("INT-143 the native adapter fails closed in the managed runtime", () => {
  const native = read(SRC, "lib", "kiosk", "nativeKiosk.ts");

  it("reads no managed config in the managed runtime — not a kiosk until the dev build lands", () => {
    // HB-A3 / files/10 §4.7: the MDM managed-config bridge and the guided-
    // access / screen-pinning probe are a dev-build native layer. Until then
    // provisioning is absent (fail closed to a normal phone) and the lockdown
    // probe reports needs_dev_build (fail closed to a tamper on a kiosk).
    expect(native).toContain("readKioskProvisioning");
    expect(native).toContain("probeLockdown");
    expect(native).toMatch(/needs_dev_build/);
    expect(native).toMatch(/HB-A3|dev.build|dev_build/i);
  });

  it("owns the idle timer and the background/foreground signal", () => {
    expect(native).toMatch(/setTimeout|setInterval/);
    expect(native).toContain("AppState");
  });
});

describe("INT-363 the idle wipe warns first and can be extended (WCAG 2.2 SC 2.2.1)", () => {
  const gate = read(SRC, "components", "KioskGate.tsx");
  const native = read(SRC, "lib", "kiosk", "nativeKiosk.ts");

  it("the adapter hands its timer to the warning machine instead of arming the wipe itself", () => {
    // The machine (kioskState.ts, tested on a fake clock) decides when to warn
    // and when to wipe; the adapter supplies only the platform's timer.
    expect(native).toMatch(/startKioskIdleClock\(/);
    expect(native).not.toContain("KIOSK_IDLE_WIPE_MS");
    expect(native).toMatch(/extend\(\)/);
  });

  it("announces the warning assertively, as a warning rather than an error", () => {
    expect(gate).toMatch(/<AnnouncedText\b[^>]*\btone="warning"[^>]*t\("kiosk\.idle\.warning"\)/);
  });

  it("offers one action that extends, and moves the screen reader's focus onto it", () => {
    expect(gate).toMatch(/<PrimaryButton\b[^>]*ref=\{extendRef\}/);
    expect(gate).toMatch(/t\("kiosk\.idle\.extend"\)/);
    expect(gate).toMatch(/onPress=\{\(\) => watchRef\.current\?\.extend\(\)\}/);
    expect(gate).toMatch(/sendAccessibilityEvent\(\s*\w+,\s*"focus"\s*\)/);
  });

  it("hides the session behind the warning from the screen reader while it stands", () => {
    expect(gate).toMatch(/accessibilityElementsHidden=\{warned\}/);
    expect(gate).toMatch(/importantForAccessibility=\{warned \? "no-hide-descendants" : "auto"\}/);
  });

  it("with no action the same wipe runs as before — the session and its drafts are cleared", () => {
    expect(gate).toMatch(/phase === "wiped"\)\s*\{\s*wipeSession\(\);/);
    // background still wipes AND flags the tamper, warning or not
    expect(gate).toMatch(
      /onBackground:\s*\(\)\s*=>\s*\{\s*wipeSession\(\);\s*dispatch\(\{ type: "tamper" \}\)/,
    );
  });
});

describe("INT-143 mount", () => {
  it("the root layout wraps the app in the kiosk gate", () => {
    const layout = read(SRC, "app", "_layout.tsx");
    expect(layout).toContain("KioskGate");
  });
});
