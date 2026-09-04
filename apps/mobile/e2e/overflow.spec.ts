/**
 * INT-284 — the screens INT-260 did not reach, at the size its control can
 * now ask for.
 *
 * INT-260 gave the patient a text step that REPLACES the OS value, up to 2.0,
 * and rewired the thirteen screens that sit under the floating tab rail. Two
 * families were left behind, and both fail the same way: a container whose
 * height was decided at 1.0 meets content that is twice as tall.
 *
 *   1. `(auth)/welcome` centres its content in a `flex: 1` box with no scroll
 *      view. Flexbox centring does not clip — it overflows BOTH ends equally,
 *      outside the safe-area padding — so at the largest step the title sits
 *      under the notch, the footer is cut off at the physical bottom edge, and
 *      a 400 pt swipe moves nothing (measured: two screenshots identical below
 *      the status bar). The clipped copy is unreachable, not merely ugly, and
 *      one of the clipped lines is the screen's own explanation of what it is.
 *   2. The focused-flow screens reserve a CONSTANT for a glass bar that grows.
 *      `GLASS_BAR_CLEARANCE` was `128`, sized when a body line was 17 pt; the
 *      bar measures 131 at the largest step with a one-line CTA and about 178
 *      once the label wraps — and `review.send` ("Hekiminize gönderin") DOES
 *      wrap there. Measured on an iPhone 16 Pro: at the end of the review
 *      screen's scroll, `Bu not hasta beyanına dayanır; tanı içermez.` — the
 *      note's provenance line — sits under the bar with nowhere left to
 *      scroll. This is the same defect INT-260 fixed for the rail ("content
 *      ran underneath the navbar", a reserved number and a rendered number
 *      free to drift), on the screens where the rail unmounts.
 *
 * Same shape and the same reason as `appearance.spec.ts`: React Native has no
 * DOM, so what CAN be proved from the tree is that the wiring exists. What
 * this file cannot prove — that the welcome screen now reaches its own footer,
 * and that the provenance line clears the bar — are simulator screenshots in
 * docs/evidence/INT-284.md, taken at the largest step in both themes.
 *
 * The arithmetic behind the clearance is proved separately and without a
 * device in `src/lib/prefs/appearance.test.ts`, where the rest of the
 * INT-260 policy already lives.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { readFontMetrics } from "./fontMetrics";
import { longestUnbreakableToken, textWidth } from "@/lib/a11y/pairedRow";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { APP_STEPS } from "@/lib/prefs/appearance";
import { scaledSize, spacing } from "@/lib/theme";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const APP = join(SRC, "app");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

function modules(root: string): { name: string; source: string }[] {
  return walk(root)
    .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test."))
    .map((path) => ({
      name: relative(MOBILE, path).split(sep).join("/"),
      source: readFileSync(path, "utf8"),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

const TREE = modules(SRC);
const SCREENS = modules(APP);

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/**
 * Code only, comments dropped — the same order `tests/release`'s truncation
 * gate runs in, and for the same reason INT-260 §6e records: a banned name
 * that survives in prose is documentation, and a gate that reddens on it
 * teaches people to stop explaining themselves.
 */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/** A container the patient can move: the only way past a too-tall screen. */
const SCROLLS = /<(ScrollView|FlatList|SectionList|KeyboardAwareScrollView)\b/;

/** Renders the whole-screen primitive itself, so it owns the safe area. */
const OWNS_A_SCREEN = /<Screen\b/;

/** Every module that renders `<Screen>`, wherever in the tree it lives. */
const SCREEN_HOSTS = TREE.filter((f) => OWNS_A_SCREEN.test(f.source));

it("the scanner sees the tree it is supposed to police", () => {
  expect(TREE.length).toBeGreaterThan(40);
  expect(SCREENS.length).toBeGreaterThan(15);
  // A screen host outside src/app is exactly the case a src/app-only scan
  // misses: components/BiometricGate.tsx renders a full Screen of its own.
  expect(SCREEN_HOSTS.length).toBeGreaterThan(10);
  expect(SCREEN_HOSTS.some((f) => !f.name.startsWith("src/app/"))).toBe(true);
});

/* ------------------------------------------------------------------ */
/* 1 · A screen the patient cannot scroll is a screen that can hide    */
/*     its own content                                                 */
/* ------------------------------------------------------------------ */

