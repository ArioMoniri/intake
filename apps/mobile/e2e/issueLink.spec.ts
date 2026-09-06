/**
 * INT-311 — issuing a Doctor Link from the patient's phone.
 *
 * Three issues declined this in a row, each correctly and each citing the
 * others: INT-137 refused the QR while INT-150 was open, INT-150 built the
 * server side and refused the delivery channel (HB-O7), INT-139 refused the
 * issuing screen. This is the single surface that resolves them. The behaviour
 * of the transport is proved without a network in `src/lib/shares/issue.test.ts`;
 * this file is the acceptance, checked from the source tree the way the other
 * device-less specs (shares, review_send, me) are.
 *
 * The four acceptance lines, in order:
 *  1. one owner, one surface for the ACT of issuing;
 *  2. a bearer credential may now be rendered, because the SERVER redemption
 *     path checks a consent scope and writes an audit entry — and INT-137's
 *     four negative controls (no link, no scheme, no token, no serialised note)
 *     STAY STANDING on the review surface;
 *  3. the copy implies no channel that does not exist (HB-O7): in-app only, no
 *     "we sent / we'll text / we'll e-mail";
 *  4. what it renders is reachable at every one of the app's text steps
 *     (INT-136: 52/248 Turkish labels overflow the row at the largest size).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { APP_STEPS } from "@/lib/prefs/appearance";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { scaledSize, spacing } from "@/lib/theme";

import { readFontMetrics } from "./fontMetrics";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const REPO = join(MOBILE, "..", "..");

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
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/** Code only, comments dropped — prose about a rule is not the rule. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const SCREEN = "src/app/(tabs)/visits/[visitId]/issue-link.tsx";
const ISSUER = "src/lib/shares/issue.ts";
const HUB = "src/app/(tabs)/visits/[visitId]/shares.tsx";

/** The review & send surface INT-137's four negative controls guard. */
const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const SHARE_LIB = "src/lib/intake/share.ts";
const CSAT_PROMPT = "src/components/CsatPrompt.tsx";
const CSAT_LIB = "src/lib/intake/csat.ts";

/** Every `shares.issue.*` string the surface adds — the copy this issue owns. */
const ISSUE_KEYS = Object.keys(tr).filter((key) => key.startsWith("shares.issue."));

/* ------------------------------------------------------------------ */
/* 1 · One owner, one surface for the act of issuing                    */
/* ------------------------------------------------------------------ */

describe("issuing has one surface, and it is reachable", () => {
  it("is a real screen with a default export, inside the file-size rule", () => {
    expect(file(SCREEN)).toContain("export default");
    for (const name of [SCREEN, ISSUER]) {
      expect(file(name).split("\n").length, name).toBeLessThan(500);
    }
  });

  it("is registered in the nav map, so it is not a stealth surface", () => {
    const nav = readFileSync(join(__dirname, "nav.spec.ts"), "utf8");
    expect(nav).toContain('"(tabs)/visits/[visitId]/issue-link.tsx"');
  });

  it("is entered from the share centre, the one hub over this note's grants", () => {
    const hub = file(HUB);
    expect(hub).toContain("/issue-link");
    expect(hub).toContain('t("shares.issue.entry")');
  });

  it("blocks capture: a bearer credential must not reach a screenshot", () => {
    expect(file(SCREEN)).toContain("useClinicalScreenPrivacy");
  });
});

/* ------------------------------------------------------------------ */
/* 2 · A credential may render, because the server redemption path is   */
/*     consent-checked and audited — and INT-137's controls STAND        */
/* ------------------------------------------------------------------ */

