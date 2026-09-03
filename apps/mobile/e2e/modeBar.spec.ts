/**
 * INT-295 — the one affordance built for being in hospital, measured.
 *
 * The mode row carries the "Hastanedeyim" switch and, in Detaylı, the
 * checkpoint control that means "I have been called in, give me my note
 * now" (02 §34). INT-293 found the checkpoint simply absent from the screen:
 * the row laid its items out in one line that neither wrapped nor scrolled,
 * so the status caption ran off the right edge mid-word and the control
 * behind it was never drawn. The walkthrough read the OS Dynamic Type
 * category (L) and called it the default size; the capture it filed measures
 * the chip at 195.7 pt, which is this app's LARGEST text step — INT-260's
 * control REPLACES the OS value, so the two can disagree and here they did.
 * The row overflows well below that step either way, which is the property
 * this file pins.
 *
 * What is asserted is reachability, not rendering: for every text size the
 * app can be set to, in both shipped catalogues, on both phone widths, every
 * item of the row must land inside the screen. The widths come from the face
 * the app ships (`e2e/fontMetrics.ts` reads Inter's own advances), and the
 * arrangement — does the row wrap, does it stack — is read out of the
 * component, so a test cannot pass by describing a layout the app does not
 * have.
 *
 * What it cannot prove is that iOS lays Yoga's rules out the way this file
 * models them. That half is the simulator capture in docs/evidence/INT-295.md,
 * against which the width model agrees to within half a point.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { readFontMetrics } from "./fontMetrics";
import { MIN_TAP } from "@/lib/a11y/target";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { APP_STEPS, isLargeText } from "@/lib/prefs/appearance";
import { scaledSize, spacing } from "@/lib/theme";

const MOBILE = join(__dirname, "..");
const MODE_BAR = readFileSync(join(MOBILE, "src/components/ModeBar.tsx"), "utf8");
const INTAKE = readFileSync(join(MOBILE, "src/app/(tabs)/visits/[visitId]/intake.tsx"), "utf8");
const metrics = readFontMetrics(
  join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
);

/**
 * Point widths of the phones the row has to hold. 402 is the iPhone 16 Pro
 * the defect was captured on; 375 is the narrowest iPhone still in service
 * (SE 3rd generation, 13 mini). Landscape is not modelled — the flow screens
 * are portrait.
 */
const PHONE_WIDTHS = [375, 402] as const;

/**
 * Every scale the app can be rendering at: the five rungs of its own control,
 * and a sweep of the OS range that theme.ts clamps to [0.5, 2.0] — dense
 * enough that no Dynamic Type category can slip between two samples.
 */
const SCALES: readonly number[] = (() => {
  const sweep: number[] = [];
  for (let scale = 0.5; scale <= 2.0001; scale += 0.05) {
    sweep.push(Math.round(scale * 100) / 100);
  }
  return [...new Set([...APP_STEPS, ...sweep])].sort((a, b) => a - b);
})();

/* ------------------------------------------------------------------ */
/* Reading the row out of the component                                */
/* ------------------------------------------------------------------ */

/**
 * The row's JSX: from where it names its own style to its closing tag. The
 * row holds chips and captions and never a nested View, so the first closing
 * tag after the style reference is its own — asserted below rather than
 * assumed.
 */
function rowBlock(): string {
  const open = MODE_BAR.indexOf("styles.modeRow");
  const close = MODE_BAR.indexOf("</View>", open);
  if (open < 0 || close < 0) {
    throw new Error("ModeBar no longer declares a row this file can find");
  }
  return MODE_BAR.slice(open, close);
}

interface RowItem {
  /** Catalogue key of the label this item renders. */
  readonly key: string;
  /** A chip carries horizontal padding around its label; a caption does not. */
  readonly chip: boolean;
  /** Where it starts in the row's source — the order it is laid out in. */
  readonly at: number;
}

const T_CALL = /t\("([^"]+)"\)/g;

/**
 * Every item the row puts on the screen, in source order.
 *
 * Chips are found by their Pressable, and each Pressable's LAST `t()` call is
 * the label it draws — the earlier one is its accessible name, which is the
 * same string and must not be counted twice. Anything else in the row is a
 * caption, measured without chip padding. Reading both kinds is deliberate:
 * a model that only knew about the declared controls would have measured a
 * row two thirds the width of the one INT-293 photographed.
 */