describe("every screen can be scrolled to its own end", () => {
  it("no module renders a Screen it cannot move", () => {
    const stuck = SCREEN_HOSTS.filter((f) => !SCROLLS.test(f.source)).map((f) => f.name);
    // 00 §2 forbids both remaining ways out: truncation inverts a Turkish
    // clinical fact, and clamping the text takes back the size the patient
    // chose. Room the patient can reach is the only one left.
    expect(
      stuck,
      "these modules own a Screen with no scroll container: at the largest text step their content overflows the safe area at BOTH ends and nothing can bring it back",
    ).toEqual([]);
  });

  it("centring is only safe inside something that scrolls", () => {
    // `justifyContent: "center"` on a `flex: 1` box does not clip when the
    // content outgrows it — it pushes the overflow out of both ends, past
    // the safe-area inset. Inside a ScrollView the same rule reads as
    // "centre while it fits", which is what the design wanted.
    for (const host of SCREEN_HOSTS.filter((f) => /justifyContent: "center"/.test(f.source))) {
      expect(SCROLLS.test(host.source), `${host.name} centres content it cannot scroll`).toBe(true);
    }
  });

  it("the welcome screen keeps its footer reachable and its title under the inset", () => {
    const welcome = file("src/app/(auth)/welcome.tsx");
    expect(welcome).toMatch(SCROLLS);
    // Centred while it fits, scrolled once it does not: flexGrow on the
    // content container is what makes one rule do both jobs. `flex: 1`
    // there would be the defect again — it caps the container at the
    // viewport and hands the overflow back to the safe area.
    expect(welcome).toContain("flexGrow: 1");
    expect(welcome).not.toMatch(/content: \{[^}]*flex: 1/);
  });

  it("the locked biometric gate is a screen like any other", () => {
    const gate = file("src/components/BiometricGate.tsx");
    expect(gate).toMatch(SCROLLS);
    expect(gate).toContain("flexGrow: 1");
  });
});

/* ------------------------------------------------------------------ */
/* 2 · The auth flow keeps the bottom safe edge it has no bar to own   */
/* ------------------------------------------------------------------ */

describe("a screen with no floating chrome keeps its bottom inset", () => {
  // Design pass 4's rule is specific: a screen drops the bottom safe edge
  // BECAUSE something else owns that zone — the tab rail, or the glass bar.
  // The auth screens have neither, so dropping it leaves the last control
  // under the home indicator, and at the largest step these screens are long
  // enough to reach it.
  const BAR_OR_RAIL = /(GlassBar|useTabBarClearance|RAIL_EDGES)/;

  for (const name of [
    "src/app/(auth)/phone.tsx",
    "src/app/(auth)/otp.tsx",
    "src/app/(auth)/consent.tsx",
    "src/app/(auth)/welcome.tsx",
  ]) {
    it(`${name} does not drop an edge nothing else covers`, () => {
      const source = file(name);
      expect(BAR_OR_RAIL.test(source), `${name} now has bottom chrome; revisit this rule`).toBe(
        false,
      );
      const edges = source.match(/edges=\{\[([^\]]*)\]\}/);
      if (edges !== null) {
        expect(edges[1], `${name} drops the bottom safe edge with nothing covering it`).toContain(
          '"bottom"',
        );
      }
    });
  }
});

/* ------------------------------------------------------------------ */
/* 3 · The bar's height and the room reserved for it are ONE number    */
/* ------------------------------------------------------------------ */

