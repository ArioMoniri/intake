/**
 * INT-141 acceptance, pinned as source facts (the auth.spec.ts / consent.spec.ts
 * technique): the notification surface IS the legal posture, so a body that
 * names a department, a marketing path that ships enabled, or a quiet-hours
 * setting that only lives in memory fails here rather than on a lock screen.
 *
 * Pins (issue acceptance, verbatim): "no PHI in push; reminders classified
 * transactional (no IYS consent needed); any marketing path requires IYS
 * consent and is off by default".
 *
 * The division of labour with the server, and why it is this way round: the
 * BODIES live in the Python catalogue (packages/intake_platform
 * notifications) because that is where the wire payload is assembled and
 * where the content-freedom assertion runs on the bytes that actually leave.
 * The app owns the patient's controls and the copy that explains them. Two
 * catalogues of bodies would be two things to keep honest; there is one.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr, type MessageKey } from "../src/lib/i18n/tr";
import {
  DEFAULT_PREFS,
  QUIET_PRESETS,
  clearQuietWindow,
  formatTimeOfDay,
  isQuiet,
  parseTimeOfDay,
  validatePrefs,
  withOptOut,
  withQuietWindow,
  type NotificationPrefs,
} from "../src/lib/notifications/preferences";

const APP = join(__dirname, "..", "src", "app");
const SRC = join(__dirname, "..", "src");
const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** The adversarial patient, mirrored from tests/legal/test_notifications.py:
 *  her branch label shares the word "ve" with generic product copy. */
const ADVERSARIAL = [
  "Kadın Hastalıkları ve Doğum",
  "göğüs ağrısı",
  "Dr. Elif Yıldırım",
  "Tiroid ultrason raporu",
];

const NOTIFICATION_KEYS = (Object.keys(tr) as MessageKey[]).filter(
  (key) => key.startsWith("notifications.") || key.startsWith("a11y.notifications."),
);

describe("route: Bildirimler lives under Profilim and is registered", () => {
  it("the screen exists", () => {
    expect(existsSync(join(APP, "(tabs)", "me", "notifications.tsx"))).toBe(true);
  });

  it("Profilim links to it", () => {
    expect(read(APP, "(tabs)", "me", "index.tsx")).toContain("/(tabs)/me/notifications");
  });

  it("it is registered in the tabs shell, not merely reachable by URL", () => {
    expect(read(APP, "(tabs)", "_layout.tsx")).toContain('name="me/notifications"');
  });
});

/**
 * INT-583 narrows the INT-141 ban without loosening what it protected. The app
 * now receives one kind of push — the server's new-sign-in notice (D35) — so
 * it needs the native notifications package to ask permission and read its
 * APNs device token. It still never assembles a notification body: nothing
 * schedules or presents a local notification, the token is the native APNs
 * one (no Expo relay), and the package is reached from exactly one module,
 * lazily, so every node-tested module stays free of it.
 */
const NATIVE_PACKAGE = "expo-notifications";
const PUSH_NATIVE = "lib/push/native.ts";
const LAZY_IMPORT = /await import\(\s*"expo-notifications"\s*\)/g;
const LOCAL_NOTIFICATION_CALLS = ["scheduleNotificationAsync", "presentNotificationAsync"];
const RELAY_TOKEN_CALL = "getExpoPushTokenAsync";

/** Every rule the tree is held to, as findings over (path under src, source). */
function nativeNotificationFindings(files: { path: string; source: string }[]): string[] {
  const findings: string[] = [];
  for (const { path, source } of files) {
    const mentions = source.split(NATIVE_PACKAGE).length - 1;
    if (mentions > 0 && path !== PUSH_NATIVE) {
      findings.push(`${path}: reaches the native notifications package`);
    }
    if (path === PUSH_NATIVE && mentions !== (source.match(LAZY_IMPORT) ?? []).length) {
      findings.push(`${path}: names the package other than as a lazy await import`);
    }
    for (const call of LOCAL_NOTIFICATION_CALLS) {
      if (source.includes(call)) {
        findings.push(`${path}: ${call}`);
      }
    }
    if (source.includes(RELAY_TOKEN_CALL)) {
      findings.push(`${path}: ${RELAY_TOKEN_CALL}`);
    }
  }
  return findings;
}

const SRC_FILES = walk(SRC)
  .filter((path) => /\.tsx?$/.test(path))
  .map((path) => ({
    path: path
      .slice(SRC.length + 1)
      .split("\\")
      .join("/"),
    source: readFileSync(path, "utf8"),
  }));

