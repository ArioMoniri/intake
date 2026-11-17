/**
 * INT-614 — the iOS Info.plist App Review reads, as Expo resolves it.
 *
 * INT-613 (docs/release/app-store-readiness.md rows 21–23) introspected the
 * config and found three things the source files did not show:
 *
 * 1. `NSFaceIDUsageDescription` carried Expo's English default. The app does
 *    use Face ID (src/lib/auth/biometrics.ts gates app open and the note
 *    review screen), so the key stays and carries a true Turkish string.
 * 2. `NSPhotoLibraryUsageDescription` was present, added by expo-image-picker's
 *    auto-applied plugin, but the app never opens the photo library: the
 *    records screen calls `launchCameraAsync` only (INT-138). The key goes.
 * 3. `UIBackgroundModes` held `audio`. withVoiceAudio strips it, but
 *    expo-audio's own mod (`enableBackgroundPlayback` defaults to true) runs
 *    after and adds it back. The product intends no background audio: INT-103
 *    is "background pauses safely", and the session discards the microphone
 *    the moment the app leaves the foreground (INT-559). So expo-audio is told
 *    not to add it, and the strip stays as a second fence.
 *
 * The source of truth here is the resolved config, not app.json: the same
 * `expo config --type introspect` that INT-613 read, run offline. A purpose
 * string in that output for a capability no production source calls is the
 * finding guideline 5.1.1 asks about, so every key must name its call site.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { beforeAll, describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const EXPO = join(MOBILE, "node_modules", ".bin", "expo");

type InfoPlist = Record<string, unknown>;

/**
 * Every purpose string the resolved Info.plist may carry, and the production
 * call that justifies it. A key absent from this map fails; a key whose call
 * site is gone fails too.
 */
const CALL_SITE: Record<string, RegExp> = {
  NSMicrophoneUsageDescription: /\bAudioModule\.requestRecordingPermissionsAsync\(/,
  NSCameraUsageDescription: /\bImagePicker\.launchCameraAsync\(/,
  NSFaceIDUsageDescription: /\bLocalAuthentication\.authenticateAsync\(/,
  NSHealthShareUsageDescription: /\bhk\.requestAuthorization\(/,
  // ITMS-90683 (INT-592): required once the HealthKit library is linked,
  // although the app requests no write type. Its call site is the linkage.
  NSHealthUpdateUsageDescription: /@kingstinct\/react-native-healthkit/,
};

/** The photo-library family: no production source reads or writes the library. */
const PHOTO_LIBRARY_KEYS = [
  "NSPhotoLibraryUsageDescription",
  "NSPhotoLibraryAddUsageDescription",
] as const;

function productionSources(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      out.push(...productionSources(path));
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      out.push(
        readFileSync(path, "utf8")
          .replace(/\/\*[\s\S]*?\*\//g, "")
          .replace(/\/\/.*$/gm, ""),
      );
    }
  }
  return out;
}

function purposeKeys(plist: InfoPlist): string[] {
  return Object.keys(plist)
    .filter((key) => key.startsWith("NS") && key.endsWith("UsageDescription"))
    .sort();
}

const catalogue = (locale: "tr" | "en") =>
  JSON.parse(readFileSync(join(SRC, "locales", `app-${locale}.json`), "utf8")) as Record<
    string,
    string
  >;

let plist: InfoPlist = {};
let code = "";

beforeAll(() => {
  if (!existsSync(EXPO)) {
    throw new Error(
      `${EXPO} is missing: the resolved config needs the workspace installed (pnpm install --frozen-lockfile).`,
    );
  }
  const stdout = execFileSync(EXPO, ["config", "--type", "introspect", "--json"], {
    cwd: MOBILE,
    env: { ...process.env, CI: "1", EXPO_NO_TELEMETRY: "1", EXPO_OFFLINE: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 16 * 1024 * 1024,
  }).toString("utf8");
  plist = (JSON.parse(stdout) as { ios: { infoPlist: InfoPlist } }).ios.infoPlist;
  code = productionSources(SRC).join("\n");
}, 120_000);

describe("INT-614: the resolved iOS Info.plist", () => {
  it("carries a purpose string only for a capability a production source calls", () => {
    const keys = purposeKeys(plist);
    expect(keys.filter((key) => !(key in CALL_SITE))).toEqual([]);
    for (const key of keys) {
      expect(CALL_SITE[key]?.test(code), `${key} has no call site`).toBe(true);
    }
  });

  it("has no photo-library key, because nothing opens the library", () => {
    for (const key of PHOTO_LIBRARY_KEYS) {
      expect(plist[key], key).toBeUndefined();
    }
    // Near miss: the camera key stays, since the records screen photographs
    // a report through the camera, not the library.
    expect(plist.NSCameraUsageDescription).toBeTypeOf("string");
    expect(code).not.toMatch(/\blaunchImageLibraryAsync\(|\brequestMediaLibraryPermissionsAsync\(/);
    expect(code).not.toMatch(/from "expo-media-library"/);
  });

  it("declares no background audio or VoIP mode", () => {
    const modes = plist.UIBackgroundModes;
    const list = Array.isArray(modes) ? (modes as string[]) : [];
    expect(list).not.toContain("audio");
    expect(list).not.toContain("voip");
  });

  it("puts the Turkish Face ID string in the base Info.plist, not Expo's English default", () => {
    const faceId = plist.NSFaceIDUsageDescription;
    expect(faceId).toBe(catalogue("tr").NSFaceIDUsageDescription);
    expect(String(faceId)).not.toMatch(/\$\(PRODUCT_NAME\)|^Allow /);
  });

  it("states what Face ID gates and that the app never sees the face data", () => {
    const tr = catalogue("tr").NSFaceIDUsageDescription ?? "";
    const en = catalogue("en").NSFaceIDUsageDescription ?? "";
    expect(tr.startsWith("Önvizit ")).toBe(true);
    expect(en.startsWith("Önvizit ")).toBe(true);
    expect(tr).toMatch(/Face ID/);
    expect(tr).toMatch(/görmez/);
    expect(en).toMatch(/never sees/);
    // siz register only (CLAUDE.md patient copy): no bare `sen` forms.
    expect(tr).not.toMatch(/(?<!\p{L})(sen|seni|senin)(?!\p{L})/u);
    // No overclaim: passkeys (D36, INT-582) are not built yet, and the
    // biometric match never leaves the operating system.
    expect(`${tr} ${en}`).not.toMatch(/passkey|geçiş anahtar|sunucu|server|saklar|stores/i);
  });
});