describe("the credential is rendered against a real, guarded redemption path", () => {
  it("issues the grant and mints the opening code on the one owning module", () => {
    const issuer = code(file(ISSUER));
    // Both share-purpose-gated routes live here and only here; their absence
    // everywhere else is asserted over the whole tree in e2e/shares.spec.ts.
    expect(issuer).toContain("/note/doctor-links");
    expect(issuer).toContain("/otp");
    expect(issuer).toMatch(/"POST"/);
  });

  it("the screen shows the token and the code the issuer returned, from memory", () => {
    const screen = code(file(SCREEN));
    expect(screen).toContain("issueDoctorLink");
    // The two halves the clinician needs: the link key (token) and the
    // opening code. They are rendered from component state — never persisted.
    expect(screen).toContain(".token");
    expect(screen).toContain(".code");
  });

  it("the SERVER redemption path checks a consent scope AND writes an audit entry", () => {
    // Acceptance line 2's precondition, checked against the deployed server so
    // the two cannot drift: doctor_link/redeem.py::open_link runs ensure_consent
    // against the note's patient on SHARE_SCOPE and records the open before it
    // answers. If either disappears, a credential is rendering with no gate.
    const redeem = readFileSync(
      join(REPO, "services", "api", "src", "intake_api", "doctor_link", "redeem.py"),
      "utf8",
    );
    expect(redeem).toMatch(/ensure_consent\([\s\S]*?scope=SHARE_SCOPE/);
    expect(redeem).toContain('action="api.doctor_link.opened"');
    expect(redeem).toContain("audit.record");
  });

  it("the ISSUING act is itself consent-gated and audited (invariant 4)", () => {
    const router = readFileSync(
      join(REPO, "services", "api", "src", "intake_api", "doctor_link", "router.py"),
      "utf8",
    );
    expect(router).toContain("ensure_consent(");
    expect(router).toContain('action="api.doctor_link.issued"');
  });

  it("INT-137's four negative controls stay standing on the review surface", () => {
    // The issuing surface is a SEPARATE screen; nothing here relaxes the
    // review & send controls, and this proves they still hold.
    const surface =
      code(file(REVIEW)) + code(file(CSAT_PROMPT)) + code(file(CSAT_LIB)) + code(file(SHARE_LIB));
    // no link, no scheme, no token
    expect(surface).not.toMatch(/https?:\/\/|intake:\/\/|doctorLink|doctor_link|bearer/i);
    // no serialised note
    expect(surface).not.toMatch(/JSON\.stringify|btoa\(|base64|toBase64|encodeURI/);
  });
});

/* ------------------------------------------------------------------ */
/* 3 · The copy implies no channel that does not exist (HB-O7)          */
/* ------------------------------------------------------------------ */

describe("the copy invents no delivery channel", () => {
  /**
   * The affirmative delivery claims a channel would license. The negative
   * "hiçbir yere gönderilmez" (it is not sent anywhere) is the crux copy and
   * must NOT be caught — so these match the completed/future SEND forms, never
   * the negated one.
   */
  const CLAIMS_A_CHANNEL =
    /gönderildi|gönderdik|gönderilecek|gönderece|iletildi|ilettik|e-?posta|e-?mail|\bSMS\b|kısa mesaj|telefonunuza|adresinize|we sent|we'll (text|e-?mail|send)|sent you|check your (phone|e-?mail)/i;

  it("no shares.issue string says a code was or will be sent", () => {
    for (const key of ISSUE_KEYS) {
      expect((tr as Record<string, string>)[key], `tr ${key}`).not.toMatch(CLAIMS_A_CHANNEL);
      expect((en as Record<string, string>)[key], `en ${key}`).not.toMatch(CLAIMS_A_CHANNEL);
    }
  });

  it("neither the screen nor the transport names a channel", () => {
    for (const name of [SCREEN, ISSUER]) {
      expect(code(file(name)), name).not.toMatch(CLAIMS_A_CHANNEL);
    }
  });

  it("says instead, in words, that it is shown on this screen only", () => {
    // The positive half: the crux sentence is present, and it is the negated,
    // in-app form.
    expect(tr["shares.issue.guide.body"]).toMatch(/gönderilmez/);
    expect(tr["shares.issue.guide.body"]).toMatch(/ekran/i);
    expect(tr["shares.issue.show"]).toMatch(/gösterin/);
  });

  it("puts no numeral in the copy — the code is runtime, not a string (invariant 22)", () => {
    for (const key of ISSUE_KEYS) {
      expect((tr as Record<string, string>)[key], `tr ${key}`).not.toMatch(/\d/);
      expect((en as Record<string, string>)[key], `en ${key}`).not.toMatch(/\d/);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 4 · Reachable at every text step (INT-136)                          */
/* ------------------------------------------------------------------ */

describe("the surface survives the largest text step", () => {
  it("scrolls, so content that grows past the viewport can still be reached", () => {
    expect(code(file(SCREEN))).toMatch(/<ScrollView\b/);
  });

  it("wraps rather than truncates — nothing here can be cut short", () => {
    const screen = code(file(SCREEN));
    for (const token of ["numberOfLines", "ellipsizeMode", "adjustsFontSizeToFit"]) {
      expect(screen, token).not.toContain(token);
    }
  });

  it("every label's longest word fits the row at every APP_STEPS size", () => {
    const metrics = readFontMetrics(
      join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
    );
    const PHONE_WIDTHS = [320, 375, 390];
    // Conservative content width: both screen gutters and a card's own padding.
    const CHROME = 2 * spacing.md;
    expect(ISSUE_KEYS.length).toBeGreaterThan(10);
    const words = ISSUE_KEYS.flatMap((key) => [
      ...(tr as Record<string, string>)[key].split(/\s+/),
      ...(en as Record<string, string>)[key].split(/\s+/),
    ]);
    for (const phone of PHONE_WIDTHS) {
      const row = phone - 2 * spacing.screen - CHROME;
      for (const scale of APP_STEPS) {
        const size = scaledSize("body", scale);
        for (const word of words) {
          expect(
            metrics.advance(word, size),
            `"${word}" @${phone}pt ${scale}x`,
          ).toBeLessThanOrEqual(row);
        }
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* 5 · Copy discipline, and a credential that never leaves memory      */
/* ------------------------------------------------------------------ */

describe("the strings and the safety posture", () => {
  it("mirrors every Turkish key into a distinct English one (invariant 5)", () => {
    expect(ISSUE_KEYS.length).toBeGreaterThan(10);
    for (const key of ISSUE_KEYS) {
      expect(en, key).toHaveProperty(key);
      expect((en as Record<string, string>)[key]).not.toBe((tr as Record<string, string>)[key]);
    }
  });

  it("addresses the patient as siz, never sen (invariant 2)", () => {
    for (const key of ISSUE_KEYS) {
      expect((tr as Record<string, string>)[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
    }
  });

  it("names no duration in the copy (invariant 20)", () => {
    for (const key of ISSUE_KEYS) {
      expect((tr as Record<string, string>)[key], key).not.toMatch(
        /\b\d+\s*(?:sn|sec|second|saniye|dk|dakika|minute|min)\b/i,
      );
    }
  });

  it("persists and logs nothing — the credential lives only in memory", () => {
    for (const name of [SCREEN, ISSUER]) {
      const source = code(file(name));
      for (const banned of [
        "AsyncStorage",
        "SecureStore",
        "expo-file-system",
        "setInterval",
        "setTimeout",
        "console.",
        "Clipboard",
        "setStringAsync",
      ]) {
        expect(source, `${name} reaches ${banned}`).not.toContain(banned);
      }
    }
  });

  it("gives the entry point an a11y hint from the catalogue", () => {
    expect(tr).toHaveProperty("a11y.shares.issueHint");
    expect(en).toHaveProperty("a11y.shares.issueHint");
  });
});
