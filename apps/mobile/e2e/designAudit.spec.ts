/**
 * INT-601 — the design-audit fixes (docs/design/audit-2026-11/README.md,
 * findings A2 and A4 to A7) as wiring checks.
 *
 * vitest runs on node with no renderer (vitest.config.ts), so, as in
 * typed_intake.spec.ts and overflow.spec.ts, the RULES are pure functions with
 * their own unit tests (lib/a11y/chip.test.ts, lib/auth/otpForm.test.ts,
 * lib/theme.test.ts) and this file holds the WIRING: that each screen reaches
 * the rule, and that the layout the audit measured is gone from the source.
 * Comments are stripped before every scan, so a file that documents what it
 * must not do is not convicted by the word.
 *
 * Finding A1 (Bugün's focal visit and state) is INT-594's, PR #1013, and is
 * tested there (lib/today.test.ts); docs/evidence/INT-601.md says why.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { MIN_TAP } from "@/lib/a11y/target";
import { spacing } from "@/lib/theme";

const MOBILE = join(__dirname, "..");
const APP = join(MOBILE, "src", "app");

function read(path: string): string {
  const source = readFileSync(join(MOBILE, path), "utf8");
  expect(source.length, `${path} is empty`).toBeGreaterThan(0);
  return source;
}

/** Code only: block comments, JSX comments and line comments dropped. */
function code(source: string): string {
  return source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** One StyleSheet entry's body, `name: { ... }`, at two-space indent. */
function styleBlock(source: string, name: string): string {
  const match = new RegExp(`\\n\\s{2}${name}:\\s*\\{([\\s\\S]*?)\\n?\\s{0,2}\\},?\\n`).exec(source);
  expect(match, `no \`${name}\` style`).not.toBeNull();
  return match![1];
}

const LAYOUT = "src/app/(tabs)/visits/_layout.tsx";
const DETAIL = "src/app/(tabs)/visits/[visitId]/index.tsx";
const INTAKE = "src/app/(tabs)/visits/[visitId]/intake.tsx";
const NEW_VISIT = "src/app/(tabs)/visits/new.tsx";
const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const DIALOGUE = "src/components/DialogueIntake.tsx";
const OTP = "src/app/(auth)/otp.tsx";

/* ------------------------------------------------------------------ */
/* A2 · the visit detail has a way back, and its action above the fold */
/* ------------------------------------------------------------------ */

describe("A2 — a visit detail opened from another tab has a working back control", () => {
  it("the visits stack names its list as the anchor every deep entry lands on", () => {
    const layout = code(read(LAYOUT));
    expect(layout).toMatch(
      /export const unstable_settings = \{\s*initialRouteName: "index",?\s*\}/,
    );
    expect(existsSync(join(APP, "(tabs)", "visits", "index.tsx"))).toBe(true);
  });

  /** Every `router.push(` into the visits stack from a screen outside it. */
  const crossTabPushes = walk(APP)
    .filter((path) => path.endsWith(".tsx"))
    .map((path) => relative(MOBILE, path).split(sep).join("/"))
    .filter((path) => !path.startsWith("src/app/(tabs)/visits/"))
    .flatMap((path) => {
      const source = code(read(path));
      const calls: { path: string; call: string }[] = [];
      const re = /router\.push\(\s*[`"]\/\(tabs\)\/visits\/[^)]*\)/g;
      for (let m = re.exec(source); m !== null; m = re.exec(source)) {
        calls.push({ path, call: m[0] });
      }
      return calls;
    });

  it("finds the pushes it guards (Bugün's two, Kayıtlar' one)", () => {
    expect(crossTabPushes.map((p) => p.path)).toEqual(
      expect.arrayContaining(["src/app/(tabs)/today.tsx", "src/app/(tabs)/records.tsx"]),
    );
    expect(crossTabPushes.length).toBeGreaterThanOrEqual(3);
  });

  it("every one loads the anchor under the pushed screen, so the header has a back", () => {
    // Without withAnchor, expo-router lands the pushed screen as the stack's
    // ROOT and the header draws a title with nothing to go back to.
    const bare = crossTabPushes.filter((p) => !/withAnchor: true/.test(p.call));
    expect(bare.map((p) => `${p.path}: ${p.call}`)).toEqual([]);
  });

  it("the detail's one action comes straight after the visit card, before the status cards", () => {
    const detail = code(read(DETAIL));
    const card = detail.indexOf("<VisitCard");
    const action = detail.indexOf("<PrimaryButton");
    expect(card).toBeGreaterThan(-1);
    expect(action).toBeGreaterThan(card);
    for (const later of [
      't("visits.new.visitType")',
      't("visits.detail.noteStatus")',
      't("shares.title")',
    ]) {
      expect(detail.indexOf(later), later).toBeGreaterThan(action);
    }
  });

  it("near miss: both actions and the sent line stay on the screen", () => {
    const detail = code(read(DETAIL));
    for (const key of ['t("visit.prepare")', 't("visit.reviewNote")', 't("review.sentInfo")']) {
      expect(detail).toContain(key);
    }
  });
});

/* ------------------------------------------------------------------ */
/* A4 · a selected chip is a shape as well as a colour, in both lanes  */
/* ------------------------------------------------------------------ */

describe.each([INTAKE, DIALOGUE])("A4 — %s marks a selected chip without colour", (host) => {
  const source = () => code(read(host));

  it("reads the look from the one chip rule", () => {
    expect(source()).toMatch(/import \{[^}]*\bchipLook\b[^}]*\} from "@\/lib\/a11y\/chip";/);
    expect(source()).toMatch(/chipLook\(on, scheme\)/);
  });

  it("draws the rule's glyph and outline on the chip", () => {
    expect(source()).toMatch(/look\.glyph !== null \? \(\s*<Icon\s+name=\{look\.glyph\}/);
    expect(source()).toContain("borderWidth: look.borderWidth");
  });

  it("the accessibilityState comes from the same rule as the look", () => {
    expect(source()).toContain("accessibilityState={look.accessibilityState}");
    expect(source()).not.toContain("accessibilityState={{ checked: on }}");
  });
});

/* ------------------------------------------------------------------ */
/* A5 · a multi-line field is a rounded rectangle                      */
/* ------------------------------------------------------------------ */

describe("A5 — the multi-line answer field is not a pill", () => {
  it("the intake's text field takes radius.field", () => {
    const block = styleBlock(code(read(INTAKE)), "textField");
    expect(block).toContain("borderRadius: radius.field");
    expect(block).not.toContain("radius.control");
  });

  it("near miss: every other multi-line field in the app does too", () => {
    // The pasted-SMS box on the new-visit form is the other multiline input.
    const newVisit = code(read(NEW_VISIT));
    expect(newVisit).toContain("multiline");
    expect(styleBlock(newVisit, "smsField")).toContain("borderRadius: radius.field");
  });
});

/* ------------------------------------------------------------------ */
/* A6 · the SMS-code boxes                                             */
/* ------------------------------------------------------------------ */

describe("A6 — the code boxes fit, scale, show the digits and say the unit", () => {
  const otp = () => code(read(OTP));

  it("does not mask the digits, so the patient can check them against the SMS", () => {
    expect(otp()).not.toContain("secureTextEntry");
  });

  it("sizes the boxes from otpLayout, not a fixed width", () => {
    expect(otp()).toMatch(/import \{[^}]*\botpLayout\b[^}]*\} from "@\/lib\/auth\/otpForm";/);
    // Measured from the card, not read off the window: a window read is the
    // landscape risk a11y.spec.ts's SC 1.3.4 scan forbids.
    expect(otp()).toMatch(
      /otpLayout\(\s*measured \?\? otpAvailableWidth\(OTP_NARROWEST_WINDOW, fontScale\)/,
    );
    expect(otp()).toContain("onLayout={(event) => setMeasured(event.nativeEvent.layout.width)}");
    expect(otp()).not.toContain("useWindowDimensions");
    expect(styleBlock(otp(), "register")).not.toMatch(/\bwidth: \d/);
    expect(otp()).toMatch(/width: layout\.box/);
    expect(otp()).toMatch(/minHeight: layout\.height/);
  });

  it("lets the row wrap into the form otpLayout chose", () => {
    expect(styleBlock(otp(), "registers")).toContain('flexWrap: "wrap"');
  });

  it("renders the countdown through resendWaitLine, which carries the unit", () => {
    expect(otp()).toContain("resendWaitLine(resendWait)");
    expect(otp()).not.toMatch(/\{t\("auth\.otp\.resendWait"\)\} \{resendWait\}/);
  });
});

/* ------------------------------------------------------------------ */
/* A7 · review: Düzenleyin and the share switch                        */
/* ------------------------------------------------------------------ */

describe("A7 — on review, edit and share are full targets, apart, and share sits in one place", () => {
  const review = () => code(read(REVIEW));

  it("both controls clear the floor by box, not by slop", () => {
    expect(styleBlock(review(), "editButton")).toContain("minHeight: MIN_TAP");
    expect(styleBlock(review(), "shareRow")).toContain("minHeight: MIN_TAP");
    expect(review()).not.toContain("verticalSlop(26)");
    expect(MIN_TAP).toBeGreaterThanOrEqual(44);
  });

  it("the edit button sits at the header's trailing edge, at least 8 pt from anything", () => {
    const header = styleBlock(review(), "sectionHeader");
    expect(header).toContain('justifyContent: "space-between"');
    expect(header).toContain("gap: spacing.sm");
    expect(spacing.sm).toBeGreaterThanOrEqual(8);
    expect(review()).not.toContain("styles.actionRow");
  });

  it("there is one share switch per card, and it is the card's last row", () => {
    const source = review();
    const switches = source.match(/accessibilityRole="switch"/g) ?? [];
    expect(switches).toHaveLength(1);
    const share = source.indexOf('accessibilityRole="switch"');
    // After every other block of the section card…
    for (const before of [
      "section.lines.map(",
      "<CarriedFactReview",
      't("review.healthProvenance")',
      't("review.medsNote")',
    ]) {
      expect(source.indexOf(before), before).toBeGreaterThan(-1);
      expect(source.indexOf(before), before).toBeLessThan(share);
    }
    // …and before the card closes.
    const close = source.indexOf("</Card>", share);
    const nextOpen = source.indexOf("<Card", share);
    expect(close).toBeGreaterThan(share);
    expect(nextOpen === -1 || close < nextOpen).toBe(true);
  });

  it("the share row spans the card, so its position cannot depend on the edit button", () => {
    const row = styleBlock(review(), "shareRow");
    expect(row).toContain('alignSelf: "stretch"');
    expect(row).toContain('flexDirection: "row"');
  });

  it("near miss: no string changed — the same state words and names are used", () => {
    const source = review();
    for (const key of ['t("review.shared")', 't("review.notShared")', 't("review.edit")']) {
      expect(source).toContain(key);
    }
    expect(source).toContain('type: "scope"');
  });
});