function rowItems(detayli: boolean): RowItem[] {
  const block = rowBlock();
  // Everything after the row's `detayli ?` gate belongs to Detaylı only, so
  // Hızlı is measured as the row the patient in the waiting room sees rather
  // than by an argument that it must be smaller.
  const gate = block.indexOf("detayli ?");
  if (gate < 0) {
    throw new Error("the mode row no longer gates anything on the mode");
  }
  const limit = detayli ? block.length : gate;
  const spans: { from: number; to: number }[] = [];
  for (let at = block.indexOf("<Pressable"); at >= 0; at = block.indexOf("<Pressable", at + 1)) {
    const end = block.indexOf("</Pressable>", at);
    if (end < 0) {
      throw new Error("a Pressable in the mode row is never closed");
    }
    spans.push({ from: at, to: end });
  }
  const items: RowItem[] = [];
  const chipLabel = new Map<number, string>();
  T_CALL.lastIndex = 0;
  let match = T_CALL.exec(block);
  while (match !== null) {
    const index = match.index;
    const span = spans.findIndex((s) => index > s.from && index < s.to);
    if (span >= 0) {
      chipLabel.set(span, match[1]);
    } else if (index < limit) {
      items.push({ key: match[1], chip: false, at: index });
    }
    match = T_CALL.exec(block);
  }
  spans.forEach((span, index) => {
    const key = chipLabel.get(index);
    if (key === undefined) {
      throw new Error("a chip in the mode row renders no catalogue key");
    }
    if (span.from < limit) {
      items.push({ key, chip: true, at: span.from });
    }
  });
  // Source order is layout order: a caption between two chips pushes the
  // second one along, and reporting the wrong one as the item that escaped
  // would point the next reader at the wrong control.
  return items.sort((a, b) => a.at - b.at);
}

/** The body of one named entry in the component's stylesheet. */
function style(name: string): string {
  const match = new RegExp(`\\n  ${name}: \\{([^}]*)\\}`).exec(MODE_BAR);
  if (match === null) {
    throw new Error(`ModeBar declares no ${name} style`);
  }
  return match[1];
}

/** The row wraps only if it says so; RN flex children do not wrap by default. */
const WRAPS = /flexWrap: "wrap"/.test(MODE_BAR);