describe("no PHI in a push — the app never assembles a notification body", () => {
  it("no local notification is scheduled or presented, and the package lives in one module", () => {
    // A client that schedules its own reminder assembles its own body from
    // whatever it has to hand — which is the visit, the branch and the
    // slots. The seam is the server's for exactly that reason.
    expect(nativeNotificationFindings(SRC_FILES)).toEqual([]);
  });

  it("the one module that reaches the package exists, reaches it lazily, and only it does", () => {
    const reaching = SRC_FILES.filter((f) => f.source.includes(NATIVE_PACKAGE)).map((f) => f.path);
    expect(reaching).toEqual([PUSH_NATIVE]);
    const native = SRC_FILES.find((f) => f.path === PUSH_NATIVE)!.source;
    expect((native.match(LAZY_IMPORT) ?? []).length).toBe(1);
  });

  it("the token it registers is the native APNs device token", () => {
    const native = SRC_FILES.find((f) => f.path === PUSH_NATIVE)!.source;
    expect(native).toContain("getDevicePushTokenAsync");
  });

  describe("the guard catches each way around it (near misses)", () => {
    const lazy = 'const n = await import("expo-notifications");';

    it("the lazy import in the one module is clean", () => {
      expect(nativeNotificationFindings([{ path: PUSH_NATIVE, source: lazy }])).toEqual([]);
    });

    it("a static import in the one module is caught", () => {
      const source = `import * as N from "expo-notifications";\n${lazy}`;
      expect(nativeNotificationFindings([{ path: PUSH_NATIVE, source }])).toHaveLength(1);
    });

    it("the same lazy import in any other module is caught", () => {
      expect(
        nativeNotificationFindings([{ path: "lib/notifications/store.ts", source: lazy }]),
      ).toHaveLength(1);
    });

    it.each([...LOCAL_NOTIFICATION_CALLS, RELAY_TOKEN_CALL])(
      "%s is caught even inside the one module",
      (call) => {
        const source = `${lazy}\nawait n.${call}();`;
        expect(nativeNotificationFindings([{ path: PUSH_NATIVE, source }])).toHaveLength(1);
      },
    );
  });

  it("no notification copy carries a branch, symptom, clinician or document title", () => {
    for (const key of NOTIFICATION_KEYS) {
      for (const term of ADVERSARIAL) {
        expect(tr[key], key).not.toContain(term);
        expect(en[key], key).not.toContain(term);
      }
    }
  });

  it("the screen tells the patient what a notification will and will not say", () => {
    const screen = read(APP, "(tabs)", "me", "notifications.tsx");
    expect(screen).toContain("notifications.contentFree");
    expect(tr["notifications.contentFree"]).toMatch(/sağlık/i);
  });
});

describe("transactional-only: no marketing path exists in the client", () => {
  it("the copy states that only service messages are sent", () => {
    expect(tr["notifications.transactionalOnly"].length).toBeGreaterThan(0);
    expect(en["notifications.transactionalOnly"].length).toBeGreaterThan(0);
  });

  it("there is no marketing or campaign toggle to ship enabled by default", () => {
    // İYS consent is not collectable here: no record shape is specified, so
    // the app must not grow a switch that implies one has been given.
    const screen = read(APP, "(tabs)", "me", "notifications.tsx");
    for (const forbidden of ["marketing", "campaign", "kampanya", "iys", "İYS"]) {
      expect(screen.toLocaleLowerCase("tr-TR")).not.toContain(forbidden.toLocaleLowerCase("tr-TR"));
    }
  });
});