describe("the glass bar reserves the room it actually occupies", () => {
  it("no module reserves bar room as a literal any more", () => {
    const guessing = TREE.filter((f) =>
      /(GLASS_BAR_CLEARANCE|DIALOGUE_BAR_CLEARANCE)/.test(code(f.source)),
    ).map((f) => f.name);
    expect(
      guessing,
      "a constant and the chrome it reserves for are two numbers free to drift — INT-260 §3.2",
    ).toEqual([]);
  });

  it("the comment stripper narrows the scan without emptying it", () => {
    // INT-260 §6e's lesson, inverted: a gate that only ever reads comments
    // out is a gate that can pass by reading everything out. The banned name
    // still appears in the tree's prose, and the code the stripper leaves
    // behind is still code.
    expect(TREE.some((f) => /GLASS_BAR_CLEARANCE/.test(f.source))).toBe(true);
    const bar = code(file("src/components/GlassBar.tsx"));
    expect(bar).toContain("export function useGlassBarClearance");
    expect(bar).not.toContain("Scroll-content bottom padding");
    // A URL is not a line comment, and stripping one would corrupt the code
    // every other assertion here reads.
    expect(code('const base = "http://127.0.0.1:8000"; // trailing')).toContain(
      '"http://127.0.0.1:8000";',
    );
  });

  it("every bar reports its height to the screen that scrolls under it", () => {
    const hosts = TREE.filter((f) => /<GlassBar\b/.test(f.source));
    expect(hosts.length).toBeGreaterThan(1);
    for (const host of hosts) {
      const sites = host.source.match(/<GlassBar\b[^>]*>/gs) ?? [];
      expect(sites.length, `${host.name} renders no GlassBar the regex can see`).toBeGreaterThan(0);
      for (const site of sites) {
        expect(site, `a GlassBar in ${host.name} reports no height`).toContain("onHeight");
      }
    }
  });

  it("the hosts pad their scroll content from the hook, not from a style constant", () => {
    for (const name of [
      "src/app/(tabs)/visits/[visitId]/intake.tsx",
      "src/app/(tabs)/visits/[visitId]/review.tsx",
      "src/components/DialogueIntake.tsx",
    ]) {
      expect(file(name)).toContain("useGlassBarClearance");
    }
  });

  it("the hook is one function over one measurement, not a second formula", () => {
    const bar = file("src/components/GlassBar.tsx");
    expect(bar).toContain("useGlassBarClearance");
    // The arithmetic lives beside railWellSize in the pure module the node
    // suite can hold; the hook only supplies the scale and the inset.
    expect(bar).toContain("glassBarClearance");
    expect(bar).toContain("onLayout");
  });

  it("the CTA height floor is declared once for the button and the room", () => {
    // The bar's pre-layout floor has to predict the button's height, and a
    // second copy of `56` is exactly the drift this issue is about.
    expect(file("src/components/Themed.tsx")).toContain("CTA_MIN_HEIGHT");
    expect(file("src/lib/prefs/appearance.ts")).toContain("export const CTA_MIN_HEIGHT");
  });
});

/* ------------------------------------------------------------------ */
/* 4 · The gate: a probe screen is still a screen                      */
/* ------------------------------------------------------------------ */

describe("the dialogue gate", () => {
  it("scrolls, and reserves room for a bottom edge rather than for a bar it does not render", () => {
    const gate = file("src/components/DialogueGate.tsx");
    expect(gate).toMatch(SCROLLS);
    // It is rendered where the glass bar is NOT: intake.tsx shows either
    // the gate, the dialogue or the typed steps, and only the latter two
    // carry a bar. Padding for absent chrome is a number with no referent.
    expect(gate).not.toMatch(/<GlassBar\b/);
    expect(gate).toContain("useSafeAreaInsets");
  });
});

/* ------------------------------------------------------------------ */
/* 5 · A row that cannot fit its own two ends must wrap, not escape    */
/* ------------------------------------------------------------------ */

describe("the review card header", () => {
  it("wraps rather than pushing its controls off the screen", () => {
    // Measured at 2.0 on an iPhone 16 Pro: the section header is a
    // `space-between` row holding a Kicker and the scope chips, and RN
    // flex children do not shrink by default — so "Paylaşılıyor" and the
    // "Düzenleyin" Pressable ran off the right edge, clipped and untappable.
    // The consent state of a section is not optional reading.
    const review = file("src/app/(tabs)/visits/[visitId]/review.tsx");
    const header = review.match(/sectionHeader: \{([^}]*)\}/);
    expect(header, "sectionHeader is not declared the way this test reads it").not.toBeNull();
    expect(header![1]).toContain('flexWrap: "wrap"');
  });
});

/* ------------------------------------------------------------------ */
/* 6 · The horizontal axis: a row that pins an item to the far end     */
/*     must be able to break a line (INT-295)                          */
/* ------------------------------------------------------------------ */

