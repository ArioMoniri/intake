/**
 * Onboarding & auth acceptance (INT-131), pinned as source facts — the same
 * technique as nav.spec.ts: the file tree and the call sites ARE the
 * security posture, so a screen dropped, a token moved out of SecureStore or
 * a FLAG_SECURE call deleted fails here before any device run would notice.
 *
 * Pins (issue acceptance, verbatim): "OTP limits per 10 §2; App Attest/Play
 * Integrity on OTP+session; refresh rotation with reuse detection; biometric
 * gate; clinical screens FLAG_SECURE; jailbreak -> typed+warn".
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const APP = join(__dirname, "..", "src", "app");
const SRC = join(__dirname, "..", "src");
const ROOT = join(__dirname, "..");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

describe("onboarding flow (02 §4: welcome → phone → otp)", () => {
  it("phone and otp screens exist as routes", () => {
    expect(() => read(APP, "(auth)/phone.tsx")).not.toThrow();
    expect(() => read(APP, "(auth)/otp.tsx")).not.toThrow();
  });

  it("welcome offers the real phone sign-in as the primary path", () => {
    const welcome = read(APP, "(auth)/welcome.tsx");
    expect(welcome).toContain("/(auth)/phone");
    // the dev accounts stay a __DEV__-only secondary path (INT-197 tier)
    expect(welcome).toContain("__DEV__ ?");
  });

  it("the OTP entry is one masked field per register, six registers", () => {
    const otp = read(APP, "(auth)/otp.tsx");
    expect(otp).toContain("OTP_LENGTH");
    const lib = read(SRC, "lib", "auth", "phone.ts");
    expect(lib).toContain("OTP_LENGTH = 6");
    expect(otp).toContain("secureTextEntry");
    // INT-361 (SC 3.3.8): one digit per register is kept by the entry state,
    // not by a field cap. The platform applies maxLength before onChangeText
    // sees the text, so a cap of one cut every paste and the OS code autofill
    // down to its first digit.
    expect(otp).not.toMatch(/maxLength=/);
    expect(otp).toContain("value={digit}");
    expect(otp).toContain("enterOtp(digits, index, ");
  });

  it("phone entry states why the number is asked (02 §8.2) from tr keys", () => {
    const phone = read(APP, "(auth)/phone.tsx");
    expect(phone).toContain('t("auth.phone.why")');
    const tr = read(SRC, "lib", "i18n", "tr.ts");
    for (const key of [
      "auth.phone.title",
      "auth.phone.why",
      "auth.otp.title",
      "auth.otp.resend",
      "auth.error.generic",
      "auth.error.limited",
      "auth.integrity.warnBody",
      "auth.biometric.prompt",
    ]) {
      expect(tr).toContain(`"${key}"`);
    }
    // en mirrors tr key-for-key via the i18n test; pin one key here anyway
    expect(read(SRC, "lib", "i18n", "en.ts")).toContain('"auth.phone.why"');
  });
});

describe("token custody (10 §2: SecureStore, never AsyncStorage)", () => {
  it("refresh tokens go through expo-secure-store", () => {
    const store = read(SRC, "lib", "auth", "tokens.ts");
    expect(store).toContain('from "expo-secure-store"');
    expect(store).toContain("refresh");
  });

  it("no AsyncStorage anywhere in the app source", () => {
    for (const file of walk(SRC)) {
      if (!/\.(ts|tsx)$/.test(file)) continue;
      expect(read(file), file).not.toContain("async-storage");
      expect(read(file), file).not.toContain("AsyncStorage");
    }
  });

  it("the DPoP proof key is device-held (noble P-256) and never leaves", () => {
    const dpop = read(SRC, "lib", "auth", "dpop.ts");
    expect(dpop).toContain("@noble/curves");
    expect(dpop).toContain("p256");
    // the private scalar is stored only in SecureStore
    expect(dpop).toContain("SecureStore");
  });

  it("the api client sends attestation on request AND verify (session start)", () => {
    const client = read(SRC, "lib", "auth", "api.ts");
    expect(client).toContain("X-Intake-Attestation");
    expect(client).toMatch(/otp\/request/);
    expect(client).toMatch(/otp\/verify/);
    expect(client).toMatch(/token\/refresh/);
    expect(client).toContain("DPoP");
  });
});

describe("clinical screens: FLAG_SECURE / screenshot blocking", () => {
  const clinical = [
    "(tabs)/visits/[visitId]/intake.tsx",
    "(tabs)/visits/[visitId]/review.tsx",
    "(tabs)/records.tsx",
    "(tabs)/wellbeing.tsx",
  ];

  it.each(clinical)("%s calls the screen-privacy guard", (route) => {
    expect(read(APP, route)).toContain("useClinicalScreenPrivacy()");
  });

  it("the guard is expo-screen-capture behind a capability detect", () => {
    const guard = read(SRC, "lib", "auth", "screenPrivacy.ts");
    expect(guard).toContain("expo-screen-capture");
    expect(guard).toContain("preventScreenCaptureAsync");
    expect(guard).toContain("allowScreenCaptureAsync");
  });
});

describe("biometric gate (10 §2: app open + note/share screens)", () => {
  it("the gate wraps the signed-in shell", () => {
    const layout = read(APP, "(tabs)/_layout.tsx");
    expect(layout).toContain("BiometricGate");
  });

  it("review (note/share) re-gates", () => {
    const review = read(APP, "(tabs)/visits/[visitId]/review.tsx");
    expect(review).toContain("BiometricGate");
  });

  it("capability-detected: no hardware or no enrolment degrades gracefully", () => {
    const biometrics = read(SRC, "lib", "auth", "biometrics.ts");
    expect(biometrics).toContain("expo-local-authentication");
    expect(biometrics).toContain("hasHardwareAsync");
    expect(biometrics).toContain("isEnrolledAsync");
  });
});

describe("jailbreak/root → typed + warn (soft signal, 10 §4)", () => {
  it("integrity signal comes from expo-device where available", () => {
    const integrity = read(SRC, "lib", "auth", "integrity.ts");
    expect(integrity).toContain("expo-device");
    expect(integrity).toContain("isRootedExperimentalAsync");
    // honesty: states that a native checker needs a dev build
    expect(integrity).toContain("needs_dev_build");
  });

  it("a compromised device forces the typed lane in the intake", () => {
    const intake = read(APP, "(tabs)/visits/[visitId]/intake.tsx");
    expect(intake).toContain("voiceAllowedForIntegrity(integrity)");
    expect(intake).toContain("!integrityCompromised");
    expect(intake).toContain('t("auth.integrity.warnBody")');
  });
});

describe("certificate pinning: wired for the next dev build, never claimed in Go", () => {
  it("the config plugin is registered in app.json", () => {
    const appJson = JSON.parse(read(ROOT, "app.json")) as {
      expo: { plugins: unknown[] };
    };
    const plugins = JSON.stringify(appJson.expo.plugins);
    expect(plugins).toContain("withCertificatePinning");
  });

  it("the plugin exists and emits pins only when pins are configured", () => {
    const plugin = read(ROOT, "plugins", "withCertificatePinning.js");
    expect(plugin).toContain("network_security_config");
    expect(plugin).toContain("NSPinnedDomains");
    expect(plugin).toMatch(/pins/);
  });

  it("runtime capability module never claims pinning in Expo Go", () => {
    const capability = read(SRC, "lib", "auth", "pinning.ts");
    expect(capability).toContain("expoGo");
    expect(capability).not.toContain("active: true");
  });
});

describe("consent gating of the shell is untouched by auth work", () => {
  it("wellbeing stays behind visibleTabs + Tabs.Protected", () => {
    const layout = read(APP, "(tabs)/_layout.tsx");
    expect(layout).toContain("visibleTabs(consents)");
    expect(layout).toMatch(/Tabs\.Protected guard=\{tabs\.includes\("wellbeing"\)\}/);
  });

  it("otp sign-in grants NO consents (they arrive with INT-132, in context)", () => {
    const session = read(SRC, "lib", "session.tsx");
    expect(session).toMatch(
      /core: false,\s*voice: false,\s*wellbeing: false,\s*documents: false,\s*health: false/,
    );
  });
});