/** The row changes form at the app's one large-text threshold, or it does not. */
const STACKS = /isLargeText\(/.test(MODE_BAR) && /flexDirection: "column"/.test(MODE_BAR);

/* ------------------------------------------------------------------ */
/* Laying the row out                                                  */
/* ------------------------------------------------------------------ */

/** The catalogues as plain lookups — a key read out of source is a string. */
const TR: Record<string, string> = tr;
const EN: Record<string, string> = en;

const CHIP_PADDING_X = spacing.sm + 2;
const ROW_GAP = spacing.xs;
const SCREEN_PADDING = spacing.screen;

interface Placed {
  readonly key: string;
  readonly line: number;
  readonly right: number;
}

function itemWidth(item: RowItem, label: string, scale: number): number {
  const natural = metrics.advance(label, scaledSize("caption", scale));
  return item.chip ? natural + 2 * CHIP_PADDING_X : natural;
}

/**
 * Where each item ends, in points from the row's left edge.
 *
 * Stacked, every item owns a line and stretches to the row: it cannot leave
 * the screen, and a label too long for one line wraps inside the chip, which
 * is what 00 §2 asks for instead of cutting a Turkish word. Inline, items run
 * end to end and a wrapping row starts a new line rather than pushing the
 * next item past the edge — which is exactly the behaviour the shipped row
 * did not have.
 */
function layout(
  items: readonly RowItem[],
  catalogue: Record<string, string>,
  scale: number,
  available: number,
): Placed[] {
  if (STACKS && isLargeText(scale)) {
    return items.map((item, line) => ({ key: item.key, line, right: available }));
  }
  let line = 0;
  let cursor = 0;
  return items.map((item) => {
    const width = itemWidth(item, catalogue[item.key], scale);
    if (WRAPS && cursor > 0 && cursor + width > available) {
      line += 1;
      cursor = 0;
    }
    const right = cursor + width;
    cursor = right + ROW_GAP;
    return { key: item.key, line, right };
  });
}

/* ------------------------------------------------------------------ */
/* 1 · The reader sees the row it is supposed to measure               */
/* ------------------------------------------------------------------ */

describe("the model describes the row the app renders", () => {
  it("finds the row, its chips and the checkpoint control", () => {
    const block = rowBlock();
    expect(block).toContain("<Pressable");
    expect(block, "a nested View would break the row's boundary").not.toContain("<View");
    const keys = rowItems(true).map((item) => item.key);
    expect(keys.length).toBeGreaterThanOrEqual(2);
    expect(keys).toContain("intake.mode.hastanedeyim");
    // The affordance this issue exists for. If it ever leaves the row, this
    // file stops being about anything.
    expect(keys).toContain("intake.queue.called");
    // Hızlı is the same row minus what the mode gates: the switch stays, the
    // checkpoint does not exist there to be reached.
    const hizli = rowItems(false).map((item) => item.key);
    expect(hizli).toEqual(["intake.mode.hastanedeyim"]);
    for (const key of keys) {
      expect(Object.keys(tr), `${key} is not a catalogue key`).toContain(key);
      expect(Object.keys(en), `${key} has no English mirror`).toContain(key);
    }
  });

  it("measures with the numbers the component and its host declare", () => {
    expect(style("modeChip")).toContain("paddingHorizontal: spacing.sm + 2");
    expect(style("modeRow")).toContain("gap: spacing.xs");
    expect(INTAKE).toContain("padding: spacing.screen");
  });

  it("agrees with the phone", () => {
    // docs/evidence/INT-295.md: the mode chip in
    // INT-293-DEFECT-siraniz-geldi-offscreen-modebar-clipped.png measures
    // 195.67 pt wide on an iPhone 16 Pro at the app's largest text step.
    const width =
      metrics.advance(tr["intake.mode.hastanedeyim"], scaledSize("caption", 2.0)) +
      2 * CHIP_PADDING_X;
    expect(Math.abs(width - 195.67)).toBeLessThan(1);
  });
});

/* ------------------------------------------------------------------ */
/* 2 · Every control lands inside the screen, at every text size       */
/* ------------------------------------------------------------------ */

describe("every mode-row control is reachable across the text-size range", () => {
  const catalogues: Record<string, Record<string, string>> = { tr: TR, en: EN };

  for (const locale of Object.keys(catalogues)) {
    for (const phone of PHONE_WIDTHS) {
      it(`${locale} on a ${phone} pt phone, in both modes`, () => {
        const available = phone - 2 * SCREEN_PADDING;
        // One line per item — the SMALLEST text size at which it leaves the
        // screen. A list of every scale that fails says the same thing many
        // times and buries which control was lost.
        const escaped = new Map<string, string>();
        for (const detayli of [false, true]) {
          const mode = detayli ? "detayli" : "hizli";
          const items = rowItems(detayli);
          for (const scale of SCALES) {
            for (const placed of layout(items, catalogues[locale], scale, available)) {
              const seen = `${mode}/${placed.key}`;
              if (placed.right > available && !escaped.has(seen)) {
                escaped.set(
                  seen,
                  `${locale}, ${mode}, ${phone} pt: ${placed.key} first leaves the ` +
                    `${available} pt row at scale ${scale}, ending at ` +
                    `${placed.right.toFixed(1)} pt — ` +
                    `${(placed.right - available).toFixed(1)} pt past the edge`,
                );
              }
            }
          }
        }
        expect(
          [...escaped.values()],
          "a row item past the right edge is drawn off the screen: the row does not " +
            "scroll, so nothing brings it back and the control is unreachable",
        ).toEqual([]);
      });
    }
  }

  it("stays one line of chrome in Turkish through the inline range", () => {
    // Reachability is carried by the wrap; this is the other half of the
    // report. Chrome that grows to three lines pushes the question itself
    // below the fold, which INT-293 filed separately about this same screen.
    // Turkish is the product's language and both widths are asserted; the
    // English mirror is longer and is allowed to wrap, which is what the wrap
    // is for.
    const items = rowItems(true);
    const spilled: string[] = [];
    for (const phone of PHONE_WIDTHS) {
      for (const scale of SCALES.filter((value) => !isLargeText(value))) {
        for (const placed of layout(items, TR, scale, phone - 2 * SCREEN_PADDING)) {
          if (placed.line > 0) {
            spilled.push(`${placed.key} on ${phone} pt at scale ${scale}`);
          }
        }
      }
    }
    expect(spilled.slice(0, 4)).toEqual([]);
  });

  it("breaks a line rather than an edge", () => {
    // The guarantee the fit above rests on. RN flex children neither wrap nor
    // shrink by default, which is exactly why the overflow left the screen
    // instead of moving down: with `flexWrap` the English labels at scale 1.5
    // on a 375 pt phone put the checkpoint chip on a second line, where it is
    // still a control.
    expect(WRAPS, "the mode row declares no flexWrap, so it cannot break a line").toBe(true);
    expect(style("modeChipInline")).toContain("flexShrink: 1");
  });

  it("changes form at the large-text threshold instead of clamping the text", () => {
    // 00 §2's rule, and the third consumer of the app's one threshold after
    // the tab rail and the segmented control. Wrapping alone would keep every
    // control on the screen at 2.0 — as a pill hugging its text on a line of
    // its own. Stacking makes that line a full-width target on purpose.
    expect(STACKS, "the mode row never changes form at large text").toBe(true);
    expect(style("modeRowStacked")).toContain('flexDirection: "column"');
  });
});

/* ------------------------------------------------------------------ */
/* 3 · Reachable vertically too, once the chips can sit above one      */
/*     another                                                          */
/* ------------------------------------------------------------------ */

describe("a mode chip is a target by box", () => {
  it("reaches the floor without slop", () => {
    // lib/a11y/target.ts refuses horizontal slop because adjacent chips sit
    // 4-8 pt apart and overlapping targets make the second one unreachable.
    // A row that wraps and stacks puts chips 4 pt apart VERTICALLY, so the
    // same argument now rules out the vertical slop this row used to carry.
    expect(style("modeChip")).toContain(`minHeight: MIN_TAP`);
    expect(MODE_BAR, "vertical slop on stacked chips overlaps").not.toContain("verticalSlop");
    expect(MIN_TAP).toBe(44);
  });
});

/* ------------------------------------------------------------------ */
/* 4 · The near-miss control: smaller type was never the fix           */
/* ------------------------------------------------------------------ */

describe("a smaller type role would not have satisfied any of this", () => {
  /**
   * The row exactly as INT-293 photographed it — switch, status caption,
   * checkpoint chip, one line, no wrap and no change of form — re-measured
   * in the SMALLEST role the type scale has (`micro`, chrome-only, 11 pt at
   * scale 1.0, two points under the caption role the row uses).
   *
   * It is the negative control the safety suites keep beside every golden:
   * if the shrunken row passed, the honest conclusion would be that the
   * arrangement was fine and the type was merely too big. It does not pass,
   * so the remedy had to be structural — which is also the only remedy 00 §2
   * allows, since the alternatives are clamping the size the patient chose
   * and cutting a Turkish word in half.
   */
  const asPhotographed: readonly RowItem[] = [
    { key: "intake.mode.hastanedeyim", chip: true, at: 0 },
    { key: "intake.mode.detayliOn", chip: false, at: 1 },
    { key: "intake.queue.called", chip: true, at: 2 },
  ];

  it("micro is genuinely the smaller role", () => {
    expect(scaledSize("micro", 1.0)).toBeLessThan(scaledSize("caption", 1.0));
    expect(scaledSize("micro", 2.0)).toBeLessThan(scaledSize("caption", 2.0));
  });

  it("still loses a control on the phone the defect was captured on", () => {
    const available = 402 - 2 * SCREEN_PADDING;
    const escaped: string[] = [];
    for (const scale of SCALES) {
      let cursor = 0;
      for (const item of asPhotographed) {
        const natural = metrics.advance(TR[item.key], scaledSize("micro", scale));
        const right = cursor + natural + (item.chip ? 2 * CHIP_PADDING_X : 0);
        if (right > available) {
          escaped.push(`${item.key} at scale ${scale}, ending at ${right.toFixed(1)} pt`);
        }
        cursor = right + ROW_GAP;
      }
    }
    expect(
      escaped.length,
      "the shrunken row fits, so the arrangement was not the defect after all — " +
        "re-read this issue before trusting anything else in this file",
    ).toBeGreaterThan(0);
    expect(escaped[0]).toContain("intake.queue.called");
  });
});