/**
 * The class INT-295 is one instance of, stated so it cannot come back
 * somewhere else.
 *
 * Sections 1-5 above swept the VERTICAL axis: a screen too tall for the
 * viewport must be scrollable, and the room reserved for floating chrome
 * must be the room it occupies. Nothing swept the horizontal one, and
 * nothing could: this app scrolls nowhere sideways, so a row that outgrows
 * its container does not become reachable by swiping — it is simply drawn
 * where the screen is not. INT-293 verified that by hand on the mode row and
 * the swipe did nothing.
 *
 * The shape that reliably produces it is a row that pins one item to the far
 * end — `justifyContent: "space-between"`, or a child carrying
 * `marginLeft: "auto"`. The pinned item is the one that leaves, and it is
 * usually the control rather than the prose: "Sıranız geldi" behind
 * "Detaylı mod açık", "Kapatın" behind a sheet title, a measurement behind
 * its label. RN flex children neither wrap nor shrink by default, so the
 * only structural answer available is `flexWrap`.
 *
 * This does not claim to catch every horizontal overflow — a plain row of
 * two long labels can still overflow without pinning anything, and only a
 * width model catches that (`e2e/modeBar.spec.ts` runs one over the mode
 * row). It catches the shape that has now produced the defect three times.
 */
const FAR_END = /(justifyContent: "space-between"|marginLeft: "auto")/;

/**
 * Rows allowed to pin without wrapping, each with the reason it is safe.
 * It may only shrink: an entry here is a row that has been argued about, and
 * a row nobody has argued about belongs in the gate, not in the list.
 */
const PINNED_WITHOUT_WRAP_ALLOW: Record<string, string> = {};

/**
 * Every `name: { ... }` rule in a StyleSheet, per module.
 *
 * Braces are counted rather than matched by a lazy pattern. A pattern that
 * stops at the first `\n  },` swallows every single-line rule that follows a
 * multi-line one, and a scan that quietly sees two rows where the tree holds
 * five is a gate that passes because it looked away.
 */