describe("opt-out and quiet hours are the patient's, and default to nothing invented", () => {
  it("a fresh patient is not opted out and has no window", () => {
    expect(DEFAULT_PREFS).toEqual({ optedOut: false, quietStart: null, quietEnd: null });
  });

  it("opting out is one field and needs no window", () => {
    const next = withOptOut(DEFAULT_PREFS, true);
    expect(next.optedOut).toBe(true);
    expect(next.quietStart).toBeNull();
    expect(validatePrefs(next).ok).toBe(true);
  });

  it("choosing a window sets both ends together", () => {
    const next = withQuietWindow(DEFAULT_PREFS, QUIET_PRESETS[0]);
    expect(next.quietStart).toBe(QUIET_PRESETS[0].start);
    expect(next.quietEnd).toBe(QUIET_PRESETS[0].end);
    expect(validatePrefs(next).ok).toBe(true);
  });

  it("clearing a window clears both ends — half a window is not a window", () => {
    const set = withQuietWindow(DEFAULT_PREFS, QUIET_PRESETS[1]);
    expect(clearQuietWindow(set)).toEqual(DEFAULT_PREFS);
  });

  it("a half window is refused rather than half-defaulted", () => {
    const half: NotificationPrefs = { optedOut: false, quietStart: "22:00", quietEnd: null };
    expect(validatePrefs(half)).toEqual({ ok: false, reason: "half_window" });
  });

  it("a zero-width window is refused", () => {
    const zero: NotificationPrefs = { optedOut: false, quietStart: "22:00", quietEnd: "22:00" };
    expect(validatePrefs(zero)).toEqual({ ok: false, reason: "empty_window" });
  });

  it("a malformed time is refused", () => {
    const bad: NotificationPrefs = { optedOut: false, quietStart: "9:00", quietEnd: "08:00" };
    expect(validatePrefs(bad)).toEqual({ ok: false, reason: "malformed_time" });
  });

  it("every offered preset is itself valid — a picker cannot offer a refusal", () => {
    for (const preset of QUIET_PRESETS) {
      expect(validatePrefs(withQuietWindow(DEFAULT_PREFS, preset)).ok, preset.start).toBe(true);
    }
  });

  it("the presets are choices, never a default: none is pre-selected", () => {
    expect(DEFAULT_PREFS.quietStart).toBeNull();
  });
});

describe("quiet-window arithmetic matches the server's, wrap included", () => {
  it("parses and formats the wire form", () => {
    expect(parseTimeOfDay("22:00")).toBe(22 * 60);
    expect(parseTimeOfDay("07:15")).toBe(7 * 60 + 15);
    expect(formatTimeOfDay(7 * 60 + 15)).toBe("07:15");
  });

  it("refuses what the server refuses", () => {
    for (const bad of ["24:00", "8:00", "22h00", "", "22:60"]) {
      expect(parseTimeOfDay(bad), bad).toBeNull();
    }
  });

  it("a window that wraps midnight covers both sides", () => {
    const prefs = withQuietWindow(DEFAULT_PREFS, { start: "22:00", end: "08:00" });
    expect(isQuiet(prefs, 23 * 60)).toBe(true);
    expect(isQuiet(prefs, 3 * 60)).toBe(true);
    expect(isQuiet(prefs, 12 * 60)).toBe(false);
  });

  it("the boundary minutes belong to the awake side, as on the server", () => {
    const prefs = withQuietWindow(DEFAULT_PREFS, { start: "22:00", end: "08:00" });
    expect(isQuiet(prefs, 22 * 60)).toBe(true);
    expect(isQuiet(prefs, 8 * 60)).toBe(false);
  });

  it("no window means nothing is quiet on the client's reading", () => {
    expect(isQuiet(DEFAULT_PREFS, 3 * 60)).toBe(false);
  });
});

describe("the setting is the server's, so it survives more than this process", () => {
  it("the client keeps no on-disk copy of the preference", () => {
    const store = read(SRC, "lib", "notifications", "store.ts");
    expect(store).not.toContain("AsyncStorage");
    expect(store).not.toContain("SecureStore");
    expect(store).not.toContain("FileSystem");
  });

  it("the seam reads and writes the server register", () => {
    const api = read(SRC, "lib", "notifications", "api.ts");
    expect(api).toContain("/v1/me/notifications");
    expect(api).toContain("authedFetch");
  });

  it("an unreachable server leaves the shown state alone rather than claiming a default", () => {
    const api = read(SRC, "lib", "notifications", "api.ts");
    expect(api).toContain("return null");
  });
});

describe("copy: tr source of truth, en mirror, B1 siz register", () => {
  it("the block exists in both catalogues", () => {
    expect(NOTIFICATION_KEYS.length).toBeGreaterThan(0);
    for (const key of NOTIFICATION_KEYS) {
      expect(en[key], key).toBeDefined();
      expect(tr[key].trim().length, key).toBeGreaterThan(0);
    }
  });

  it("no sen forms, no ALL-CAPS, no unexplained jargon", () => {
    for (const key of NOTIFICATION_KEYS) {
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
      expect(tr[key], key).not.toMatch(/push|notification/iu);
    }
  });

  it("the new keys are appended as one block at the END of each catalogue", () => {
    // Mechanical union merges: two agents appending blocks to the same
    // catalogue must not interleave.
    for (const file of ["tr.ts", "en.ts"]) {
      const source = read(SRC, "lib", "i18n", file);
      expect(source).toContain("INT-141");
      const marker = source.indexOf("INT-141");
      const firstKeyLine = source.indexOf('"app.name"');
      expect(marker).toBeGreaterThan(firstKeyLine);
    }
  });
});
