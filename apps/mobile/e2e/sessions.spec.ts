/**
 * INT-583 acceptance, pinned as source facts (the me.spec.ts technique): a
 * rendered assertion needs a device, so what is proved here is the wiring —
 * the screen is reachable, the device registers for new-sign-in notices
 * without a cold prompt, signing out drops the registration, and the copy
 * holds the catalogue's register. The behaviour of the pieces is proved next
 * to them, in src/lib/push/*.test.ts and src/lib/sessions/*.test.ts.
 *
 * D35: a sign-in from a new device is told to the patient's earlier devices
 * by push, never by SMS. The notice's words are the server's; nothing here
 * writes one.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr, type MessageKey } from "../src/lib/i18n/tr";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const TREE: { name: string; source: string }[] = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test."))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

const SCREEN = "src/app/(tabs)/me/sessions.tsx";
const LAYOUT = "src/app/(tabs)/_layout.tsx";
const NATIVE = "src/lib/push/native.ts";

const SESSION_KEYS = (Object.keys(tr) as MessageKey[]).filter(
  (key) => key === "me.sessions" || key.startsWith("sessions.") || key.startsWith("a11y.sessions."),
);

describe("Cihazlarınız is a real, reachable screen", () => {
  it("has a route, registered in the tabs layout and in the nav map", () => {
    expect(file(SCREEN)).toContain("export default");
    expect(file(LAYOUT)).toContain('name="me/sessions"');
    expect(readFileSync(join(__dirname, "nav.spec.ts"), "utf8")).toContain(
      '"(tabs)/me/sessions.tsx"',
    );
  });

  it("Profilim carries the entry row", () => {
    const me = file("src/app/(tabs)/me/index.tsx");
    expect(me).toContain('router.push("/(tabs)/me/sessions")');
    expect(me).toContain('t("me.sessions")');
  });

  it("the screen reads and writes the server's sessions through the signed-in fetch", () => {
    expect(file(SCREEN)).toContain("createSessionsApi(authedFetch)");
    const api = file("src/lib/sessions/api.ts");
    for (const route of [
      '"/v1/auth/sessions"',
      '"/v1/auth/sessions/sign-out-others"',
      "`/v1/auth/sessions/${",
    ]) {
      expect(api).toContain(route);
    }
  });

  it("fits the file-size rule the constitution sets", () => {
    for (const name of [SCREEN, NATIVE, "src/lib/sessions/model.ts", "src/lib/sessions/api.ts"]) {
      expect(file(name).split("\n").length, name).toBeLessThan(500);
    }
  });
});

describe("registration: never a cold prompt", () => {
  it("the signed-in shell registers silently, and only for a phone-verified account", () => {
    const layout = file(LAYOUT);
    expect(layout).toContain("usePushRegistration(");
    expect(layout).toMatch(/kind === "otp"/);
  });

  it("the silent path never asks; only the enable path does", () => {
    const native = file(NATIVE);
    const silent = native.slice(native.indexOf("export function registerPushSilently"));
    expect(silent.slice(0, silent.indexOf("\n}"))).toContain("asked: false");
    const enable = native.slice(native.indexOf("export function enablePush"));
    expect(enable.slice(0, enable.indexOf("\n}"))).toContain("asked: true");
  });

  it("the enable path is reached from the screen's button and from nowhere else", () => {
    const callers = TREE.filter((f) => f.name !== NATIVE && f.source.includes("enablePush(")).map(
      (f) => f.name,
    );
    expect(callers).toEqual([SCREEN]);
    expect(file(SCREEN)).toMatch(/onPress=\{[^}]*enable/);
  });

  it("the shell's hook reaches the native module lazily", () => {
    const hook = file("src/lib/push/usePushRegistration.ts");
    expect(hook).toMatch(/import\(\s*["']\.\/native["']\s*\)/);
    expect(hook).not.toMatch(/^import .* from ["']\.\/native["']/m);
  });

  it("the system prompt is requested in one place", () => {
    const callers = TREE.filter((f) => f.source.includes("requestPermissionsAsync")).map(
      (f) => f.name,
    );
    expect(callers).toEqual([NATIVE]);
  });
});

describe("signing out drops this device's registration", () => {
  it("sign-out reaches the unregister lazily, so the provider stays node-importable", () => {
    const session = file("src/lib/session.tsx");
    const signOut = session.slice(session.indexOf("const signOut"));
    const body = signOut.slice(0, signOut.indexOf("}, []);"));
    expect(body).toMatch(/import\(\s*["']\.\/push\/native["']\s*\)/);
    expect(body).toContain("forgetPushRegistration");
  });

  it("the unregister deletes the server's token and clears the stop on unbound sessions", () => {
    const native = file(NATIVE);
    const forget = native.slice(native.indexOf("export async function forgetPushRegistration"));
    const body = forget.slice(0, forget.indexOf("\n}"));
    expect(body).toContain("resetPushRegistration()");
    expect(body).toContain("deletePushToken(authedFetch)");
  });
});

describe("copy: tr source of truth, en mirror, B1 siz register", () => {
  it("the block exists in both catalogues", () => {
    expect(SESSION_KEYS.length).toBeGreaterThan(10);
    for (const key of SESSION_KEYS) {
      expect(en[key], key).toBeDefined();
      expect(tr[key].trim().length, key).toBeGreaterThan(0);
    }
  });

  it("no sen forms and no technical words a patient would have to look up", () => {
    for (const key of SESSION_KEYS) {
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
      expect(tr[key], key).not.toMatch(/push|token|apns|expo|oturum açma|session/iu);
    }
  });

  it("calm, not alarming: no alarm words in the Turkish copy", () => {
    for (const key of SESSION_KEYS) {
      expect(tr[key], key).not.toMatch(/tehlike|saldır|hack|acil|uyarı|!/iu);
    }
  });

  it("the block is appended at the end of each catalogue under its issue id", () => {
    for (const name of ["tr.ts", "en.ts"]) {
      const source = file(`src/lib/i18n/${name}`);
      const marker = source.indexOf("INT-583");
      expect(marker, name).toBeGreaterThan(source.indexOf('"red.doNots"'));
    }
  });
});