function styleRules(source: string): Map<string, string> {
  const rules = new Map<string, string>();
  const head = /\n {2}([A-Za-z0-9_]+): \{/g;
  let match = head.exec(source);
  while (match !== null) {
    let depth = 1;
    let index = head.lastIndex;
    while (index < source.length && depth > 0) {
      if (source[index] === "{") {
        depth += 1;
      } else if (source[index] === "}") {
        depth -= 1;
      }
      index += 1;
    }
    rules.set(match[1], source.slice(head.lastIndex, index - 1));
    head.lastIndex = index;
    match = head.exec(source);
  }
  return rules;
}

describe("a row that pins an item to the far end can break a line", () => {
  const pinned = TREE.flatMap((f) =>
    [...styleRules(f.source).entries()]
      .filter(([, body]) => /flexDirection: "row"/.test(body) && FAR_END.test(body))
      .map(([name, body]) => ({ where: `${f.name}::${name}`, body })),
  );

  it("finds the rows it is supposed to police", () => {
    // A gate that matches nothing passes for the wrong reason. The pinning
    // shape is common enough in this tree that an empty result means the
    // rule stopped reading StyleSheet bodies, not that the tree got safer.
    expect(pinned.length).toBeGreaterThan(3);
  });

  it("every one of them wraps, or says why it does not have to", () => {
    const stuck = pinned
      .filter(({ where, body }) => {
        if (Object.prototype.hasOwnProperty.call(PINNED_WITHOUT_WRAP_ALLOW, where)) {
          return false;
        }
        return !/flexWrap: "wrap"/.test(body);
      })
      .map((entry) => entry.where);
    expect(
      stuck,
      "these rows push their far item off the screen as the text grows, and " +
        "nothing scrolls sideways to bring it back (INT-295)",
    ).toEqual([]);
  });

  it("the allow-list holds nothing that is no longer there", () => {
    for (const where of Object.keys(PINNED_WITHOUT_WRAP_ALLOW)) {
      expect(
        pinned.some((entry) => entry.where === where),
        `${where} is allow-listed but no longer pins anything; drop the entry`,
      ).toBe(true);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 7 · The progress row: decoration yields, the fact does not          */
/*     (INT-295)                                                       */
/* ------------------------------------------------------------------ */

/**
 * The second control INT-293 found off the right edge, on the same screen and
 * at the same default text size: "N soru yanıtlandı".
 *
 * The dots are decoration and are hidden from assistive technology; the
 * counter beside them is the only place the progress is stated as a fact
 * (SC 1.4.1). But the dots are one per applicable question — a Detaylı flow
 * reached about thirty of them — and at 8 pt plus a 4 pt gap that rail is
 * wider than the content box on its own, whatever the text is doing. In a
 * plain row it pushed the counter out of the screen.
 *
 * So the row is asserted from both ends: the decoration must be able to give
 * room back (wrap and shrink), and the counter must never need more room than
 * the narrowest phone has at the largest step, in either catalogue — measured
 * in the shipped face rather than assumed.
 */
describe("the progress counter is never pushed off the row", () => {
  const metrics = readFontMetrics(
    join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
  );
  const intake = file("src/app/(tabs)/visits/[visitId]/intake.tsx");

  it("hands the room back from the decoration, not from the fact", () => {
    const dots = /progressRail: \{([\s\S]*?)\n {2}\}/.exec(intake);
    expect(dots, "the dot rail no longer owns a box of its own").not.toBeNull();
    expect(dots![1]).toContain('flexWrap: "wrap"');
    expect(dots![1]).toContain("flexShrink: 1");
    expect(intake).toContain("progressCount: { flexShrink: 0");
  });

  it("fits the narrowest phone at the largest step, in both catalogues", () => {
    // Tabular figures (`fontVariant`) give every digit one advance, so a
    // two-digit count is the widest a flow of this length can print.
    const tooWide: string[] = [];
    for (const [locale, catalogue] of [
      ["tr", tr],
      ["en", en],
    ] as const) {
      const line = `99 ${catalogue["intake.progress.answered"]}`;
      const width = metrics.advance(line, scaledSize("caption", 2.0));
      const available = 375 - 2 * spacing.screen;
      if (width > available) {
        tooWide.push(`${locale}: ${width.toFixed(1)} pt against ${available} pt`);
      }
    }
    expect(tooWide).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* The paired row's estimator never under-reserves for a Turkish word  */
/* ------------------------------------------------------------------ */

describe("lib/a11y/pairedRow's width model is safe against the shipped face", () => {
  // The module decides, at render time and inside the app bundle, whether a
  // label and a control can still share a line. It cannot read a font file, so
  // it estimates in three glyph-advance classes — and an estimate is only
  // acceptable in ONE direction. Over-reserving changes a row's form one step
  // early: visible, recoverable, harmless. Under-reserving squeezes a Turkish
  // word until React Native breaks it mid-syllable, which 00 §2 forbids
  // tree-wide and which is the defect the module exists to end.
  //
  // The test runner CAN read the font, with the same reader the gates above
  // use, so the bias is proved rather than asserted in a comment.
  const metrics = readFontMetrics(
    join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
  );

  const LABELS = [
    ...Object.values(tr as Record<string, string>),
    ...Object.values(en as Record<string, string>),
  ].filter((value) => typeof value === "string" && value.length > 0 && value.length <= 60);

  it("reserves at least what the real face needs, at every step, in both catalogues", () => {
    const under: string[] = [];
    for (const step of APP_STEPS) {
      const size = scaledSize("body", step);
      for (const label of LABELS) {
        const token = longestUnbreakableToken(label);
        if (token.length === 0) {
          continue;
        }
        if (textWidth(token, size) < metrics.advance(token, size)) {
          under.push(`${token} @ ${step}`);
        }
      }
    }
    expect(under).toEqual([]);
  });

  it("is an estimate, not a second measurement — it must not be wildly loose either", () => {
    // Over-reserving is safe but not free: a model twice the real width would
    // stack every row and pass the assertion above vacuously. This bounds the
    // slack, so the safety bias stays a bias rather than becoming a blunt
    // always-stack in disguise.
    const size = scaledSize("body", 1.0);
    for (const token of ["Paylaşımlarınız", "iyileştirme", "görüşme", "Araştırma"]) {
      const ratio = textWidth(token, size) / metrics.advance(token, size);
      expect(ratio, token).toBeGreaterThanOrEqual(1);
      expect(ratio, token).toBeLessThan(1.35);
    }
  });
});
